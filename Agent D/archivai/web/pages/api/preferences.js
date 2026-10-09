// GET  /api/preferences — effective config (defaults ⊕ global ⊕ user).
// POST /api/preferences { reset: "search"|"dashboard"|"taxonomy"|"chat"|null }
//      — reset one key (or all) to defaults via reset_config() (the only write path
//        besides the agent's set_config; both are audit-logged Postgres functions).
import { q } from "../../lib/db";
import { requireUser } from "../../lib/auth";

export default async function handler(req, res) {
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const userId = user.id;
    if (req.method === "POST") {
      const key = (req.body && req.body.reset) || null;
      const r = await q("SELECT reset_config($1::uuid, $2) AS config", [userId, key]);
      return res.json({ config: r.rows[0].config, reset: key || "all" });
    }
    if (req.method !== "GET") {
      return res.status(405).json({ error: "method not allowed" });
    }
    const r = await q("SELECT get_all_config($1::uuid) AS config", [userId]);
    res.json({ config: r.rows[0].config });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
