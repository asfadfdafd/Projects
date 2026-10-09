// GET  /api/dashboard — cached stats (computes them if missing).
// POST /api/dashboard — force recompute (single source of truth: compute_dashboard_stats()).
import { q } from "../../lib/db";

export default async function handler(req, res) {
  try {
    if (req.method === "POST") {
      await q("SELECT compute_dashboard_stats()");
    } else if (req.method !== "GET") {
      return res.status(405).json({ error: "method not allowed" });
    }
    let r = await q("SELECT data, computed_at FROM dashboard_stats WHERE id = 1");
    if (!r.rows.length) {
      await q("SELECT compute_dashboard_stats()");
      r = await q("SELECT data, computed_at FROM dashboard_stats WHERE id = 1");
    }
    if (!r.rows.length) return res.json({ stats: null, computed_at: null });
    res.json({ stats: r.rows[0].data, computed_at: r.rows[0].computed_at });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
