// POST /api/connector — "Pull now": trigger the bulk-ingest connector (w6).
import { requireUser } from "../../lib/auth";

const N8N_WEBHOOK_BASE = (process.env.N8N_WEBHOOK_BASE || "http://localhost:5678/webhook").replace(/\/+$/, "");

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "method not allowed" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const r = await fetch(N8N_WEBHOOK_BASE + "/connector-pull", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(90000),
    });
    const text = await r.text();
    let j = null;
    try { j = JSON.parse(text); } catch (e) { /* non-JSON */ }
    if (!r.ok || !j) {
      return res.status(502).json({
        error: "connector webhook failed (is workflow 6 active? try `make n8n-activate`)",
        detail: (j && j.message) || text.slice(0, 200),
      });
    }
    res.json(j);
  } catch (e) {
    res.status(502).json({ error: String((e && e.message) || e) });
  }
};
