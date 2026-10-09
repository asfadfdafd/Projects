// GET /api/metrics — latest storage-environment readings (latest_metrics()).
import { q } from "../../lib/db";
import { requireUser } from "../../lib/auth";

export default async function handler(req, res) {
  if (req.method !== "GET") return res.status(405).json({ error: "method not allowed" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const r = await q("SELECT latest_metrics() AS m");
    res.json({ metrics: r.rows[0].m || [] });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
