// GET /api/scan/<bucket>/<object...> — stream a scan from MinIO to the browser.
// Keeps MinIO private: the UI never needs a public object-storage endpoint.
import { getClient, BUCKET } from "../../../lib/minio";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }
  const parts = req.query.path;
  if (!Array.isArray(parts) || parts.length < 2) {
    return res.status(400).json({ error: "bad object path" });
  }
  const bucket = parts[0];
  const key = parts.slice(1).join("/");
  // scans = uploads; connector bucket = bulk-pulled files (Phase 7)
  const ALLOWED = new Set([BUCKET, process.env.CONNECTOR_BUCKET || "import"]);
  if (!ALLOWED.has(bucket)) {
    return res.status(403).json({ error: "bucket not allowed" });
  }
  try {
    const client = getClient();
    const stat = await client.statObject(bucket, key);
    const ctype =
      (stat.metaData && (stat.metaData["content-type"] || stat.metaData["Content-Type"])) ||
      "application/octet-stream";
    res.setHeader("Content-Type", ctype);
    res.setHeader("Content-Length", String(stat.size));
    res.setHeader("Cache-Control", "private, max-age=3600");
    const stream = await client.getObject(bucket, key);
    stream.on("error", function () {
      if (!res.headersSent) res.status(500);
      res.end();
    });
    stream.pipe(res);
  } catch (e) {
    res.status(404).json({ error: "object not found" });
  }
};
