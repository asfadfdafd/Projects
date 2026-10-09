-- Phase 5.5 — the agent as OPERATOR + custom dashboard widgets.
-- Same security model as 06: the LLM picks tools/templates + params; every
-- execution path and every SQL statement lives here, validated and audit-logged.
-- Spec: docs/AGENT_LAYER.md §10.

-- ----------------------------------------------------------------------------
-- Tool registry — single source for the LLM prompt AND agent_run() validation.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agent_tools() RETURNS JSONB AS $$
  SELECT jsonb_build_object(
    'resolve_entities', jsonb_build_object(
      'description', 'слить дубликаты сущностей (алиасы сохраняются, граф пересобирается)',
      'params', '{}'::jsonb),
    'recompute_stats', jsonb_build_object(
      'description', 'пересчитать статистику дашборда',
      'params', '{}'::jsonb),
    'reprocess_documents', jsonb_build_object(
      'description', 'повторно прогнать документы через пайплайн (например, после изменения таксономии). Verified-документы по умолчанию НЕ трогаются — только при явном status=verified',
      'params', jsonb_build_object(
        'document_type', 'фильтр по типу (слаг), опционально',
        'status', 'processed|verified|failed, опционально',
        'limit', 'сколько документов, 1..20 (по умолчанию 5, новые первыми)')),
    'open_search', jsonb_build_object(
      'description', 'открыть страницу поиска с готовым запросом (выполняется в UI)',
      'params', jsonb_build_object('query', 'поисковый запрос, 2..200 символов'))
  );
$$ LANGUAGE sql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- agent_run — execute the agent's commands. Per-command atomicity + audit.
-- reprocess_documents does not run the pipeline itself: it marks nothing and
-- returns the candidate payloads; the n8n workflow fans them back into
-- /webhook/ingest (async), keeping heavy work out of this transaction.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agent_run(p_user UUID, p_commands JSONB,
                                     p_actor TEXT DEFAULT 'agent')
RETURNS JSONB AS $$
DECLARE
  cmd    JSONB;
  res    JSONB := '[]'::jsonb;
  v_tool TEXT;
  prm    JSONB;
  spec   JSONB;
  r      JSONB;
  docs   JSONB;
  lim    INT;
  dt     TEXT;
  st     TEXT;
  q      TEXT;
BEGIN
  IF p_commands IS NULL OR jsonb_typeof(p_commands) <> 'array' THEN
    RETURN '[]'::jsonb;
  END IF;
  FOR cmd IN SELECT * FROM jsonb_array_elements(p_commands) LOOP
    v_tool := cmd->>'tool';
    prm    := COALESCE(cmd->'params', '{}'::jsonb);
    BEGIN
      spec := agent_tools() -> v_tool;
      IF spec IS NULL THEN
        RAISE EXCEPTION 'unknown tool "%" (allowed: resolve_entities, recompute_stats, reprocess_documents, open_search)',
          COALESCE(v_tool, '?');
      END IF;

      IF v_tool = 'resolve_entities' THEN
        r := resolve_entities();
        r := jsonb_build_object('merged', r->'merged');

      ELSIF v_tool = 'recompute_stats' THEN
        r := jsonb_build_object('documents_processed',
                                compute_dashboard_stats()->'documents_processed');

      ELSIF v_tool = 'open_search' THEN
        q := trim(COALESCE(prm->>'query', ''));
        IF length(q) < 2 THEN
          RAISE EXCEPTION 'open_search needs a query of 2..200 chars';
        END IF;
        r := jsonb_build_object('query', left(q, 200));

      ELSIF v_tool = 'reprocess_documents' THEN
        -- Phase 6: reprocessing rewrites shared data — admin only (NULL = internal)
        IF NOT is_admin(p_user) THEN
          RAISE EXCEPTION 'only an admin can reprocess documents';
        END IF;
        lim := LEAST(GREATEST(COALESCE((prm->>'limit')::int, 5), 1), 20);
        dt  := prm->>'document_type';
        st  := prm->>'status';
        SELECT COALESCE(jsonb_agg(jsonb_build_object(
                 'doc_id', d.id, 'filename', d.filename, 'original_url', d.original_url,
                 'pages', COALESCE(NULLIF(
                   (SELECT jsonb_agg(jsonb_build_object('image_url', pg.image_url,
                                                        'page_no', pg.page_no)
                                     ORDER BY pg.page_no)
                    FROM pages pg WHERE pg.document_id = d.id), 'null'::jsonb),
                   CASE WHEN d.original_url IS NOT NULL
                        THEN jsonb_build_array(jsonb_build_object('image_url', d.original_url,
                                                                  'page_no', 1))
                        ELSE '[]'::jsonb END))), '[]'::jsonb)
        INTO docs
        FROM (SELECT * FROM documents d0
              -- human-verified docs are protected: reprocess touches them only on
              -- an EXPLICIT status='verified' request, never by default
              WHERE (CASE WHEN st IS NULL THEN d0.status IN ('processed', 'failed')
                          ELSE d0.status::text = st
                            AND d0.status IN ('processed', 'verified', 'failed') END)
                AND (dt IS NULL OR d0.document_type = dt)
              ORDER BY d0.created_at DESC
              LIMIT lim) d;
        r := jsonb_build_object('count', jsonb_array_length(docs), 'documents', docs);
      END IF;

      res := res || jsonb_build_array(jsonb_build_object(
               'tool', v_tool, 'ok', true, 'result', r));
      INSERT INTO audit_log (actor, action, target_type, detail)
      VALUES (p_user, 'agent_run', 'tool',
              jsonb_build_object('tool', v_tool, 'params', prm, 'via', p_actor));
    EXCEPTION WHEN OTHERS THEN
      res := res || jsonb_build_array(jsonb_build_object(
               'tool', COALESCE(v_tool, '?'), 'ok', false, 'error', SQLERRM));
    END;
  END LOOP;
  RETURN res;
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- widget_data — compute data for every agent-built widget spec. Parameterized
-- queries are ours; specs were already validated by set_config('widget_specs').
-- Per-widget errors are reported inline, never thrown.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION widget_data(p_user UUID) RETURNS JSONB AS $$
DECLARE
  w    JSONB;
  wout JSONB := '[]'::jsonb;
  d    JSONB;
  tpl  TEXT;
  prm  JSONB;
  gb   TEXT;
  gran TEXT;
  et   TEXT;
  lim  INT;
  dt   TEXT;
  st   TEXT;
  lang TEXT;
BEGIN
  FOR w IN SELECT * FROM jsonb_array_elements(
             COALESCE(get_config(p_user, 'custom_widgets')->'widgets', '[]'::jsonb)) LOOP
    tpl := w->>'template';
    prm := COALESCE(w->'params', '{}'::jsonb);
    BEGIN
      IF tpl = 'doc_count' THEN
        gb := COALESCE(prm->>'group_by', 'document_type');
        SELECT COALESCE(jsonb_agg(jsonb_build_object('label', k, 'n', c) ORDER BY c DESC),
                        '[]'::jsonb) INTO d
        FROM (SELECT COALESCE(CASE WHEN gb = 'language' THEN language
                                   WHEN gb = 'status'   THEN status::text
                                   ELSE document_type END, '—') AS k, count(*) AS c
              FROM documents GROUP BY 1) s;

      ELSIF tpl = 'doc_timeline' THEN
        gran := COALESCE(prm->>'granularity', 'year');
        dt   := prm->>'document_type';
        SELECT COALESCE(jsonb_agg(jsonb_build_object('label', k, 'n', c) ORDER BY k),
                        '[]'::jsonb) INTO d
        FROM (SELECT to_char(date_parsed,
                             CASE WHEN gran = 'month' THEN 'YYYY-MM' ELSE 'YYYY' END) AS k,
                     count(*) AS c
              FROM documents
              WHERE date_parsed IS NOT NULL
                AND (dt IS NULL OR document_type = dt)
              GROUP BY 1) s;

      ELSIF tpl = 'top_entities' THEN
        et  := COALESCE(prm->>'entity_type', 'person');
        lim := LEAST(GREATEST(COALESCE((prm->>'limit')::int, 5), 3), 10);
        SELECT COALESCE(jsonb_agg(jsonb_build_object('label', s.canonical_name,
                                                     'n', s.document_count)),
                        '[]'::jsonb) INTO d
        FROM (SELECT canonical_name, document_count FROM entities
              WHERE type::text = et
              ORDER BY document_count DESC, canonical_name LIMIT lim) s;

      ELSIF tpl = 'kpi_count' THEN
        dt   := prm->>'document_type';
        st   := prm->>'status';
        lang := prm->>'language';
        SELECT jsonb_build_object('n', count(*)) INTO d
        FROM documents
        WHERE (dt IS NULL OR document_type = dt)
          AND (st IS NULL OR status::text = st)
          AND (lang IS NULL OR language = lang);
      ELSE
        d := NULL;
      END IF;

      wout := wout || jsonb_build_array(w || jsonb_build_object('data', d));
    EXCEPTION WHEN OTHERS THEN
      wout := wout || jsonb_build_array(w || jsonb_build_object('data', NULL,
                                                                'error', SQLERRM));
    END;
  END LOOP;
  RETURN wout;
END; $$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- agent_context — now also carries the tool registry (return-type change vs 06,
-- hence DROP + single definition here).
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS agent_context(UUID, UUID);
CREATE OR REPLACE FUNCTION agent_context(p_user UUID, p_session UUID)
RETURNS TABLE (config JSONB, capabilities JSONB, history JSONB, tools JSONB) AS $$
  SELECT get_all_config(p_user),
         agent_capabilities(),
         COALESCE((SELECT jsonb_agg(jsonb_build_object('role', m.role, 'content', m.content)
                                    ORDER BY m.created_at)
                   FROM (SELECT role, content, created_at
                         FROM chat_messages
                         WHERE session_id = p_session
                         ORDER BY created_at DESC LIMIT 6) m),
                  '[]'::jsonb),
         agent_tools();
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- create_document — Phase 5.5 adds reprocessing: pass p_doc_id to re-run an
-- EXISTING document through the pipeline in place (ingest_extraction is
-- idempotent per document: pages/mentions are replaced, fields updated).
-- ----------------------------------------------------------------------------
DROP FUNCTION IF EXISTS create_document(TEXT, TEXT, INT);
DROP FUNCTION IF EXISTS create_document(TEXT, TEXT, INT, UUID);
CREATE OR REPLACE FUNCTION create_document(p_filename TEXT, p_original_url TEXT,
                                           p_pages INT, p_doc_id UUID DEFAULT NULL)
RETURNS TABLE (doc_id UUID, taxonomy JSONB) AS $$
DECLARE new_id UUID;
BEGIN
  IF p_doc_id IS NOT NULL THEN
    UPDATE documents SET status = 'processing', process_error = NULL
    WHERE id = p_doc_id
    RETURNING id INTO new_id;
    IF new_id IS NULL THEN
      RAISE EXCEPTION 'reprocess: document % not found', p_doc_id;
    END IF;
  ELSE
    INSERT INTO documents (filename, original_url, page_count, status)
    VALUES (p_filename, p_original_url, GREATEST(p_pages, 1), 'processing')
    RETURNING id INTO new_id;
  END IF;
  RETURN QUERY SELECT new_id, get_config(NULL, 'taxonomy')->'document_types';
END; $$ LANGUAGE plpgsql;
