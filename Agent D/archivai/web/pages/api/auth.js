// GET  /api/auth                       → { user } (null = show /login)
// POST /api/auth {action:"login", email, password} → sets the session cookie
// POST /api/auth {action:"logout"}                 → kills it
// POST /api/auth {action:"password", old, new}     → change_password()
import { q } from "../../lib/db";
import { COOKIE, parseCookies, sessionCookie, clientIp, sessionUser } from "../../lib/auth";

const WEEK = 7 * 24 * 3600;

export default async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const user = await sessionUser(req);
      return res.json({ user: user || null, optional: process.env.AUTH_OPTIONAL === "1" });
    }
    if (req.method !== "POST") return res.status(405).json({ error: "method not allowed" });
    const body = req.body || {};

    if (body.action === "login") {
      const r = await q("SELECT login($1, $2, $3, $4) AS token", [
        body.email || "", body.password || "", clientIp(req),
        req.headers["user-agent"] || "",
      ]);
      const token = r.rows[0].token;
      if (!token) return res.status(401).json({ error: "неверный email или пароль" });
      res.setHeader("Set-Cookie", sessionCookie(token, WEEK));
      const u = await q("SELECT * FROM auth_user($1)", [token]);
      return res.json({ user: u.rows[0] || null });
    }

    if (body.action === "logout") {
      const token = parseCookies(req.headers.cookie)[COOKIE];
      if (token) await q("SELECT logout($1)", [token]);
      res.setHeader("Set-Cookie", sessionCookie(null, 0));
      return res.json({ ok: true });
    }

    if (body.action === "password") {
      const user = await sessionUser(req);
      if (!user) return res.status(401).json({ error: "unauthorized" });
      await q("SELECT change_password($1::uuid, $2, $3)", [user.id, body.old || "", body.new || ""]);
      return res.json({ ok: true });
    }

    res.status(400).json({ error: "unknown action" });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
