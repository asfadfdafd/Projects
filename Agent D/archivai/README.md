# ArchivAI

An open-source, self-hostable **AI document archive** for historical scanned documents — a competing alternative to *Agent D*. Upload scanned archival pages or multi-page **PDFs** (handwritten or typed, 20th-century **Kazakh & Russian**, mixed scripts) and get OCR'd text, a document classification, sender/recipient, an AI summary, categorized entities (people, organizations, dates, places, quantities), a knowledge graph, semantic search, and a human-verification workflow.

**n8n is the orchestration core.** Every processing stage is an n8n workflow, so OCR/LLM models are swappable and the whole pipeline is visible, re-runnable, and extensible without rewriting the app.

> This repository is the **foundation + core pipeline** (architecture, infra, database, AI service, ingestion & processing workflows). UI, search, dashboard, entity-resolution and graph are layered on top in later phases — see `docs/ROADMAP.md`.

---

## Architecture

```
  Browser ──▶ Web App (Next.js)  ──DB reads──▶  Postgres + pgvector  ◀──▶  n8n (workflows)
                    │                                   ▲                        │
                    └──── webhooks (upload/search/verify)│                        ▼
                                                         │              AI Service (FastAPI)
                                        MinIO (scans) ◀──┘              OCR + LLM extraction
                                                                       (open-source models)
```

- **n8n** — runs the pipeline: ingest → OCR → extract → persist → embed → resolve → aggregate.
- **AI Service** (`services/ai`) — FastAPI microservice wrapping **open-source** OCR + LLM extraction tuned for historical Kazakh/Russian. Model backend is swappable (Qwen2.5-VL vision-LLM by default; Tesseract/Surya fallback).
- **Postgres + pgvector** — single source of truth (documents, entities, mentions, edges, embeddings).
- **MinIO** — S3-compatible object storage for original scans/PDFs and page images.
- **PDF ingest** — a PDF is rendered to one image per page (poppler, `AI /pdf/split`) before
  ingest, so it becomes an ordinary multi-page document. Digital PDFs reuse their own text
  layer instead of OCR (exact text, no model call); scanned PDFs go through OCR as usual.
  Each page keeps two text variants: reading order for search/AI, and a layout-preserving
  one (columns, indentation) shown behind the viewer's "keep page layout" switch.
- **Web app** (`web`) — Next.js UI (scaffolded; built out in later phases).

Deployment-agnostic: one `docker-compose.yml` runs locally or on any VPS/cloud host.

See `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` for detail.

---

## Why open-source models for 20th-century Kazakh & Russian

Historical Central-Asian documents are hard: mixed Cyrillic Russian, Cyrillic Kazakh, and pre-1940 **Latin-script Kazakh** (Jañalıp) can appear on the same page, plus handwriting, stamps, and aged paper. The AI service therefore defaults to an **open vision-language model (Qwen2.5-VL)** that does OCR + structured extraction in one pass and handles mixed scripts and handwriting far better than classic OCR. Deterministic fallbacks (**Tesseract** `rus`+`kaz`, **Surya OCR**) are available as an n8n branch for typed pages or GPU-less hosts. All models run locally via **Ollama/vLLM** — no paid API, no data leaving the host.

---

## Quick start

```bash
cp .env.example .env          # set secrets (starts in stub mode: AI_STUB=1)
make smoke                    # boot + headless n8n setup + full E2E smoke test
```

`make smoke` boots the stack (no models needed), imports the Postgres credential and
all workflows into n8n, activates them, then asserts the whole pipeline: ingest →
documents/pages/entities/edges/embeddings/stats → search → chat with citations →
⭐ configuration agent (NL → validated config writes → changed behavior) →
failure path. When it's green, switch to the real open-source models (~12GB disk):

```bash
# Linux server (bundled Ollama container):
# in .env: AI_STUB=0
make up && make models        # starts Ollama + pulls qwen2.5vl, qwen2.5, bge-m3
docker compose up -d --force-recreate ai-service

# macOS (recommended): run Ollama NATIVELY — Docker on a Mac has no GPU access,
# native Ollama uses Apple Metal and is far faster:
brew install ollama
ollama pull qwen2.5vl:7b && ollama pull qwen2.5:7b-instruct && ollama pull bge-m3
# in .env: AI_STUB=0  and  LLM_ENDPOINT=http://host.docker.internal:11434
docker compose up -d --force-recreate ai-service      # ollama container not needed
```

Tight on disk? Swap in `qwen2.5vl:3b` / `qwen2.5:3b` (~6GB total, weaker on
handwriting) via `VISION_MODEL` / `TEXT_MODEL` in `.env`.

Manual setup and the webhook API are documented in `n8n/README.md`. A static
contract check that needs no Docker: `python3 scripts/simulate_stub_pipeline.py`.

---

## Repository layout

```
archivai/
  docker-compose.yml          # all services
  .env.example                # config + model backend selection
  Makefile                    # up/down/db-init/n8n-import/test
  db/init/                    # Postgres schema + pgvector (auto-applied)
  services/ai/                # FastAPI OCR + extraction microservice (core)
  n8n/workflows/              # importable pipeline workflows
  web/                        # Next.js app scaffold (later phases)
  docs/                       # architecture, data model, roadmap
  samples/                    # place test scans here
```

## Status

Implemented: **Phases 0–5** — scaffold/infra, core pipeline, full web UI (upload/archive/
detail with inline entity editing + verification), semantic search + dashboard, the
⭐ **"Ask ArchivAI" RAG chat assistant** (grounded, cited — a feature Agent D lacks;
`docs/CHAT_ASSISTANT.md`), entity resolution + knowledge graph + CSV export, and the
⭐ **agentic layer**: reconfigure search weights, dashboard widgets, the document-type
taxonomy and chat behavior in natural language — an LLM emits actions, Postgres
validates and applies them per user, audit-logged and resettable (`docs/AGENT_LAYER.md`).
Remaining phases (auth/SSO, connectors, signature/stamp, IoT, hardening): `docs/ROADMAP.md`.
