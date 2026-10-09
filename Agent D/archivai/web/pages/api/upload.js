// POST /api/upload (multipart) — store scans in MinIO, then trigger the n8n
// ingest webhook. Fields: files (1..n), combine ("1" = all files become one
// multi-page document; default: one document per file).
//
// PDFs are accepted too: the original file is kept, and the AI service renders it
// into page images (one per page) that are stored alongside it — so a 12-page PDF
// becomes a 12-page document, identical to uploading 12 scans.
import fs from "fs";
import path from "path";
import formidable from "formidable";
import { getClient, BUCKET, internalUrl } from "../../lib/minio";
import { expandPdf } from "../../lib/pdf";

const N8N_WEBHOOK_BASE = (process.env.N8N_WEBHOOK_BASE || "http://localhost:5678/webhook").replace(/\/+$/, "");
const IMAGE_EXT = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"];
const ALLOWED_EXT = IMAGE_EXT.concat([".pdf"]);

function asArray(v) {
  if (v === undefined || v === null) return [];
  return Array.isArray(v) ? v : [v];
}

function safeName(name) {
  return String(name || "scan")
    .replace(/[\\/]/g, "_")
    .replace(/[^\p{L}\p{N}._ ()\-№]/gu, "_")
    .slice(0, 140);
}

// pages: [{ image_url, text? }] — `text` is a PDF text layer and lets the AI
// service skip OCR for that page.
//
// Retries a restarting n8n (503/502/504 or a refused connection). Everything
// expensive — rendering and storing the pages — already happened by this point, so
// losing a 12-page PDF to a two-second blip is the one failure worth retrying.
const INGEST_RETRY_STATUS = [502, 503, 504];
const INGEST_RETRY_DELAYS_MS = [2000, 5000];

async function ingest(filename, originalUrl, pages) {
  const body = {
    filename: filename,
    original_url: originalUrl,
    pages: pages,
  };
  let last = null;
  for (let attempt = 0; attempt <= INGEST_RETRY_DELAYS_MS.length; attempt++) {
    if (attempt > 0) {
      await new Promise(function (r) { setTimeout(r, INGEST_RETRY_DELAYS_MS[attempt - 1]); });
    }
    try {
      // Ingest is async: n8n responds immediately with {doc_id, status:"processing"}
      // and the pipeline continues in the background (the UI polls for completion).
      const resp = await fetch(N8N_WEBHOOK_BASE + "/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(60000),
      });
      const text = await resp.text();
      let json = null;
      try { json = JSON.parse(text); } catch (e) { /* non-JSON reply */ }
      last = { httpStatus: resp.status, reply: json || { raw: text.slice(0, 300) } };
      if (INGEST_RETRY_STATUS.indexOf(resp.status) === -1) return last;
    } catch (e) {
      // n8n not listening yet (restart window) — same class of failure as a 503
      last = { httpStatus: 0, reply: { error: "ingest unreachable: " + String((e && e.message) || e) } };
    }
  }
  return last;
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    // PDFs of a whole file/case are routinely bigger than a single scan.
    const maxMb = parseInt(process.env.UPLOAD_MAX_FILE_MB || "200", 10);
    const form = formidable({ multiples: true, maxFileSize: maxMb * 1024 * 1024, maxFiles: 40 });
    const parsed = await form.parse(req);
    const fields = parsed[0];
    const files = asArray(parsed[1].files);
    if (!files.length) return res.status(400).json({ error: "no files uploaded" });

    const combine = asArray(fields.combine)[0] === "1";
    files.sort(function (a, b) {
      return String(a.originalFilename || "").localeCompare(String(b.originalFilename || ""));
    });

    // 1) store every file in MinIO (PDFs additionally get split into page images)
    const client = getClient();
    const stored = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const orig = safeName(f.originalFilename);
      const ext = path.extname(orig).toLowerCase();
      if (ALLOWED_EXT.indexOf(ext) === -1) {
        stored.push({ filename: orig, error: "unsupported file type (images and PDF only)" });
        continue;
      }
      const objectName = Date.now() + "-" + Math.random().toString(36).slice(2, 8) + "-" + orig;
      await client.fPutObject(BUCKET, objectName, f.filepath, {
        "Content-Type": f.mimetype || (ext === ".pdf" ? "application/pdf" : "application/octet-stream"),
      });
      try { fs.unlinkSync(f.filepath); } catch (e) { /* tmp cleanup best-effort */ }
      const url = internalUrl(objectName);

      if (ext !== ".pdf") {
        stored.push({ filename: orig, url: url, pages: [{ image_url: url }] });
        continue;
      }
      // PDF: render pages now so the document has real per-page images.
      try {
        const split = await expandPdf({ url: url, filename: orig });
        stored.push({
          filename: orig,
          url: url,                       // original_url keeps pointing at the PDF
          pages: split.pages,
          truncated: split.truncated,
          page_count: split.page_count,
          text_layer_pages: split.text_layer_pages,
        });
      } catch (e) {
        stored.push({
          filename: orig,
          error: "PDF could not be split: " + String((e && e.message) || e),
        });
      }
    }

    const good = stored.filter(function (s) { return !!s.url; });
    const results = stored.filter(function (s) { return !!s.error; })
      .map(function (s) { return { filename: s.filename, ok: false, error: s.error }; });

    // 2) trigger ingest per document
    if (good.length) {
      if (combine) {
        const name = asArray(fields.title)[0] || good[0].filename;
        // Files keep their order; a PDF contributes all of its pages here.
        const allPages = good.reduce(function (acc, s) { return acc.concat(s.pages); }, []);
        const r = await ingest(name, good[0].url, allPages);
        results.push({
          filename: name,
          pages: allPages.length,
          truncated: good.some(function (s) { return !!s.truncated; }),
          page_count: good.reduce(function (n, s) { return n + (s.page_count || s.pages.length); }, 0),
          text_layer_pages: good.reduce(function (n, s) { return n + (s.text_layer_pages || 0); }, 0),
          ok: (r.httpStatus === 200 || r.httpStatus === 202) && r.reply && (r.reply.status === "processing" || r.reply.status === "processed"),
          doc_id: r.reply ? r.reply.doc_id : null,
          status: r.reply ? r.reply.status : null,
          error: (r.httpStatus === 200 || r.httpStatus === 202) ? null : (r.reply && r.reply.error) || ("ingest HTTP " + r.httpStatus),
        });
      } else {
        for (let i = 0; i < good.length; i++) {
          const s = good[i];
          const r = await ingest(s.filename, s.url, s.pages);
          results.push({
            filename: s.filename,
            pages: s.pages.length,
            truncated: !!s.truncated,
            page_count: s.page_count || s.pages.length,
            text_layer_pages: s.text_layer_pages || 0,
            ok: (r.httpStatus === 200 || r.httpStatus === 202) && r.reply && (r.reply.status === "processing" || r.reply.status === "processed"),
            doc_id: r.reply ? r.reply.doc_id : null,
            status: r.reply ? r.reply.status : null,
            error: (r.httpStatus === 200 || r.httpStatus === 202) ? null : (r.reply && r.reply.error) || ("ingest HTTP " + r.httpStatus),
          });
        }
      }
    }

    res.json({ results: results });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};

export const config = {
  api: { bodyParser: false },
};
