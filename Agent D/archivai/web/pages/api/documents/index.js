// GET /api/documents?page=1&size=20&status=processed
import { q } from "../../../lib/db";
import { toProxyPath } from "../../../lib/minio";

const STATUSES = ["uploaded", "processing", "processed", "failed", "verified"];

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const page = Math.max(1, parseInt(req.query.page || "1", 10) || 1);
    const size = Math.min(100, Math.max(1, parseInt(req.query.size || "20", 10) || 20));
    const status = (req.query.status || "").trim();
    if (status && STATUSES.indexOf(status) === -1) {
      return res.status(400).json({ error: "invalid status" });
    }

    const where = status ? "WHERE d.status = $3" : "";
    const params = [size, (page - 1) * size];
    if (status) params.push(status);

    const list = await q(
      `SELECT d.id, d.filename, d.status, d.document_type, d.date_text, d.language,
              d.page_count, d.created_at, d.verified_at,
              (SELECT count(*)::int FROM entity_mentions m WHERE m.document_id = d.id) AS entity_count,
              (SELECT p.image_url FROM pages p WHERE p.document_id = d.id
                ORDER BY p.page_no LIMIT 1) AS thumb_url
       FROM documents d
       ${where}
       ORDER BY d.created_at DESC
       LIMIT $1 OFFSET $2`,
      params
    );
    const total = await q(
      `SELECT count(*)::int AS n FROM documents d ${status ? "WHERE d.status = $1" : ""}`,
      status ? [status] : []
    );

    const documents = list.rows.map(function (r) {
      const out = Object.assign({}, r, { thumb: toProxyPath(r.thumb_url) });
      delete out.thumb_url;
      return out;
    });
    res.json({ page: page, size: size, total: total.rows[0].n, documents: documents });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
