# Architecture

## Components

| Component | Tech | Role |
|---|---|---|
| Orchestration | **n8n** | Runs every pipeline stage as a workflow; the automation core |
| AI service | **FastAPI** (`services/ai`) | Stateless OCR + extraction + embeddings over open-source models |
| Model server | **Ollama** (Qwen2.5-VL, Qwen2.5, bge-m3) | Serves the open models locally; no external APIs |
| Database | **Postgres + pgvector** | Single source of truth + vector search |
| Object storage | **MinIO** (S3-compatible) | Original scans + page images |
| Web app | **Next.js** (`web`) | UI (built out in later phases) |

## Data flow (core pipeline)

```
Upload ─▶ MinIO (store scan)
   │        └─ PDF? ─▶ AI /pdf/split (poppler) ─▶ page images stored in MinIO
   │                   (digital PDFs also hand over their text layer → no OCR)
   ▼  POST /webhook/ingest
 n8n ──▶ create_document()                → documents row (status=processing)
   │
   ├──▶ AI /process  (Ollama vision-LLM)  → full_text + structured extraction
   │
   ├──▶ ingest_extraction()               → update document, upsert entities +
   │                                         mentions, rebuild graph edges
   │
   ├──▶ AI /embed    (bge-m3)             → 1024-dim vector
   ├──▶ upsert_embedding()                → embeddings (pgvector, HNSW index)
   └──▶ compute_dashboard_stats()         → cached, consistent analytics
```

Search: `POST /webhook/search` → embed query → `search_documents()` (0.7·cosine + 0.3·trigram) → ranked docs.

## Design decisions

- **Functions over fat workflows.** DB mutations are Postgres functions (`create_document`,
  `ingest_extraction`, `upsert_embedding`, `search_documents`, `compute_dashboard_stats`,
  `mark_verified`, `mark_failed`, `rag_retrieve`, `log_chat_turn`). n8n calls one function
  per stage → workflows are readable and portable across n8n versions.
- **Stateless AI service.** It never touches the DB; n8n owns persistence. This lets you
  swap OCR/LLM backends (`OCR_BACKEND`, `EXTRACT_BACKEND`) or scale the service independently.
- **Documents are embedded in chunks, not whole.** A single vector per file averages
  a 12-page document into something that matches no specific query, and the trigram
  half of the score approaches zero as the text grows — long documents effectively
  disappeared from search. `chunking.py` cuts on page boundaries (splitting long pages
  with an overlap, merging tiny ones) and n8n stores one `embeddings` row per chunk.
  `search_documents` already ranked by `MIN(distance)` per document and `rag_retrieve`
  already returned chunks, so both got better without changing their SQL.
- **Text extraction picks its own mode.** Some templates draw an unfilled layer under
  the real text; poppler's block analysis shreds those pages into 10-character fragments,
  while drawing order (`-raw`) keeps lines whole. Both are extracted per page and the one
  with longer lines wins (`PDF_TEXT_AUTO_RAW`, `PDF_RAW_MARGIN`) — no per-file tuning.
- **Two text variants per page.** `pages.ocr_text` is reading-order text — what search,
  embeddings and the models consume. `pages.layout_text` is the same page with its
  columns and indentation kept as spaces, for display only (the viewer has a "keep page
  layout" switch, monospace + horizontal scroll). Only PDFs with a text layer produce it;
  scans have `NULL` and the viewer falls back to the OCR text.
- **Long documents are clipped, not silently truncated.** Overflowing a model's context
  window returns empty fields, not an error — that is how a 12-page PDF ends up with no
  summary. The extraction prompt is cut to `EXTRACT_MAX_CHARS` (head + tail, where
  type/sender/date/signature live) and the cut is logged; documents longer than
  `VISION_ONESHOT_MAX_PAGES` skip the one-shot vision call and are OCR'd page by page,
  which also gives real per-page text.
- **PDFs become pages as early as possible.** `/pdf/split` renders one image per page and
  the web app stores those images, so ingest, the pages table, the viewer and reprocessing
  all keep working on "one image per page" — nothing downstream knows about PDFs.
  A digital PDF's text layer travels with the page and replaces OCR for it
  (exact text, no model call); scanned PDFs have none and fall back to OCR.
  The AI service also expands a raw `.pdf` URL it is handed directly, so no caller
  can break by not knowing about the split step.
- **Stub mode.** `AI_STUB=1` returns deterministic output so the whole pipeline can be tested
  without models — cheap CI and fast onboarding. Its embeddings are hash vectors, not
  semantics (cosine ≈0.07 between any pair), so nothing can clear the search relevance
  floor `search.min_score`; the smoke test drops the floor for its search asserts and
  restores it. Relevance quality is only meaningful with real models.
- **Consistent analytics.** Dashboard numbers come from one `compute_dashboard_stats()` query
  (fixes the count mismatches visible in Agent D's demo).
- **Deployment-agnostic.** Everything is in one `docker-compose.yml`; runs identically on a
  laptop or a VPS. GPU is optional (uncomment the Ollama `deploy` block) but strongly advised
  for the vision model.

## Model choices for 20th-century Kazakh & Russian

- **Primary:** `qwen2.5vl` — open vision-LLM; one-pass OCR + extraction; robust on handwriting
  and mixed Cyrillic/Latin-Kazakh scripts.
- **Fallback OCR:** Tesseract (`rus+kaz`) for clean typed pages / GPU-less hosts; optional
  Surya hook for layout-aware OCR.
- **Embeddings:** `bge-m3` — multilingual, 1024-dim, good for Russian/Kazakh semantic search.
- **Extraction (text mode):** `qwen2.5:7b-instruct` when OCR is run separately.

All are swappable via `.env` without code changes.
