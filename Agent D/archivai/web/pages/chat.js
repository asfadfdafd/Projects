import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const EXAMPLES = [
  "Что известно об Абае Кунанбаеве?",
  "Кто переписывался с обкомом в 1940 году?",
  "Какие организации упоминаются чаще всего?",
];

function Citations({ citations }) {
  if (!citations || !citations.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {citations.map((c) => (
        <Link
          key={c.ref}
          href={c.document_id ? "/documents/" + c.document_id : "/documents"}
          className="chip bg-white border border-slate-300 text-slate-600 hover:border-accent-500 hover:text-accent-600"
          title="open source document"
        >
          [{c.ref}] {c.filename || "document"}
        </Link>
      ))}
    </div>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text) => {
    const question = (text || input).trim();
    if (!question || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, session_id: sessionId }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "chat failed");
      if (j.session_id) setSessionId(j.session_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: j.answer,
          citations: j.citations || [],
          grounded: j.grounded,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "⚠ " + String(e.message || e), grounded: false, error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setMessages([]);
    setSessionId(null);
  };

  return (
    <div className="max-w-3xl flex flex-col" style={{ minHeight: "calc(100vh - 48px)" }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Ask ArchivAI</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Answers come only from your archive, with citations — a feature Agent D doesn&apos;t have.
          </p>
        </div>
        {messages.length > 0 && (
          <button className="btn-secondary" onClick={reset}>New conversation</button>
        )}
      </div>

      <div className="flex-1 space-y-4 mb-4">
        {messages.length === 0 && (
          <div className="card p-8 text-center">
            <div className="text-3xl mb-3">🗂️</div>
            <div className="text-sm text-slate-600 mb-4">
              Ask about people, places and events — the assistant retrieves relevant passages
              and answers with sources you can open.
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  className="chip bg-white border border-slate-300 text-slate-600 hover:border-accent-500 cursor-pointer"
                  onClick={() => send(ex)}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={"flex " + (m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={
                "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed " +
                (m.role === "user"
                  ? "bg-navy-800 text-white"
                  : m.error
                  ? "bg-red-50 border border-red-200 text-red-700"
                  : "bg-white border border-slate-200 text-slate-800")
              }
            >
              <div className="whitespace-pre-wrap">{m.content}</div>
              {m.role === "assistant" && !m.error && m.grounded === false && (
                <div className="text-xs text-amber-600 mt-2">
                  not found in the archive — no sources to cite
                </div>
              )}
              {m.role === "assistant" && <Citations citations={m.citations} />}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-3 bg-white border border-slate-200 text-slate-400 text-sm">
              retrieving &amp; answering…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="sticky bottom-4">
        <div className="card p-2 flex gap-2 shadow-md">
          <input
            className="input flex-1 border-0 focus:ring-0"
            placeholder="Ask about the archive… (любой язык)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
          />
          <button className="btn-primary" disabled={busy || !input.trim()} onClick={() => send()}>
            Send
          </button>
        </div>
        <div className="text-[11px] text-slate-400 mt-1 px-1">
          Multi-turn memory per session is persisted (chat_sessions / chat_messages).
        </div>
      </div>
    </div>
  );
}
