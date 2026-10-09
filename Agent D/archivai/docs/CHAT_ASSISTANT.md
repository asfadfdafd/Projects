# "Ask ArchivAI" — conversational RAG assistant

A chat interface that answers natural-language questions grounded in the archive, **with
citations** to source documents. Agent D does not have this (its search only returns document
lists), so it's a headline differentiator. Everything runs on the same open-source models.

## Pipeline (n8n workflow `3_chat.json`, webhook `POST /webhook/chat`)

```
question ─▶ AI /embed ─▶ PG rag_retrieve(top 6) ─▶ Build contexts ─▶ AI /answer ─▶ PG log_chat_turn ─▶ respond
```

1. **Embed** the question (bge-m3) via the AI service `/embed`.
2. **Retrieve** the 6 nearest chunks from `embeddings` via `rag_retrieve(q_vec, k)` (pgvector
   cosine). Each row carries `document_id` + `filename` for citation.
3. **Build contexts** — number them `[1..k]` as `{ref, document_id, filename, text}`.
4. **Answer** via the AI service `/answer`: the LLM (Qwen2.5) is prompted (`ANSWER_SYSTEM`) to
   respond **only from the passages**, cite each claim with its `[ref]`, reply in the question's
   language, and say "not found" when unsupported. The service returns `{answer, citations,
   grounded}` (citations are parsed from the `[ref]` markers).
5. **Persist** the turn with `log_chat_turn(session, user, question, answer, citations)` —
   creates the session on first turn; stores user + assistant messages (`chat_sessions`,
   `chat_messages`).
6. **Respond** with `{session_id, answer, citations, grounded}`.

## Contracts

- AI service `POST /answer`
  - in: `{ question, contexts:[{ref, document_id, filename, text}], history? }`
  - out: `{ answer, citations:[{ref, document_id, filename}], grounded }`
- Data: `chat_sessions(id, user_id, title)`, `chat_messages(id, session_id, role, content, citations)`.

## Design notes / next steps

- **Grounded + honest:** `grounded=false` and an explicit "not in the archive" reply when no
  passage supports an answer — no hallucination.
- **Citations open the document** in the UI (a 4th navigation path beside search→doc, entity→doc,
  and the document list).
- **Reuses `embeddings`** — build it right after semantic search (Phase 3b).
- **To extend:** feed `history` for multi-turn follow-ups; add **knowledge-graph expansion**
  (pull co-occurring entities/docs to widen context); stream tokens to the chat panel; scope
  retrieval by the user's access/profile.
- **Test offline:** with `AI_STUB=1`, `/answer` returns a deterministic cited answer so the whole
  `/chat` workflow (retrieve → answer → persist) can be validated without models.

## Try it

```bash
curl -X POST http://localhost:5678/webhook/chat \
  -H 'Content-Type: application/json' \
  -d '{ "question": "Что известно об Абае Кунанбаеве?", "user_id": null, "session_id": null }'
# -> { "session_id": "...", "answer": "... [1][2]", "citations": [...], "grounded": true }
```
