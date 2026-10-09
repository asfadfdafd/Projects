// GET /api/entities/graph?limit=60 — nodes + co-occurrence edges for the
// knowledge graph (people ↔ organizations ↔ places across shared documents).
import { q } from "../../../lib/db";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  try {
    const limit = Math.min(150, Math.max(5, parseInt(req.query.limit || "60", 10) || 60));
    const nodesRes = await q(
      `SELECT e.id, e.canonical_name AS name, e.type::text AS type, e.document_count
       FROM entities e
       WHERE e.type IN ('person', 'organization', 'place')
       ORDER BY e.document_count DESC, e.canonical_name
       LIMIT $1`,
      [limit]
    );
    const ids = nodesRes.rows.map(function (n) { return n.id; });
    let edges = [];
    if (ids.length) {
      const edgesRes = await q(
        `SELECT entity_a AS a, entity_b AS b, weight
         FROM entity_edges
         WHERE entity_a = ANY($1::uuid[]) AND entity_b = ANY($1::uuid[])
         ORDER BY weight DESC
         LIMIT 400`,
        [ids]
      );
      edges = edgesRes.rows;
    }
    res.json({ nodes: nodesRes.rows, edges: edges });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
