# Phase 7 — Connectors & Integration · Design Proposal

Status: **PROPOSAL — awaiting sign-off.**

Competitor promises to match (transcript §6.3): bulk ingestion — connect to client
file storage and **pull 50–100+ docs at once** (manual upload stays); **bidirectional
webhooks** to legacy systems (client stack: old Java + PostgreSQL 6/7); minimal
footprint — the system needs only the client's **file storage + database**.

## 1. Pull connector — bulk ingest from object storage

**Source v1: S3-compatible storage** (client S3 / MinIO; a local "watch folder" is
just a bucket mount — `mc mirror` one-liner documented). SMB/FTP = later adapters.

- New n8n workflow **6 · Connector: Pull** with two triggers:
  **Schedule (every 5 min)** + **`POST /webhook/connector-pull`** ("Pull now" for
  demos and the Upload page button).
- Flow: S3 node lists `${CONNECTOR_BUCKET}` (default `import`, created by
  minio-init) → **`connector_filter_new(files jsonb)`** in PG returns only objects
  not yet ingested (dedup by `documents.original_url`, cap 100/run) → fan-out
  self-call to `/webhook/ingest` per file (async 202 each — the existing pipeline
  and its failure branch do the rest) → respond `{found, new, dispatched}`.
- Re-running is idempotent: second pull → `dispatched: 0`.
- **PDFs in the source bucket** are expanded before ingest: the fan-out posts each
  file to the web app's `POST /api/pdf/expand`, which renders the PDF (AI
  `/pdf/split`) and stores one page image per page — a pulled 30-page PDF lands as a
  30-page document. Non-PDF files pass through untouched. If the web app is not
  running (it sits behind the compose `full` profile), the workflow falls back to the
  original URL and the AI service splits the PDF itself during `/process`.
- Headless S3 credential ("ArchivAI MinIO") imported by the smoke script like the
  Postgres one.

## 2. Push connector — outbox → client webhook (bidirectional layer)

Robust **outbox pattern** (retry-safe, auditable — not fire-and-forget):

```sql
connector_outbox (id, document_id, payload jsonb, status pending|sending|sent|failed,
                  attempts, last_error, created_at, sent_at)
```
- Trigger on `documents` (status → `processed`) enqueues
  **`document_payload(doc_id)`** — full structured JSON: metadata, sender/recipient,
  summary, full text, entities with roles, page refs. The client's legacy Java/PG
  side just consumes JSON POSTs.
- New n8n workflow **7 · Connector: Push**: Schedule (1 min) + `POST /webhook/push-now`
  (manual flush) → `outbox_take(10)` → HTTP POST each to `$env.CLIENT_WEBHOOK_URL` →
  `outbox_mark(id, ok, detail)`; on failure attempts<5 → back to pending, else
  `failed` with `last_error`.
- **8 · Client Sink (demo)** — a stub "legacy system": webhook `/webhook/client-sink`
  → `log_client_push(payload)` (audit row). Default `CLIENT_WEBHOOK_URL` points at it
  so the bidirectional loop E2Es out of the box; real deployments point the env at
  the client endpoint and delete the sink.

## 3. Config & env

`.env`: `CONNECTOR_BUCKET=import` · `CLIENT_WEBHOOK_URL=http://127.0.0.1:5678/webhook/client-sink`
(empty = push disabled). compose: minio-init also creates the `import` bucket; n8n
gets both vars. Agent-tunable connector settings (schedule, prefix) — later, via the
existing `agent_capabilities()` mechanism.

## 4. Verification

- Simulator: allow Schedule-trigger workflows (reachability from all triggers;
  responder required only when a webhook exists); PG-contract checks cover the new
  single-call functions.
- Smoke: drop a file into `import` via `mc` → `/webhook/connector-pull` →
  `{dispatched ≥ 1}` → document processed; second pull → `dispatched: 0` (dedup);
  `/webhook/push-now` → outbox drained → `client_push_received` audit row with the
  full payload; failure path: bad `CLIENT_WEBHOOK_URL` → attempts grow, row stays
  pending.

## 5. Decision points

1. **Pull source v1**: S3/MinIO (recommended — client S3 speaks the same protocol,
   folders mount into it) · or SMB/FTP adapter first.
2. **Push payload**: full structured document JSON via outbox with retries
   (recommended — the "replaces the legacy app" pitch) · or minimal notification
   (id, type, link) with pull-on-demand.
3. **Pull cadence**: schedule every 5 min + "Pull now" webhook/button (recommended)
   · or manual-only.
