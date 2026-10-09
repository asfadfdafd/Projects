# Phase 6 — Auth, Profiles & Compliance · Spec

Status: **APPROVED 2026-07-18 (all three §7 decisions = recommended) and IMPLEMENTED**
(`08_auth.sql`, `lib/auth.js`, `/login`, `/usage`, session-user swap across all API
routes, `search_and_log` in w2, admin gates in `set_config`/`agent_run`,
`AUTH_OPTIONAL` dev flag). Live gate: `make smoke` (step 7d) + `make web-rebuild` +
login click-test with `AUTH_OPTIONAL=0`.

Competitor promises to match (transcript §6.2): per-user profiles + SSO, personalized
search behavior, per-user search history, compliance/usage analytics (queries, top
documents, active users, **IPs**).

## 1. Approach

**Local auth first, SSO-ready.** The client's SSO provider is still an open question
(HANDOFF §6), so v1 ships email+password with the schema and routes shaped so OIDC
drops in later without migration (`users.auth_provider`, nullable `password_hash`,
callback route reserved). Same locked pattern as everything else: **all logic in
Postgres functions** (pgcrypto), Node is a thin cookie courier; **thin n8n**; no new
external dependencies (no next-auth, no bcrypt binary — pgcrypto `crypt()/bf`).

## 2. Schema — `db/init/08_auth.sql`

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'local';
-- password_hash already exists (01_schema)

CREATE TABLE sessions (
  token_hash  TEXT PRIMARY KEY,          -- sha256 of the cookie token (raw never stored)
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ip          INET, user_agent TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL       -- rolling 7 days
);

CREATE TABLE search_history (
  id UUID PK, user_id UUID REFERENCES users, query TEXT NOT NULL,
  result_count INT, ip INET, created_at TIMESTAMPTZ DEFAULT now()
);
-- document views land in audit_log (action='view_document') — no new table.
```

### PG functions (pgcrypto)

| Function | Purpose |
|---|---|
| `register_user(email, password, display_name, role)` | admin-only creation; `crypt(pw, gen_salt('bf'))`; audit-logged |
| `login(email, password, ip, ua) → token` | verifies, creates session (random token; stores sha256), audit `action='login'` with IP; NULL on failure (+ audit `login_failed`) |
| `auth_user(token) → users row` | resolves cookie → user; bumps rolling expiry; NULL if expired |
| `logout(token)` | deletes session, audit-logged |
| `change_password(user, old, new)` | self-service |
| `log_search(user, query, count, ip)` | called from the search workflow |
| `usage_stats() → jsonb` | one source for the admin page: searches/day, top queries, top documents (views from audit_log), active users (live sessions), recent logins **with IPs**, per-user activity |

Seeded demo user gets a default password (env `DEMO_PASSWORD`, default printed in
README) so `make full` remains one-command.

## 3. Web

- **`/login`** page; httpOnly cookie `archivai_session` (raw token; DB stores hash).
- `lib/auth.js` → `requireUser(req,res)` / `requireAdmin(req,res)`: every existing
  API route swaps `demoUserId()` for the session user (the per-user preferences,
  chat, agent scopes light up for real — schema was per-user since Phase 5).
- Layout: real user name + role + Logout instead of the hardcoded "Demo User";
  pages redirect to `/login` when no session.
- **`/usage`** (admin-only): searches/day sparkline, top queries, most-viewed
  documents, active users, login/IP table — the compliance screen the client asked for.
- Document Detail API logs `view_document` (per-user top-docs need it).

## 4. n8n

- `2_search.json`: the single PG call becomes `search_and_log(vec, q, user, ip)`
  (wraps `search_documents` + `log_search`; still one function call — simulator rule).
  `/api/search` passes the session user + request IP.
- `/search` page: "recent searches" chips per user (from `search_history`) — the
  personalization v1; ranking personalization stays Phase 8 (learning).

## 5. Role gating (first real use of `users.role`)

- `admin`: register users, `/usage`, global-scope config (taxonomy), reprocess.
- `reviewer`: verify/edit documents, everything else per-user.
- Enforced in the API layer now; `set_config`/`agent_run` gain an optional
  `p_role` check later if needed (agent webhook is inside the trusted network).

## 6. Verification

Smoke additions: register→login→cookie→`auth_user` roundtrip in SQL; failed login
audited; `log_search` row with IP after a search; `usage_stats()` returns all keys;
expired-session rejected. Simulator: w2 contract update (`search_and_log`).
Live: login flow click-test, `/usage` renders, recent-search chips.

## 7. Decision points

1. **Auth v1**: local email+password, SSO-ready (recommended — client's provider
   unknown) · or build OIDC now (need provider choice today).
2. **Gate the whole app?** Login required everywhere (recommended: real demo story,
   matches compliance pitch) · or `AUTH_OPTIONAL=1` dev flag that auto-logs-in the
   demo user (kept in `.env.example` for dev, off in demos).
3. **Role gating v1**: admin-only for taxonomy + reprocess + `/usage` (recommended)
   · or everyone-can-everything until the client defines roles.
