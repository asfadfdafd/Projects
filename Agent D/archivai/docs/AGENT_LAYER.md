# Phase 5 — Agentic Layer ("Agent D" flagship) · Spec

Status: **APPROVED 2026-07-16 (all four §8 decisions = recommended options) and
IMPLEMENTED.** Implementation deltas from the original proposal: dashboard widget
ids follow the real UI cards (6 ids — `top_entities` is one combined card, not two);
`create_document`/`search_documents` moved from `02_functions.sql` into
`06_preferences.sql` (their bodies read `get_config()`, which must exist first —
and n8n PG nodes stay single-function-call); the Archive page has no type-filter
dropdown, so taxonomy wiring covers extraction + the agent UI only.

## 1. What it is

A user tells ArchivAI in natural language how the system should behave —
*«сделай поиск более семантическим»*, *«убери таймлайн с дашборда, покажи топ-10»*,
*«добавь тип документа "протокол"»* — and an LLM agent applies it, no code, per user.
The competitor only *promised* this; we ship it.

**Principles (locked-decision compliant):**
- The LLM **never** writes SQL or touches the DB. It emits structured *actions*
  (`{key, patch}`); a Postgres function validates and applies them. Thin n8n,
  logic in PG, stateless AI service, open models only, deterministic stub mode.
- Single source of truth for "what is tunable" lives in **one** PG function
  (`agent_capabilities()`), used both to build the LLM prompt and to validate writes —
  prompt and validation can't drift apart.
- Every change is audit-logged with old→new values and is resettable.

## 2. Data model — `db/init/06_preferences.sql`

```sql
CREATE TABLE user_preferences (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id    UUID REFERENCES users(id) ON DELETE CASCADE,  -- NULL = global scope
  key        TEXT NOT NULL,                                -- 'search'|'dashboard'|'taxonomy'|'chat'
  value      JSONB NOT NULL,
  updated_by TEXT NOT NULL DEFAULT 'agent',                -- 'agent'|'user'|'system'
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- NULL-safe uniqueness (one row per scope+key):
CREATE UNIQUE INDEX uq_prefs_scope_key
  ON user_preferences (COALESCE(user_id,'00000000-0000-0000-0000-000000000000'::uuid), key);
```

Also: `ALTER TABLE chat_sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'rag'`
(`'rag'` | `'agent'`) — agent conversations reuse the existing chat tables for
multi-turn memory («ещё семантичнее» must work).

### PG functions (all logic here)

| Function | Purpose |
|---|---|
| `agent_capabilities() → jsonb` | Manifest: keys, fields, types, bounds, allowed enum values, RU descriptions. Fed into the LLM prompt **and** used by validation. |
| `get_config(p_user, p_key) → jsonb` | Effective config: hardcoded defaults ⊕ global row ⊕ user row (deep merge). |
| `get_all_config(p_user) → jsonb` | All keys merged — for UI and agent context. |
| `set_config(p_user, p_key, p_patch, p_actor) → jsonb` | **The only write path.** Whitelists key, validates each field against `agent_capabilities()` (numeric bounds, enum membership, array shape/length), deep-merges patch into the scope row, writes `audit_log` (`action='agent_set_config'`, detail = `{key, old, new, actor}`), returns effective config. Rejects unknown fields with a clear error. |
| `agent_apply(p_user, p_actions jsonb, p_actor) → jsonb` | Loops `set_config` over the agent's action array in one transaction; returns `[{key, old, new}]` diff. One PG call per agent turn — n8n stays thin. |
| `reset_config(p_user, p_key)` | Deletes scope row(s) → back to defaults. Audit-logged. |

## 3. What is agent-tunable in v1

Only behaviors that already exist end-to-end, so every change is *demonstrably real*:

### `search` (per-user)
```json
{ "vector_weight": 0.7, "keyword_weight": 0.3, "limit": 20, "snippet_source": "summary" }
```
Bounds: weights ∈ [0,1] (normalized to sum 1), limit 1–50, snippet_source ∈ summary|full_text.
Wiring: `search_documents()` gains `p_user UUID DEFAULT NULL` and reads weights/limit
from `get_config` (current 0.7/0.3/20 become the seeded defaults — zero behavior change
until the agent is used). n8n `2_search.json` passes `user_id` through.

### `dashboard` (per-user)
```json
{ "widgets": ["kpi_cards","entity_distribution","top_entities",
              "language_distribution","recent_activity","timeline"],
  "top_n": 5 }
```
Bounds: widgets ⊆ the whitelist above (order = display order), top_n 3–10.
Wiring: `compute_dashboard_stats()` computes top-10 lists (instead of top-5);
the dashboard page reads `/api/preferences` and renders/slices per config.
Stats data stays global and consistent — only *presentation* is per-user.

### `taxonomy` (global scope — affects the shared pipeline)
```json
{ "document_types": [
    {"id":"official_correspondence","label":"Официальная переписка"},
    {"id":"report","label":"Отчёт"}, {"id":"decree","label":"Приказ/постановление"},
    {"id":"article","label":"Статья"}, {"id":"list","label":"Список"} ] }
```
Bounds: 2–25 types, id = `[a-z0-9_]{2,40}` unique, label ≤ 60 chars.
Wiring: n8n `1_ingest_and_process.json` fetches the taxonomy (`get_config(NULL,'taxonomy')`)
and passes `taxonomy` to AI `/process`; `prompts.py` injects «classify as ONE of: …» into
the extraction prompt. Archive-page type filter reads the same list. Existing docs keep
their old labels (no retro-reclassification in v1; a "reprocess" action is Phase 8+).

### `chat` (per-user, cheap to include)
```json
{ "retrieve_k": 6, "style": "concise" }   // style: concise|detailed
```
Wiring: `3_chat.json` reads `retrieve_k` for `rag_retrieve`; `style` appended to the
answer prompt.

## 4. AI service — `POST /agent` (stateless)

```jsonc
// request
{ "message": "сделай поиск более семантическим",
  "history": [{"role":"user","content":"..."},{"role":"assistant","content":"..."}],  // last ~6
  "current_config": { ... },      // get_all_config(user)
  "capabilities": { ... } }       // agent_capabilities()
// response
{ "reply": "Готово: вес семантического поиска повышен до 0.9.",   // RU/KZ per user language
  "actions": [ {"key":"search","patch":{"vector_weight":0.9,"keyword_weight":0.1},
                "reason":"user asked for more semantic search"} ] }
```
- One LLM call, STRICT-JSON prompt (same hardening style as extraction: temperature 0,
  fence-stripping, regex JSON recovery). Pydantic validates shape; PG validates semantics.
- Small-model accommodation (observed live on qwen2.5:3b): for `taxonomy`, a patched
  `document_types` list with zero id-overlap against the current taxonomy is treated
  as *additive* (current types appended) instead of a (bound-violating) replacement —
  `_merge_additive_taxonomy()` in `agent.py`, plus a few-shot example in the prompt.
- Unactionable/off-scope requests → `actions: []` + honest reply listing what it *can* tune.
- **Stub mode:** deterministic keyword rules (семантич/вес → search; виджет/дашборд/убери →
  dashboard; тип/классифика → taxonomy; ответ/чат → chat) so `make smoke` fully exercises
  the loop with no model.
- Works on qwen2.5:3b (small-model-safe: tiny output schema, capabilities inlined compactly);
  quality scales up with the model like everything else.

**Why not the n8n native AI-Agent (LangChain) node:** unreliable tool-calling on small
local models, no stub determinism, and it moves logic out of PG into the canvas. Our
`/agent` endpoint keeps the established pattern; the *workflow* remains the visible
n8n showpiece. (Decision point — see §8.)

## 5. n8n workflow — `5_agent.json`, webhook `POST /webhook/agent`

```
Webhook: Agent  →  PG: Load Context   →  AI: /agent  →  PG: agent_apply(...)
{message,           SELECT get_all_config($u) cfg,          (validates+applies+audits,
 session_id?,              agent_capabilities() caps,        returns diff; [] if no actions)
 user_id}                  agent_history($s) hist                     ↓
                                                    PG: log turn (chat kind='agent')
                                                              ↓
                                        Respond: {session_id, reply, applied[], config}
```
6 nodes, mirrors `3_chat.json`. `agent_history(p_session)` = small SQL helper returning
the last N turns. Failure branch → HTTP 500 `{error}` (config untouched — apply is
transactional).

## 6. Web UI

- New page **`/agent`** («Agent» in the sidebar, flagged ⭐): chat-style panel
  (reuses chat components); each turn shows the reply plus **diff chips**
  (`search.vector_weight 0.7 → 0.9`); right column = live effective config as three
  cards (Search / Dashboard / Taxonomy) each with «Reset to defaults»; suggestion
  chips for first-time users (the three demo phrases).
- `/api/agent` proxy → n8n webhook (same pattern as `/api/chat`).
- `/api/preferences` (GET merged config; POST reset) — reads via SQL, writes via
  `reset_config` only.
- Dashboard + Archive pages start reading config (§3). Until Phase 6 auth, the acting
  user is the seeded demo user (existing `demoUserId()` pattern) — the schema is already
  per-user, so SSO later changes nothing here.

## 7. Verification

- `simulate_stub_pipeline.py`: cover w5 node JS + SQL signatures (same mechanical checks).
- `make smoke` additions (stub mode, live):
  1. agent turn «сделай поиск более семантическим» → assert `user_preferences` row,
     weights changed, `/webhook/search` still returns results;
  2. «убери таймлайн» → dashboard config widgets exclude `timeline`;
  3. taxonomy add → `get_config(NULL,'taxonomy')` contains new type; next `/ingest`
     passes it to `/process` (stub echoes taxonomy back for assertability);
  4. guardrail: direct `set_config` with out-of-bounds patch → SQL exception;
     unknown key → exception;
  5. `reset_config` → defaults restored; `audit_log` has the full old→new trail;
  6. multi-turn: second message «ещё сильнее» uses history.
- Live gate: `make full`, click-test `/agent`, then a real-model pass with qwen2.5:3b.

## 8. Decision points (need your call)

1. **Apply mode** — ✦recommended: apply immediately + diff chips + reset/undo
   (demo-wow; fully audit-logged). Alternative: agent proposes, user clicks «Apply».
2. **Tunable scope v1** — ✦recommended: search + dashboard + taxonomy + chat.
   Alternative: drop `chat` (the three from the transcript only).
3. **Agent engine** — ✦recommended: AI-service `/agent` endpoint (§4).
   Alternative: n8n native AI-Agent node (more "n8n-native" visually, but unreliable
   on 3b models, breaks stub determinism, moves logic out of PG).
4. **Taxonomy scope** — ✦recommended: global (it steers the shared extraction pipeline);
   per-user taxonomy would fork classification per viewer. Role-gating (admin-only)
   arrives naturally with Phase 6 auth.

## 10. Phase 5.5 — Custom widgets + Operator (direction approved 2026-07-16)

Rationale: v1 tunables ≈ a settings form behind NL. NL earns its keep where the user
*generates* things a form can't offer and where the agent *acts*, not just configures.
Same security model throughout: LLM picks templates/params, Postgres validates and owns
all SQL.

### A. Custom dashboard widgets from natural language
- New config key **`custom_widgets`** (scope: user, max 6):
  `{"widgets":[{"id","title","template","params"}]}`.
- **Template registry** lives inside `agent_capabilities()` (same single source for
  prompt + validation). v1 palette:
  - `doc_count` — docs grouped by `document_type|language|status`; donut/bar
  - `doc_timeline` — docs over time, optional `document_type` filter (validated against
    the live taxonomy), granularity `year|month`
  - `top_entities` — top-N `person|organization|place`, N ∈ 3..10
  - `kpi_count` — single number with optional `status/document_type/language` filter
- `set_config` validates template ∈ registry + params per template (enums/bounds/slug).
- **`widget_data(p_user)`** (new PG fn) computes data for every spec — parameterized
  queries are ours; the LLM never writes SQL. `GET /api/widgets` → `[{spec, data}]`;
  dashboard renders a "Custom widgets" section. Example: «добавь виджет: динамика
  приказов по годам» → `{template:"doc_timeline", params:{document_type:"decree",
  granularity:"year"}}`.

### B. Operator commands (agent acts via existing machinery)
- `AgentResponse` gains **`commands: [{tool, params, reason}]`**, validated against a
  tool registry (`agent_tools()` in SQL, same pattern):
  - `resolve_entities {}` → PG `resolve_entities()` (already built)
  - `recompute_stats {}` → PG `compute_dashboard_stats()`
  - `reprocess_documents {document_type?|status?, limit ≤ 20}` → re-ingest matching
    docs through the pipeline (n8n self-call to `/webhook/ingest` with pages from the
    `pages` table) — closes the taxonomy demo loop: add type → reclassify archive
  - `open_search {query}` → no server exec; UI renders a "открыть поиск" link
    (`/search?q=…` autorun)
- New PG **`agent_run(p_user, commands)`** executes PG-side tools + returns the
  reprocess candidate list for n8n to fan out; results shown as chips in the agent UI
  (⚙ resolve: merged 3 · ↻ reprocessed 12 docs · 🔎 открыть поиск).
- Compound intents: multi-action + multi-command per turn already supported
  (`agent_apply` + `agent_run`); prompt gains few-shot examples.

### C. Verification
Stub rules (deterministic): «слей дубликаты»→resolve · «пересчитай статистику»→
recompute · «найди/покажи документы про X»→open_search · «переклассифицируй»→
reprocess · «добавь виджет …»→doc_timeline spec. Smoke: widget spec lands in config +
`/api/widgets` returns data; resolve/recompute audit rows; reprocess flips statuses and
re-classifies after a taxonomy change; simulator gets w5 command-path + parity checks.

## 9. Deliverables checklist (implementation phase)

`db/init/06_preferences.sql` · `services/ai/app/agent.py` + prompt + schemas + stub +
selftest case · `n8n/workflows/5_agent.json` (fixed id `archivai-w5`) · patched
`search_documents` / `compute_dashboard_stats` / `2_search.json` / `1_ingest_and_process.json` /
`3_chat.json` · `web/pages/agent.js` + `/api/agent` + `/api/preferences` + dashboard/archive
config reads · smoke + simulator coverage · README/ROADMAP/DATA_MODEL updates.
