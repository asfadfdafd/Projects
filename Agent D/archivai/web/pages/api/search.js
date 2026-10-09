// POST /api/search { query } — proxies the n8n hybrid search webhook.
// GET  /api/search — recent searches for the session user (personalization v1).
// Session user + client IP ride along: per-user tuned search + compliance history.
import { q } from "../../lib/db";
import { requireUser, clientIp } from "../../lib/auth";

const N8N_WEBHOOK_BASE = (process.env.N8N_WEBHOOK_BASE || "http://localhost:5678/webhook").replace(/\/+$/, "");

export default async function handler(req, res) {
  if (req.method === "GET") {
    try {
      const user = await requireUser(req, res);
      if (!user) return;
      const r = await q("SELECT * FROM recent_searches($1::uuid, 8)", [user.id]);
      return res.json({ recent: r.rows });
    } catch (e) {
      return res.status(500).json({ error: String((e && e.message) || e) });
    }
  }
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const query = ((req.body && req.body.query) || "").trim();
  if (!query) return res.status(400).json({ error: "query required" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const r = await fetch(N8N_WEBHOOK_BASE + "/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, user_id: user.id, ip: clientIp(req) }),
      signal: AbortSignal.timeout(90000),
    });
    const text = await r.text();
    let j = null;
    try { j = JSON.parse(text); } catch (e) { /* non-JSON */ }
    if (!r.ok || !j) {
      return res.status(502).json({
        error: "search webhook failed (is the workflow active? try `make n8n-activate`)",
        detail: (j && j.message) || text.slice(0, 200),
      });
    }
    res.json(j);
  } catch (e) {
    res.status(502).json({ error: String((e && e.message) || e) });
  }
};
