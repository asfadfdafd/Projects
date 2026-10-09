# Data model

Postgres schema in `db/init/01_schema.sql`; functions in `02_functions.sql`.

## Tables

- **users** — accounts (seeded with `demo@archivai.local`).
- **documents** — one row per document: filename, `original_url`, `status`
  (`uploaded→processing→processed→verified`, or `failed`), page_count, and extracted
  metadata: `document_type`, `date_text`/`date_parsed`, `language`, sender/recipient
  (name+role), `ai_summary`, `full_text`, provenance (`ocr_backend`, `extract_backend`,
  `ocr_confidence`), and verification (`verified_by`, `verified_at`).
- **pages** — per-page `image_url` + `ocr_text` + `layout_text` + `confidence` (multi-page
  scans and PDFs); written by `ingest_extraction()` from the payload's `pages[]` (drives the
  per-page view in Document Detail). `ocr_text` is reading order (search, embeddings, LLM
  input); `layout_text` is the same page with columns/indentation preserved, for display
  only — filled from a PDF text layer, `NULL` for scans.
- **entities** — canonical entity: `canonical_name`, `type`
  (person/organization/date/place/quantity), `role_description`, `aliases[]`,
  `document_count` (auto-maintained by trigger). Unique on (name, type).
- **entity_mentions** — links an entity to a document (`surface_form`, `confidence`).
  Unique on (entity, document). Drives counts, graph edges, and "documents per entity".
- **entity_edges** — co-occurrence graph (entity_a < entity_b, `weight` = shared docs).
- **embeddings** — `vector(1024)` per document chunk; HNSW cosine index for semantic search.
  Ingest writes one row per chunk (`chunk_no` 0..N, page-sized — see `services/ai/app/chunking.py`);
  `ingest_extraction()` clears the document's old rows first, so reprocessing never leaves
  stale chunks. Search ranks documents by their best chunk, chat cites the chunk itself.
- **audit_log** — who did what (verification, entity edits, every config change with
  its old→new values).
- **dashboard_stats** — single cached JSON blob of analytics (one source → consistent numbers).
- **user_preferences** (Phase 5) — agent-managed configuration: one JSONB row per
  (scope, key); `user_id NULL` = global scope. Keys: `search` (hybrid-search weights,
  limit, snippet source), `dashboard` (visible widgets + order, top-N), `taxonomy`
  (document types, global), `chat` (retrieve_k, answer style). Effective value =
  defaults ⊕ global ⊕ user. Writes only via `set_config()`, which validates against
  the `agent_capabilities()` manifest; `reset_config()` restores defaults.
  `chat_sessions.kind` (`'rag'`|`'agent'`) separates assistant and agent conversations.

## Entity categories

`person · organization · date · place · quantity` — mirrors what Agent D surfaces, and
matches the AI service extraction schema (`services/ai/app/schemas.py`).

## Provenance & confidence (improvement over Agent D)

Every document records which OCR/extract backend produced it and an average confidence,
and every mention carries a confidence — enabling review queues, quality filtering, and
reproducibility that the original demo lacked.

## Entity resolution (Phase 4 — built)

`db/init/05_resolution.sql`: `norm_name()` (lowercase, ё→е, punctuation-stripped),
`merge_entities(keep, drop)` (mention repointing, alias union, orphan cleanup) and
`resolve_entities()` — pass 1 merges same-type entities with identical normalized names;
pass 2 merges a person/org whose token set is contained in **exactly one** larger
same-type entity (e.g. "Абай" → "Абай Кунанбаев"; ambiguous containment is skipped).
Old names fold into `aliases`, every run is audit-logged, edges are rebuilt — directly
fixing the dedup gaps seen in the Agent D demo. Triggered via n8n `POST /webhook/resolve`
or the Entities page. Extension hook: embedding-similarity merging for spellings that
don't overlap textually ("КазФилиал АН СССР" vs "Каз. Филиал Академии Наук СССР").
