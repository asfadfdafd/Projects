-- Phase 8 (slice) — external/IoT metrics on the dashboard (client-requested:
-- storage temperature & humidity), plus demo-data cleanup for client showings.

CREATE TABLE IF NOT EXISTS metrics (
  id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  sensor TEXT NOT NULL,                 -- e.g. 'storage-room-1'
  metric TEXT NOT NULL,                 -- e.g. 'temperature' | 'humidity'
  value  NUMERIC NOT NULL,
  unit   TEXT,                          -- '°C' | '%'
  at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_metrics_lookup ON metrics(sensor, metric, at DESC);

-- Generic intake (one call for the n8n webhook). Accepts either
--   {sensor, metrics: {temperature: 18.4, humidity: 41}, units?: {...}}
-- or {sensor, metric, value, unit}.
CREATE OR REPLACE FUNCTION ingest_metric(p JSONB) RETURNS INT AS $$
DECLARE
  kv  RECORD;
  n   INT := 0;
  def JSONB := '{"temperature": "°C", "humidity": "%"}'::jsonb;
BEGIN
  IF p ? 'metrics' AND jsonb_typeof(p->'metrics') = 'object' THEN
    FOR kv IN SELECT * FROM jsonb_each(p->'metrics') LOOP
      CONTINUE WHEN jsonb_typeof(kv.value) <> 'number';
      INSERT INTO metrics (sensor, metric, value, unit)
      VALUES (COALESCE(NULLIF(trim(p->>'sensor'), ''), 'storage'),
              kv.key, (kv.value)::text::numeric,
              COALESCE(p->'units'->>kv.key, def->>kv.key));
      n := n + 1;
    END LOOP;
  ELSIF COALESCE(p->>'metric', '') <> '' AND jsonb_typeof(p->'value') = 'number' THEN
    INSERT INTO metrics (sensor, metric, value, unit)
    VALUES (COALESCE(NULLIF(trim(p->>'sensor'), ''), 'storage'),
            p->>'metric', (p->'value')::text::numeric,
            COALESCE(p->>'unit', def->>(p->>'metric')));
    n := 1;
  END IF;
  RETURN n;
END; $$ LANGUAGE plpgsql;

-- Latest value per (sensor, metric) + 24h min/max — one source for the widget.
CREATE OR REPLACE FUNCTION latest_metrics() RETURNS JSONB AS $$
  SELECT COALESCE(jsonb_agg(x ORDER BY x->>'sensor', x->>'metric'), '[]'::jsonb) FROM (
    SELECT jsonb_build_object(
      'sensor', l.sensor, 'metric', l.metric, 'value', l.value, 'unit', l.unit,
      'at', l.at,
      'min24', (SELECT min(value) FROM metrics m2
                WHERE m2.sensor = l.sensor AND m2.metric = l.metric
                  AND m2.at > now() - interval '24 hours'),
      'max24', (SELECT max(value) FROM metrics m2
                WHERE m2.sensor = l.sensor AND m2.metric = l.metric
                  AND m2.at > now() - interval '24 hours')) AS x
    FROM (SELECT DISTINCT ON (sensor, metric) sensor, metric, value, unit, at
          FROM metrics ORDER BY sensor, metric, at DESC) l) s;
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- Demo hygiene: remove smoke/stub artifacts before a client showing.
-- Deletes stub-extracted documents (cascades to pages/mentions/embeddings/outbox),
-- prunes orphaned entities, rebuilds edges + stats. Audit rows stay (compliance).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION cleanup_test_data() RETURNS JSONB AS $$
DECLARE v_docs INT; v_ents INT; v_chats INT;
BEGIN
  DELETE FROM documents
  WHERE filename LIKE 'smoke%'
     OR full_text LIKE '%[stub OCR text for page%'
     OR (status = 'failed' AND original_url IS NULL);
  GET DIAGNOSTICS v_docs = ROW_COUNT;

  DELETE FROM entities e
  WHERE NOT EXISTS (SELECT 1 FROM entity_mentions m WHERE m.entity_id = e.id);
  GET DIAGNOSTICS v_ents = ROW_COUNT;

  DELETE FROM chat_sessions WHERE kind IN ('rag', 'agent');
  GET DIAGNOSTICS v_chats = ROW_COUNT;

  DELETE FROM metrics WHERE at < now() - interval '7 days';

  PERFORM rebuild_all_edges();
  PERFORM compute_dashboard_stats();
  RETURN jsonb_build_object('documents_removed', v_docs,
                            'entities_pruned', v_ents,
                            'chat_sessions_cleared', v_chats);
END; $$ LANGUAGE plpgsql;
