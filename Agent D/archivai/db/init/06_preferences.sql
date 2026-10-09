-- Phase 5 — Agentic layer: per-user/global configuration the agent (and UI) can
-- change safely. The LLM NEVER writes SQL: it emits actions [{key, patch}] and the
-- ONLY write path is set_config(), which validates every field against the
-- capability manifest (agent_capabilities()) — the same manifest that is inlined
-- into the LLM prompt, so prompt and validation cannot drift apart.
-- Spec: docs/AGENT_LAYER.md. Applied after 01..05 (order matters: this file also
-- re-defines create_document/search_documents as config-aware).

-- ----------------------------------------------------------------------------
-- Table: one row per (scope, key). user_id NULL = global scope.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_preferences (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id    UUID REFERENCES users(id) ON DELETE CASCADE,   -- NULL = global
  key        TEXT NOT NULL,                                 -- search|dashboard|taxonomy|chat
  value      JSONB NOT NULL,
  updated_by TEXT NOT NULL DEFAULT 'agent',                 -- agent|user|system
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- NULL-safe uniqueness: one row per scope+key (NULL user_id folded to a zero uuid).
CREATE UNIQUE INDEX IF NOT EXISTS uq_prefs_scope_key
  ON user_preferences (COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid), key);

-- Agent conversations reuse the chat tables (multi-turn memory).
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'rag';

-- ----------------------------------------------------------------------------
-- Hardcoded defaults (seeded behavior = pre-Phase-5 behavior, zero drift).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION default_config(p_key TEXT) RETURNS JSONB AS $$
  SELECT CASE p_key
    WHEN 'search' THEN
      '{"vector_weight": 0.7, "keyword_weight": 0.3, "limit": 20, "snippet_source": "summary", "min_score": 0.2, "cutoff_ratio": 0.75}'::jsonb
    WHEN 'dashboard' THEN
      '{"widgets": ["kpi_cards","entity_distribution","top_entities","language_distribution","recent_activity","storage_env","timeline"], "top_n": 5}'::jsonb
    WHEN 'taxonomy' THEN
      '{"document_types": [
         {"id": "official_correspondence", "label": "Официальная переписка"},
         {"id": "report",  "label": "Отчёт"},
         {"id": "decree",  "label": "Приказ / постановление"},
         {"id": "article", "label": "Статья"},
         {"id": "list",    "label": "Список"}]}'::jsonb
    WHEN 'chat' THEN
      '{"retrieve_k": 6, "style": "concise"}'::jsonb
    WHEN 'custom_widgets' THEN
      '{"widgets": []}'::jsonb
    ELSE NULL
  END;
$$ LANGUAGE sql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- Capability manifest — single source of truth for WHAT is tunable and WITHIN
-- WHICH BOUNDS. Used to build the LLM prompt AND to validate writes.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agent_capabilities() RETURNS JSONB AS $$
  SELECT jsonb_build_object(
    'search', jsonb_build_object(
      'scope', 'user',
      'description', 'Гибридный поиск по архиву (семантический + точный)',
      'fields', jsonb_build_object(
        'vector_weight',  jsonb_build_object('type','number',  'min',0, 'max',1,
          'description','вес семантического (векторного) сходства; нормализуется с keyword_weight к сумме 1'),
        'keyword_weight', jsonb_build_object('type','number',  'min',0, 'max',1,
          'description','вес точного текстового совпадения'),
        'limit',          jsonb_build_object('type','integer', 'min',1, 'max',50,
          'description','сколько результатов возвращать'),
        'min_score',      jsonb_build_object('type','number', 'min',0, 'max',1,
          'description','абсолютный порог релевантности (ниже — не показывать)'),
        'cutoff_ratio',   jsonb_build_object('type','number', 'min',0, 'max',1,
          'description','относительный порог: результат не слабее этой доли от лучшего'),
        'snippet_source', jsonb_build_object('type','enum',
          'values', jsonb_build_array('summary','full_text'),
          'description','что показывать в сниппете результата'))),
    'dashboard', jsonb_build_object(
      'scope', 'user',
      'description', 'Состав и порядок виджетов дашборда',
      'fields', jsonb_build_object(
        'widgets', jsonb_build_object('type','widget_list',
          'values', jsonb_build_array('kpi_cards','entity_distribution','top_entities',
                                      'language_distribution','recent_activity',
                                      'storage_env','timeline'),
          'description','видимые виджеты в порядке отображения (массив заменяется целиком); storage_env = датчики хранилища (температура/влажность)'),
        'top_n', jsonb_build_object('type','integer', 'min',3, 'max',10,
          'description','размер списков «топ людей/организаций»'))),
    'taxonomy', jsonb_build_object(
      'scope', 'global',
      'description', 'Типы документов для классификации при обработке (общие для всех)',
      'fields', jsonb_build_object(
        'document_types', jsonb_build_object('type','type_list', 'min_items',2, 'max_items',25,
          'description','[{id: латиницей ^[a-z0-9_]{2,40}$, label: до 60 символов}] — массив заменяется целиком'))),
    'chat', jsonb_build_object(
      'scope', 'user',
      'description', 'Поведение ассистента «Ask ArchivAI»',
      'fields', jsonb_build_object(
        'retrieve_k', jsonb_build_object('type','integer', 'min',2, 'max',20,
          'description','сколько фрагментов извлекать для ответа'),
        'style', jsonb_build_object('type','enum',
          'values', jsonb_build_array('concise','detailed'),
          'description','стиль ответов ассистента'))),
    'custom_widgets', jsonb_build_object(
      'scope', 'user',
      'description', 'Пользовательские виджеты дашборда, собранные агентом из шаблонов',
      'fields', jsonb_build_object(
        'widgets', jsonb_build_object('type','widget_specs', 'max_items',6,
          'description','[{id: слаг, title: до 60, template, params}] — массив заменяется целиком',
          'templates', jsonb_build_object(
            'doc_count', jsonb_build_object(
              'description','число документов по группам',
              'params', jsonb_build_object(
                'group_by', jsonb_build_object('type','enum',
                  'values', jsonb_build_array('document_type','language','status')))),
            'doc_timeline', jsonb_build_object(
              'description','документы по времени (опц. фильтр по типу документа)',
              'params', jsonb_build_object(
                'document_type', jsonb_build_object('type','slug','optional',true),
                'granularity', jsonb_build_object('type','enum',
                  'values', jsonb_build_array('year','month')))),
            'top_entities', jsonb_build_object(
              'description','топ сущностей по числу документов',
              'params', jsonb_build_object(
                'entity_type', jsonb_build_object('type','enum',
                  'values', jsonb_build_array('person','organization','place')),
                'limit', jsonb_build_object('type','integer','min',3,'max',10,'optional',true))),
            'kpi_count', jsonb_build_object(
              'description','одно число: документы с фильтрами',
              'params', jsonb_build_object(
                'document_type', jsonb_build_object('type','slug','optional',true),
                'status', jsonb_build_object('type','enum','optional',true,
                  'values', jsonb_build_array('processing','processed','verified','failed')),
                'language', jsonb_build_object('type','enum','optional',true,
                  'values', jsonb_build_array('Russian','Kazakh','Mixed'))))))))
  );
$$ LANGUAGE sql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- Effective config: defaults ⊕ global row ⊕ user row (shallow merge — all
-- values are flat objects; arrays replace wholesale by design).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_config(p_user UUID, p_key TEXT) RETURNS JSONB AS $$
  SELECT default_config(p_key)
    || COALESCE((SELECT value FROM user_preferences
                 WHERE user_id IS NULL AND key = p_key), '{}'::jsonb)
    || COALESCE((SELECT value FROM user_preferences
                 WHERE user_id = p_user AND key = p_key), '{}'::jsonb);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION get_all_config(p_user UUID) RETURNS JSONB AS $$
  SELECT COALESCE(jsonb_object_agg(k, get_config(p_user, k)), '{}'::jsonb)
  FROM jsonb_object_keys(agent_capabilities()) AS k;
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- set_config — THE only write path. Validates every patched field against
-- agent_capabilities(), merges, upserts the scope row, audit-logs old→new.
-- (Note: pg_catalog has a built-in set_config(text,text,bool); ours differs by
-- signature — always call with a uuid first argument.)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_config(p_user UUID, p_key TEXT, p_patch JSONB,
                                      p_actor TEXT DEFAULT 'agent')
RETURNS JSONB AS $$
DECLARE
  caps       JSONB;
  spec       JSONB;
  fld        RECORD;
  pf         RECORD;
  pspec      JSONB;
  t          JSONB;
  scope_user UUID;
  cur_row    JSONB;
  merged     JSONB;
  eff_old    JSONB;
  eff_new    JSONB;
  n          NUMERIC;
  cnt        INT;
  dcnt       INT;
  badcnt     INT;
  vw         NUMERIC;
  kw         NUMERIC;
  wsum       NUMERIC;
  allowed    TEXT;
BEGIN
  caps := agent_capabilities() -> p_key;
  IF caps IS NULL THEN
    SELECT string_agg(k0, ', ') INTO allowed FROM jsonb_object_keys(agent_capabilities()) AS k0;
    RAISE EXCEPTION 'unknown config key "%" (allowed: %)', p_key, allowed;
  END IF;
  IF p_patch IS NULL OR jsonb_typeof(p_patch) <> 'object' OR p_patch = '{}'::jsonb THEN
    RAISE EXCEPTION 'patch for "%" must be a non-empty JSON object', p_key;
  END IF;
  -- Global-scope keys (taxonomy) always write the global row, whoever asks —
  -- but only admins (Phase 6; is_admin() lives in 08_auth.sql; NULL user =
  -- trusted internal path).
  IF caps->>'scope' = 'global' AND NOT is_admin(p_user) THEN
    RAISE EXCEPTION 'only an admin can change the global "%" configuration', p_key;
  END IF;
  scope_user := CASE WHEN caps->>'scope' = 'global' THEN NULL ELSE p_user END;

  -- Field-by-field validation against the manifest.
  FOR fld IN SELECT * FROM jsonb_each(p_patch) LOOP
    spec := caps -> 'fields' -> fld.key;
    IF spec IS NULL THEN
      SELECT string_agg(k, ', ') INTO allowed FROM jsonb_object_keys(caps->'fields') AS k;
      RAISE EXCEPTION 'unknown field "%.%" (allowed: %)', p_key, fld.key, allowed;
    END IF;

    CASE spec->>'type'
      WHEN 'number', 'integer' THEN
        IF jsonb_typeof(fld.value) <> 'number' THEN
          RAISE EXCEPTION '%.% must be a number', p_key, fld.key;
        END IF;
        n := (fld.value)::text::numeric;
        IF n < (spec->>'min')::numeric OR n > (spec->>'max')::numeric THEN
          RAISE EXCEPTION '%.% = % out of bounds [% .. %]',
            p_key, fld.key, n, spec->>'min', spec->>'max';
        END IF;
        IF spec->>'type' = 'integer' AND n <> floor(n) THEN
          RAISE EXCEPTION '%.% must be an integer', p_key, fld.key;
        END IF;

      WHEN 'enum' THEN
        IF jsonb_typeof(fld.value) <> 'string' OR NOT (spec->'values' ? (fld.value #>> '{}')) THEN
          RAISE EXCEPTION '%.% must be one of %', p_key, fld.key, spec->'values';
        END IF;

      WHEN 'widget_list' THEN
        IF jsonb_typeof(fld.value) <> 'array' THEN
          RAISE EXCEPTION '%.% must be an array of widget ids', p_key, fld.key;
        END IF;
        SELECT count(*), count(DISTINCT x.val),
               count(*) FILTER (WHERE NOT (spec->'values' ? x.val))
          INTO cnt, dcnt, badcnt
          FROM jsonb_array_elements_text(fld.value) AS x(val);
        IF cnt < 1 THEN
          RAISE EXCEPTION '%.%: at least one widget must stay visible', p_key, fld.key;
        END IF;
        IF badcnt > 0 THEN
          RAISE EXCEPTION '%.%: unknown widget id (allowed: %)', p_key, fld.key, spec->'values';
        END IF;
        IF dcnt <> cnt THEN
          RAISE EXCEPTION '%.%: duplicate widget ids', p_key, fld.key;
        END IF;

      WHEN 'type_list' THEN
        IF jsonb_typeof(fld.value) <> 'array' THEN
          RAISE EXCEPTION '%.% must be an array of {id, label} objects', p_key, fld.key;
        END IF;
        cnt := jsonb_array_length(fld.value);
        IF cnt < (spec->>'min_items')::int OR cnt > (spec->>'max_items')::int THEN
          RAISE EXCEPTION '%.%: % items out of bounds [% .. %]',
            p_key, fld.key, cnt, spec->>'min_items', spec->>'max_items';
        END IF;
        FOR t IN SELECT * FROM jsonb_array_elements(fld.value) LOOP
          IF jsonb_typeof(t) <> 'object'
             OR COALESCE(t->>'id','') !~ '^[a-z0-9_]{2,40}$' THEN
            RAISE EXCEPTION '%.%: each item needs an id matching ^[a-z0-9_]{2,40}$ (got %)',
              p_key, fld.key, t;
          END IF;
          IF length(COALESCE(t->>'label', t->>'id')) > 60 THEN
            RAISE EXCEPTION '%.%: label longer than 60 chars for id "%"', p_key, fld.key, t->>'id';
          END IF;
        END LOOP;
        SELECT count(DISTINCT x2->>'id') INTO dcnt FROM jsonb_array_elements(fld.value) AS x2;
        IF dcnt <> cnt THEN
          RAISE EXCEPTION '%.%: duplicate type ids', p_key, fld.key;
        END IF;

      WHEN 'widget_specs' THEN
        IF jsonb_typeof(fld.value) <> 'array' THEN
          RAISE EXCEPTION '%.% must be an array of widget specs', p_key, fld.key;
        END IF;
        cnt := jsonb_array_length(fld.value);
        IF cnt > (spec->>'max_items')::int THEN
          RAISE EXCEPTION '%.%: at most % widgets', p_key, fld.key, spec->>'max_items';
        END IF;
        FOR t IN SELECT * FROM jsonb_array_elements(fld.value) LOOP
          IF jsonb_typeof(t) <> 'object'
             OR COALESCE(t->>'id','') !~ '^[a-z0-9_]{2,40}$'
             OR length(COALESCE(t->>'title','')) NOT BETWEEN 1 AND 60
             OR spec->'templates'->(t->>'template') IS NULL THEN
            SELECT string_agg(k2, ', ') INTO allowed
            FROM jsonb_object_keys(spec->'templates') AS k2;
            RAISE EXCEPTION '%.%: each widget needs id (^[a-z0-9_]{2,40}$), title (1..60) and template (one of %); got %',
              p_key, fld.key, allowed, t;
          END IF;
          FOR pf IN SELECT * FROM jsonb_each(COALESCE(t->'params', '{}'::jsonb)) LOOP
            pspec := spec->'templates'->(t->>'template')->'params'->pf.key;
            IF pspec IS NULL THEN
              RAISE EXCEPTION '%.%: unknown param "%" for template "%"',
                p_key, fld.key, pf.key, t->>'template';
            END IF;
            CASE pspec->>'type'
              WHEN 'enum' THEN
                IF jsonb_typeof(pf.value) <> 'string'
                   OR NOT (pspec->'values' ? (pf.value #>> '{}')) THEN
                  RAISE EXCEPTION '%.%: param "%" must be one of %',
                    p_key, fld.key, pf.key, pspec->'values';
                END IF;
              WHEN 'integer' THEN
                IF jsonb_typeof(pf.value) <> 'number' THEN
                  RAISE EXCEPTION '%.%: param "%" must be a number', p_key, fld.key, pf.key;
                END IF;
                n := (pf.value)::text::numeric;
                IF n <> floor(n) OR n < (pspec->>'min')::numeric OR n > (pspec->>'max')::numeric THEN
                  RAISE EXCEPTION '%.%: param "%" = % out of bounds [% .. %]',
                    p_key, fld.key, pf.key, n, pspec->>'min', pspec->>'max';
                END IF;
              WHEN 'slug' THEN
                IF jsonb_typeof(pf.value) <> 'string'
                   OR (pf.value #>> '{}') !~ '^[a-z0-9_]{2,40}$' THEN
                  RAISE EXCEPTION '%.%: param "%" must be a slug ^[a-z0-9_]{2,40}$',
                    p_key, fld.key, pf.key;
                END IF;
              ELSE
                RAISE EXCEPTION 'manifest error: param %.% has unknown type %',
                  t->>'template', pf.key, pspec->>'type';
            END CASE;
          END LOOP;
        END LOOP;
        SELECT count(DISTINCT x3->>'id') INTO dcnt FROM jsonb_array_elements(fld.value) AS x3;
        IF dcnt <> cnt THEN
          RAISE EXCEPTION '%.%: duplicate widget ids', p_key, fld.key;
        END IF;

      ELSE
        RAISE EXCEPTION 'manifest error: field %.% has unknown type %', p_key, fld.key, spec->>'type';
    END CASE;
  END LOOP;

  eff_old := get_config(p_user, p_key);
  cur_row := COALESCE((SELECT value FROM user_preferences
                       WHERE COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid)
                             = COALESCE(scope_user, '00000000-0000-0000-0000-000000000000'::uuid)
                         AND key = p_key), '{}'::jsonb);
  merged := cur_row || p_patch;

  -- search weights: normalize the pair to sum 1 (values may mix patch+defaults).
  IF p_key = 'search' AND (p_patch ? 'vector_weight' OR p_patch ? 'keyword_weight') THEN
    vw := COALESCE((merged->>'vector_weight')::numeric,
                   (eff_old->>'vector_weight')::numeric, 0.7);
    kw := COALESCE((merged->>'keyword_weight')::numeric,
                   (eff_old->>'keyword_weight')::numeric, 0.3);
    wsum := vw + kw;
    IF wsum <= 0 THEN
      RAISE EXCEPTION 'search weights cannot both be zero';
    END IF;
    -- ::float8 keeps jsonb numbers clean (0.9, not the scale-preserving 0.900)
    merged := merged || jsonb_build_object(
      'vector_weight',  round(vw / wsum, 3)::float8,
      'keyword_weight', round(kw / wsum, 3)::float8);
  END IF;

  INSERT INTO user_preferences (user_id, key, value, updated_by)
  VALUES (scope_user, p_key, merged, p_actor)
  ON CONFLICT (COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid), key)
  DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now();

  eff_new := get_config(p_user, p_key);
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (p_user, 'set_config', 'config', scope_user,
          jsonb_build_object('key', p_key, 'patch', p_patch,
                             'old', eff_old, 'new', eff_new, 'via', p_actor));
  RETURN eff_new;
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- agent_apply — apply the agent's action array in one call (thin n8n).
-- Per-action atomicity: invalid actions are reported, valid ones land.
-- Returns [{key, ok, old, new} | {key, ok:false, error}].
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agent_apply(p_user UUID, p_actions JSONB,
                                       p_actor TEXT DEFAULT 'agent')
RETURNS JSONB AS $$
DECLARE
  act  JSONB;
  res  JSONB := '[]'::jsonb;
  kk   TEXT;
  oldv JSONB;
  newv JSONB;
BEGIN
  IF p_actions IS NULL OR jsonb_typeof(p_actions) <> 'array' THEN
    RETURN '[]'::jsonb;
  END IF;
  FOR act IN SELECT * FROM jsonb_array_elements(p_actions) LOOP
    kk := act->>'key';
    BEGIN
      oldv := get_config(p_user, kk);
      newv := set_config(p_user, kk, act->'patch', p_actor);
      res := res || jsonb_build_array(jsonb_build_object('key', kk, 'ok', true,
                                                         'old', oldv, 'new', newv));
    EXCEPTION WHEN OTHERS THEN
      res := res || jsonb_build_array(jsonb_build_object('key', COALESCE(kk, '?'),
                                                         'ok', false, 'error', SQLERRM));
    END;
  END LOOP;
  RETURN res;
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- reset_config — back to defaults (one key or all). Audit-logged.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION reset_config(p_user UUID, p_key TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
  kk         TEXT;
  caps       JSONB;
  scope_user UUID;
BEGIN
  FOR kk IN SELECT k FROM jsonb_object_keys(agent_capabilities()) AS k LOOP
    CONTINUE WHEN p_key IS NOT NULL AND kk <> p_key;
    caps := agent_capabilities() -> kk;
    scope_user := CASE WHEN caps->>'scope' = 'global' THEN NULL ELSE p_user END;
    DELETE FROM user_preferences
    WHERE key = kk
      AND COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid)
          = COALESCE(scope_user, '00000000-0000-0000-0000-000000000000'::uuid);
    IF FOUND THEN
      INSERT INTO audit_log (actor, action, target_type, target_id, detail)
      VALUES (p_user, 'reset_config', 'config', scope_user, jsonb_build_object('key', kk));
    END IF;
  END LOOP;
  RETURN get_all_config(p_user);
END; $$ LANGUAGE plpgsql;

-- agent_context() moved to 07_agent_ops.sql (Phase 5.5 added a `tools` column —
-- return-type changes need DROP+CREATE, so it lives where it's current).

-- ----------------------------------------------------------------------------
-- log_agent_turn — persist one agent turn (kind='agent'); the applied diff is
-- stored in the assistant message's jsonb payload column. Returns the session
-- id plus the fresh effective config (so the workflow responds in one call).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION log_agent_turn(p_session UUID, p_user UUID, p_message TEXT,
                                          p_reply TEXT, p_applied JSONB)
RETURNS TABLE (session_id UUID, config JSONB) AS $$
DECLARE sid UUID;
BEGIN
  sid := p_session;
  IF sid IS NULL THEN
    INSERT INTO chat_sessions (user_id, title, kind)
    VALUES (p_user, left(p_message, 80), 'agent')
    RETURNING id INTO sid;
  END IF;
  INSERT INTO chat_messages (session_id, role, content) VALUES (sid, 'user', p_message);
  INSERT INTO chat_messages (session_id, role, content, citations)
  VALUES (sid, 'assistant', p_reply, COALESCE(p_applied, '[]'::jsonb));
  RETURN QUERY SELECT sid, get_all_config(p_user);
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- Config-aware retrieval for the chat workflow: k and answer style from config.
-- `style` rides along on every row (the workflow reads it off the first one).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rag_retrieve_cfg(q_vec vector, p_user UUID DEFAULT NULL)
RETURNS TABLE (chunk_id UUID, document_id UUID, filename TEXT, content TEXT,
               distance REAL, style TEXT) AS $$
  SELECT r.*, get_config(p_user, 'chat')->>'style'
  FROM rag_retrieve(q_vec,
         GREATEST(2, LEAST(20, COALESCE((get_config(p_user, 'chat')->>'retrieve_k')::int, 6)))) r;
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- Config-aware replacements for 02_functions.sql (moved here because their
-- bodies reference get_config, which must exist first).
-- ----------------------------------------------------------------------------

-- search_documents: weights/limit/snippet now come from config (defaults keep
-- the exact pre-Phase-5 behavior: 0.7 / 0.3 / 20 / summary).
DROP FUNCTION IF EXISTS search_documents(vector, TEXT, INT);
DROP FUNCTION IF EXISTS search_documents(vector, TEXT, UUID, INT);
CREATE OR REPLACE FUNCTION search_documents(q_vec vector, q_text TEXT,
                                            p_user UUID DEFAULT NULL, k INT DEFAULT NULL)
RETURNS TABLE (document_id UUID, filename TEXT, document_type TEXT, date_text TEXT,
               score REAL, snippet TEXT) AS $$
  WITH cfg AS (SELECT get_config(p_user, 'search') AS c),
  vec AS (
    SELECT e.document_id, MIN(e.embedding <=> q_vec) AS vdist
    FROM embeddings e GROUP BY e.document_id
  ),
  ranked AS (
    SELECT d.id, d.filename AS fn, d.document_type AS dt, d.date_text AS dtx,
           ((SELECT COALESCE((c->>'vector_weight')::real, 0.7) FROM cfg)
              * (1 - COALESCE(v.vdist, 1))
            + (SELECT COALESCE((c->>'keyword_weight')::real, 0.3) FROM cfg)
              * COALESCE(similarity(d.full_text, q_text), 0))::real AS sc,
           CASE WHEN (SELECT c->>'snippet_source' FROM cfg) = 'full_text'
                THEN left(COALESCE(d.full_text, d.ai_summary, ''), 240)
                ELSE left(COALESCE(d.ai_summary, d.full_text, ''), 240) END AS sn
    FROM documents d
    LEFT JOIN vec v ON v.document_id = d.id
    WHERE q_text = '' OR d.full_text ILIKE '%'||q_text||'%'
          OR d.ai_summary ILIKE '%'||q_text||'%' OR v.vdist IS NOT NULL
    ORDER BY sc DESC
    LIMIT COALESCE(k, (SELECT (c->>'limit')::int FROM cfg), 20)
  )
  -- Relevance cutoff: drop background-similarity noise. A result must clear BOTH
  -- the absolute floor (min_score) and the relative bar (cutoff_ratio × best).
  SELECT r.id, r.fn, r.dt, r.dtx, r.sc, r.sn
  FROM ranked r
  WHERE r.sc >= GREATEST(
          (SELECT COALESCE((c->>'min_score')::real, 0.2) FROM cfg),
          (SELECT max(r2.sc) FROM ranked r2)
            * (SELECT COALESCE((c->>'cutoff_ratio')::real, 0.75) FROM cfg))
  ORDER BY r.sc DESC;
$$ LANGUAGE sql STABLE;

-- create_document() moved to 07_agent_ops.sql (Phase 5.5 added the optional
-- p_doc_id reprocess parameter; single definition lives there).
