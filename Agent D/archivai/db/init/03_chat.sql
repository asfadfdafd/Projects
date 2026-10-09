-- "Ask ArchivAI" conversational RAG assistant: history + retrieval helpers.

CREATE TABLE IF NOT EXISTS chat_sessions (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id     UUID REFERENCES users(id),
  title       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content     TEXT NOT NULL,
  citations   JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{ref,document_id,filename}]
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);

-- Retrieve top-k grounding chunks for a query vector (with source doc for citations).
CREATE OR REPLACE FUNCTION rag_retrieve(q_vec vector, k INT DEFAULT 6)
RETURNS TABLE (chunk_id UUID, document_id UUID, filename TEXT, content TEXT, distance REAL) AS $$
  SELECT e.id, e.document_id, d.filename, e.content, (e.embedding <=> q_vec)::real
  FROM embeddings e
  JOIN documents d ON d.id = e.document_id
  ORDER BY e.embedding <=> q_vec
  LIMIT k;
$$ LANGUAGE sql;

-- Persist one Q&A turn; creates the session if p_session is NULL. Returns session id.
CREATE OR REPLACE FUNCTION log_chat_turn(
  p_session UUID, p_user UUID, p_question TEXT, p_answer TEXT, p_citations JSONB
) RETURNS UUID AS $$
DECLARE sid UUID;
BEGIN
  sid := p_session;
  IF sid IS NULL THEN
    INSERT INTO chat_sessions (user_id, title)
    VALUES (p_user, left(p_question, 80))
    RETURNING id INTO sid;
  END IF;
  INSERT INTO chat_messages (session_id, role, content) VALUES (sid, 'user', p_question);
  INSERT INTO chat_messages (session_id, role, content, citations)
    VALUES (sid, 'assistant', p_answer, COALESCE(p_citations, '[]'::jsonb));
  RETURN sid;
END; $$ LANGUAGE plpgsql;
