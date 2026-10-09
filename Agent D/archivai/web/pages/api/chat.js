// POST /api/chat { question, session_id? } — proxies the n8n RAG chat webhook.
// Attaches the demo user so turns are persisted per user (auth lands in Phase 6).
import { requireUser } from "../../lib/auth";

const N8N_WEBHOOK_BASE = (process.env.N8N_WEBHOOK_BASE || "http://localhost:5678/webhook").replace(/\/+$/, "");

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const question = ((req.body && req.body.question) || "").trim();
  const sessionId = (req.body && req.body.session_id) || null;
  if (!question) return res.status(400).json({ error: "question required" });
  try {
    const user = await requireUser(req, res);
    if (!user) return;
    const userId = user.id;
    const r = await fetch(N8N_WEBHOOK_BASE + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, session_id: sessionId, user_id: userId }),
      signal: AbortSignal.timeout(180000),
    });
    const text = await r.text();
    let j = null;
    try { j = JSON.parse(text); } catch (e) { /* non-JSON */ }
    if (!r.ok || !j) {
      return res.status(502).json({
        error: "chat webhook failed (is the workflow active? try `make n8n-activate`)",
        detail: (j && j.message) || text.slice(0, 200),
      });
    }
    res.json(j);
  } catch (e) {
    res.status(502).json({ error: String((e && e.message) || e) });
  }
};
