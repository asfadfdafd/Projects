// Inline entity editing for one document (human-in-the-loop corrections).
//   POST   { name, type, role? }        → add_entity_to_document()
//   PATCH  { entity_id, new_name }      → rename_entity_in_document()
//   DELETE { entity_id }                → remove_entity_from_document()
import { q, isUuid } from "../../../../lib/db";
import { requireUser } from "../../../../lib/auth";

const TYPES = ["person", "organization", "date", "place", "quantity"];

export default async function handler(req, res) {
  const id = req.query.id;
  if (!isUuid(id)) return res.status(400).json({ error: "invalid document id" });
  const body = req.body || {};

  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const actor = user.id;

    if (req.method === "POST") {
      const name = (body.name || "").trim();
      const type = (body.type || "").trim();
      const role = (body.role || "").trim() || null;
      if (!name) return res.status(400).json({ error: "name required" });
      if (TYPES.indexOf(type) === -1) return res.status(400).json({ error: "invalid type" });
      const r = await q(
        "SELECT add_entity_to_document($1::uuid, $2, $3::entity_type, $4, $5::uuid) AS entity_id",
        [id, name, type, role, actor]
      );
      return res.json({ ok: true, entity_id: r.rows[0].entity_id });
    }

    if (req.method === "PATCH") {
      const entityId = body.entity_id;
      const newName = (body.new_name || "").trim();
      if (!isUuid(entityId)) return res.status(400).json({ error: "invalid entity_id" });
      if (!newName) return res.status(400).json({ error: "new_name required" });
      const r = await q(
        "SELECT rename_entity_in_document($1::uuid, $2::uuid, $3, $4::uuid) AS entity_id",
        [id, entityId, newName, actor]
      );
      return res.json({ ok: true, entity_id: r.rows[0].entity_id });
    }

    if (req.method === "DELETE") {
      const entityId = body.entity_id;
      if (!isUuid(entityId)) return res.status(400).json({ error: "invalid entity_id" });
      await q(
        "SELECT remove_entity_from_document($1::uuid, $2::uuid, $3::uuid)",
        [id, entityId, actor]
      );
      return res.json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
