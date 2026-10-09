-- Server-side functions so n8n workflows stay thin: one call per stage.
-- NOTE (Phase 5): create_document() and search_documents() moved to
-- 06_preferences.sql — they are config-aware now (their bodies read
-- get_config(), which must be created first).

-- Rebuild the co-occurrence graph from scratch (correct + idempotent; fine at archive scale).
CREATE OR REPLACE FUNCTION rebuild_all_edges() RETURNS void AS $$
BEGIN
  DELETE FROM entity_edges;
  INSERT INTO entity_edges (entity_a, entity_b, weight)
  SELECT LEAST(a.entity_id, b.entity_id) AS ea,
         GREATEST(a.entity_id, b.entity_id) AS eb,
         count(*) AS w
  FROM entity_mentions a
  JOIN entity_mentions b
    ON a.document_id = b.document_id AND a.entity_id < b.entity_id
  GROUP BY ea, eb;
END; $$ LANGUAGE plpgsql;

-- Apply an extraction payload to a document: update fields, store per-page OCR,
-- upsert entities + mentions.
-- payload = { document_type, date_text, language, sender:{name,role}, recipient:{name,role},
--             summary, full_text, confidence, ocr_backend, extract_backend,
--             entities:[{name,type,role,surface_form}],
--             pages:[{page_no,image_url,ocr_text,layout_text,confidence}] }
-- ocr_text = reading-order text (search, embeddings, LLM input);
-- layout_text = the same page with its physical layout preserved (columns,
-- indentation) for display — only PDFs with a text layer carry it.
CREATE OR REPLACE FUNCTION ingest_extraction(p_doc UUID, payload JSONB)
RETURNS void AS $$
DECLARE
  ent JSONB;
  pg_item JSONB;
  v_entity_id UUID;
  v_type entity_type;
BEGIN
  UPDATE documents SET
    document_type   = payload->>'document_type',
    date_text       = payload->>'date_text',
    language        = payload->>'language',
    sender_name     = payload#>>'{sender,name}',
    sender_role     = payload#>>'{sender,role}',
    recipient_name  = payload#>>'{recipient,name}',
    recipient_role  = payload#>>'{recipient,role}',
    ai_summary      = payload->>'summary',
    full_text       = payload->>'full_text',
    ocr_confidence  = NULLIF(payload->>'confidence','')::real,
    ocr_backend     = payload->>'ocr_backend',
    extract_backend = payload->>'extract_backend',
    status          = 'processed'
  WHERE id = p_doc;

  -- Replace this document's pages (idempotent on reprocess)
  DELETE FROM pages WHERE document_id = p_doc;
  FOR pg_item IN SELECT * FROM jsonb_array_elements(COALESCE(payload->'pages','[]'::jsonb))
  LOOP
    INSERT INTO pages (document_id, page_no, image_url, ocr_text, layout_text, confidence)
    VALUES (p_doc,
            COALESCE(NULLIF(pg_item->>'page_no','')::int, 1),
            pg_item->>'image_url',
            pg_item->>'ocr_text',
            pg_item->>'layout_text',
            NULLIF(pg_item->>'confidence','')::real)
    ON CONFLICT (document_id, page_no) DO UPDATE
      SET image_url   = EXCLUDED.image_url,
          ocr_text    = EXCLUDED.ocr_text,
          layout_text = EXCLUDED.layout_text,
          confidence  = EXCLUDED.confidence;
  END LOOP;

  -- Drop stale chunk vectors: the new run may produce fewer chunks than the old
  -- one, and upsert_embedding() alone would leave the extras behind. n8n stores
  -- the fresh vectors right after this function returns.
  DELETE FROM embeddings WHERE document_id = p_doc;

  -- Replace this document's mentions (idempotent on reprocess)
  DELETE FROM entity_mentions WHERE document_id = p_doc;

  FOR ent IN SELECT * FROM jsonb_array_elements(COALESCE(payload->'entities','[]'::jsonb))
  LOOP
    CONTINUE WHEN (ent->>'name') IS NULL OR trim(ent->>'name') = '';
    BEGIN
      v_type := (ent->>'type')::entity_type;
    EXCEPTION WHEN invalid_text_representation THEN
      CONTINUE;  -- skip unknown types
    END;

    INSERT INTO entities (canonical_name, type, role_description)
    VALUES (trim(ent->>'name'), v_type, ent->>'role')
    ON CONFLICT (canonical_name, type)
      DO UPDATE SET role_description = COALESCE(entities.role_description, EXCLUDED.role_description)
    RETURNING id INTO v_entity_id;

    INSERT INTO entity_mentions (entity_id, document_id, surface_form, confidence)
    VALUES (v_entity_id, p_doc, COALESCE(ent->>'surface_form', ent->>'name'),
            NULLIF(payload->>'confidence','')::real)
    ON CONFLICT (entity_id, document_id) DO NOTHING;
  END LOOP;

  PERFORM rebuild_all_edges();
END; $$ LANGUAGE plpgsql;

-- Store one embedding chunk.
CREATE OR REPLACE FUNCTION upsert_embedding(p_doc UUID, p_chunk INT, p_content TEXT, p_vec vector)
RETURNS void AS $$
BEGIN
  INSERT INTO embeddings (document_id, chunk_no, content, embedding)
  VALUES (p_doc, p_chunk, p_content, p_vec)
  ON CONFLICT (document_id, chunk_no)
    DO UPDATE SET content = EXCLUDED.content, embedding = EXCLUDED.embedding;
END; $$ LANGUAGE plpgsql;

-- Mark a document as failed (pipeline error branch) with the reason preserved.
CREATE OR REPLACE FUNCTION mark_failed(p_doc UUID, p_error TEXT)
RETURNS void AS $$
BEGIN
  UPDATE documents
  SET status = 'failed',
      process_error = left(COALESCE(NULLIF(trim(p_error), ''), 'unknown error'), 2000)
  WHERE id = p_doc;
END; $$ LANGUAGE plpgsql;

-- Mark a document human-verified.
CREATE OR REPLACE FUNCTION mark_verified(p_doc UUID, p_user UUID)
RETURNS void AS $$
BEGIN
  UPDATE documents SET status='verified', verified_by=p_user, verified_at=now()
  WHERE id = p_doc;
  INSERT INTO audit_log (actor, action, target_type, target_id)
  VALUES (p_user, 'verify_document', 'document', p_doc);
END; $$ LANGUAGE plpgsql;

-- Compute dashboard stats from a single source and cache them (consistent numbers).
-- Top lists carry up to 10 entries; the dashboard slices to the per-user top_n.
CREATE OR REPLACE FUNCTION compute_dashboard_stats() RETURNS JSONB AS $$
DECLARE result JSONB;
BEGIN
  SELECT jsonb_build_object(
    'documents_processed', (SELECT count(*) FROM documents WHERE status IN ('processed','verified')),
    'people_identified',   (SELECT count(*) FROM entities WHERE type='person'),
    'organizations',       (SELECT count(*) FROM entities WHERE type='organization'),
    'total_entities',      (SELECT count(*) FROM entities),
    'entity_distribution', (SELECT jsonb_object_agg(type::text, c) FROM
                             (SELECT type, count(*) c FROM entities GROUP BY type) s),
    'language_distribution',(SELECT jsonb_object_agg(COALESCE(language,'Unknown'), c) FROM
                             (SELECT language, count(*) c FROM documents GROUP BY language) s),
    'top_people', (SELECT jsonb_agg(x) FROM
        (SELECT canonical_name AS name, document_count AS docs FROM entities
         WHERE type='person' ORDER BY document_count DESC, canonical_name LIMIT 10) x),
    'top_organizations', (SELECT jsonb_agg(x) FROM
        (SELECT canonical_name AS name, document_count AS docs FROM entities
         WHERE type='organization' ORDER BY document_count DESC, canonical_name LIMIT 10) x),
    'recent_activity', (SELECT jsonb_agg(x) FROM
        (SELECT d.id, d.filename, d.date_text,
                (SELECT count(*) FROM entity_mentions m WHERE m.document_id=d.id) AS entities
         FROM documents d ORDER BY d.created_at DESC LIMIT 5) x),
    'timeline', (SELECT jsonb_agg(x) FROM
        (SELECT d.id, d.filename, d.date_text, d.date_parsed, d.document_type
         FROM documents d
         WHERE d.date_text IS NOT NULL OR d.date_parsed IS NOT NULL
         ORDER BY d.date_parsed NULLS LAST, d.created_at
         LIMIT 50) x)
  ) INTO result;

  INSERT INTO dashboard_stats (id, data, computed_at) VALUES (1, result, now())
  ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data, computed_at=now();
  RETURN result;
END; $$ LANGUAGE plpgsql;
