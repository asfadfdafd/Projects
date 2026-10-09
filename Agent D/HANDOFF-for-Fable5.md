# ArchivAI — Project Handoff Brief (for a fresh build chat)

Paste this into the new chat as context. It is self-contained: goal, full requirements,
locked decisions, what already exists, and exactly what to build next. Two companion docs
hold the detail: **`Agent-D_Demo-Analysis.md`** (what the competitor does) and
**`Agent-D-Alternative_Build-Plan.md`** (how we beat it). The code scaffold lives in
**`Agent D/archivai/`**.

---

## 0. Progress update — 2026-07-10 (build session 1)

**Task 1 (smoke-test) done.** Audit found and fixed pipeline-breaking bugs: all n8n
Postgres params moved to array expressions (comma-splitting corrupted vectors/JSON/text),
`pages` table now persisted by `ingest_extraction()`, failure branch added
(`mark_failed()` + HTTP 500), zero-row hang fixed (`alwaysOutputData`), Code nodes use
`.first()`, headless credential import, `make db-init` applies all SQL. New:
**`make smoke`** (one-command live E2E on the host: boot → headless n8n setup → ingest →
DB asserts → search → chat → resolve → failure path → selftest) and
**`scripts/simulate_stub_pipeline.py`** (mechanical offline verification: executes the
real Code-node JS + expressions under Node with exact stub outputs, checks every SQL
call against parsed function signatures — 93/93 green).

**Phases 2, 3, 3b, 4 code-complete** (all mechanically verified; live gates not yet run):
- Phase 2: Next.js app in `web/` — Upload (multi-file, combine option), Archive
  (filters, thumbs, auto-poll), Detail (zoom viewer, per-page/all-pages, inline entity
  edit via new `04_ui_functions.sql`, Mark as Verified). MinIO kept private via
  `/api/scan` proxy. Reads = SQL; writes = PG functions only.
- Phase 3: `/search` + `/dashboard` (timeline added to `compute_dashboard_stats()`).
- Phase 3b: `/chat` panel — citations open the source document.
- Phase 4: `05_resolution.sql` (`resolve_entities()`: normalized-dup + unambiguous
  token-containment merges, alias-folding) + n8n `4_resolve_entities.json`
  (`/webhook/resolve`) + Entities page (tabs, aliases, expandable rows→docs, CSV export,
  dependency-free SVG knowledge graph).

**Live verification:** ✅ `make smoke` PASSED 32/32 on the host (2026-07-10) — ingest →
documents/pages/entities/mentions/edges/embeddings/stats → search → cited chat →
entity resolution → failure path → AI selftest, all live in stub mode.
Getting there surfaced three **n8n 2.x** (2.19.4, `:latest`) breaking changes, all fixed
and documented in `archivai/n8n/README.md`: (1) publish/unpublish model replaced the
active toggle — the smoke script publishes each workflow by ID (`publish:workflow`);
(2) CLI imports on an ownerless instance are orphaned/invisible — the script creates the
owner headlessly first (default `admin@archivai.local` / `ArchivAI-Dev1`); (3) `$env` in
expressions is blocked by default — compose sets `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
(trusted single-tenant instance). Workflows carry fixed IDs `archivai-w1..w4` so
re-imports update in place.
**Remaining gate:** ✅ PASSED — `make full` built and the whole UI was click-tested live.
Fixes that came out of live testing: API routes converted CJS→ESM (Next 14 requires
`export default` handlers), image-error placeholders, verify-button gating,
**async ingest** (webhook answers `202 {doc_id, processing}` immediately; pipeline
continues in n8n; UI polls — kills the whole HTTP-timeout chain on slow hosts;
pulled forward from Phase 9), `WEB_PORT` override.

**Real-model run done (2026-07-15)** on a 1930 ОГПУ prikaz, dev machine = 8GB MacBook Air:
7B vision via Docker/native was unusable (RAM swap, 0.06 tok/s) → production config for
this machine is `OCR_BACKEND=tesseract` + `EXTRACT_BACKEND=ollama_text` with
`qwen2.5:3b` via **native Ollama** (`LLM_ENDPOINT=http://host.docker.internal:11434`).
OCR preprocessing added (grayscale/upscale/contrast/despeckle + best-of language passes:
rus+kaz vs rus vs kaz by confidence); extraction prompts hardened for small models
(summary strictly Russian, no date invention, no garbage entities, null sender for
decrees). Result: correct type (decree), correct summary content, key entities; residual
OCR noise is the human-in-the-loop demo material. **Qwen2.5-VL on a GPU host remains the
production-quality path** — just point `LLM_ENDPOINT` at it.

**Phase 5 — agentic layer BUILT (2026-07-16, build session 3).** Design agreed
(immediate apply + reset, scope = search+dashboard+taxonomy+chat, engine = AI-service
`/agent` endpoint, taxonomy global) and implemented per `archivai/docs/AGENT_LAYER.md`:
- `db/init/06_preferences.sql` — `user_preferences` (user/global scopes),
  `agent_capabilities()` manifest = single source for the LLM prompt AND SQL validation,
  `set_config` (whitelist/bounds/audit old→new), `agent_apply`, `reset_config`;
  config-aware `search_documents` + `create_document` (moved from 02 — they read
  `get_config()`), `rag_retrieve_cfg`. LLM never writes SQL.
- AI `/agent` (strict-JSON one-call, deterministic stub rules incl. RU/KZ translit
  for taxonomy ids) + `5_agent.json` (`/webhook/agent`, no Code nodes, error→500) +
  `/agent` UI page (diff-chips old→new, live config cards, per-section reset) +
  dashboard/search/chat/ingest now read the config.
- Verified mechanically: simulator extended to w5 + stub parity — **121/121 green**;
  AI selftest incl. agent cases — green (offline shims; container run = `make test`).
- **Live smoke gate ✅ PASSED 47/47 on the host (2026-07-16)** — full pipeline incl.
  step 7c: agent turns changed search weights / hid the timeline widget / added a
  taxonomy type that the next ingest classified with, multi-turn session persisted,
  out-of-bounds + unknown-key writes rejected in SQL, reset restored defaults.
  **Live UI gate ✅ (2026-07-16):** `/agent` click-tested via `make full` (note: after
  web/ changes run `make web-rebuild` — stale image serves 404). UI distinguishes
  "changed (diff chips)" / "already set" / "no actions".
  **Real-model gate ✅ CONFIRMED (qwen2.5:3b, 2026-07-16 01:06)** via
  `chat_messages.citations` (each agent reply stores its applied[]; stub replies
  carry a `[stub]` prefix — audit_log alone can't tell stub from real): the real
  turn emitted a correct strict-JSON search action, `agent_apply` validated and
  applied it (`ok:true`); old==new only because the same values were already set
  by an earlier stub click — that's why no diff chips showed (UI now renders
  "already set" for this case). Guardrails never triggered.
  **Taxonomy add-type on the real model:** first attempt failed exactly as
  predicted — qwen2.5:3b sent ONLY the new type instead of the full replacement
  array; `set_config` rejected it (min_items bound) and the UI showed the red
  error chip (guardrails proven live). Fixed two-sided: few-shot example in
  AGENT_SYSTEM + `_merge_additive_taxonomy()` in the AI service (zero id-overlap
  with current taxonomy ⇒ treat the list as additive and append current types;
  overlapping ids pass through as intentional replacement). Selftest covers both
  branches. Re-test after `docker compose up -d --build ai-service`.

**Phase 5.5 BUILT (2026-07-18, session 4) — agent got real teeth** (Dauren's call:
v1 tunables ≈ settings form; NL must generate and act). Design in `AGENT_LAYER.md`
§10, all three forks = recommended (reprocess in v1; 4 templates; ✕ on widgets):
- **Custom widgets from NL** («добавь виджет: динамика приказов по годам»):
  `custom_widgets` config + template registry in the manifest + `widget_specs`
  validation + `widget_data()` (07_agent_ops.sql) + `/api/widgets` + dashboard
  section with ✕. LLM picks template+params; all SQL is ours.
- **Operator**: `agent_tools()`/`agent_run()`; w5 now: context(+tools) → AI(+commands)
  → agent_apply → agent_run → log → respond(+ran) → fan-out reprocess docs into
  `/webhook/ingest` (self-call, 127.0.0.1); `create_document(p_doc_id)` = in-place
  reprocess. UI ran-chips (⚙/↻/🔎), `/search?q=` autorun.
- Verified mechanically: simulator **138/138** (w5 command path, fan-out contract,
  stub parity), selftest green. **First live smoke: 53/1** — the one fail was a
  stale assert (user_preferences row count crossed scopes; fixed to `user_id IS
  NULL`, and 7c now resets BOTH global and demo-user scopes at baseline).
  ⚠ Lesson from that run: the stub reprocess turn dispatched **17 docs** and
  overwrote pre-existing documents (incl. the real-model 1930 prikaz) with stub
  extractions. Fixed two ways: stub reprocess limit → **2** (only this run's own
  smoke docs; real model still chooses its own limit, capped 20), and `agent_run`
  now **excludes `verified` documents from reprocess by default** (touched only on
  an explicit `status='verified'` request — human-in-the-loop protection).
  To restore the real doc: re-upload/reprocess it with `AI_STUB=0`.
  **Real-model gate (qwen2.5:3b, 2026-07-18): the flagship compound phrase WORKS
  live** — «добавь тип документа "протокол" и переклассифицируй документы» produced
  a valid full-array taxonomy action + reprocess command in ONE turn (after adding
  a full compound few-shot to AGENT_SYSTEM; before it the 3b answered
  conversationally with empty actions — the honest UI exposed exactly that).
  Also fixed: never-ask-about-default-params rule; reply-must-match-actions rule;
  transliterate-not-translate rule for new taxonomy ids (3b turned «справка» into
  id `summary`; prompt now demands `spravka`-style translit). Post-reboot note:
  native Ollama must be started manually (`ollama serve`) — down Ollama = agent
  error branch 500.
  **Remaining live checks:** confirm the 5 reprocessed docs flipped to `protokol`
  in the archive; widget phrase + operator phrases on the real model; re-run
  `make smoke` after the prompt tweaks (expect 54/54).

**Phase 6 BUILT (2026-07-18, session 4) — auth, profiles, compliance** (all three
design forks = recommended: local SSO-ready auth · login required + `AUTH_OPTIONAL=1`
dev flag · admin gates). Spec `archivai/docs/PHASE6_AUTH.md`:
- `08_auth.sql`: pgcrypto logic in PG (login → hashed session token, rolling expiry,
  IP-audited incl. failures; register/change_password/logout; `search_and_log` wraps
  search + history; `log_doc_view`; `usage_stats()`); demo login
  **demo@archivai.local / archivai-demo**.
- Web: `/login`, session cookie via thin `lib/auth.js`, ALL api routes now use the
  session user (demoUserId retired), Layout user menu + admin-only **/usage**
  (searches/day, top queries, top docs, active sessions, login/IP table),
  recent-search chips on /search.
- SQL role gates: global config + reprocess = admin-only (`is_admin`, NULL = trusted
  internal). w2 → `search_and_log($1,$2,$3::uuid,$4)`.
- Mechanical: simulator 138/138, smoke gains step **7d** (register/login/auth_user/
  logout, bad-login audit, reviewer blocked from taxonomy+reprocess, history,
  usage_stats). **Live gate not yet run:** `make smoke` → `make web-rebuild` →
  click-test; then set `AUTH_OPTIONAL=0` + recreate web for the real login screen.

**Phase 6 live gate ✅ (2026-07-27): smoke 65/65** after two test fixes (scope-aware
user_preferences assert; smoke user reused — audit FK forbids user deletion, by
design) and one SQL fix (usage_stats aggregate-in-GROUP-BY). Sidebar made sticky
(logout was below the fold on long pages). `AUTH_OPTIONAL=1` in dev .env.

**Phase 7 BUILT (2026-07-27, session 5) — connectors** (all three forks =
recommended: S3/MinIO source · full-JSON outbox push · 5-min schedule + Pull now).
Spec `archivai/docs/PHASE7_CONNECTORS.md`:
- w6 pull: S3 list → `connector_filter_new()` dedup → async fan-out to ingest;
  `import` bucket auto-created; "Pull from storage" button on Upload.
- w7 push: outbox (trigger on processed → `outbox_take()` fresh `document_payload()`
  → POST `$env.CLIENT_WEBHOOK_URL` → `outbox_mark()` retry/fail); w8 demo sink logs
  `client_push_received`. Env: `CONNECTOR_BUCKET`, `CLIENT_WEBHOOK_URL` (compose+n8n).
- Simulator now handles schedule-trigger workflows — **187/187 green**; smoke gains
  step 7e (drop→pull→processed→dedup→push→sink→sent) and expects 8 webhooks.
  **Live gate ✅ (2026-07-27):** smoke 7e passed on the host (S3 node worked as-is);
  a real MinIO-console upload → "Pull from storage" → both files ingested; scan-proxy
  bucket allowlist extended to the `import` bucket (thumbnails were 403 before).
  **Real-model operator confirmed:** «переобработай документы» first landed as a
  wrong-array action (tool name as config key) → guardrail red chip; fixed with
  `_rescue_misplaced_tools()` (action whose key is a tool name → command) + a prompt
  rule/example + dynamic allowed-keys error text — after rebuild the same phrase
  works live. Pattern now established: every observed 3b failure mode gets a
  deterministic server-side rescue + a prompt few-shot.

**Pre-demo build (2026-07-27): IoT widget + demo package** (client demo in 1–2 days;
Dauren picked both recommended items, signature/stamp deferred to a GPU host):
- IoT: `10_metrics.sql` + w9 `/webhook/metrics` + dashboard Storage Environment card
  (live poll, norm colors) + `make sensor-demo`. Widget id `storage_env` is in the
  agent manifest. Smoke 7f, simulator **197/197**.
- Demo package: `make demo-clean` (`cleanup_test_data()`: smoke/stub docs + orphan
  entities out, audit kept) + **`docs/DEMO_SCRIPT.md`** (полный сценарий: подготовка,
  9 шагов, козыри против Agent D, план Б на сбои).
  **Live gate not yet run:** `make smoke` (жду ~79/0) → `make web-rebuild` →
  прогон DEMO_SCRIPT.md целиком на реальных моделях.

**Search relevance + OCR sprint (2026-07-27, prompted by real usage):**
- Search: `min_score` + `cutoff_ratio` (default 0.2 / 0.75·best) added to the search
  config (agent-tunable) — background-similarity noise no longer pads results.
  Doc-type near-misses snap to taxonomy ids (`decreet`→`decree`, `_snap_type`).
  Duplicate docs from mixed ingest paths: SQL dedup given; content-hash dedup on
  ingest = backlog.
- OCR for the real corpus (1931 stenogram sample: typewriter, yellowed paper, red
  hand edits, blue stamp): new `app/preproc.py` (pure PIL) — **color-ink
  suppression** (red edits/stamps whitened before OCR), **deskew** (projection
  profile; verified exact on synthetic), **Otsu binarization**; era **user-words**
  list for tesseract (`app/data/user_words_ru_kz.txt`); opt-in **LLM proofreading**
  (`OCR_LLM_CORRECT=1`, length-guarded, pages keep raw text); flags in .env.
  **`scripts/ocr_eval.py`** — CER/WER benchmark vs `samples/eval/*.gt.txt`
  (waits for service boot; `/ocr` now also applies the optional proofreading so the
  benchmark matches the pipeline). Rule: no OCR change without the number moving down.
- **First measured A/B (1931 stenogram, `samples/eval/stenogramma1931`)** — baseline
  CER **0.309** → **0.198** (−36%). Findings:
  · `TESSERACT_PSM=6` (uniform block) 0.296 vs psm4 0.309 vs auto 0.309;
  · **Otsu binarization HURTS** faded type (0.296 → 0.219) — now default 0;
  · **LLM proofreading on qwen2.5:3b HURTS badly** (0.202 → 0.565: it rewrites
    instead of correcting) — default 0, guards tightened (length 0.9–1.1 AND
    char-similarity ≥ 0.85); re-benchmark only on 7B+.
  · **kaz-pack noise on Russian pages** ("тов"→"тоз", "МЕНДЕШЕВ"→"МЕҢДЕШЕВ",
    "Қазакстана") — new `_kaz_noise_penalty()`: a language pass with implausibly
    SPARSE Kazakh-only letters (0.5–3%) loses the best-of-N race. CER effect is
    marginal (0.202→0.198 together with `--oem 1`, which showed no benefit and was
    reverted to default), but it protects PERSON/PLACE NAMES → entity dedup and
    search, which CER doesn't measure. Kept for that reason.
  Winning profile is now the default in `.env`/`.env.example`:
  psm6 · ink-suppression on · deskew on · binarize off · llm-correct off ·
  script-penalty on · default OEM.
  Remaining error is dominated by the SOURCE (blurred header/bottom of a photo, not
  a 300dpi scan) and by digits ("1916"→"1212") — both beyond tesseract tuning; the
  next real step-change is a proper scan + Qwen2.5-VL on GPU. Also: a single eval
  page can't resolve deltas < ~0.02 — add 10–15 pages before chasing smaller gains.
  Longer-term (GPU): Qwen-VL 7B+ one-pass, and the verification flywheel
  (verified pages → fine-tuning data). Note: part of the residual CER is the
  ground truth itself (typed from a photo — two ambiguous words, cropped last line).

**Next: demo rehearsal per DEMO_SCRIPT.md; after the client showing — Phase 8
remainder (signature/stamp on GPU, learning) + Phase 9 hardening.**

---

## 1. Goal

Build **ArchivAI**, an open-source, self-hostable competitor to **"Agent D"** (by Chordify) —
an AI archive that turns scanned historical documents into a **searchable, entity-linked,
human-verifiable** collection. Target domain: **20th-century Kazakh & Russian** archival
records (typed + handwritten, mixed Cyrillic/Latin-Kazakh scripts; e.g. 1940s South-Kazakhstan
correspondence). End user = **researcher** searching people/places/events and discovering
hidden relations. Client = an **archival institution** (archives, inventories, storage
monitoring).

**n8n is the orchestration core.** Every pipeline stage is an n8n workflow so models are
swappable and the pipeline is visible/extensible. The web app is a thin Next.js front end.

## 2. Locked decisions (do not re-litigate)

- **Models: open-source only**, must read historical Kazakh + Russian, typed + handwritten.
  Default **Qwen2.5-VL** (vision-LLM, one-pass OCR+extraction) via **Ollama**; **Tesseract
  `rus+kaz`** fallback; **bge-m3** embeddings. No paid APIs, no data leaving the host.
- **Stack:** n8n · FastAPI AI service · **Postgres + pgvector** · **MinIO** · **Next.js + Tailwind**.
- **Deployment-agnostic:** one `docker-compose` (on-prem / private cloud / server). Host TBD.
- **Approach:** foundation + core first, then extend. DB writes are **Postgres functions**;
  n8n workflows stay thin. AI service is **stateless** (n8n owns persistence).
- **Stub mode** (`AI_STUB=1`) returns deterministic output so the whole pipeline can be tested
  with no GPU/models.

## 3. What already exists in `archivai/` (Phases 0–1 done)

- `docker-compose.yml` — postgres(pgvector), minio(+bucket init), ollama, ai-service, n8n, web(placeholder, `--profile full`).
- `.env.example`, `Makefile` (`up`, `models`, `n8n-import`, `db-init`, `test`), `README.md`, `docs/` (ARCHITECTURE, DATA_MODEL, ROADMAP).
- **DB** `db/init/01_schema.sql` + `02_functions.sql`: tables `users, documents, pages, entities,
  entity_mentions, entity_edges, embeddings, audit_log, dashboard_stats`; functions
  `create_document, ingest_extraction, upsert_embedding, mark_verified, search_documents
  (hybrid vector+trigram), compute_dashboard_stats, rebuild_all_edges`. Enums: `doc_status`,
  `entity_type(person|organization|date|place|quantity)`. Provenance + confidence fields present.
- **AI service** `services/ai/` (FastAPI): `/health`, `/ocr`, `/process` (OCR+extraction), `/embed`.
  Backends swappable via env; prompts tuned for historical KZ/RU in `app/prompts.py`;
  offline `app/selftest.py`. (Verified: syntax compiles; JSON-parse/dedupe/embed logic tested.
  Full run needs pydantic/httpx/pillow, installed in the Docker image.)
- **n8n** `n8n/workflows/`: `1_ingest_and_process.json` (webhook `/ingest`), `2_search.json`
  (webhook `/search`), and `3_chat.json` (webhook `/chat` — RAG chat). All validated as
  importable JSON with verified connection integrity. n8n Postgres node needs a credential named
  **"ArchivAI Postgres"**; version-specific param notes in `n8n/README.md`.
- ⭐ **"Ask ArchivAI" chat assistant scaffolded** (backend): AI `/answer` (grounded, cited,
  honest "not found"), `db/init/03_chat.sql` (`chat_sessions`, `chat_messages`, `rag_retrieve()`,
  `log_chat_turn()`), `3_chat.json`, spec in `docs/CHAT_ASSISTANT.md`. Stub-tested. **UI chat
  panel still to build.**

**Not yet built:** the entire web UI (incl. the chat panel), semantic-search UI, dashboard UI,
entity resolution, knowledge graph, and everything in §4 below.

## 4. Full requirement set to match/beat Agent D (from screens + transcript)

**Demonstrated (must have):**
- Upload; per-page OCR of printed+handwritten; **all-pages** aggregate view.
- Per-document: type classification, date, language, **sender/recipient (name+role)**,
  **AI summary**, entities in 5 categories, full text.
- **Inline editing** of entities (fix spelling / add missed) + **Mark as Verified** (human-in-loop).
- **Contextual + semantic search** (natural language, highlights, jump to match).
- **Knowledge graph** linking people↔orgs↔places; entity→document navigation; **CSV export**.
- **Dashboard**: docs processed, people/orgs/entities counts, distributions, top-5 entities,
  language distribution, recent activity, timeline.
- Download/export per page, all pages, entities.

**Promised/roadmap (differentiators to win on):**
- ⭐ **Agentic no-code layer ("Agent D")** — user reconfigures search/dashboard/classification
  in natural language; an LLM agent applies it per user. Build as an n8n agent workflow writing
  to a `config`/`user_preferences` table.
- **Signature & stamp extraction** — bounding-box → cropped image artifacts (`document_artifacts`).
- **Per-user profiles + SSO**, personalized search, **search history**.
- **Compliance/usage analytics** — queries, top docs, active users, **IPs** (extend `audit_log`).
- **Bulk ingestion + connectors** — pull 50–100+ docs from client storage (S3/SMB/folder/DB);
  **bidirectional webhooks** to legacy systems; system needs only **file storage + database**.
- **External/IoT dashboard widgets** (e.g. storage temperature/humidity via API → `metrics`).
- ⭐ **"Ask ArchivAI" conversational RAG chat assistant** (prioritized; **Agent D does NOT have
  this** — its search only returns doc lists). Chat over the corpus: embed question → pgvector
  retrieve → graph expansion → open LLM → **answer with citations** that open the source doc;
  multi-turn memory (`chat_sessions`/`chat_messages`), grounded/no-hallucination, per-user,
  open-source models. Also serves as the client-requested archival-expert assistant.
- **Learning/recommendations** from usage.

**Non-functional:** on-prem / private-cloud / data residency; minimal footprint; customizable
taxonomy, dashboard, and search.

**Our edge over the original (already designed in):** real **entity resolution/dedup**
(`entities.aliases[]`), **single-source consistent dashboard stats**, **confidence + provenance**
on every extraction.

## 5. Recommended next steps for the new chat (in order)

1. **Stand up & smoke-test** the core in **stub mode** (`AI_STUB=1`): `make up`, create the
   n8n Postgres credential, `make n8n-import`, POST a sample to `/webhook/ingest`, confirm rows
   in `documents/entities/entity_mentions/entity_edges/embeddings` and that
   `compute_dashboard_stats()` returns. Then `AI_STUB=0` + `make models` for a real run.
2. **Phase 2 — Web UI** (Next.js in `web/`): Upload → Document Archive → Document Detail
   (scan viewer, per-page + all-pages, inline entity edit, Mark as Verified). API contracts are
   fixed by the DB functions + n8n webhooks.
3. **Phase 3 — Semantic search UI + Dashboard** (read `dashboard_stats`).
4. **Phase 3b — "Ask ArchivAI" chat assistant** ⭐ (build right after search; reuses `embeddings`):
   n8n `/chat` RAG workflow with citations + chat panel. Prioritized differentiator.
5. **Phase 4 — Entity resolution workflow + Entities page + knowledge graph + CSV**.
6. **Phase 5 — the agentic layer** (flagship). Then profiles/SSO, connectors, signature/stamp,
   IoT + recommendations (Phases 6–8), hardening/deployment (Phase 9). See Build Plan §10 + ROADMAP.

## 6. Open questions to resolve with the client

- Which host in the end (on-prem vs private cloud + region)? Drives packaging.
- SSO provider (OIDC/SAML) and whether per-user personalization is in the first cut.
- Client file-storage + DB types for the connector layer (they mentioned old Java + PostgreSQL 6/7).
- Document-type taxonomy to standardize on.
- Are signature/stamp extraction and the IoT dashboard in scope for v1?
- GPU availability (Qwen2.5-VL is much better with a GPU).

## 7. File map

```
Agent D/
  Agent-D_Demo-Analysis.md            # what Agent D does (screens + transcript §6)
  Agent-D-Alternative_Build-Plan.md   # how we compete; §9 decisions, §10 expanded scope
  HANDOFF-for-Fable5.md               # this file
  archivai/                           # the code scaffold (Phases 0–1 built)
    README.md · docker-compose.yml · Makefile · .env.example
    db/init/{01_schema,02_functions}.sql
    services/ai/…                     # FastAPI OCR+extraction (open-source)
    n8n/workflows/{1_ingest_and_process,2_search}.json · n8n/README.md
    web/…                             # placeholder → build Next.js here
    docs/{ARCHITECTURE,DATA_MODEL,ROADMAP}.md
    samples/                          # drop test scans here
```
