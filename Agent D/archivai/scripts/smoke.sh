#!/usr/bin/env bash
# ArchivAI end-to-end smoke test (stub mode — no GPU/models required).
#
#   make smoke     (or: bash scripts/smoke.sh)
#
# What it does, in order:
#   1. Boots postgres + minio + ai-service + n8n (Ollama not needed for stub)
#   2. Applies/refreshes all db/init/*.sql (idempotent)
#   3. Imports the Postgres credential + all workflows into n8n headlessly,
#      activates them, restarts n8n so webhooks register
#   4. Ingest → asserts documents/pages/entities/mentions/edges/embeddings/stats
#   5. Search → asserts ranked results
#   6. Chat → asserts grounded, cited answer + persisted session
#   7. Entity resolution → asserts a merge report
#   7c. Agent layer → NL turns change search/dashboard/taxonomy/chat config,
#       taxonomy reaches the ingest pipeline, guardrails reject bad writes, reset
#   8. Failure path → asserts mark_failed() + HTTP 500
#   9. Runs the AI service contract selftest
# On webhook failures it prints full diagnostics (response body, registered
# webhooks, last n8n executions + error, env, log tail).
set -u
cd "$(dirname "$0")/.."

PASS=0; FAIL=0; FAILED_STEPS=()
ok()   { PASS=$((PASS+1)); echo "  [ok]   $1"; }
fail() { FAIL=$((FAIL+1)); FAILED_STEPS+=("$1"); echo "  [FAIL] $1"; }
step() { echo; echo "== $1 =="; }

# --- 0. Environment -----------------------------------------------------------
step "0. Environment"
command -v docker >/dev/null 2>&1 || { echo "docker not found — install Docker Desktop first"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose v2 not found"; exit 1; }
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  (created .env from .env.example)"
fi
set -a; . ./.env; set +a
if [ "${AI_STUB:-0}" != "1" ]; then
  echo "  AI_STUB is not 1 in .env — this smoke test runs in stub mode."
  echo "  Set AI_STUB=1 in .env and re-run (switch back to 0 for real models)."
  exit 1
fi
ok "docker + .env present, AI_STUB=1"

PSQL() { docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -qtA -U "${POSTGRES_USER:-archivai}" -d "${POSTGRES_DB:-archivai}" -c "$1"; }
# JSON field getter, tolerant of n8n array-wrapping the response ([{...}] vs {...}).
JGET() { python3 -c "
import json, sys
d = json.load(sys.stdin)
if isinstance(d, list) and d: d = d[0]
print(d$1)" 2>/dev/null; }

# Stub embeddings are deterministic hash vectors, not semantics: the cosine between
# ANY two of them is ≈0.07, so no document can clear the product relevance floor
# (search.min_score = 0.2) and every stub search would return 0 rows. Drop the floor
# for the search asserts — in stub mode they verify the ranking/pipeline WIRING, not
# relevance quality, which stub mode cannot express. Re-applied after every
# reset_config below; the final reset in 7c restores the product default (0.2).
SEARCH_NO_FLOOR() {
  PSQL "SELECT set_config(NULL::uuid,'search','{\"min_score\":0}'::jsonb,'smoke');" >/dev/null 2>&1
}

# POST a JSON body to a webhook path. Sets HTTP_CODE and BODY globals.
HOOK() {
  local path="$1" data="$2" timeout="${3:-120}"
  BODY=$(curl -s --max-time "$timeout" -w '\n%{http_code}' -X POST "http://localhost:5678/webhook/$path" \
    -H 'Content-Type: application/json' -d "$data" 2>/dev/null)
  HTTP_CODE=$(echo "$BODY" | tail -1)
  BODY=$(echo "$BODY" | sed '$d')
}

diagnose() {
  echo
  echo "  ---------------- diagnostics ----------------"
  echo "  [n8n env]"
  echo -n "    AI_SERVICE_URL = "; docker compose exec -T n8n printenv AI_SERVICE_URL 2>/dev/null || echo "(NOT SET — n8n cannot reach the AI service)"
  echo "  [workflows known to n8n]"
  docker compose exec -T n8n n8n list:workflow 2>/dev/null | sed 's/^/    /' || echo "    (list:workflow failed)"
  echo "  [registered webhook routes]"
  PSQL "SELECT '    ' || method || ' /webhook/' || \"webhookPath\" FROM webhook_entity ORDER BY \"webhookPath\";" 2>/dev/null \
    || echo "    (webhook_entity not readable — no webhooks registered?)"
  echo "  [last 5 executions]"
  PSQL "SELECT '    #' || id || ' wf=' || COALESCE(\"workflowId\"::text,'?') || ' ' || status || ' ' || COALESCE(\"stoppedAt\"::text,'') FROM execution_entity ORDER BY id DESC LIMIT 5;" 2>/dev/null \
    || echo "    (no executions recorded)"
  echo "  [last failed execution — error detail]"
  PSQL "SELECT left(regexp_replace(ed.data, '\s+', ' ', 'g'), 900)
        FROM execution_data ed JOIN execution_entity e ON e.id = ed.\"executionId\"
        WHERE e.status IN ('error','crashed','failed')
        ORDER BY e.id DESC LIMIT 1;" 2>/dev/null | sed 's/^/    /' || true
  echo "  [last execution — data excerpt (any status)]"
  PSQL "SELECT left(regexp_replace(ed.data, '\s+', ' ', 'g'), 1200)
        FROM execution_data ed JOIN execution_entity e ON e.id = ed.\"executionId\"
        ORDER BY e.id DESC LIMIT 1;" 2>/dev/null | sed 's/^/    /' || true
  echo "  [recent documents — shows whether mark_failed ran and why]"
  PSQL "SELECT '    ' || left(id::text, 8) || ' | ' || status || ' | ' || filename || ' | ' || COALESCE(left(process_error, 220), '')
        FROM documents ORDER BY created_at DESC LIMIT 3;" 2>/dev/null || echo "    (no documents)"
  echo "  [n8n log tail]"
  docker compose logs --no-color --tail=25 n8n 2>/dev/null | tail -25 | sed 's/^/    /'
  echo "  ----------------------------------------------"
}

# --- 1. Boot the stack (no Ollama needed in stub mode) -------------------------
step "1. Boot stack (postgres, minio, ai-service, n8n)"
docker compose up -d postgres minio minio-init ai-service n8n || { echo "compose up failed"; exit 1; }

echo -n "  waiting for postgres"
for i in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-archivai}" -d "${POSTGRES_DB:-archivai}" >/dev/null 2>&1 && break
  echo -n "."; sleep 2
done; echo
PSQL "SELECT 1;" >/dev/null 2>&1 && ok "postgres ready" || { fail "postgres not ready"; exit 1; }

echo -n "  waiting for ai-service"
AIH=""
for i in $(seq 1 60); do
  AIH=$(curl -sf --max-time 3 http://localhost:8000/health 2>/dev/null) && break
  echo -n "."; sleep 2
done; echo
[ -n "$AIH" ] && ok "ai-service up: $AIH" || { fail "ai-service /health unreachable"; exit 1; }
[ "$(echo "$AIH" | JGET "['stub']")" = "True" ] && ok "ai-service running in stub mode" \
  || { fail "ai-service NOT in stub mode — set AI_STUB=1 and: docker compose up -d --force-recreate ai-service"; exit 1; }

echo -n "  waiting for n8n"
for i in $(seq 1 90); do
  curl -sf --max-time 3 http://localhost:5678/healthz >/dev/null 2>&1 && break
  echo -n "."; sleep 2
done; echo
curl -sf http://localhost:5678/healthz >/dev/null 2>&1 && ok "n8n ready" || { fail "n8n /healthz unreachable"; exit 1; }

# --- 2. Apply/refresh schema + functions (idempotent) --------------------------
step "2. Apply db/init/*.sql"
DBOK=1
for f in db/init/*.sql; do
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "${POSTGRES_USER:-archivai}" -d "${POSTGRES_DB:-archivai}" < "$f" >/dev/null || { DBOK=0; fail "apply $f"; }
done
[ "$DBOK" = "1" ] && ok "all SQL applied"
# deterministic baseline: agent config from a previous (interrupted) run or from
# UI sessions must not leak into the asserts (stub classifies with taxonomy[0]).
# Reset BOTH scopes: global and the demo user (the web UI writes as the demo user).
PSQL "SELECT reset_config(NULL::uuid, NULL);" >/dev/null 2>&1 || true
PSQL "SELECT reset_config(u.id, NULL) FROM users u WHERE u.email='demo@archivai.local';" >/dev/null 2>&1 || true

# --- 3. Headless n8n setup: owner + credential + workflows + publish ------------
step "3. n8n setup: owner, credential, workflows, publish"

# 3a. Ensure an owner account exists. n8n only shows workflows that belong to a
# project, and CLI imports on an ownerless instance end up orphaned/invisible.
OWNER_EMAIL="${N8N_OWNER_EMAIL:-admin@archivai.local}"
OWNER_PASSWORD="${N8N_OWNER_PASSWORD:-ArchivAI-Dev1}"
SETUP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:5678/rest/owner/setup \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$OWNER_EMAIL\",\"firstName\":\"Archiv\",\"lastName\":\"AI\",\"password\":\"$OWNER_PASSWORD\"}")
if [ "$SETUP_CODE" = "200" ]; then
  ok "owner account created — n8n UI login: $OWNER_EMAIL / $OWNER_PASSWORD"
else
  ok "owner already set up (HTTP $SETUP_CODE) — using the existing account"
fi

python3 - "$POSTGRES_HOST" "$POSTGRES_PORT" "$POSTGRES_DB" "$POSTGRES_USER" "$POSTGRES_PASSWORD" \
          "${MINIO_ROOT_USER:-archivai}" "${MINIO_ROOT_PASSWORD:-change_me_minio}" <<'PYEOF' > /tmp/archivai-pg-cred.json
import json, sys
host, port, db, user, pw, s3u, s3p = sys.argv[1:8]
print(json.dumps([{
  "id": "archivai-pg", "name": "ArchivAI Postgres", "type": "postgres",
  "data": {"host": host, "port": int(port), "database": db, "user": user,
            "password": pw, "allowUnauthorizedCerts": False, "ssl": "disable",
            "sshTunnel": False}
}, {
  "id": "archivai-s3", "name": "ArchivAI MinIO", "type": "s3",
  "data": {"endpoint": "http://minio:9000", "region": "us-east-1",
            "accessKeyId": s3u, "secretAccessKey": s3p,
            "forcePathStyle": True, "ignoreSSLIssues": True}
}]))
PYEOF
docker compose cp /tmp/archivai-pg-cred.json n8n:/tmp/archivai-pg-cred.json >/dev/null 2>&1
rm -f /tmp/archivai-pg-cred.json
docker compose exec -T n8n n8n import:credentials --input=/tmp/archivai-pg-cred.json >/dev/null 2>&1 \
  && ok "credential 'ArchivAI Postgres' imported" || fail "credential import"
docker compose exec -T n8n rm -f /tmp/archivai-pg-cred.json >/dev/null 2>&1

# 3b. Delete previous ArchivAI copies (incl. ownerless strays from earlier runs),
# then import fresh so the workflows bind to the owner's project.
PSQL "DELETE FROM workflow_entity WHERE name LIKE 'ArchivAI%';" >/dev/null 2>&1 || true
IMP=$(docker compose exec -T n8n n8n import:workflow --separate --input=/workflows 2>&1) \
  && ok "workflows imported" || { fail "workflow import"; echo "$IMP" | tail -5 | sed 's/^/    /'; }

# 3c. n8n 2.x replaced the active toggle with publish/unpublish; production
# webhooks only register for PUBLISHED workflows. Fall back to the deprecated
# activate flag on 1.x images.
if docker compose exec -T n8n n8n publish:workflow --help >/dev/null 2>&1; then
  PUBOK=1
  for wid in archivai-w1 archivai-w2 archivai-w3 archivai-w4 archivai-w5 archivai-w6 archivai-w7 archivai-w8 archivai-w9; do
    POUT=$(docker compose exec -T n8n n8n publish:workflow --id="$wid" 2>&1) \
      || { PUBOK=0; echo "    publish $wid failed:"; echo "$POUT" | tail -4 | sed 's/^/      /'; }
  done
  [ "$PUBOK" = "1" ] && ok "9 workflows published (n8n 2.x publish model)" || fail "workflow publish"
else
  docker compose exec -T n8n n8n update:workflow --all --active=true >/dev/null 2>&1 \
    && ok "workflows activated (n8n 1.x)" || fail "workflow activation"
fi
docker compose restart n8n >/dev/null 2>&1
echo -n "  waiting for n8n to come back"
for i in $(seq 1 90); do
  curl -sf --max-time 3 http://localhost:5678/healthz >/dev/null 2>&1 && break
  echo -n "."; sleep 2
done; echo; sleep 3
WHOOKS=$(PSQL "SELECT count(*) FROM webhook_entity;" 2>/dev/null || echo 0)
if [ "${WHOOKS:-0}" -ge 9 ] 2>/dev/null; then
  ok "n8n restarted — $WHOOKS webhook routes registered"
else
  fail "only ${WHOOKS:-0} webhook routes registered (expected 9+)"
  diagnose
fi

# --- 4. Ingest (async: webhook answers immediately, pipeline continues) --------
step "4. Ingest a stub document (async)"
HOOK ingest '{ "filename": "smoke, комма-тест №1.png",
  "original_url": "http://minio:9000/scans/smoke.png",
  "pages": [ { "image_url": "http://minio:9000/scans/smoke.png" } ] }' 60
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "202" ]; then
  fail "ingest webhook HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 400)"
  [ "$HTTP_CODE" = "404" ] && echo "  hint: webhook not registered — workflow inactive; see diagnostics"
  diagnose
  echo "Aborting remaining steps."; exit 1
fi
DOC_ID=$(echo "$BODY" | JGET "['doc_id']")
STATUS=$(echo "$BODY" | JGET "['status']")
if [ -n "$DOC_ID" ] && [ "$STATUS" = "processing" ]; then
  ok "ingest accepted → doc_id=$DOC_ID (processing in background)"
else
  fail "ingest response unexpected: $BODY"
  diagnose
  exit 1
fi
echo -n "  waiting for the pipeline to finish"
ST=""
for i in $(seq 1 90); do
  ST=$(PSQL "SELECT status FROM documents WHERE id='$DOC_ID'")
  [ "$ST" = "processed" ] && break
  [ "$ST" = "failed" ] && break
  echo -n "."; sleep 1
done; echo
if [ "$ST" = "processed" ]; then
  ok "pipeline finished → status=processed"
else
  fail "pipeline ended with status=$ST"
  [ "$ST" = "failed" ] && echo "  process_error: $(PSQL "SELECT left(process_error,300) FROM documents WHERE id='$DOC_ID'")"
  diagnose
  exit 1
fi

step "5. Verify DB rows for the ingested document"
[ "$(PSQL "SELECT status FROM documents WHERE id='$DOC_ID'")" = "processed" ] && ok "documents.status=processed" || fail "documents.status"
[ "$(PSQL "SELECT document_type FROM documents WHERE id='$DOC_ID'")" = "official_correspondence" ] && ok "document_type extracted" || fail "document_type"
[ "$(PSQL "SELECT sender_name FROM documents WHERE id='$DOC_ID'")" = "Домков" ] && ok "sender extracted" || fail "sender"
[ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$DOC_ID'")" = "1" ] && ok "pages row written (per-page OCR)" || fail "pages row"
[ "$(PSQL "SELECT count(*) FROM entity_mentions WHERE document_id='$DOC_ID'")" = "4" ] && ok "4 entity mentions" || fail "entity_mentions"
[ "$(PSQL "SELECT count(*) FROM entities")" -ge 4 ] 2>/dev/null && ok "entities upserted" || fail "entities"
[ "$(PSQL "SELECT count(*) FROM entity_edges")" -ge 6 ] 2>/dev/null && ok "co-occurrence edges built" || fail "entity_edges"
[ "$(PSQL "SELECT count(*) FROM embeddings WHERE document_id='$DOC_ID'")" = "1" ] && ok "embedding stored (1024-dim)" || fail "embeddings"
[ "$(PSQL "SELECT (data->>'documents_processed')::int >= 1 FROM dashboard_stats WHERE id=1")" = "t" ] && ok "dashboard stats computed" || fail "dashboard_stats"

# --- 6. Search ------------------------------------------------------------------
step "6. Search"
SEARCH_NO_FLOOR
HOOK search '{ "query": "Домков, письмо" }' 60
CNT=$(echo "$BODY" | JGET "['count']")
if [ "$HTTP_CODE" = "200" ] && [ -n "$CNT" ] && [ "$CNT" -ge 1 ] 2>/dev/null; then
  ok "search → $CNT result(s)"
  echo "$BODY" | JGET "['results'][0]['document_id']" >/dev/null && ok "results carry document_id + snippet" || fail "search result shape"
else
  fail "search HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 300)"
  diagnose
fi

# --- 7. Chat (Ask ArchivAI) ------------------------------------------------------
step "7. Chat (RAG with citations)"
HOOK chat '{ "question": "Кто, кому и о чём писал?", "session_id": null, "user_id": null }' 120
SES=$(echo "$BODY" | JGET "['session_id']")
GRD=$(echo "$BODY" | JGET "['grounded']")
NCIT=$(echo "$BODY" | JGET "['citations'].__len__()")
if [ "$HTTP_CODE" = "200" ] && [ -n "$SES" ]; then
  ok "chat → session_id=$SES"
  [ "$GRD" = "True" ] && ok "answer grounded" || fail "grounded flag"
  [ -n "$NCIT" ] && [ "$NCIT" -ge 1 ] 2>/dev/null && ok "$NCIT citation(s) attached" || fail "citations"
  [ "$(PSQL "SELECT count(*) FROM chat_messages WHERE session_id='$SES'")" = "2" ] && ok "turn persisted (2 chat_messages)" || fail "chat persistence"
else
  fail "chat HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 300)"
  diagnose
fi

# --- 7b. Entity resolution --------------------------------------------------------
step "7b. Entity resolution workflow"
HOOK resolve '{}' 60
MRG=$(echo "$BODY" | JGET "['merged']")
if [ "$HTTP_CODE" = "200" ] && [ -n "$MRG" ]; then
  ok "resolve → merged=$MRG duplicates"
else
  fail "resolve HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 300)"
  diagnose
fi

# --- 7c. Agent layer (Phase 5) -----------------------------------------------------
step "7c. Configuration agent (NL → validated config writes)"
# fresh baseline so asserts are deterministic even on re-runs (both scopes)
PSQL "SELECT reset_config(NULL::uuid, NULL);" >/dev/null 2>&1
PSQL "SELECT reset_config(u.id, NULL) FROM users u WHERE u.email='demo@archivai.local';" >/dev/null 2>&1
SEARCH_NO_FLOOR   # reset wiped it; the retune check below searches again

# (1) make search more semantic → weights change, search still works
HOOK agent '{ "message": "сделай поиск более семантическим", "session_id": null, "user_id": null }' 120
ASES=$(echo "$BODY" | JGET "['session_id']")
AOK=$(echo "$BODY" | JGET "['applied'][0]['ok']")
if [ "$HTTP_CODE" = "200" ] && [ -n "$ASES" ] && [ "$AOK" = "True" ]; then
  ok "agent turn → session_id=$ASES, action applied"
else
  fail "agent HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 300)"
  diagnose
fi
[ "$(PSQL "SELECT (get_config(NULL::uuid,'search')->>'vector_weight')::numeric = 0.9")" = "t" ] \
  && ok "user_preferences: search.vector_weight=0.9" || fail "search weight write"
[ "$(PSQL "SELECT count(*) FROM user_preferences WHERE key='search' AND user_id IS NULL")" = "1" ] \
  && ok "one global scope row for search" || fail "user_preferences row"
HOOK search '{ "query": "Домков, письмо" }' 60
SCNT=$(echo "$BODY" | JGET "['count']")
[ "$HTTP_CODE" = "200" ] && [ -n "$SCNT" ] && [ "$SCNT" -ge 1 ] 2>/dev/null \
  && ok "search still returns results with tuned weights" || fail "search after retune"

# (2) hide the timeline widget
HOOK agent '{ "message": "убери таймлайн с дашборда", "session_id": null, "user_id": null }' 120
[ "$(PSQL "SELECT get_config(NULL::uuid,'dashboard')->'widgets' ? 'timeline'")" = "f" ] \
  && ok "dashboard.widgets no longer contains timeline" || fail "widget hide"

# (3) add a document type → next ingest classifies with it (stub uses taxonomy[0])
HOOK agent '{ "message": "добавь тип документа «протокол»", "session_id": null, "user_id": null }' 120
[ "$(PSQL "SELECT get_config(NULL::uuid,'taxonomy')->'document_types'->0->>'id'")" = "protokol" ] \
  && ok "taxonomy: protokol prepended (global scope)" || fail "taxonomy write"
HOOK ingest '{ "filename": "smoke-taxonomy.png", "pages": [ { "image_url": "http://minio:9000/scans/smoke.png" } ] }' 60
TDOC=$(echo "$BODY" | JGET "['doc_id']")
TST=""
for i in $(seq 1 60); do
  TST=$(PSQL "SELECT status FROM documents WHERE id='$TDOC'")
  { [ "$TST" = "processed" ] || [ "$TST" = "failed" ]; } && break
  sleep 1
done
[ "$(PSQL "SELECT document_type FROM documents WHERE id='$TDOC'")" = "protokol" ] \
  && ok "ingest classified with agent-added type (protokol)" || fail "taxonomy → pipeline wiring (type=$(PSQL "SELECT document_type FROM documents WHERE id='$TDOC'"))"

# (3w) custom widget from NL (Phase 5.5): spec validated + data computed
HOOK agent '{ "message": "добавь виджет: динамика приказов по годам", "session_id": null, "user_id": null }' 120
[ "$(PSQL "SELECT get_config(NULL::uuid,'custom_widgets')->'widgets'->0->>'template'")" = "doc_timeline" ] \
  && ok "custom widget spec stored (doc_timeline)" || fail "widget spec write"
[ "$(PSQL "SELECT get_config(NULL::uuid,'custom_widgets')->'widgets'->0->'params'->>'document_type'")" = "decree" ] \
  && ok "widget params matched taxonomy label (decree)" || fail "widget params"
[ "$(PSQL "SELECT jsonb_array_length(widget_data(NULL::uuid))")" = "1" ] \
  && ok "widget_data() computes the widget" || fail "widget_data"

# (3op) operator commands (Phase 5.5): resolve + recompute in one turn
HOOK agent '{ "message": "слей дубликаты и пересчитай статистику", "session_id": null, "user_id": null }' 120
ROK1=$(echo "$BODY" | JGET "['ran'][0]['ok']")
ROK2=$(echo "$BODY" | JGET "['ran'][1]['ok']")
[ "$ROK1" = "True" ] && [ "$ROK2" = "True" ] \
  && ok "compound turn ran 2 tools (resolve + recompute)" || fail "agent_run tools — ran: $(echo "$BODY" | JGET "['ran']")"
[ "$(PSQL "SELECT count(*) >= 2 FROM audit_log WHERE action='agent_run'")" = "t" ] \
  && ok "tool runs audit-logged" || fail "agent_run audit"

# (3rp) reprocess (Phase 5.5): NL → tool → self-webhook → pipeline reclassifies
# taxonomy[0] is now protokol, so the stub re-extraction must flip the first doc.
HOOK agent '{ "message": "переклассифицируй документы", "session_id": null, "user_id": null }' 120
RPC=$(echo "$BODY" | JGET "['ran'][0]['result']['count']")
[ -n "$RPC" ] && [ "$RPC" -ge 1 ] 2>/dev/null \
  && ok "reprocess dispatched $RPC document(s)" || fail "reprocess dispatch — ran: $(echo "$BODY" | JGET "['ran']")"
RPT=""
for i in $(seq 1 60); do
  RPT=$(PSQL "SELECT document_type FROM documents WHERE id='$DOC_ID'")
  [ "$RPT" = "protokol" ] && break
  sleep 1
done
[ "$RPT" = "protokol" ] \
  && ok "reprocessed doc reclassified with agent-added type (full NL→pipeline loop)" \
  || fail "reprocess reclassification (document_type=$RPT)"

# (4) multi-turn memory: second message reuses the session
HOOK agent "{ \"message\": \"отвечай в чате подробнее\", \"session_id\": \"$ASES\", \"user_id\": null }" 120
[ "$(PSQL "SELECT get_config(NULL::uuid,'chat')->>'style'")" = "detailed" ] \
  && ok "chat.style=detailed via agent" || fail "chat style write"
[ "$(PSQL "SELECT count(*) FROM chat_messages WHERE session_id='$ASES'")" = "4" ] \
  && ok "agent session persisted (4 messages, multi-turn)" || fail "agent session persistence"
[ "$(PSQL "SELECT kind FROM chat_sessions WHERE id='$ASES'")" = "agent" ] \
  && ok "session kind=agent" || fail "session kind"

# (5) guardrails: the ONLY write path validates bounds/keys (LLM never writes SQL)
if PSQL "SELECT set_config(NULL::uuid,'search','{\"vector_weight\":5}'::jsonb,'test');" >/dev/null 2>&1; then
  fail "out-of-bounds patch was accepted (must be rejected)"
else
  ok "out-of-bounds patch rejected by set_config()"
fi
if PSQL "SELECT set_config(NULL::uuid,'hacking','{\"x\":1}'::jsonb,'test');" >/dev/null 2>&1; then
  fail "unknown config key accepted (must be rejected)"
else
  ok "unknown config key rejected by set_config()"
fi
[ "$(PSQL "SELECT count(*) >= 4 FROM audit_log WHERE action='set_config'")" = "t" ] \
  && ok "audit_log carries the old→new trail" || fail "audit trail"

# (6) reset → defaults restored (also leaves a clean state for later steps/re-runs)
PSQL "SELECT reset_config(NULL::uuid, NULL);" >/dev/null 2>&1
[ "$(PSQL "SELECT (get_config(NULL::uuid,'search')->>'vector_weight')::numeric = 0.7")" = "t" ] \
  && ok "reset_config → defaults restored (0.7/0.3)" || fail "reset"

# --- 7d. Auth, history & compliance (Phase 6) --------------------------------------
step "7d. Auth, search history, usage stats"
ADMIN_ID=$(PSQL "SELECT id FROM users WHERE email='demo@archivai.local'")

# register (admin-gated) + login → session → logout.
# NOTE: users with an audit trail can't be deleted (audit_log FK, by design),
# so the smoke user is created once and reused on re-runs.
if [ -z "$(PSQL "SELECT id FROM users WHERE email='smoke@test.local'")" ]; then
  PSQL "SELECT register_user('smoke@test.local','smokepw1','Smoke','reviewer','$ADMIN_ID'::uuid);" >/dev/null 2>&1 \
    && ok "register_user (as admin)" || fail "register_user"
else
  ok "smoke user already present (audit FK forbids deletion — reused)"
fi
TOK=$(PSQL "SELECT login('smoke@test.local','smokepw1','127.0.0.1','smoke-test')")
[ -n "$TOK" ] && ok "login → session token" || fail "login"
[ "$(PSQL "SELECT email FROM auth_user('$TOK')")" = "smoke@test.local" ] \
  && ok "auth_user resolves the cookie token" || fail "auth_user"
[ -z "$(PSQL "SELECT login('smoke@test.local','WRONG','127.0.0.1','smoke-test')")" ] \
  && ok "wrong password → NULL" || fail "bad login rejected"
[ "$(PSQL "SELECT count(*) >= 1 FROM audit_log WHERE action='login_failed'")" = "t" ] \
  && ok "failed login audit-logged" || fail "login_failed audit"
PSQL "SELECT logout('$TOK');" >/dev/null 2>&1
[ -z "$(PSQL "SELECT email FROM auth_user('$TOK')")" ] \
  && ok "logout kills the session" || fail "logout"

# non-admin cannot touch global config, reprocess or register users (SQL gates)
SMOKE_UID=$(PSQL "SELECT id FROM users WHERE email='smoke@test.local'")
if PSQL "SELECT register_user('nope@test.local','password1','X','reviewer','$SMOKE_UID'::uuid);" >/dev/null 2>&1; then
  fail "reviewer registered a user (must be admin-only)"
else
  ok "register_user is admin-gated"
fi
if PSQL "SELECT set_config('$SMOKE_UID'::uuid,'taxonomy','{\"document_types\":[{\"id\":\"x1\",\"label\":\"X\"},{\"id\":\"x2\",\"label\":\"Y\"}]}'::jsonb,'test');" >/dev/null 2>&1; then
  fail "reviewer changed global taxonomy (must be admin-only)"
else
  ok "global config is admin-gated"
fi
[ "$(PSQL "SELECT agent_run('$SMOKE_UID'::uuid, '[{\"tool\":\"reprocess_documents\",\"params\":{}}]'::jsonb, 'test')->0->>'ok'")" = "false" ] \
  && ok "reprocess is admin-gated" || fail "reprocess gate"

# search history: the earlier search webhook calls must have logged rows
[ "$(PSQL "SELECT count(*) >= 1 FROM search_history")" = "t" ] \
  && ok "search_history rows written by search_and_log" || fail "search_history"
[ "$(PSQL "SELECT count(*) >= 1 FROM (SELECT * FROM recent_searches(NULL::uuid, 8)) s")" = "t" ] \
  && ok "recent_searches returns suggestions" || fail "recent_searches"

# usage stats: one source for the /usage page
USOK=$(PSQL "SELECT (usage_stats() ? 'totals') AND (usage_stats() ? 'recent_logins') AND (usage_stats() ? 'top_queries')")
[ "$USOK" = "t" ] && ok "usage_stats() carries totals/logins/queries" || fail "usage_stats"

# --- 7e. Connectors (Phase 7): bulk pull + outbox push -----------------------------
step "7e. Connectors: pull (dedup) + push (outbox → sink)"

# drop a fresh file into the import bucket (the client's "file storage")
CKEY="smoke-connector-$(date +%s).png"
docker compose run --rm --entrypoint /bin/sh minio-init -c \
  "mc alias set local http://minio:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null && \
   echo stub > /tmp/c.png && mc cp /tmp/c.png local/\${CONNECTOR_BUCKET:-import}/$CKEY" >/dev/null 2>&1 \
  && ok "test file dropped into the import bucket ($CKEY)" || fail "mc cp into import bucket"

HOOK connector-pull '{}' 90
FOUND=$(echo "$BODY" | JGET "['found']")
DISP=$(echo "$BODY" | JGET "['dispatched']")
if [ "$HTTP_CODE" = "200" ] && [ -n "$DISP" ] && [ "$DISP" -ge 1 ] 2>/dev/null; then
  ok "pull → found=$FOUND, dispatched=$DISP"
else
  fail "connector-pull HTTP $HTTP_CODE — body: $(echo "$BODY" | head -c 300)"
  diagnose
fi
CDOC=""
for i in $(seq 1 60); do
  CDOC=$(PSQL "SELECT status FROM documents WHERE original_url LIKE '%$CKEY'")
  { [ "$CDOC" = "processed" ] || [ "$CDOC" = "failed" ]; } && break
  sleep 1
done
[ "$CDOC" = "processed" ] && ok "pulled file went through the pipeline (processed)" \
  || fail "pulled file status=$CDOC"

HOOK connector-pull '{}' 90
DISP2=$(echo "$BODY" | JGET "['dispatched']")
[ "$DISP2" = "0" ] && ok "second pull → dispatched=0 (dedup by original_url)" \
  || fail "dedup (second pull dispatched=$DISP2)"

# push: the processed doc was enqueued by trigger → flush → sink logged it
OBX=$(PSQL "SELECT count(*) FROM connector_outbox WHERE status IN ('pending','sending')")
[ -n "$OBX" ] && [ "$OBX" -ge 1 ] 2>/dev/null && ok "outbox holds $OBX pending push(es)" \
  || fail "outbox enqueue trigger"
HOOK push-now '{}' 90
TAKEN=$(echo "$BODY" | JGET "['taken']")
[ "$HTTP_CODE" = "200" ] && [ -n "$TAKEN" ] && [ "$TAKEN" -ge 1 ] 2>/dev/null \
  && ok "push-now → taken=$TAKEN" || fail "push-now HTTP $HTTP_CODE — $(echo "$BODY" | head -c 200)"
SENTOK=""
for i in $(seq 1 30); do
  SENTOK=$(PSQL "SELECT count(*) FROM audit_log WHERE action='client_push_received' AND detail->>'source'='archivai'")
  [ -n "$SENTOK" ] && [ "$SENTOK" -ge 1 ] 2>/dev/null && break
  sleep 1
done
[ -n "$SENTOK" ] && [ "$SENTOK" -ge 1 ] 2>/dev/null \
  && ok "client sink received the structured payload (bidirectional loop closed)" \
  || { fail "client_push_received"; diagnose; }
[ "$(PSQL "SELECT count(*) >= 1 FROM connector_outbox WHERE status='sent'")" = "t" ] \
  && ok "outbox row marked sent" || fail "outbox_mark sent"

# --- 7f. IoT metrics intake (Phase 8 slice) ----------------------------------------
step "7f. IoT metrics → dashboard widget data"
HOOK metrics '{ "sensor": "smoke-sensor", "metrics": { "temperature": 18.4, "humidity": 46.5 } }' 30
STORED=$(echo "$BODY" | JGET "['stored']")
[ "$HTTP_CODE" = "200" ] && [ "$STORED" = "2" ] \
  && ok "metrics webhook stored 2 readings" || fail "metrics intake HTTP $HTTP_CODE — $(echo "$BODY" | head -c 200)"
[ "$(PSQL "SELECT (latest_metrics())::text LIKE '%smoke-sensor%'")" = "t" ] \
  && ok "latest_metrics() serves the readings" || fail "latest_metrics"
[ "$(PSQL "SELECT ingest_metric('{\"sensor\":\"x\",\"metrics\":{\"temperature\":\"oops\"}}'::jsonb)")" = "0" ] \
  && ok "non-numeric readings rejected (stored 0)" || fail "metric validation"

# --- 7g. Multi-page PDF ingest --------------------------------------------------
# A PDF must land as an ordinary multi-page document: one `pages` row per PDF page.
# The fixture carries a text layer, so those pages must come back with the exact
# text (no OCR). Uses the AI service's own fixture builder — no binary in the repo.
step "7g. Multi-page PDF ingest (split + text layer)"
PKEY="smoke-multipage-$(date +%s).pdf"
PDF_B64=$(docker compose exec -T ai-service python3 -c "
import base64, sys
from app.selftest import _tiny_pdf
sys.stdout.write(base64.b64encode(_tiny_pdf([
  ['ArchivAI smoke: multi-page PDF ingest, page one of the fixture.',
   'Sender: Domkov, secretary of the regional committee of the party.',
   'Recipient: comrade Kulpov, secretary of the central committee.',
   'This page carries a text layer, so the pipeline must skip OCR here.',
   'Each page is deliberately long enough to stay its own embedding chunk,',
   'which is what makes a long document findable by its individual parts.',
   'Comfortably above the merge threshold so the assertion below is stable.'],
  ['Page two of the smoke fixture, also carrying plenty of typed text.',
   'Protokol No 17, dated 19 February 1941, Alma-Ata region, archive stock.',
   'Both pages stay above PDF_TEXT_MIN_CHARS and above CHUNK_MIN_CHARS,',
   'so the document is stored as two pages and indexed as several chunks.',
   'The layout column on the right margin keeps this page two-dimensional,',
   'which is how the layout-preserving variant differs from reading order.',
   'Comfortably above the merge threshold so the assertion below is stable.'],
])).decode())" 2>/dev/null)

if [ -z "$PDF_B64" ]; then
  fail "could not build the PDF fixture (is ai-service up?)"
else
  docker compose run --rm --entrypoint /bin/sh minio-init -c \
    "mc alias set local http://minio:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null && \
     echo '$PDF_B64' | base64 -d > /tmp/s.pdf && mc cp /tmp/s.pdf local/\${MINIO_BUCKET:-scans}/$PKEY" \
    >/dev/null 2>&1 \
    && ok "2-page PDF stored in the scans bucket ($PKEY)" || fail "mc cp of the PDF fixture"

  PURL="http://minio:9000/${MINIO_BUCKET:-scans}/$PKEY"
  HOOK ingest "{ \"filename\": \"$PKEY\", \"original_url\": \"$PURL\",
    \"pages\": [ { \"image_url\": \"$PURL\" } ] }" 120
  PDOC=$(echo "$BODY" | JGET "['doc_id']")
  if [ -n "$PDOC" ]; then
    ok "PDF ingest accepted → doc_id=$PDOC"
    PST=""
    for i in $(seq 1 90); do
      PST=$(PSQL "SELECT status FROM documents WHERE id='$PDOC'")
      { [ "$PST" = "processed" ] || [ "$PST" = "failed" ]; } && break
      sleep 1
    done
    [ "$PST" = "processed" ] && ok "PDF pipeline finished (processed)" \
      || fail "PDF pipeline status=$PST — $(PSQL "SELECT left(process_error,200) FROM documents WHERE id='$PDOC'")"
    [ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC'")" = "2" ] \
      && ok "PDF split into 2 pages rows" \
      || fail "expected 2 pages rows, got $(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC'")"
    [ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC' AND ocr_text LIKE '%Domkov%'")" -ge 1 ] 2>/dev/null \
      && ok "PDF text layer used verbatim (no OCR on digital pages)" || fail "PDF text layer not in pages.ocr_text"
    [ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC' AND confidence = 1")" = "2" ] \
      && ok "text-layer pages stored with confidence 1.0" || fail "text-layer confidence"
    # display variant: same page with columns kept (the fixture has a right-margin stamp)
    [ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC' AND layout_text LIKE '%   %'")" = "2" ] \
      && ok "layout-preserving text stored per page" || fail "pages.layout_text"
    [ "$(PSQL "SELECT count(*) FROM pages WHERE document_id='$PDOC' AND layout_text <> ocr_text")" = "2" ] \
      && ok "layout text differs from the reading-order text used for search" || fail "layout vs reading order"
    # chunked embeddings: a long document must be findable by its individual parts,
    # not by one averaged vector (search and RAG both score the best chunk)
    NEMB=$(PSQL "SELECT count(*) FROM embeddings WHERE document_id='$PDOC'")
    [ "${NEMB:-0}" -ge 2 ] 2>/dev/null \
      && ok "document indexed as $NEMB chunks (one embedding per chunk)" \
      || fail "expected several chunk embeddings, got ${NEMB:-0}"
    [ "$(PSQL "SELECT count(DISTINCT chunk_no) = count(*) FROM embeddings WHERE document_id='$PDOC'")" = "t" ] \
      && ok "chunk numbers unique per document" || fail "chunk_no uniqueness"
    [ "$(PSQL "SELECT bool_and(length(content) > 0) FROM embeddings WHERE document_id='$PDOC'")" = "t" ] \
      && ok "every chunk stored with its text (citable in chat)" || fail "chunk content"
  else
    fail "PDF ingest response unexpected: $(echo "$BODY" | head -c 300)"
  fi
fi

# --- 8. Failure path -------------------------------------------------------------
step "8. Failure path (empty pages → background mark_failed)"
HOOK ingest '{ "filename": "smoke-failure.png", "pages": [] }' 60
FDOC=$(echo "$BODY" | JGET "['doc_id']")
{ [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "202" ]; } && [ -n "$FDOC" ] \
  && ok "ingest accepted (async)" || fail "expected 200/202+doc_id, got $HTTP_CODE — $(echo "$BODY" | head -c 200)"
FST=""
for i in $(seq 1 30); do
  FST=$(PSQL "SELECT status FROM documents WHERE id='$FDOC'")
  [ "$FST" = "failed" ] && break
  sleep 1
done
[ "$FST" = "failed" ] && ok "documents.status=failed" || fail "failed-status write (status=$FST)"
[ -n "$FDOC" ] && [ -n "$(PSQL "SELECT process_error FROM documents WHERE id='$FDOC'")" ] \
  && ok "process_error recorded" || fail "process_error"

# --- 9. AI service contract selftest ----------------------------------------------
step "9. AI service selftest"
# AI_STUB=1 forced: these are stub-contract checks, and the host may run real models.
docker compose exec -T -e AI_STUB=1 ai-service python -m app.selftest >/dev/null 2>&1 \
  && ok "app.selftest: all contract checks passed" || fail "app.selftest"

# --- Summary -----------------------------------------------------------------------
echo
echo "===================================================="
echo " SMOKE RESULT: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  printf ' failed: %s\n' "${FAILED_STEPS[@]}"
  echo "===================================================="
  exit 1
fi
echo " Pipeline is healthy end-to-end in stub mode."
echo " Go live: set AI_STUB=0 in .env, then:"
echo "   make up && make models"
echo "   docker compose up -d --force-recreate ai-service"
echo "===================================================="
