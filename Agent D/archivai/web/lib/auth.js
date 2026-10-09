// Phase 6 session helpers. All auth logic lives in Postgres (08_auth.sql);
// this module only carries the cookie. AUTH_OPTIONAL=1 (dev/smoke convenience)
// auto-authenticates as the seeded demo admin — set 0 for real deployments.
const { q } = require("./db");

const COOKIE = "archivai_session";

function parseCookies(header) {
  const out = {};
  (header || "").split(";").forEach((part) => {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  });
  return out;
}

function sessionCookie(token, maxAgeSec) {
  return (
    COOKIE + "=" + (token || "") +
    "; Path=/; HttpOnly; SameSite=Lax; Max-Age=" + (token ? maxAgeSec : 0)
  );
}

function clientIp(req) {
  const fwd = (req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return fwd || (req.socket && req.socket.remoteAddress) || null;
}

async function sessionUser(req) {
  if (process.env.AUTH_OPTIONAL === "1") {
    const r = await q(
      "SELECT id, email, display_name, role FROM users WHERE email = 'demo@archivai.local'"
    );
    return r.rows[0] || null;
  }
  const token = parseCookies(req.headers.cookie)[COOKIE];
  if (!token) return null;
  const r = await q("SELECT * FROM auth_user($1)", [token]);
  return r.rows[0] || null;
}

// Returns the user or null; on null a 401 has already been sent.
async function requireUser(req, res) {
  const u = await sessionUser(req);
  if (!u) {
    res.status(401).json({ error: "unauthorized" });
    return null;
  }
  return u;
}

async function requireAdmin(req, res) {
  const u = await requireUser(req, res);
  if (!u) return null;
  if (u.role !== "admin") {
    res.status(403).json({ error: "admin only" });
    return null;
  }
  return u;
}

module.exports = { COOKIE, parseCookies, sessionCookie, clientIp, sessionUser, requireUser, requireAdmin };
