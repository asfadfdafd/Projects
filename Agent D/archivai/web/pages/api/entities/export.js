// GET /api/entities/export — CSV of all entities (Agent D parity feature).
import { q } from "../../../lib/db";

function csvCell(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const r = await q(
      `SELECT e.canonical_name, e.type::text AS type, e.role_description,
              e.document_count, array_to_string(e.aliases, ' | ') AS aliases
       FROM entities e
       ORDER BY e.type, e.document_count DESC, e.canonical_name`
    );
    const header = "name,type,role_description,documents,aliases";
    const lines = r.rows.map(function (row) {
      return [
        csvCell(row.canonical_name),
        csvCell(row.type),
        csvCell(row.role_description),
        csvCell(row.document_count),
        csvCell(row.aliases),
      ].join(",");
    });
    const csv = "\uFEFF" + header + "\n" + lines.join("\n") + "\n"; // BOM for Cyrillic in Excel
    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader("Content-Disposition", 'attachment; filename="archivai-entities.csv"');
    res.send(csv);
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
