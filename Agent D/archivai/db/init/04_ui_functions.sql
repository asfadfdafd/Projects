-- Phase 2 UI write operations. All UI writes stay in Postgres functions
-- (same pattern as the n8n pipeline: thin callers, logic in the DB), and every
-- human correction is audit-logged — provenance is a differentiator vs Agent D.

-- Reviewer adds an entity the AI missed. Human input → confidence 1.0.
CREATE OR REPLACE FUNCTION add_entity_to_document(
  p_doc UUID, p_name TEXT, p_type entity_type, p_role TEXT, p_actor UUID
) RETURNS UUID AS $$
DECLARE v_id UUID;
BEGIN
  IF p_name IS NULL OR trim(p_name) = '' THEN
    RAISE EXCEPTION 'entity name required';
  END IF;

  INSERT INTO entities (canonical_name, type, role_description)
  VALUES (trim(p_name), p_type, NULLIF(trim(COALESCE(p_role, '')), ''))
  ON CONFLICT (canonical_name, type)
    DO UPDATE SET role_description = COALESCE(entities.role_description, EXCLUDED.role_description)
  RETURNING id INTO v_id;

  INSERT INTO entity_mentions (entity_id, document_id, surface_form, confidence)
  VALUES (v_id, p_doc, trim(p_name), 1.0)
  ON CONFLICT (entity_id, document_id) DO UPDATE SET confidence = 1.0;

  PERFORM rebuild_all_edges();
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (p_actor, 'add_entity', 'document', p_doc,
          jsonb_build_object('entity_id', v_id, 'name', trim(p_name), 'type', p_type::text));
  RETURN v_id;
END; $$ LANGUAGE plpgsql;

-- Reviewer fixes an entity's spelling for this document. The mention is
-- re-pointed to the corrected entity (created if needed); the old name is kept
-- as an alias (feeds Phase 4 entity resolution); an orphaned old entity is removed.
CREATE OR REPLACE FUNCTION rename_entity_in_document(
  p_doc UUID, p_entity UUID, p_new_name TEXT, p_actor UUID
) RETURNS UUID AS $$
DECLARE
  v_old     entities%ROWTYPE;
  v_surface TEXT;
  v_new     UUID;
BEGIN
  SELECT * INTO v_old FROM entities WHERE id = p_entity;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'entity % not found', p_entity;
  END IF;
  IF p_new_name IS NULL OR trim(p_new_name) = '' THEN
    RAISE EXCEPTION 'new name required';
  END IF;
  IF trim(p_new_name) = v_old.canonical_name THEN
    RETURN p_entity;  -- nothing to do
  END IF;

  SELECT surface_form INTO v_surface
  FROM entity_mentions WHERE document_id = p_doc AND entity_id = p_entity;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'entity % is not mentioned in document %', p_entity, p_doc;
  END IF;

  -- Target entity: corrected name, same type; remember the old spelling as an alias.
  INSERT INTO entities (canonical_name, type, role_description, aliases)
  VALUES (trim(p_new_name), v_old.type, v_old.role_description, ARRAY[v_old.canonical_name])
  ON CONFLICT (canonical_name, type) DO UPDATE
    SET role_description = COALESCE(entities.role_description, EXCLUDED.role_description),
        aliases = (SELECT ARRAY(SELECT DISTINCT a
                                FROM unnest(entities.aliases || v_old.canonical_name) AS a))
  RETURNING id INTO v_new;

  -- Move the mention via delete+insert so count triggers fire on both sides.
  DELETE FROM entity_mentions WHERE document_id = p_doc AND entity_id = p_entity;
  INSERT INTO entity_mentions (entity_id, document_id, surface_form, confidence)
  VALUES (v_new, p_doc, COALESCE(v_surface, v_old.canonical_name), 1.0)
  ON CONFLICT (entity_id, document_id) DO UPDATE SET confidence = 1.0;

  -- Drop the old entity if no document references it anymore.
  DELETE FROM entities e
  WHERE e.id = p_entity
    AND NOT EXISTS (SELECT 1 FROM entity_mentions m WHERE m.entity_id = e.id);

  PERFORM rebuild_all_edges();
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (p_actor, 'rename_entity', 'document', p_doc,
          jsonb_build_object('from', v_old.canonical_name, 'to', trim(p_new_name),
                             'old_entity_id', p_entity, 'new_entity_id', v_new));
  RETURN v_new;
END; $$ LANGUAGE plpgsql;

-- Reviewer removes a wrong extraction from this document.
CREATE OR REPLACE FUNCTION remove_entity_from_document(
  p_doc UUID, p_entity UUID, p_actor UUID
) RETURNS void AS $$
BEGIN
  DELETE FROM entity_mentions WHERE document_id = p_doc AND entity_id = p_entity;

  DELETE FROM entities e
  WHERE e.id = p_entity
    AND NOT EXISTS (SELECT 1 FROM entity_mentions m WHERE m.entity_id = e.id);

  PERFORM rebuild_all_edges();
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (p_actor, 'remove_entity', 'document', p_doc,
          jsonb_build_object('entity_id', p_entity));
END; $$ LANGUAGE plpgsql;
