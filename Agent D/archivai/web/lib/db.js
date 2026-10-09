// Postgres pool (single source of truth lives in the DB; writes go through
// Postgres functions — see db/init/02_functions.sql and 04_ui_functions.sql).
const { Pool } = require("pg");

function getPool() {
  if (!global.__archivaiPool) {
    global.__archivaiPool = new Pool({
      host: process.env.POSTGRES_HOST || "localhost",
      port: parseInt(process.env.POSTGRES_PORT || "5432", 10),
      database: process.env.POSTGRES_DB || "archivai",
      user: process.env.POSTGRES_USER || "archivai",
      password: process.env.POSTGRES_PASSWORD || "change_me_pg",
      max: 10,
      idleTimeoutMillis: 30000,
    });
  }
  return global.__archivaiPool;
}

async function q(text, params) {
  return getPool().query(text, params || []);
}

// Until auth lands (Phase 6), UI writes act as the seeded demo reviewer.
async function demoUserId() {
  const r = await q("SELECT id FROM users WHERE email = 'demo@archivai.local' LIMIT 1");
  return r.rows.length ? r.rows[0].id : null;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function isUuid(v) {
  return typeof v === "string" && UUID_RE.test(v);
}

module.exports = { q, demoUserId, isUuid };
