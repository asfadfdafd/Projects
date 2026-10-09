// POST /api/documents/:id/verify — human-in-the-loop verification.
import { q, isUuid } from "../../../../lib/db";
import { requireUser } from "../../../../lib/auth";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const id = req.query.id;
  if (!isUuid(id)) return res.status(400).json({ error: "invalid document id" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const actor = user.id;
    await q("SELECT mark_verified($1::uuid, $2::uuid)", [id, actor]);
    const r = await q(
      "SELECT status, verified_by, verified_at FROM documents WHERE id = $1",
      [id]
    );
    if (!r.rows.length) return res.status(404).json({ error: "document not found" });
    res.json({ ok: true, document: r.rows[0] });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
