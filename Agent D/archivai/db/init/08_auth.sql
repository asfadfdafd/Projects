-- Phase 6 — local auth (SSO-ready), sessions, search history, usage/compliance.
-- All logic here (pgcrypto); Node is a thin cookie courier. Spec: docs/PHASE6_AUTH.md.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'local';

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,               -- sha256(raw cookie token); raw never stored
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ip         INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS search_history (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
  query        TEXT NOT NULL,
  result_count INT,
  ip           INET,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id, created_at DESC);

-- tolerant inet cast (proxies can hand us junk; never fail a login over it)
CREATE OR REPLACE FUNCTION safe_inet(t TEXT) RETURNS INET AS $$
BEGIN
  RETURN NULLIF(trim(COALESCE(t, '')), '')::inet;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END; $$ LANGUAGE plpgsql IMMUTABLE;

-- NULL actor = trusted internal path (smoke, n8n network); real users need the role.
CREATE OR REPLACE FUNCTION is_admin(p_user UUID) RETURNS BOOLEAN AS $$
  SELECT p_user IS NULL
         OR EXISTS (SELECT 1 FROM users WHERE id = p_user AND role = 'admin');
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- Accounts & sessions
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION register_user(p_email TEXT, p_password TEXT,
                                         p_display TEXT, p_role TEXT, p_actor UUID)
RETURNS UUID AS $$
DECLARE new_id UUID;
BEGIN
  IF NOT is_admin(p_actor) THEN
    RAISE EXCEPTION 'only an admin can register users';
  END IF;
  IF p_role NOT IN ('admin', 'reviewer') THEN
    RAISE EXCEPTION 'role must be admin or reviewer';
  END IF;
  IF length(COALESCE(p_password, '')) < 6 THEN
    RAISE EXCEPTION 'password must be at least 6 characters';
  END IF;
  INSERT INTO users (email, display_name, role, password_hash)
  VALUES (lower(trim(p_email)), NULLIF(trim(COALESCE(p_display, '')), ''),
          p_role, crypt(p_password, gen_salt('bf')))
  RETURNING id INTO new_id;
  INSERT INTO audit_log (actor, action, target_type, target_id, detail)
  VALUES (p_actor, 'register_user', 'user', new_id,
          jsonb_build_object('email', lower(trim(p_email)), 'role', p_role));
  RETURN new_id;
END; $$ LANGUAGE plpgsql;

-- Returns the RAW session token (cookie value) or NULL on bad credentials.
CREATE OR REPLACE FUNCTION login(p_email TEXT, p_password TEXT, p_ip TEXT, p_ua TEXT)
RETURNS TEXT AS $$
DECLARE u users%ROWTYPE; tok TEXT;
BEGIN
  SELECT * INTO u FROM users WHERE email = lower(trim(p_email));
  IF NOT FOUND OR u.password_hash IS NULL
     OR u.password_hash <> crypt(COALESCE(p_password, ''), u.password_hash) THEN
    INSERT INTO audit_log (actor, action, target_type, detail)
    VALUES (NULL, 'login_failed', 'auth',
            jsonb_build_object('email', lower(trim(COALESCE(p_email, ''))), 'ip', p_ip));
    RETURN NULL;
  END IF;
  tok := encode(gen_random_bytes(32), 'hex');
  INSERT INTO sessions (token_hash, user_id, ip, user_agent, expires_at)
  VALUES (encode(digest(tok, 'sha256'), 'hex'), u.id, safe_inet(p_ip),
          left(COALESCE(p_ua, ''), 300), now() + interval '7 days');
  INSERT INTO audit_log (actor, action, target_type, detail)
  VALUES (u.id, 'login', 'auth', jsonb_build_object('ip', p_ip));
  RETURN tok;
END; $$ LANGUAGE plpgsql;

-- Cookie token -> user (rolling 7-day expiry). Empty result = not authenticated.
CREATE OR REPLACE FUNCTION auth_user(p_token TEXT)
RETURNS TABLE (id UUID, email TEXT, display_name TEXT, role TEXT) AS $$
DECLARE h TEXT := encode(digest(COALESCE(p_token, ''), 'sha256'), 'hex');
BEGIN
  DELETE FROM sessions WHERE expires_at <= now();
  UPDATE sessions SET expires_at = now() + interval '7 days' WHERE token_hash = h;
  RETURN QUERY
    SELECT u.id, u.email, u.display_name, u.role
    FROM sessions s JOIN users u ON u.id = s.user_id
    WHERE s.token_hash = h;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION logout(p_token TEXT) RETURNS VOID AS $$
DECLARE h TEXT := encode(digest(COALESCE(p_token, ''), 'sha256'), 'hex');
        uid UUID;
BEGIN
  DELETE FROM sessions WHERE token_hash = h RETURNING user_id INTO uid;
  IF uid IS NOT NULL THEN
    INSERT INTO audit_log (actor, action, target_type) VALUES (uid, 'logout', 'auth');
  END IF;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION change_password(p_user UUID, p_old TEXT, p_new TEXT)
RETURNS VOID AS $$
DECLARE u users%ROWTYPE;
BEGIN
  SELECT * INTO u FROM users WHERE id = p_user;
  IF NOT FOUND OR u.password_hash IS NULL
     OR u.password_hash <> crypt(COALESCE(p_old, ''), u.password_hash) THEN
    RAISE EXCEPTION 'current password is incorrect';
  END IF;
  IF length(COALESCE(p_new, '')) < 6 THEN
    RAISE EXCEPTION 'new password must be at least 6 characters';
  END IF;
  UPDATE users SET password_hash = crypt(p_new, gen_salt('bf')) WHERE id = p_user;
  INSERT INTO audit_log (actor, action, target_type) VALUES (p_user, 'change_password', 'auth');
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- Search history + document views (compliance trail)
-- ----------------------------------------------------------------------------
-- Search + history in ONE call (n8n single-function-call rule).
CREATE OR REPLACE FUNCTION search_and_log(q_vec vector, q_text TEXT,
                                          p_user UUID DEFAULT NULL, p_ip TEXT DEFAULT NULL)
RETURNS TABLE (document_id UUID, filename TEXT, document_type TEXT, date_text TEXT,
               score REAL, snippet TEXT) AS $$
DECLARE v_cnt INT;
BEGIN
  RETURN QUERY SELECT * FROM search_documents(q_vec, q_text, p_user);
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF trim(COALESCE(q_text, '')) <> '' THEN
    INSERT INTO search_history (user_id, query, result_count, ip)
    VALUES (p_user, left(trim(q_text), 300), v_cnt, safe_inet(p_ip));
  END IF;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recent_searches(p_user UUID, k INT DEFAULT 8)
RETURNS TABLE (query TEXT, last_at TIMESTAMPTZ) AS $$
  SELECT h.query, max(h.created_at) AS last_at
  FROM search_history h
  WHERE (p_user IS NULL AND h.user_id IS NULL) OR h.user_id = p_user
  GROUP BY h.query ORDER BY last_at DESC LIMIT k;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION log_doc_view(p_user UUID, p_doc UUID) RETURNS VOID AS $$
BEGIN
  INSERT INTO audit_log (actor, action, target_type, target_id)
  VALUES (p_user, 'view_document', 'document', p_doc);
END; $$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- Usage / compliance analytics — one source for the admin /usage page.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION usage_stats() RETURNS JSONB AS $$
  SELECT jsonb_build_object(
    'totals', jsonb_build_object(
      'users',    (SELECT count(*) FROM users),
      'searches', (SELECT count(*) FROM search_history),
      'doc_views',(SELECT count(*) FROM audit_log WHERE action = 'view_document'),
      'logins',   (SELECT count(*) FROM audit_log WHERE action = 'login')),
    'active_sessions', (SELECT COALESCE(jsonb_agg(x), '[]'::jsonb) FROM
      (SELECT u.email, u.role, s.ip::text, s.created_at
       FROM sessions s JOIN users u ON u.id = s.user_id
       WHERE s.expires_at > now() ORDER BY s.created_at DESC LIMIT 20) x),
    'searches_per_day', (SELECT COALESCE(jsonb_agg(jsonb_build_object('day', g.d, 'n', g.n)
                                                   ORDER BY g.d), '[]'::jsonb) FROM
      (SELECT to_char(created_at, 'YYYY-MM-DD') AS d, count(*) AS n
       FROM search_history WHERE created_at > now() - interval '14 days'
       GROUP BY 1) g),
    'top_queries', (SELECT COALESCE(jsonb_agg(x), '[]'::jsonb) FROM
      (SELECT jsonb_build_object('query', query, 'n', count(*)) AS x
       FROM search_history WHERE created_at > now() - interval '30 days'
       GROUP BY query ORDER BY count(*) DESC LIMIT 10) s),
    'top_documents', (SELECT COALESCE(jsonb_agg(x), '[]'::jsonb) FROM
      (SELECT jsonb_build_object('document_id', a.target_id, 'filename', d.filename,
                                 'n', count(*)) AS x
       FROM audit_log a JOIN documents d ON d.id = a.target_id
       WHERE a.action = 'view_document' AND a.created_at > now() - interval '30 days'
       GROUP BY a.target_id, d.filename ORDER BY count(*) DESC LIMIT 10) s),
    'recent_logins', (SELECT COALESCE(jsonb_agg(x), '[]'::jsonb) FROM
      (SELECT jsonb_build_object('at', a.created_at, 'ok', a.action = 'login',
                                 'email', COALESCE(u.email, a.detail->>'email'),
                                 'ip', a.detail->>'ip') AS x
       FROM audit_log a LEFT JOIN users u ON u.id = a.actor
       WHERE a.action IN ('login', 'login_failed')
       ORDER BY a.created_at DESC LIMIT 20) s)
  );
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- Seed: give the demo user a password so `make full` stays one-command.
-- Default login: demo@archivai.local / archivai-demo  (change via change_password).
-- ----------------------------------------------------------------------------
UPDATE users SET password_hash = crypt('archivai-demo', gen_salt('bf'))
WHERE email = 'demo@archivai.local' AND password_hash IS NULL;
