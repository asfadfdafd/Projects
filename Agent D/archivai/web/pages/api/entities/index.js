// GET /api/entities?type=person&filter=аба&page=1&size=50 — entity table data.
import { q } from "../../../lib/db";

const TYPES = ["person", "organization", "date", "place", "quantity"];

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const type = (req.query.type || "").trim();
    if (type && TYPES.indexOf(type) === -1) {
      return res.status(400).json({ error: "invalid type" });
    }
    const filter = (req.query.filter || "").trim();
    const page = Math.max(1, parseInt(req.query.page || "1", 10) || 1);
    const size = Math.min(200, Math.max(1, parseInt(req.query.size || "50", 10) || 50));

    const conds = [];
    const params = [];
    if (type) { params.push(type); conds.push("e.type = $" + params.length); }
    if (filter) {
      params.push("%" + filter + "%");
      conds.push("(e.canonical_name ILIKE $" + params.length +
        " OR array_to_string(e.aliases, ' ') ILIKE $" + params.length + ")");
    }
    const where = conds.length ? "WHERE " + conds.join(" AND ") : "";

    const countRes = await q("SELECT count(*)::int AS n FROM entities e " + where, params);

    params.push(size);
    params.push((page - 1) * size);
    const rows = await q(
      `SELECT e.id, e.canonical_name AS name, e.type::text AS type,
              e.role_description AS role, e.aliases, e.document_count
       FROM entities e
       ${where}
       ORDER BY e.document_count DESC, e.canonical_name
       LIMIT $${params.length - 1} OFFSET $${params.length}`,
      params
    );

    const tabRes = await q(
      "SELECT type::text AS type, count(*)::int AS n FROM entities GROUP BY type"
    );
    const tabs = { all: 0 };
    tabRes.rows.forEach(function (r) {
      tabs[r.type] = r.n;
      tabs.all += r.n;
    });

    res.json({ page: page, size: size, total: countRes.rows[0].n, tabs: tabs, entities: rows.rows });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
