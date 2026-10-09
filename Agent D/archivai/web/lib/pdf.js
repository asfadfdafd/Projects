// PDF ingest helper.
//
// A PDF is split into page images BEFORE ingest, so everything downstream — the
// n8n pipeline, the pages table, the scan viewer, reprocessing — keeps working on
// "one image per page" and never has to special-case PDFs.
//
//   PDF in object storage
//     -> ai-service /pdf/split   (poppler: render pages + read the text layer)
//     -> each page image stored back in the scans bucket
//     -> [{ image_url, text? }] handed to the ingest webhook
//
// Digital PDFs also carry a text layer; it travels with the page so the AI
// service can skip OCR for that page (exact text, no model call).
const { getClient, BUCKET, internalUrl } = require("./minio");

const AI_SERVICE_URL = (process.env.AI_SERVICE_URL || "http://ai-service:8000").replace(/\/+$/, "");
// Rendering ~100 pages at 200 dpi is minutes on a small box, not seconds.
const SPLIT_TIMEOUT_MS = parseInt(process.env.PDF_SPLIT_TIMEOUT_MS || "600000", 10);

function isPdfName(name) {
  return /\.pdf$/i.test(String(name || "").split("?")[0].trim());
}

function isPdfUrl(url) {
  return isPdfName(String(url || "").split("?")[0]);
}

// Strip the extension so page objects read "<doc>-p001.jpg".
function baseName(name) {
  return String(name || "document").replace(/\.[^.\\/]+$/, "");
}

// Ask the AI service to rasterize the PDF. Accepts a URL (preferred: the service
// pulls it straight from MinIO) or the raw bytes.
async function splitPdf({ url, buffer }) {
  const body = url ? { pdf_url: url } : { pdf_b64: Buffer.from(buffer).toString("base64") };
  const r = await fetch(AI_SERVICE_URL + "/pdf/split", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(SPLIT_TIMEOUT_MS),
  });
  const text = await r.text();
  let j = null;
  try { j = JSON.parse(text); } catch (e) { /* non-JSON reply */ }
  if (!r.ok) {
    const detail = (j && (j.detail || j.error)) || text.slice(0, 200);
    throw new Error("pdf split failed (HTTP " + r.status + "): " + detail);
  }
  if (!j || !Array.isArray(j.pages) || !j.pages.length) {
    throw new Error("pdf split returned no pages");
  }
  return j;
}

// Store one rendered page and return its stored URL.
async function storePage(client, objectPrefix, page) {
  const n = String(page.page_no).padStart(3, "0");
  const objectName = `${objectPrefix}-p${n}.jpg`;
  const buf = Buffer.from(page.image_b64, "base64");
  await client.putObject(BUCKET, objectName, buf, buf.length, { "Content-Type": "image/jpeg" });
  return internalUrl(objectName);
}

/**
 * Split a PDF into stored page images.
 * @returns {Promise<{pages: Array<{image_url: string, text?: string}>, page_count: number,
 *                    rendered: number, truncated: boolean, text_layer_pages: number}>}
 */
async function expandPdf({ url, buffer, filename }) {
  const split = await splitPdf({ url, buffer });
  const client = getClient();
  const prefix =
    Date.now() + "-" + Math.random().toString(36).slice(2, 8) + "-" + baseName(filename);

  const pages = [];
  for (const p of split.pages) {
    const image_url = await storePage(client, prefix, p);
    const page = { image_url };
    if (p.text && String(p.text).trim()) page.text = p.text;
    // layout variant travels with the page and is stored for display only
    if (p.layout_text && String(p.layout_text).trim()) page.layout_text = p.layout_text;
    pages.push(page);
  }
  return {
    pages,
    page_count: split.page_count || pages.length,
    rendered: split.rendered || pages.length,
    truncated: !!split.truncated,
    text_layer_pages: split.text_layer_pages || 0,
  };
}

/**
 * Expand any PDF entries in an ingest `pages` array; other entries pass through.
 * Used by the connector path, where files arrive as bare URLs in a bucket.
 */
async function expandPageList(pages, filename) {
  const out = [];
  let expanded = 0;
  for (const p of pages || []) {
    const url = p && p.image_url;
    if (!isPdfUrl(url)) {
      out.push(p);
      continue;
    }
    const r = await expandPdf({ url, filename: filename || url.split("/").pop() });
    out.push(...r.pages);
    expanded += 1;
  }
  return { pages: out, expanded };
}

module.exports = { isPdfName, isPdfUrl, expandPdf, expandPageList };
