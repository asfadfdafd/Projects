# "Agent D" Alternative — Build Plan (n8n-centric)

Goal: a competing solution that does the same job as Agent D — turn scanned archival documents into a searchable, entity-linked, human-verifiable archive — with **n8n as the core orchestration engine** and a **web app** front end.

Working name suggestion: **ArchivAI** (rename freely).

---

## 1. Strategy: why n8n at the center

Agent D's real value is a **pipeline**: OCR → LLM extraction → entity resolution → embeddings → storage → verification → analytics. That pipeline is exactly what n8n is built to run. Instead of burying it in backend code, we make each stage an **n8n workflow node**. Benefits:

- Swap OCR/LLM providers without touching the app.
- Visible, debuggable, re-runnable pipeline (retries, error branches, manual re-process).
- Easy to add steps (translation, confidence scoring, de-dup, notifications).
- The web app stays thin: it uploads files, reads the database, and calls n8n webhooks.

**Split of responsibilities**
- **n8n** = all processing (ingest, OCR, extraction, embeddings, entity resolution, search-embed, aggregation).
- **Web app** = UI + auth + reads/writes to DB + triggers n8n via webhooks.
- **Postgres (+pgvector)** = single source of truth (documents, entities, mentions, edges, vectors).
- **Object storage (MinIO/S3)** = original scans + page images.

---

## 2. Architecture

```
                    ┌────────────────────────────────────────────┐
  Browser ─────────▶│  Web App (Next.js + Tailwind)              │
                    │  Dashboard · Archive · Detail · Search ·   │
                    │  Entities graph · Upload                   │
                    └───────┬───────────────────────┬────────────┘
                            │ REST/DB reads          │ webhook (upload, search, verify)
                            ▼                        ▼
                    ┌───────────────┐        ┌────────────────────────────┐
                    │ Postgres +    │◀──────▶│  n8n (workflow engine)     │
                    │ pgvector      │        │  1 Ingest  2 Process       │
                    └───────────────┘        │  3 Resolve 4 Search        │
                            ▲                │  5 Verify  6 Aggregate     │
                            │                └───────┬───────────┬────────┘
                    ┌───────────────┐                │           │
                    │ MinIO / S3    │◀───────────────┘           ▼
                    │ (scan images) │                   OCR + LLM + Embeddings
                    └───────────────┘                   (provider APIs)
```

All of it runs from a single **docker-compose** (n8n, Postgres+pgvector, MinIO, web app) for local dev; the same compose deploys to a VPS.

---

## 3. n8n workflows

**1. Ingestion** (Webhook trigger from Upload)
Receive file → store original to MinIO → if PDF, split into page images → create `document` + `page` rows (status=`processing`) → fire the Processing workflow per document.

**2. Document Processing** (the heart)
For each page: **vision-LLM OCR** → concatenate to `full_text` → **LLM structured-extraction call** returning JSON (type, date, language, sender{name,role}, recipient{name,role}, summary, entities[{name,type,role}]) → validate/parse → write document fields + entity rows + mentions → **embed** full_text (+chunks) → upsert vectors → set status=`processed`. Error branch → status=`failed` + logged reason + retry.

**3. Entity Resolution** (triggered after processing, or scheduled/batch)
Normalize names → fuzzy-match + embedding-similarity to merge duplicates ("Абай" ↔ "Абай Кунанбаев") → maintain canonical entities + aliases → rebuild co-occurrence **edges** (entities sharing a document). *This is where we beat Agent D's dedup gaps.*

**4. Search** (Webhook)
Embed query → pgvector similarity + keyword/trigram search → merge/rank → return document + entity hits with snippets.

**5. Verification** (Webhook)
Mark document verified, record reviewer + timestamp, write audit row; optionally lock entities.

**6. Aggregation** (Webhook or scheduled)
Compute dashboard stats from one query set (KPIs, distributions, top entities, language split, recent activity, timeline) → cache table so numbers are always consistent.

---

## 4. Data model (Postgres)

- `users` (auth)
- `documents` — id, filename, original_url, status, document_type, date_text, date_parsed, language, sender_name, sender_role, recipient_name, recipient_role, ai_summary, full_text, verified_by, verified_at, created_at
- `pages` — id, document_id, page_no, image_url, ocr_text
- `entities` — id, canonical_name, type (person|organization|date|place|quantity), role_description, aliases[], document_count
- `entity_mentions` — id, entity_id, document_id, surface_form, confidence
- `entity_edges` — entity_a, entity_b, weight (shared-doc count)
- `embeddings` — id, document_id, chunk_no, vector(pgvector), text
- `dashboard_stats` — cached aggregates
- `audit_log` — action, actor, target, timestamp

---

## 5. Front-end screens (parity with Agent D)

1. **Dashboard** — 4 KPI cards, entity-distribution donut, top entities, language split, recent activity, timeline (Recharts).
2. **Document Archive** — table with thumbnail, name, type, date, language, status, actions; upload; pagination; status filter.
3. **Document Detail** — scan viewer (zoom + multi-page) | right panel: type/date/language/status chips, sender/recipient, AI summary, editable entity groups (+Add/remove), full text, **Mark as Verified**.
4. **Search** — semantic + keyword, result cards with snippets, type filters.
5. **Entities** — knowledge-graph (react-force-graph / Cytoscape), tabs All/People/Orgs, filter, **Export CSV**, expandable rows → linked documents.
6. **Upload** — drag-drop, multi-file, progress, triggers Ingestion webhook.
7. **Auth / Folders**.

---

## 6. Recommended stack (proposal — to confirm)

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **n8n** (self-hosted, docker) | Project's central requirement |
| Web app | **Next.js + Tailwind** | Matches Agent D's look; fast to build; API routes for DB |
| DB | **Postgres + pgvector** | Relational + vector search in one |
| Object storage | **MinIO** (S3-compatible) | Local + cloud parity |
| OCR + extraction | **Vision-LLM** (GPT-4o / Claude / Gemini) one-shot OCR+extract | Best on handwritten multilingual scans; fewest moving parts |
| Embeddings | provider embeddings (or local `bge-m3`) | Multilingual semantic search |
| Graph UI | react-force-graph | Matches the entity-relationship canvas |
| Deploy | docker-compose → VPS | One command up |

Open OCR alternative (no per-page API cost): Tesseract + TrOCR — cheaper but weaker on handwriting; can be a fallback branch in n8n.

---

## 7. Phased roadmap

- **Phase 0 — Scaffold (foundation):** docker-compose (n8n + Postgres/pgvector + MinIO + Next.js), DB schema/migrations, env + secrets, health checks.
- **Phase 1 — Pipeline MVP (end-to-end, one doc):** Ingestion + Processing workflows in n8n; a single scan → OCR → extracted JSON → DB. Verify against a sample from the video.
- **Phase 2 — Core UI:** Upload, Document Archive, Document Detail (with editable entities + Mark as Verified).
- **Phase 3 — Search + Dashboard:** embeddings + Search workflow + search UI; Aggregation workflow + dashboard.
- **Phase 4 — Entities + graph:** Entity Resolution workflow (dedup), Entities page, knowledge graph, CSV export.
- **Phase 5 — Hardening:** multilingual/handwriting tuning, confidence scores + provenance, auth, folders, batch upload, deployment.

**MVP = Phases 0–2** (upload → process → view/verify). That alone demonstrates a working competitor.

---

## 8. What beats the original

- Proper **entity resolution** (dedup/aliases) — fixes visible gaps in Agent D.
- **Consistent analytics** from a single aggregation source.
- **Confidence scores + provenance/audit** on every extraction.
- **Provider-agnostic, visible pipeline** — swap OCR/LLM, re-run, and extend in n8n without a rewrite.

---

## 9. Decisions locked (with the client)

1. **Scope** — architecture + core first ("do it properly, main parts first, then extend"). Foundation + core pipeline are built (`archivai/`); UI and later features follow.
2. **AI models** — **open-source only**, able to read 20th-century Kazakh & Russian (typed + handwritten, mixed Cyrillic/Latin-Kazakh). Default Qwen2.5-VL vision-LLM via Ollama; Tesseract `rus+kaz` fallback; bge-m3 embeddings. No paid APIs.
3. **Frontend** — Next.js + Tailwind.
4. **Deployment** — kept **deployment-agnostic** (one docker-compose, on-prem / private cloud / server) because the target host is not yet decided. Matches the original's on-prem / private-cloud / data-residency pitch.
5. **Samples** — use any stand-in scans for now.

---

## 10. Expanded scope from the transcript (must-match feature set + differentiators)

The narration revealed features that are **promised** by the original but not all shown. To truly compete, the plan now includes them. Each maps cleanly onto the n8n-centric architecture.

**The agentic layer ("Agent D" = the differentiator).** An LLM **agent** that lets users reconfigure behavior in **natural language, no code** — "make search work like X", "show Y on the dashboard", "classify docs as Z". Build as a dedicated **n8n agent workflow** (LLM + tools) that writes per-user config (search weights, dashboard widgets, classification taxonomy) to a `user_preferences` / `config` table the app and pipeline read. This is the headline feature to nail.

**Signature & stamp extraction (optional models).** Object-detection step in the processing workflow: detect signature/stamp regions → crop bounding boxes → store as image artifacts in MinIO, linked to the document (`document_artifacts` table: type=signature|stamp, bbox, image_url). Enables signature verification. Use an open detector (e.g. YOLO fine-tune / layout model) as an n8n branch, toggled per client.

**True semantic search** (client asked explicitly). Already designed via pgvector + bge-m3; upgrade the Search workflow to full natural-language Q&A and "related documents / hidden relations" ranking (embedding neighbourhood + graph expansion).

**Per-user profiles, SSO & personalization.** Auth with SSO (OIDC/SAML); `users`, `user_preferences`, `search_history` tables; search ranking parameterized per profile; the agent tunes each user's search.

**Compliance & usage analytics.** `search_history` + `audit_log` capture queries, most-used documents, active users, **IP addresses**, timestamps; a usage dashboard on top. (Extends the audit_log already in the schema.)

**Bulk ingestion + storage/DB connectors ("connection layer").** A **watch/pull connector** (n8n Schedule/trigger against S3/MinIO/SMB/folder or the client DB) ingests **50–100+ docs at once**; manual upload remains. Bidirectional **webhooks** push structured results back to the client's database/legacy system. Design so the system needs only the client's **file storage + database**.

**External/IoT data on the dashboard.** Generic webhook/API intake (e.g. storage **temperature & humidity**) rendered as dashboard widgets — decoupled ingestion into a `metrics` table.

**"Ask ArchivAI" — conversational RAG chat assistant (prioritized feature).** A real
chatbot the user talks to, not just a search box. Agent D does **not** have this (its search
only returns document lists; a chat assistant was only *requested* by the client) — so it's a
clear win for us.
- **Flow (n8n chat workflow, webhook `/chat`):** embed the question (bge-m3) → retrieve top-k
  chunks from `embeddings` (pgvector) → optional **knowledge-graph expansion** (pull entities +
  co-occurring docs to widen context) → call the open LLM (Qwen2.5) with an **archival-expert
  system prompt** → return a written answer **with inline citations** linking to the source
  documents.
- **Grounded + honest:** answers only from the corpus + extracted entities/inventories; cites
  every claim; says "not found in the archive" when unsupported (no hallucination).
- **Conversational memory:** multi-turn per user; history stored in `chat_sessions` /
  `chat_messages`; respects per-user profile + access rules.
- **Wired into navigation:** clicking a citation opens the document (adds a 4th path alongside
  search→doc, entity→doc, doc-list). Streamed responses in a chat panel in the UI.
- **Open-source only:** same Ollama models; no paid APIs; on-prem friendly.
- Doubles as the **archival-expert assistant** the client asked for (expertise about documents
  and inventories).

**Learning / recommendations.** Periodic n8n job mines `search_history` + usage to surface "popular / trending / recommended" items on the dashboard.

### Revised roadmap (superset)
- **Phase 2 — Core UI** (upload, archive, document detail w/ inline entity edit + verify, per-page & all-pages views, export).
- **Phase 3 — Search + Dashboard** (semantic search; analytics dashboard from single source).
- **Phase 4 — Entities + knowledge graph** (resolution/dedup, graph, CSV, entity→doc / search→doc / doc navigation).
- **Phase 5 — Agentic layer** (natural-language no-code customization; per-user config) — *the flagship*.
- **Phase 6 — Auth/SSO, profiles, personalization, search history & compliance analytics.**
- **Phase 7 — Connectors & integration** (bulk pull from storage/DB, bidirectional webhooks to legacy systems).
- **Phase 8 — Signature/stamp extraction, IoT dashboard widgets, archival-expert RAG assistant, recommendations.**
- **Phase 9 — Hardening & deployment** (on-prem / private-cloud packaging, data residency, handwriting/model tuning, eval set).

### Data-model additions (beyond the built core)
`chat_sessions`, `chat_messages` (RAG assistant history), `user_preferences`, `search_history`,
`document_artifacts` (signatures/stamps), `metrics` (IoT), `config` (per-user/global agent-managed
settings). The built schema already has `users`, `audit_log`, `entities.aliases[]`, `embeddings`
(pgvector), and provenance/confidence fields to grow into these — the chat assistant reuses
`embeddings` directly, so it can be built right after semantic search.
