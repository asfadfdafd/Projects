# Kickoff prompt — paste into the new chat

I'm working in the "Agent D" folder. This project (**ArchivAI**) is an open-source,
self-hostable competitor to a product called "Agent D" — an AI archive that turns scanned
20th-century Kazakh/Russian documents (typed + handwritten) into a searchable, entity-linked,
human-verifiable collection. **n8n is the orchestration core**; a thin Next.js web app sits on top.

**Before doing anything, read these files in the folder to load full context:**
1. `HANDOFF-for-Fable5.md` — the master brief (goal, decisions, current state, next steps, file map). Start here.
2. `Agent-D_Demo-Analysis.md` — what the original does (screens + transcript §6).
3. `Agent-D-Alternative_Build-Plan.md` — how we compete (§9 locked decisions, §10 expanded scope).
4. `archivai/docs/ARCHITECTURE.md`, `DATA_MODEL.md`, `ROADMAP.md`, `CHAT_ASSISTANT.md`, and the `archivai/` code.

**Locked decisions (do not re-litigate):** open-source models only (Qwen2.5-VL + Tesseract rus+kaz
fallback + bge-m3, via Ollama; no paid APIs); stack = n8n · FastAPI AI service · Postgres+pgvector ·
MinIO · Next.js+Tailwind; deployment-agnostic (one docker-compose); DB writes live in Postgres
functions so n8n workflows stay thin; the AI service is stateless; `AI_STUB=1` gives an offline
dry-run.

**Already built (Phases 0–1 + chat backend):** docker-compose, DB schema + functions, AI service
(`/process`, `/ocr`, `/embed`, `/answer`), and n8n workflows `1_ingest_and_process`, `2_search`,
`3_chat` (RAG assistant with citations). All validated in stub mode. **Not built:** the entire web
UI, plus the features in Build Plan §10.

**Your first tasks, in order:**
1. Stand up the stack in **stub mode** and smoke-test the pipeline end-to-end (ingest → verify DB
   rows in documents/entities/mentions/edges/embeddings → search → chat). Report anything broken
   and fix it. Then confirm the switch to real models is documented.
2. Build **Phase 2 — the web UI** in `archivai/web/` (Next.js + Tailwind): Upload → Document
   Archive → Document Detail (scan viewer, per-page + all-pages, inline entity editing, Mark as
   Verified). API contracts are already fixed by the DB functions + n8n webhooks.
3. Then Phase 3 (semantic search UI + dashboard), **Phase 3b chat panel** (wire citations to open
   the source doc), Phase 4 (entity resolution + knowledge graph), Phase 5 (the agentic no-code
   layer — the flagship). Follow `archivai/docs/ROADMAP.md`.

**Working rules:** keep the n8n-thin / Postgres-function pattern; keep everything open-source and
on-prem-friendly; use a task list; verify each step (JSON validity, compiles, stub run,
screenshots of the UI); ask me before any change that departs from the locked decisions or scope.
Don't rebuild what's already in `archivai/` — extend it.

Start by reading `HANDOFF-for-Fable5.md`, then propose a short plan for task 1 and go.
