// GET /api/documents/:id — document + pages + entities grouped by type.
// Each view is audit-logged per user (compliance: "most-used documents").
import { q, isUuid } from "../../../lib/db";
import { toProxyPath } from "../../../lib/minio";
import { requireUser } from "../../../lib/auth";

const TYPES = ["person", "organization", "date", "place", "quantity"];

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const id = req.query.id;
  if (!isUuid(id)) return res.status(400).json({ error: "invalid document id" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    q("SELECT log_doc_view($1::uuid, $2::uuid)", [user.id, id]).catch(() => {});
    const docRes = await q("SELECT * FROM documents WHERE id = $1", [id]);
    if (!docRes.rows.length) return res.status(404).json({ error: "document not found" });
    const doc = docRes.rows[0];
    doc.original = toProxyPath(doc.original_url);

    const pagesRes = await q(
      "SELECT page_no, image_url, ocr_text, layout_text, confidence FROM pages WHERE document_id = $1 ORDER BY page_no",
      [id]
    );
    const pages = pagesRes.rows.map(function (p) {
      return {
        page_no: p.page_no,
        image: toProxyPath(p.image_url),
        ocr_text: p.ocr_text,
        // layout-preserving variant (PDF text layer); the viewer offers it as a toggle
        layout_text: p.layout_text,
        confidence: p.confidence,
      };
    });

    const entRes = await q(
      `SELECT e.id, e.canonical_name AS name, e.type::text AS type,
              e.role_description AS role, e.document_count,
              m.surface_form, m.confidence
       FROM entity_mentions m
       JOIN entities e ON e.id = m.entity_id
       WHERE m.document_id = $1
       ORDER BY e.canonical_name`,
      [id]
    );
    const entities = {};
    TYPES.forEach(function (t) { entities[t] = []; });
    entRes.rows.forEach(function (r) {
      if (entities[r.type]) entities[r.type].push(r);
    });

    res.json({ document: doc, pages: pages, entities: entities });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
