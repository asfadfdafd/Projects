# n8n workflows

The pipeline lives here as importable workflows. Database work is done by Postgres
functions (`db/init/02_functions.sql`, `03_chat.sql`), so the workflows stay thin.

## Workflows

- **1 · Ingest & Process** (`POST /webhook/ingest`) — the core pipeline, **async**:
  create document → **respond immediately** `202 {doc_id, status:"processing"}` →
  AI `/process` (OCR + extraction) → `ingest_extraction` (fields, per-page OCR,
  entities, mentions, edges) → AI `/embed` → `upsert_embedding` → recompute stats.
  Poll `documents.status` (the UI does this automatically) for
  `processed`/`failed`; on AI failure the reason lands in `documents.process_error`.
  Async means slow CPU-only hosts can take many minutes per document without any
  HTTP timeout in the chain.
- **2 · Search** (`POST /webhook/search`) — embed the query → `search_documents`
  (hybrid vector + keyword) → respond `{query, count, results:[...]}` (empty archive
  returns `{count: 0, results: []}`, it never hangs).
- **3 · Ask ArchivAI** (`POST /webhook/chat`) — RAG chat: embed → `rag_retrieve` →
  AI `/answer` (grounded, cited) → `log_chat_turn` → reply with
  `{session_id, answer, citations, grounded}`. See `../docs/CHAT_ASSISTANT.md`.
- **4 · Entity Resolution** (`POST /webhook/resolve`) — merges duplicate entities
  (`resolve_entities()`: normalized-name duplicates + unambiguous token-containment
  for people/orgs, e.g. «Абай» → «Абай Кунанбаев»), folds old names into `aliases[]`,
  rebuilds edges, recomputes stats → responds `{merged, details}`. Also triggered
  from the Entities page. Extension hook: embedding-similarity merging.
- **5 · Configuration Agent** ⭐ (`POST /webhook/agent`) — the Phase 5/5.5 agentic
  layer: `agent_context()` (config + capability manifest + tool registry + history) →
  AI `/agent` (one strict-JSON LLM call → `{reply, actions[], commands[]}`;
  deterministic stub) → `agent_apply()` (config writes, validated in Postgres) →
  `agent_run()` (operator tools: resolve_entities · recompute_stats ·
  reprocess_documents · open_search) → `log_agent_turn()` → respond
  `{session_id, reply, applied[], ran[], config}` → **after responding**, reprocess
  candidates are fanned back into `/webhook/ingest` (self-call with `doc_id` =
  in-place re-run; async, no timeout chain). The LLM never writes SQL. AI-node
  errors return HTTP 500 `{error}`, config untouched. Spec: `../docs/AGENT_LAYER.md`.

- **6 · Connector: Pull** (Schedule 5 min + `POST /webhook/connector-pull`) — bulk
  ingest from S3-compatible storage: list `${CONNECTOR_BUCKET}` (credential
  "ArchivAI MinIO") → `connector_filter_new()` (dedup by original_url, ≤100/run) →
  respond `{found, dispatched}` → async fan-out into `/webhook/ingest`.
- **7 · Connector: Push** (Schedule 1 min + `POST /webhook/push-now`) — outbox
  delivery: `outbox_take(10)` (fresh `document_payload()` per row) → POST
  `$env.CLIENT_WEBHOOK_URL` → `outbox_mark()` (sent / retry <5 / failed).
- **8 · Client Sink** (`POST /webhook/client-sink`) — demo "legacy system":
  logs received payloads (`client_push_received`); replace with the client's real
  endpoint via `CLIENT_WEBHOOK_URL`.

Note: schedule-triggered runs hit the Respond nodes too — they carry
`onError: continueRegularOutput` so non-webhook executions continue past them.

## Setup

**Zero-touch (recommended):** `make smoke` boots the stack in stub mode, creates the
n8n owner account if none exists (default `admin@archivai.local` / `ArchivAI-Dev1` —
override with `N8N_OWNER_EMAIL` / `N8N_OWNER_PASSWORD`), imports the Postgres
credential + all workflows headlessly, **publishes** them, and runs the full
end-to-end test. Nothing to click.

**n8n version note (2.x):** three breaking changes matter here.
1. The active/inactive toggle became a **publish/unpublish model** — production
   webhooks only register for *published* workflows; `update:workflow` is deprecated.
2. Workflows imported while the instance has **no owner account** end up attached
   to no project: present in the DB but invisible in the UI, webhooks never register.
3. **`$env` is blocked in expressions by default** (`N8N_BLOCK_ENV_ACCESS_IN_NODE`
   now defaults to `true`). Our workflows read `AI_SERVICE_URL` via `$env`, so the
   compose file sets it back to `false` — fine for this trusted single-tenant
   instance. If your security posture forbids that, hardcode the AI service URL in
   the four HTTP nodes instead.

The smoke script handles all of this (owner first, then import, then
`publish:workflow` per ID, then restart); `make n8n-activate` publishes with a
1.x fallback.

**Manual (UI) alternative:**

1. Start the stack: `make up` (or `make up-stub` — no Ollama, enough for stub mode).
2. Open n8n at http://localhost:5678, complete the owner setup, and create a
   **Postgres credential** named `ArchivAI Postgres` (host `postgres`, db/user/pass
   from `.env`). If you import workflows via the UI (drag the JSONs in), re-select
   this credential on each Postgres node — credential *IDs* from the JSON only bind
   when imported via CLI (`n8n import:credentials`, see `scripts/smoke.sh`).
3. Import workflows: `make n8n-import`.
4. Publish: `make n8n-activate` (publishes all five workflows and restarts n8n so
   the webhook routes register), or click **Publish** on each workflow in the UI.

The AI service URL comes from `$env.AI_SERVICE_URL` (set in compose to
`http://ai-service:8000`), so no per-node editing is needed.

## Version notes (n8n Postgres node)

Query parameters are passed as **a single expression returning an array**, e.g.
`={{ [ $json.doc_id, JSON.stringify($json.payload) ] }}`, referenced in SQL as
`$1, $2, …`. Do **not** use the comma-separated form (`={{ a }},={{ b }}`): n8n
splits that string on every comma *after* resolving expressions, which corrupts
values containing commas — vector literals, JSON payloads, and most free text.
The array form also passes real `NULL`s (a resolved `null` in the string form
becomes the text `"null"`). Nodes that can legitimately return zero rows
(`search`, `rag_retrieve`) set `alwaysOutputData` so the Respond node always runs;
the Code node after them filters out the empty placeholder item.

## Trigger the pipeline

In stub mode (`AI_STUB=1`, the default) the image URL is never fetched, so any URL
works. With real models, upload the scan to MinIO first (MinIO console or `mc`) and
use its URL:

```bash
curl -X POST http://localhost:5678/webhook/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "filename": "10.png",
    "original_url": "http://minio:9000/scans/10.png",
    "pages": [ { "image_url": "http://minio:9000/scans/10.png" } ]
  }'
# -> 202 { "doc_id": "…", "status": "processing" }   (immediately)
# then poll:  SELECT status, process_error FROM documents WHERE id = '<doc_id>';
# -> processed  (or failed, with the reason in process_error)
```

Search:

```bash
curl -X POST http://localhost:5678/webhook/search \
  -H 'Content-Type: application/json' \
  -d '{ "query": "памятник Амангельды Иманову" }'
# -> { "query": "…", "count": N,
#      "results": [ { "document_id", "filename", "document_type",
#                     "date_text", "score", "snippet" }, … ] }
```

Chat (Ask ArchivAI):

```bash
curl -X POST http://localhost:5678/webhook/chat \
  -H 'Content-Type: application/json' \
  -d '{ "question": "Что известно об Абае Кунанбаеве?", "session_id": null, "user_id": null }'
# -> { "session_id": "…", "answer": "… [1][2]", "citations": [...], "grounded": true }
```

Configuration agent (Phase 5):

```bash
curl -X POST http://localhost:5678/webhook/agent \
  -H 'Content-Type: application/json' \
  -d '{ "message": "сделай поиск более семантическим", "session_id": null, "user_id": null }'
# -> { "session_id": "…", "reply": "Готово: …",
#      "applied": [ { "key": "search", "ok": true, "old": {...}, "new": {...} } ],
#      "config": { "search": {...}, "dashboard": {...}, "taxonomy": {...}, "chat": {...} } }
```

## Testing without GPU/models

`AI_STUB=1` (the default in `.env.example`): the AI service returns deterministic
stub OCR/extraction/embeddings/answers so you can validate the **entire n8n +
Postgres wiring** (documents, pages, entities, mentions, edges, embeddings, stats,
search, chat) before pulling the multi-GB open models — that's exactly what
`make smoke` asserts. There is also an offline static check that needs no Docker:
`python3 scripts/simulate_stub_pipeline.py`.

Go live: set `AI_STUB=0`, run `make models`, then
`docker compose up -d --force-recreate ai-service`.
