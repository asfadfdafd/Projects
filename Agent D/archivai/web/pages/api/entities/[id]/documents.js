// GET /api/entities/:id/documents — the documents an entity appears in
// (powers the expandable rows + entity→document navigation).
import { q, isUuid } from "../../../../lib/db";
import { toProxyPath } from "../../../../lib/minio";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const id = req.query.id;
  if (!isUuid(id)) return res.status(400).json({ error: "invalid entity id" });
  try {
    const r = await q(
      `SELECT d.id, d.filename, d.document_type, d.date_text, d.status,
              left(COALESCE(d.ai_summary, d.full_text, ''), 200) AS snippet,
              m.surface_form,
              (SELECT p.image_url FROM pages p WHERE p.document_id = d.id
                ORDER BY p.page_no LIMIT 1) AS thumb_url
       FROM entity_mentions m
       JOIN documents d ON d.id = m.document_id
       WHERE m.entity_id = $1
       ORDER BY d.created_at DESC`,
      [id]
    );
    const documents = r.rows.map(function (row) {
      const out = Object.assign({}, row, { thumb: toProxyPath(row.thumb_url) });
      delete out.thumb_url;
      return out;
    });
    res.json({ documents: documents });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
