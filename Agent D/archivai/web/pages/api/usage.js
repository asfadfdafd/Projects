// GET /api/usage — compliance/usage analytics (admin only, usage_stats() in SQL).
import { q } from "../../lib/db";
import { requireAdmin } from "../../lib/auth";

export default async function handler(req, res) {
  if (req.method !== "GET") return res.status(405).json({ error: "method not allowed" });
  try {
    const admin = await requireAdmin(req, res);
    if (!admin) return;
    const r = await q("SELECT usage_stats() AS stats");
    res.json({ stats: r.rows[0].stats });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
