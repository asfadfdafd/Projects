// POST /api/pdf/expand — turn PDF entries in an ingest `pages` array into page
// images stored in object storage.
//
//   in:  { filename?, original_url?, pages: [{ image_url }] }
//   out: { filename, original_url, pages: [{ image_url, text? }], expanded }
//
// Internal endpoint for the connector workflow (n8n w6), which discovers files in
// the client's bucket as bare URLs and cannot rasterize them itself. The web app
// owns object-storage writes, so the split happens here — same code path as an
// interactive upload. Non-PDF entries pass through unchanged, so it is safe to
// call for every file.
//
// Unauthenticated like /api/upload: reachable only inside the compose network.
import { expandPageList } from "../../../lib/pdf";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const body = req.body || {};
    const pages = Array.isArray(body.pages) ? body.pages : [];
    if (!pages.length) return res.status(400).json({ error: "no pages provided" });

    const out = await expandPageList(pages, body.filename);
    res.json({
      filename: body.filename || null,
      original_url: body.original_url || null,
      pages: out.pages,
      expanded: out.expanded,        // how many inputs were PDFs
    });
  } catch (e) {
    res.status(502).json({ error: String((e && e.message) || e) });
  }
};

export const config = {
  // Page images go straight to object storage; only the small JSON body is parsed.
  api: { bodyParser: { sizeLimit: "2mb" } },
};
