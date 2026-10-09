-- Phase 7 — connectors: bulk pull (dedup) + outbox push to legacy systems.
-- Spec: docs/PHASE7_CONNECTORS.md. The client side needs only file storage + DB.

-- ----------------------------------------------------------------------------
-- Pull: given the listed source files, return only the ones not yet ingested
-- (dedup by documents.original_url). Caps one run at 100 files.
-- Input:  [{key, url, size}]
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION connector_filter_new(p_files JSONB) RETURNS JSONB AS $$
  SELECT COALESCE(jsonb_agg(s.f), '[]'::jsonb) FROM (
    SELECT f FROM jsonb_array_elements(COALESCE(p_files, '[]'::jsonb)) AS f
    WHERE COALESCE(f->>'url', '') <> ''
      AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.original_url = f->>'url')
    LIMIT 100) s;
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- Push: full structured document JSON for the client's legacy system.
-- Built at SEND time (outbox_take), so it reflects human edits/verification.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION document_payload(p_doc UUID) RETURNS JSONB AS $$
  SELECT jsonb_build_object(
    'source', 'archivai',
    'document_id', d.id,
    'filename', d.filename,
    'original_url', d.original_url,
    'status', d.status,
    'verified', d.status = 'verified',
    'document_type', d.document_type,
    'date_text', d.date_text,
    'date_parsed', d.date_parsed,
    'language', d.language,
    'sender', jsonb_build_object('name', d.sender_name, 'role', d.sender_role),
    'recipient', jsonb_build_object('name', d.recipient_name, 'role', d.recipient_role),
    'summary', d.ai_summary,
    'full_text', d.full_text,
    'confidence', d.ocr_confidence,
    'entities', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                   'name', e.canonical_name, 'type', e.type,
                   'role', e.role_description, 'aliases', e.aliases))
                 FROM entity_mentions m JOIN entities e ON e.id = m.entity_id
                 WHERE m.document_id = d.id), '[]'::jsonb),
    'pages', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                   'page_no', p.page_no, 'image_url', p.image_url)
                   ORDER BY p.page_no)
                 FROM pages p WHERE p.document_id = d.id), '[]'::jsonb),
    'pushed_at', now())
  FROM documents d WHERE d.id = p_doc;
$$ LANGUAGE sql STABLE;

-- Outbox: retry-safe queue of processed documents to push.
CREATE TABLE IF NOT EXISTS connector_outbox (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  status      TEXT NOT NULL DEFAULT 'pending',   -- pending|sending|sent|failed
  attempts    INT  NOT NULL DEFAULT 0,
  last_error  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON connector_outbox(status, created_at);

-- Enqueue whenever a document finishes processing (incl. reprocess runs).
CREATE OR REPLACE FUNCTION trg_outbox_enqueue() RETURNS trigger AS $$
BEGIN
  IF NEW.status = 'processed' AND OLD.status IS DISTINCT FROM 'processed' THEN
    INSERT INTO connector_outbox (document_id) VALUES (NEW.id);
  END IF;
  RETURN NULL;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_outbox ON documents;
CREATE TRIGGER trg_documents_outbox AFTER UPDATE OF status ON documents
  FOR EACH ROW EXECUTE FUNCTION trg_outbox_enqueue();

-- Take a batch for delivery: marks 'sending', bumps attempts, returns fresh
-- payloads. Also reclaims 'sending' rows stuck for >10 min (crashed run).
CREATE OR REPLACE FUNCTION outbox_take(p_batch INT DEFAULT 10)
RETURNS TABLE (id UUID, document_id UUID, payload JSONB) AS $$
  UPDATE connector_outbox o
  SET status = 'sending', attempts = o.attempts + 1
  WHERE o.id IN (
    SELECT b.id FROM connector_outbox b
    WHERE b.status = 'pending'
       OR (b.status = 'sending' AND now() - b.created_at > interval '10 minutes')
    ORDER BY b.created_at
    LIMIT GREATEST(COALESCE(p_batch, 10), 1)
    FOR UPDATE SKIP LOCKED)
  RETURNING o.id, o.document_id, document_payload(o.document_id);
$$ LANGUAGE sql;

-- Delivery result: sent, or retry (attempts < 5) / failed with the reason.
CREATE OR REPLACE FUNCTION outbox_mark(p_id UUID, p_ok BOOLEAN, p_detail TEXT)
RETURNS VOID AS $$
BEGIN
  IF p_ok THEN
    UPDATE connector_outbox SET status = 'sent', sent_at = now(), last_error = NULL
    WHERE id = p_id;
  ELSE
    UPDATE connector_outbox
    SET status = CASE WHEN attempts >= 5 THEN 'failed' ELSE 'pending' END,
        last_error = left(COALESCE(p_detail, 'unknown error'), 500)
    WHERE id = p_id;
  END IF;
END; $$ LANGUAGE plpgsql;

-- Demo "legacy system" sink: audit-log every received push (E2E-provable loop).
CREATE OR REPLACE FUNCTION log_client_push(p_payload JSONB) RETURNS VOID AS $$
BEGIN
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (NULL, 'client_push_received', 'connector',
          NULLIF(p_payload->>'document_id', '')::uuid, p_payload);
END; $$ LANGUAGE plpgsql;
