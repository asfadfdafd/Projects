# Web app (Next.js + Tailwind)

Thin front end over the DB functions + n8n webhooks. Pages Router, plain JS.

## Screens

| Route | Screen | Status |
|---|---|---|
| `/upload` | Drag-drop multi-file upload → MinIO → n8n ingest (optional "combine into one multi-page document") | ✅ Phase 2 |
| `/documents` | Document Archive — thumbnails, type, date, language, entity count, status filter, pagination, auto-poll while processing | ✅ Phase 2 |
| `/documents/[id]` | Document Detail — scan viewer (zoom + page nav), chips, sender/recipient, AI summary, per-page + all-pages text, **inline entity editing** (add / fix spelling / remove, audit-logged), **Mark as Verified** | ✅ Phase 2 |
| `/search` | Hybrid semantic + keyword search with result cards → Document Detail | ✅ Phase 3 |
| `/dashboard` | KPIs, entity donut, top-5 lists, language split, recent activity, timeline — all from `dashboard_stats` | ✅ Phase 3 |
| `/chat` | "Ask ArchivAI" RAG chat; **citations open the source document**; session-persistent | ✅ Phase 3b |
| `/entities` | Tabs + filter + table with aliases, expandable rows → documents, **CSV export**, **knowledge graph** (SVG force layout, zero deps), Run-resolution button | ✅ Phase 4 |

## API routes (server-side)

- `GET  /api/documents` — list (page, size, status filter)
- `GET  /api/documents/:id` — document + pages + entities grouped by type
- `POST /api/documents/:id/verify` — `mark_verified()`
- `POST/PATCH/DELETE /api/documents/:id/entities` — `add_entity_to_document()` /
  `rename_entity_in_document()` / `remove_entity_from_document()` (db/init/04_ui_functions.sql)
- `POST /api/upload` — multipart → MinIO → `POST {n8n}/webhook/ingest` per document
- `GET  /api/scan/<bucket>/<key>` — streams scans from MinIO (MinIO stays private)

Reads go straight to Postgres; **all writes go through Postgres functions** — same
pattern as the n8n pipeline.

## Run — in Docker (recommended)

```bash
docker compose --profile full up -d --build web   # or: make full
# open http://localhost:3000
```

The container gets its config from `.env` (compose `env_file`): `POSTGRES_*`,
`MINIO_*`, `N8N_WEBHOOK_BASE`.

## Run — dev mode on the host

```bash
cd web && npm install
# create web/.env.local with host-facing endpoints:
#   POSTGRES_HOST=localhost
#   MINIO_ENDPOINT=http://localhost:9000
#   MINIO_INTERNAL_ENDPOINT=http://minio:9000
#   N8N_WEBHOOK_BASE=http://localhost:5678/webhook
#   POSTGRES_PASSWORD=…  MINIO_ROOT_PASSWORD=…   (from ../.env)
npm run dev   # http://localhost:3000
```

`MINIO_INTERNAL_ENDPOINT` is what gets written into stored scan URLs so the
**ai-service container** can fetch them; the browser never needs MinIO — scans are
streamed through `/api/scan/...`.

## Auth

Not yet (Phase 6): UI writes act as the seeded `demo@archivai.local` reviewer and
are audit-logged with that identity.
