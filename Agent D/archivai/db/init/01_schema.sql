-- ArchivAI schema. Applied automatically on first Postgres boot.
-- Single source of truth for documents, entities, relationships, embeddings.

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fuzzy / trigram keyword search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------
DO $$ BEGIN
  CREATE TYPE doc_status  AS ENUM ('uploaded','processing','processed','failed','verified');
  CREATE TYPE entity_type AS ENUM ('person','organization','date','place','quantity');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ----------------------------------------------------------------------------
-- Users
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  password_hash TEXT,
  role          TEXT NOT NULL DEFAULT 'reviewer',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Documents
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  filename       TEXT NOT NULL,
  original_url   TEXT,                       -- MinIO object URL of the uploaded file
  status         doc_status NOT NULL DEFAULT 'uploaded',
  page_count     INT NOT NULL DEFAULT 1,

  -- extracted metadata
  document_type  TEXT,                        -- e.g. official_correspondence
  date_text      TEXT,                        -- as written, e.g. '19/II 194г.'
  date_parsed    DATE,                        -- best-effort normalized date
  language       TEXT,                        -- Russian | Kazakh | Mixed
  sender_name    TEXT,
  sender_role    TEXT,
  recipient_name TEXT,
  recipient_role TEXT,
  ai_summary     TEXT,
  full_text      TEXT,

  -- pipeline / provenance
  ocr_backend    TEXT,
  extract_backend TEXT,
  ocr_confidence REAL,                        -- 0..1 average confidence
  process_error  TEXT,

  -- verification
  verified_by    UUID REFERENCES users(id),
  verified_at    TIMESTAMPTZ,

  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_status   ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_type      ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_fulltext  ON documents USING gin (full_text gin_trgm_ops);

-- Per-page images + OCR text (multi-page scans)
--   ocr_text    — reading-order text: what search, embeddings and the LLM consume
--   layout_text — the same page with its physical layout kept (columns, indents),
--                 for display only. Filled from a PDF text layer; NULL for scans.
CREATE TABLE IF NOT EXISTS pages (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_no      INT NOT NULL,
  image_url    TEXT,
  ocr_text     TEXT,
  layout_text  TEXT,
  confidence   REAL,
  UNIQUE (document_id, page_no)
);
-- migration for databases created before layout_text existed
ALTER TABLE pages ADD COLUMN IF NOT EXISTS layout_text TEXT;

-- ----------------------------------------------------------------------------
-- Entities (canonical) + mentions + graph edges
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical_name   TEXT NOT NULL,
  type             entity_type NOT NULL,
  role_description TEXT,
  aliases          TEXT[] NOT NULL DEFAULT '{}',
  document_count   INT NOT NULL DEFAULT 0,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (canonical_name, type)
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities USING gin (canonical_name gin_trgm_ops);

-- One row per (entity appears in document)
CREATE TABLE IF NOT EXISTS entity_mentions (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_id    UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  surface_form TEXT,                          -- exact text as it appeared
  confidence   REAL,
  UNIQUE (entity_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_mentions_doc    ON entity_mentions(document_id);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);

-- Co-occurrence edges (entities sharing a document) for the knowledge graph
CREATE TABLE IF NOT EXISTS entity_edges (
  entity_a  UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  entity_b  UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  weight    INT NOT NULL DEFAULT 1,           -- number of shared documents
  PRIMARY KEY (entity_a, entity_b),
  CHECK (entity_a < entity_b)
);

-- ----------------------------------------------------------------------------
-- Embeddings for semantic search (bge-m3 = 1024 dims)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_no     INT NOT NULL DEFAULT 0,
  content      TEXT,
  embedding    vector(1024),
  UNIQUE (document_id, chunk_no)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_vec
  ON embeddings USING hnsw (embedding vector_cosine_ops);

-- ----------------------------------------------------------------------------
-- Audit + cached dashboard stats (consistent analytics from one source)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor       UUID REFERENCES users(id),
  action      TEXT NOT NULL,                  -- e.g. 'verify_document','edit_entity'
  target_type TEXT,
  target_id   UUID,
  detail      JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dashboard_stats (
  id          INT PRIMARY KEY DEFAULT 1,
  data        JSONB NOT NULL,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (id = 1)
);

-- ----------------------------------------------------------------------------
-- Helpers: keep document_count and updated_at fresh
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_touch ON documents;
CREATE TRIGGER trg_documents_touch BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE OR REPLACE FUNCTION refresh_entity_count() RETURNS trigger AS $$
BEGIN
  UPDATE entities e SET document_count = (
    SELECT count(*) FROM entity_mentions m WHERE m.entity_id = e.id
  ) WHERE e.id = COALESCE(NEW.entity_id, OLD.entity_id);
  RETURN NULL;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mentions_count ON entity_mentions;
CREATE TRIGGER trg_mentions_count AFTER INSERT OR DELETE ON entity_mentions
  FOR EACH ROW EXECUTE FUNCTION refresh_entity_count();

-- Seed a demo user
INSERT INTO users (email, display_name, role)
VALUES ('demo@archivai.local', 'Demo User', 'admin')
ON CONFLICT (email) DO NOTHING;
