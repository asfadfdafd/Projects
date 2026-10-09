// Phase 5 — the flagship agentic layer: reconfigure ArchivAI in natural language.
// Each turn shows the agent's reply plus a diff of applied changes; the right
// column mirrors the live effective config with per-section reset.
import { useCallback, useEffect, useRef, useState } from "react";

const EXAMPLES = [
  "Сделай поиск более семантическим",
  "Добавь виджет: динамика приказов по годам",
  "Добавь тип документа «протокол» и переклассифицируй документы",
  "Слей дубликаты сущностей",
  "Покажи топ-10 вместо топ-5",
  "Отвечай в чате подробнее",
];

const KEY_LABELS = {
  search: "Search",
  dashboard: "Dashboard",
  custom_widgets: "Custom widgets",
  taxonomy: "Taxonomy",
  chat: "Ask ArchivAI",
};

// Shallow field diff between two flat config objects → [{field, from, to}]
function diffFields(oldCfg, newCfg) {
  const out = [];
  const keys = new Set([...Object.keys(oldCfg || {}), ...Object.keys(newCfg || {})]);
  for (const k of keys) {
    const a = JSON.stringify((oldCfg || {})[k]);
    const b = JSON.stringify((newCfg || {})[k]);
    if (a !== b) out.push({ field: k, from: (oldCfg || {})[k], to: (newCfg || {})[k] });
  }
  return out;
}

function short(v) {
  if (v === undefined || v === null) return "—";
  if (Array.isArray(v)) {
    const s = v.map((x) => (x && typeof x === "object" ? x.id || x.label || "?" : x)).join(", ");
    return s.length > 60 ? s.slice(0, 57) + "…" : s || "[]";
  }
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}

function AppliedDiff({ applied }) {
  // applied === undefined → not an agent turn (no hint); [] → agent changed nothing.
  if (!applied) return null;
  if (!applied.length) {
    return <div className="text-xs text-slate-400 mt-2">настройки не менялись</div>;
  }
  return (
    <div className="mt-2 space-y-1">
      {applied.map((a, i) => {
        if (!a.ok) {
          return (
            <div key={i} className="text-xs text-red-600">
              ✕ {a.key}: {a.error}
            </div>
          );
        }
        const diffs = diffFields(a.old, a.new);
        if (!diffs.length) {
          return (
            <div key={i} className="text-xs text-slate-400">
              = {a.key}: значения уже были такими — без изменений
            </div>
          );
        }
        return diffs.map((d) => (
          <div key={i + "." + d.field} className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="chip bg-emerald-50 border border-emerald-200 text-emerald-700">
              {a.key}.{d.field}
            </span>
            <span className="text-slate-400 line-through">{short(d.from)}</span>
            <span className="text-slate-400">→</span>
            <span className="text-slate-700 font-medium">{short(d.to)}</span>
          </div>
        ));
      })}
    </div>
  );
}

// Operator command results (Phase 5.5): what the agent RAN, not just configured.
function RanChips({ ran }) {
  if (!ran || !ran.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {ran.map((r, i) => {
        if (!r.ok) {
          return (
            <div key={i} className="text-xs text-red-600">
              ✕ {r.tool}: {r.error}
            </div>
          );
        }
        const x = r.result || {};
        if (r.tool === "open_search") {
          return (
            <a
              key={i}
              href={"/search?q=" + encodeURIComponent(x.query || "")}
              className="chip bg-white border border-slate-300 text-slate-600 hover:border-accent-500 hover:text-accent-600 inline-flex"
            >
              🔎 открыть поиск: {x.query}
            </a>
          );
        }
        const label =
          r.tool === "resolve_entities"
            ? "⚙ дубликаты: слито " + (x.merged != null ? x.merged : "?")
            : r.tool === "recompute_stats"
            ? "⚙ статистика пересчитана"
            : r.tool === "reprocess_documents"
            ? "↻ на переобработку: " + (x.count != null ? x.count : "?") + " док."
            : "⚙ " + r.tool;
        return (
          <div key={i} className="chip bg-sky-50 border border-sky-200 text-sky-700 inline-flex mr-1.5">
            {label}
          </div>
        );
      })}
    </div>
  );
}

function ConfigCard({ title, cfg, onReset, busy }) {
  if (!cfg) return null;
  return (
    <div className="card p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-semibold text-slate-700 uppercase tracking-wide">{title}</div>
        <button
          className="text-[11px] text-slate-400 hover:text-accent-600 disabled:opacity-40"
          onClick={onReset}
          disabled={busy}
          title="reset to defaults"
        >
          reset
        </button>
      </div>
      <dl className="space-y-1">
        {Object.entries(cfg).map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-2 text-xs">
            <dt className="text-slate-400 shrink-0">{k}</dt>
            <dd className="text-slate-700 text-right break-words min-w-0">{short(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function Agent() {
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [config, setConfig] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  const loadConfig = useCallback(async () => {
    try {
      const r = await fetch("/api/preferences");
      const j = await r.json();
      if (r.ok) setConfig(j.config);
    } catch (e) { /* card just stays empty */ }
  }, []);

  useEffect(() => { loadConfig(); }, [loadConfig]);
  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text) => {
    const message = (text || input).trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setBusy(true);
    try {
      const r = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message, session_id: sessionId }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "agent failed");
      if (j.session_id) setSessionId(j.session_id);
      if (j.config) setConfig(j.config);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: j.reply, applied: j.applied || [], ran: j.ran || [] },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "⚠ " + String(e.message || e), error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const reset = async (key) => {
    setBusy(true);
    try {
      const r = await fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset: key }),
      });
      const j = await r.json();
      if (r.ok) {
        setConfig(j.config);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: key
              ? `Настройки «${KEY_LABELS[key] || key}» сброшены к значениям по умолчанию.`
              : "Все настройки сброшены к значениям по умолчанию.",
          },
        ]);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex gap-6" style={{ minHeight: "calc(100vh - 48px)" }}>
      <div className="flex-1 min-w-0 flex flex-col max-w-3xl">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              Agent <span className="text-accent-500">⭐</span>
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Reconfigure search, dashboard, taxonomy and chat in natural language —
              no code. Changes apply instantly, are audit-logged and resettable.
            </p>
          </div>
          {messages.length > 0 && (
            <button className="btn-secondary" onClick={() => { setMessages([]); setSessionId(null); }}>
              New conversation
            </button>
          )}
        </div>

        <div className="flex-1 space-y-4 mb-4">
          {messages.length === 0 && (
            <div className="card p-8 text-center">
              <div className="text-3xl mb-3">🛠️</div>
              <div className="text-sm text-slate-600 mb-4">
                Скажите, как система должна работать — агент применит настройку и
                покажет, что именно изменилось.
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
                {m.role === "assistant" && <RanChips ran={m.ran} />}
                {m.role === "assistant" &&
                  <AppliedDiff applied={m.ran && m.ran.length && m.applied && !m.applied.length ? undefined : m.applied} />}
              </div>
            </div>
          ))}

          {busy && (
            <div className="flex justify-start">
              <div className="rounded-2xl px-4 py-3 bg-white border border-slate-200 text-slate-400 text-sm">
                configuring…
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="sticky bottom-4">
          <div className="card p-2 flex gap-2 shadow-md">
            <input
              className="input flex-1 border-0 focus:ring-0"
              placeholder="Например: сделай поиск более семантическим…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
            />
            <button className="btn-primary" disabled={busy || !input.trim()} onClick={() => send()}>
              Send
            </button>
          </div>
          <div className="text-[11px] text-slate-400 mt-1 px-1">
            The LLM only proposes actions — every change is validated and written by
            Postgres set_config(), with the old→new trail in audit_log.
          </div>
        </div>
      </div>

      <aside className="w-72 shrink-0 hidden lg:block">
        <div className="sticky top-6 space-y-3">
          <div className="flex items-center justify-between px-1">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Effective config
            </div>
            <button
              className="text-[11px] text-slate-400 hover:text-accent-600 disabled:opacity-40"
              onClick={() => reset(null)}
              disabled={busy}
            >
              reset all
            </button>
          </div>
          {!config && <div className="text-sm text-slate-300 px-1">loading…</div>}
          {config &&
            Object.entries(KEY_LABELS).map(([key, label]) => (
              <ConfigCard
                key={key}
                title={label}
                cfg={config[key]}
                onReset={() => reset(key)}
                busy={busy}
              />
            ))}
        </div>
      </aside>
    </div>
  );
}
