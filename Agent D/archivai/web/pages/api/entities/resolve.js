// POST /api/entities/resolve — trigger the n8n entity-resolution workflow.
const N8N_WEBHOOK_BASE = (process.env.N8N_WEBHOOK_BASE || "http://localhost:5678/webhook").replace(/\/+$/, "");

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const r = await fetch(N8N_WEBHOOK_BASE + "/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(120000),
    });
    const text = await r.text();
    let j = null;
    try { j = JSON.parse(text); } catch (e) { /* non-JSON */ }
    if (!r.ok || !j) {
      return res.status(502).json({
        error: "resolve webhook failed (is workflow 4 active? try `make n8n-activate`)",
        detail: (j && j.message) || text.slice(0, 200),
      });
    }
    res.json(j);
  } catch (e) {
    res.status(502).json({ error: String((e && e.message) || e) });
  }
};
