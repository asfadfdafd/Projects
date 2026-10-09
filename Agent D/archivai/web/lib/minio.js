// MinIO access + URL helpers.
//
// Two endpoints matter:
//  - MINIO_ENDPOINT           where THIS process connects (in compose: http://minio:9000;
//                             for `npm run dev` on the host: http://localhost:9000)
//  - MINIO_INTERNAL_ENDPOINT  the base written into stored URLs so that OTHER
//                             containers (ai-service) can fetch scans. Defaults to
//                             MINIO_ENDPOINT; only needs setting in host-dev mode.
//
// Browsers never talk to MinIO directly — scans are streamed through
// /api/scan/[...path], so nothing depends on MinIO being publicly exposed.
const Minio = require("minio");

const BUCKET = process.env.MINIO_BUCKET || "scans";
const ENDPOINT = process.env.MINIO_ENDPOINT || "http://localhost:9000";
const INTERNAL_BASE = (process.env.MINIO_INTERNAL_ENDPOINT || ENDPOINT).replace(/\/+$/, "");

function getClient() {
  if (!global.__archivaiMinio) {
    const u = new URL(ENDPOINT);
    global.__archivaiMinio = new Minio.Client({
      endPoint: u.hostname,
      port: parseInt(u.port || (u.protocol === "https:" ? "443" : "80"), 10),
      useSSL: u.protocol === "https:",
      accessKey: process.env.MINIO_ROOT_USER || "archivai",
      secretKey: process.env.MINIO_ROOT_PASSWORD || "change_me_minio",
    });
  }
  return global.__archivaiMinio;
}

// Stored object URL (reachable from inside the compose network).
function internalUrl(objectName) {
  return `${INTERNAL_BASE}/${BUCKET}/${objectName}`;
}

// Map a stored URL to the browser-facing streaming proxy path.
function toProxyPath(url) {
  if (!url) return null;
  try {
    const u = new URL(url);
    return "/api/scan" + u.pathname;
  } catch (e) {
    return null;
  }
}

module.exports = { getClient, BUCKET, internalUrl, toProxyPath };
