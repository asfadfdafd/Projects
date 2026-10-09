# Roadmap

Legend: ✅ done in this repo · ▶ next · ◻ later

## Phase 0 — Foundation ✅
- ✅ docker-compose (Postgres+pgvector, MinIO, Ollama, AI service, n8n, web scaffold)
- ✅ DB schema + functions (auto-applied on boot)
- ✅ `.env` config + Makefile + stub mode

## Phase 1 — Core pipeline ✅
- ✅ AI service: `/process` (OCR + extraction), `/ocr`, `/embed`, `/pdf/split` (PDF → page
  images + text layer); open-model backends + fallbacks
- ✅ n8n **Ingest & Process** workflow (end-to-end: scan → structured, embedded, stored),
  incl. per-page OCR persistence (`pages`), a failure branch (`mark_failed` +
  `documents.process_error`), and **async ingest** (immediate `202 {doc_id, processing}`,
  pipeline continues in background, UI polls — no timeout chain on slow hosts;
  pulled forward from Phase 9)
- ✅ n8n **Search** workflow (hybrid vector + keyword; `{query, count, results}` response,
  safe on an empty archive)
- ✅ Offline contract self-test + mechanical pipeline simulation
  (`scripts/simulate_stub_pipeline.py`)
- ✅ One-command E2E smoke test (`make smoke`): headless n8n credential/workflow import +
  activation, ingest → DB assertions → search → chat → failure path

## Phase 2 — Core UI ✅ (code complete; verify live with `make full`)
- ✅ Next.js + Tailwind app in `web/` (Pages Router; standalone Docker build; MinIO kept
  private via `/api/scan` streaming proxy)
- ✅ Upload (drag-drop multi-file → MinIO → ingest webhook; optional combine into one
  multi-page document)
- ✅ Document Archive table (thumbnail, type, date, language, entity count, status filter,
  pagination, auto-poll while processing)
- ✅ Document Detail (scan viewer with zoom + page nav, chips, sender/recipient, AI summary,
  per-page + all-pages text, **inline entity editing** via `04_ui_functions.sql`
  (add/rename/remove, audit-logged, alias-preserving), **Mark as Verified** → `mark_verified`)

## Phase 3 — Search & Dashboard ✅ (code complete; verify live with `make full`)
- ✅ Search UI over the search webhook (`/search` page + `/api/search` proxy; result cards
  with type/score/snippet linking to Document Detail)
- ✅ Dashboard reading `dashboard_stats` (`/dashboard` + `/api/dashboard` read/recompute):
  4 KPI cards, entity-distribution donut, top-5 people/orgs, language distribution,
  recent activity, **document timeline** (added `timeline` to `compute_dashboard_stats()`)

## Phase 3b — "Ask ArchivAI" chat assistant  ⭐ prioritized (client-wanted; Agent D lacks it)
- ✅ n8n chat workflow `3_chat.json` (`/chat`): embed → `rag_retrieve` → build contexts →
  AI `/answer` (archival-expert prompt) → **answer with citations** → `log_chat_turn`
- ✅ AI service `/answer` endpoint (grounded, cited, honest "not found") + stub-mode test
- ✅ Schema `03_chat.sql`: `chat_sessions`, `chat_messages`, `rag_retrieve()`, `log_chat_turn()`
- ✅ Chat panel in the UI (`/chat` + `/api/chat` proxy): session-persistent multi-turn,
  **citations open the source document** (4th navigation path), honest not-found styling
- ◻ Extend: pass `history` to `/answer` for follow-ups, knowledge-graph expansion,
  streaming, access-scoped retrieval (spec in `CHAT_ASSISTANT.md`)

## Phase 4 — Entities & graph ✅ (code complete; verify live with `make full`)
- ✅ Entity Resolution: `resolve_entities()` in `05_resolution.sql` (normalized-duplicate
  merge + unambiguous token-containment merge for people/orgs, alias-folding, audit-logged)
  + thin n8n workflow `4_resolve_entities.json` (`POST /webhook/resolve`) + UI trigger.
  ◻ Extension: embedding-similarity merging (bge-m3) for non-overlapping spellings
- ✅ Entities page: tabs + filter + table (role, doc count, aliases), expandable rows →
  linked documents (entity→doc navigation), **CSV export** (BOM for Cyrillic Excel),
  dependency-free SVG force-directed **knowledge graph** (legend, zoom/reset, click-to-filter)

## Phase 5 — Agentic layer ✅  ⭐ flagship (all gates passed 2026-07-16: smoke 47/47 · live UI · real qwen2.5:3b action confirmed via chat_messages.citations)
- ✅ `06_preferences.sql`: `user_preferences` (per-user + global scopes),
  `agent_capabilities()` manifest (single source for prompt AND validation),
  `get_config`/`set_config` (whitelist + bounds + audit old→new)/`agent_apply`/
  `reset_config`; config-aware `search_documents` (weights/limit/snippet),
  `create_document` (hands taxonomy to the pipeline), `rag_retrieve_cfg` (chat k/style)
- ✅ AI `/agent` (strict-JSON, one call, deterministic stub; qwen-safe prompt) +
  n8n `5_agent.json` (`/webhook/agent`, error branch, sessions `kind='agent'`)
- ✅ `/agent` UI page: NL chat + applied-diff chips + live effective-config cards with
  per-section reset; dashboard renders widgets/top-N per config; extraction prompt
  constrained by agent-managed taxonomy
- ✅ Verification: simulator covers w5 + stub-agent parity (121 checks green);
  smoke step 7c (weights→search, widget hide, taxonomy→ingest, multi-turn,
  guardrail rejects, reset); selftest agent cases
  *This is the "Agent D" differentiator — see transcript §6.2. Spec: `AGENT_LAYER.md`.*

## Phase 5.5 — Agent: custom widgets + operator ✅ (code complete; live gate = `make smoke` + `make web-rebuild`)
- ✅ **Custom widgets from NL**: config key `custom_widgets` (≤6 specs), template
  registry in `agent_capabilities()` (doc_count / doc_timeline / top_entities /
  kpi_count), `widget_specs` validation in `set_config`, `widget_data()` computes
  (SQL is ours — LLM only picks template+params), `/api/widgets` + dashboard
  "Custom widgets" section with per-widget ✕ (removal via the same set_config path)
- ✅ **Operator commands**: `agent_tools()` registry + `agent_run()` (07_agent_ops.sql):
  resolve_entities · recompute_stats · reprocess_documents (n8n fans candidates back
  into `/webhook/ingest`; `create_document(p_doc_id)` reprocesses IN PLACE) ·
  open_search (UI link, `/search?q=` autorun). Ran-chips in the agent UI
- ✅ Compound intents («добавь тип и переклассифицируй») = actions + commands in one
  turn; verified: simulator 138/138 incl. w5 fan-out + stub parity; selftest;
  smoke 7c extended (widget → widget_data, 2-tool turn, reprocess reclassifies
  the archive after a taxonomy change)

## Phase 6 — Auth, profiles & compliance ✅ (code complete; live gate = smoke 7d + login click-test)
- ✅ Local auth, SSO-ready (`users.auth_provider`; OIDC drops in when the client names
  a provider): pgcrypto logic fully in `08_auth.sql` (`register_user`/`login`/
  `auth_user`/`logout`/`change_password`; hashed session tokens, rolling 7-day expiry,
  every login/fail audited **with IP**); `/login` page; `AUTH_OPTIONAL=1` dev flag
- ✅ Real per-user everywhere: session user replaces demoUserId across all API routes —
  preferences/agent/chat/widgets/verification actor light up per profile
- ✅ `search_history` via `search_and_log()` (w2, still one PG call) + recent-searches
  chips on /search (personalization v1); `log_doc_view` per document open
- ✅ Compliance: admin-only **/usage** page from `usage_stats()` — searches/day, top
  queries, most-viewed docs, active sessions, login/IP table
- ✅ Role gating v1 in SQL: global config (taxonomy) + reprocess = admin-only
  (`is_admin`; NULL = trusted internal path), /usage + register_user admin-only
- ◻ Later: OIDC/SAML provider integration; personalized ranking (Phase 8 learning)

## Phase 7 — Connectors & integration ✅ (code complete; live gate = `make smoke` step 7e)
- ✅ **Pull** (w6 `6_connector_pull.json`): Schedule 5 min + `POST /webhook/connector-pull`
  ("Pull now" button on Upload) → S3 list of `${CONNECTOR_BUCKET}` (default `import`,
  auto-created; client S3 = same protocol, folders via `mc mirror`) →
  `connector_filter_new()` dedup by `original_url` (cap 100/run) → async fan-out into
  the existing ingest pipeline. Second pull → `dispatched: 0`.
- ✅ **Push** (w7): **outbox pattern** — trigger enqueues on `status→processed`,
  `outbox_take()` builds fresh `document_payload()` (full structured JSON: fields,
  entities+aliases, pages) at send time, HTTP POST to `$env.CLIENT_WEBHOOK_URL`,
  `outbox_mark()` → sent / retry (<5) / failed+reason. Schedule 1 min +
  `POST /webhook/push-now` flush.
- ✅ **Demo sink** (w8 `/webhook/client-sink`) = stub legacy system: logs received
  payloads to audit (`client_push_received`) so the bidirectional loop E2Es out of
  the box; production points `CLIENT_WEBHOOK_URL` at the client endpoint.
- ✅ Headless S3 credential import; simulator supports schedule-trigger workflows
  (187 checks green); smoke 7e: drop file → pull → processed → dedup → push-now →
  sink received payload → outbox sent.
- ◻ Later: SMB/FTP adapters; agent-tunable connector settings; client-DB polling

## Phase 8 — Advanced extraction & assistant (partial)
- ✅ **External/IoT dashboard widgets** (client-requested): `10_metrics.sql`
  (`metrics`, `ingest_metric()` tolerant intake, `latest_metrics()`), w9
  `POST /webhook/metrics`, dashboard **Storage Environment** card (live 15s poll,
  archival-norm colors 16–20°C / 40–55%RH, 24h min/max), `storage_env` widget id is
  agent-manageable, `make sensor-demo` simulator, smoke 7f
- ✅ Demo hygiene: `cleanup_test_data()` + `make demo-clean` (smoke/stub docs out,
  orphan entities pruned, audit kept); **`docs/DEMO_SCRIPT.md`** — полный сценарий
  показа клиенту
- ◻ Signature/stamp detection → cropped image artifacts (`document_artifacts`, bbox) —
  needs a detector + realistically a GPU host
- ◻ Learning/recommendations from usage
  *(the archival-expert RAG assistant is now its own prioritized Phase 3b, above)*

## Phase 9 — Hardening & deployment ◻
- ✅ **Multi-page PDF ingest**: upload or connector-pull a PDF → AI `/pdf/split`
  (poppler) renders one image per page into MinIO, so it becomes an ordinary
  multi-page document (viewer, per-page text, reprocess all work unchanged).
  Digital PDFs reuse their own text layer instead of OCR (`PDF_TEXT_LAYER`),
  which also skips the vision model entirely for born-digital files.
- ◻ Review queue, handwriting/model tuning, eval set
- ◻ On-prem / private-cloud packaging + data residency

**Shipped now = a working competing core:** upload-ready pipeline that turns scans into
searchable, entity-linked, embedded records with consistent analytics — all orchestrated in n8n.
Full promised feature set (agentic layer, profiles, connectors, signature/stamp, assistant)
is scoped above and detailed in `../../Agent-D-Alternative_Build-Plan.md` §10.
