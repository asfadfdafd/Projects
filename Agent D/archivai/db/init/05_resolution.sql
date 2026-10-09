-- Phase 4: entity resolution — the dedup Agent D visibly lacks
-- ("Абай" / "Абай Кунанбаев" / "Абай (Ибрагим) Кунанбаев" shown as separate entities).
--
-- v1 is deterministic SQL (no models needed):
--   pass 1: same type + same normalized name            → merge
--   pass 2: people/orgs whose token set is contained in EXACTLY ONE
--           larger entity of the same type               → merge into it
-- Every merge folds the losing name into aliases[] and is audit-logged.
-- Extension hook: embedding-similarity merging (bge-m3) can be layered on later.

-- Normalize a name for comparison: lowercase, ё→е, punctuation → spaces.
CREATE OR REPLACE FUNCTION norm_name(t TEXT) RETURNS TEXT AS $$
  SELECT trim(regexp_replace(
           translate(lower(COALESCE(t, '')), 'ё', 'е'),
           '[[:punct:]«»№]+', ' ', 'g'
         ))
$$ LANGUAGE sql IMMUTABLE;

-- Merge entity p_drop into p_keep: repoint mentions, fold aliases, drop loser.
CREATE OR REPLACE FUNCTION merge_entities(p_keep UUID, p_drop UUID)
RETURNS void AS $$
DECLARE v_drop entities%ROWTYPE;
BEGIN
  IF p_keep = p_drop THEN RETURN; END IF;
  SELECT * INTO v_drop FROM entities WHERE id = p_drop;
  IF NOT FOUND THEN RETURN; END IF;

  -- move mentions doc-by-doc via delete+insert so count triggers stay correct
  INSERT INTO entity_mentions (entity_id, document_id, surface_form, confidence)
  SELECT p_keep, m.document_id, m.surface_form, m.confidence
  FROM entity_mentions m
  WHERE m.entity_id = p_drop
  ON CONFLICT (entity_id, document_id) DO NOTHING;
  DELETE FROM entity_mentions WHERE entity_id = p_drop;

  UPDATE entities e SET
    aliases = (SELECT ARRAY(SELECT DISTINCT a
                            FROM unnest(e.aliases || v_drop.aliases || v_drop.canonical_name) AS a
                            WHERE a IS NOT NULL AND a <> e.canonical_name)),
    role_description = COALESCE(e.role_description, v_drop.role_description)
  WHERE e.id = p_keep;

  DELETE FROM entities WHERE id = p_drop;
END; $$ LANGUAGE plpgsql;

-- Run both resolution passes. Returns a jsonb report for the n8n workflow / UI.
CREATE OR REPLACE FUNCTION resolve_entities() RETURNS JSONB AS $$
DECLARE
  r RECORD;
  v_keep UUID;
  v_candidates INT;
  v_merged INT := 0;
  v_details JSONB := '[]'::jsonb;
BEGIN
  -- Pass 1: exact normalized duplicates within a type.
  FOR r IN
    SELECT type, norm_name(canonical_name) AS nname, array_agg(id ORDER BY length(canonical_name) DESC, document_count DESC) AS ids,
           array_agg(canonical_name ORDER BY length(canonical_name) DESC, document_count DESC) AS names
    FROM entities
    GROUP BY type, norm_name(canonical_name)
    HAVING count(*) > 1
  LOOP
    v_keep := r.ids[1];
    FOR i IN 2 .. array_length(r.ids, 1) LOOP
      PERFORM merge_entities(v_keep, r.ids[i]);
      v_merged := v_merged + 1;
      v_details := v_details || jsonb_build_object(
        'pass', 1, 'kept', r.names[1], 'merged', r.names[i], 'type', r.type::text);
    END LOOP;
  END LOOP;

  -- Pass 2: people/orgs whose token set is strictly contained in EXACTLY ONE
  -- larger entity of the same type ("Абай" → "Абай Кунанбаев"). Ambiguous
  -- containment (several possible supersets) is left alone on purpose.
  FOR r IN
    SELECT small.id AS small_id, small.canonical_name AS small_name, small.type AS stype
    FROM entities small
    WHERE small.type IN ('person', 'organization')
  LOOP
    SELECT count(*), min(big.id::text)::uuid INTO v_candidates, v_keep
    FROM entities big
    WHERE big.type = r.stype
      AND big.id <> r.small_id
      AND length(norm_name(big.canonical_name)) > length(norm_name(r.small_name))
      AND (SELECT bool_and(tok = ANY (string_to_array(norm_name(big.canonical_name), ' ')))
           FROM unnest(string_to_array(norm_name(r.small_name), ' ')) AS tok
           WHERE tok <> '');
    IF v_candidates = 1 AND norm_name(r.small_name) <> '' THEN
      v_details := v_details || jsonb_build_object(
        'pass', 2, 'kept', (SELECT canonical_name FROM entities WHERE id = v_keep),
        'merged', r.small_name, 'type', r.stype::text);
      PERFORM merge_entities(v_keep, r.small_id);
      v_merged := v_merged + 1;
    END IF;
  END LOOP;

  IF v_merged > 0 THEN
    PERFORM rebuild_all_edges();
  END IF;

  INSERT INTO audit_log (action, target_type, detail)
  VALUES ('resolve_entities', 'entities',
          jsonb_build_object('merged', v_merged, 'details', v_details));

  RETURN jsonb_build_object('merged', v_merged, 'details', v_details);
END; $$ LANGUAGE plpgsql;
