// GET  /api/widgets — agent-built custom widgets with computed data
//      (widget_data(): specs validated by set_config, SQL owned by Postgres).
// POST /api/widgets { remove: "<widget_id>" } — remove one widget via the same
//      single write path (set_config with the full array minus the widget).
import { q } from "../../lib/db";
import { requireUser } from "../../lib/auth";

export default async function handler(req, res) {
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const userId = user.id;
    if (req.method === "POST") {
      const removeId = (req.body && req.body.remove) || null;
      if (!removeId) return res.status(400).json({ error: "remove (widget id) required" });
      const cur = await q("SELECT get_config($1::uuid,'custom_widgets') AS cfg", [userId]);
      const widgets = ((cur.rows[0].cfg || {}).widgets || []).filter((w) => w.id !== removeId);
      await q("SELECT set_config($1::uuid, 'custom_widgets', $2::jsonb, 'user')",
              [userId, JSON.stringify({ widgets })]);
    } else if (req.method !== "GET") {
      return res.status(405).json({ error: "method not allowed" });
    }
    const r = await q("SELECT widget_data($1::uuid) AS widgets", [userId]);
    res.json({ widgets: r.rows[0].widgets || [] });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
