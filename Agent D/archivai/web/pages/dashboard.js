import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const TYPE_COLORS = {
  person: "#3b82f6",
  organization: "#22c55e",
  date: "#f59e0b",
  place: "#a855f7",
  quantity: "#94a3b8",
};
const TYPE_LABELS = {
  person: "People",
  organization: "Organizations",
  date: "Dates",
  place: "Places",
  quantity: "Quantities",
};

// Agent-managed defaults (mirrors default_config('dashboard') in 06_preferences.sql)
const DEFAULT_DASHBOARD = {
  widgets: ["kpi_cards", "entity_distribution", "top_entities",
            "language_distribution", "recent_activity", "storage_env", "timeline"],
  top_n: 5,
};

// Archival storage norms → status colors (client-requested IoT widget)
function envStatus(metric, v) {
  const val = Number(v);
  if (metric === "temperature") {
    if (val >= 16 && val <= 20) return "text-emerald-600";
    if (val >= 14 && val <= 23) return "text-amber-600";
    return "text-red-600";
  }
  if (metric === "humidity") {
    if (val >= 40 && val <= 55) return "text-emerald-600";
    if (val >= 30 && val <= 65) return "text-amber-600";
    return "text-red-600";
  }
  return "text-slate-800";
}
const METRIC_LABELS = { temperature: "Температура", humidity: "Влажность" };

function Donut({ distribution }) {
  const entries = Object.keys(TYPE_COLORS)
    .map((t) => ({ type: t, n: (distribution && distribution[t]) || 0 }))
    .filter((e) => e.n > 0);
  const total = entries.reduce((s, e) => s + e.n, 0);
  if (!total) {
    return <div className="text-sm text-slate-400 py-10 text-center">no entities yet</div>;
  }
  const R = 40;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex items-center gap-6">
      <svg viewBox="0 0 100 100" className="h-36 w-36 -rotate-90">
        {entries.map((e) => {
          const frac = e.n / total;
          const seg = (
            <circle
              key={e.type}
              cx="50"
              cy="50"
              r={R}
              fill="none"
              stroke={TYPE_COLORS[e.type]}
              strokeWidth="14"
              strokeDasharray={frac * C + " " + C}
              strokeDashoffset={-offset * C}
            />
          );
          offset += frac;
          return seg;
        })}
      </svg>
      <div className="space-y-1.5">
        <div className="text-xs text-slate-400 mb-1">Total: {total}</div>
        {entries.map((e) => (
          <div key={e.type} className="flex items-center gap-2 text-sm text-slate-600">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLORS[e.type] }} />
            {TYPE_LABELS[e.type]} <b className="text-slate-800">{e.n}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopList({ title, items, color }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">{title}</div>
      {(!items || !items.length) && <div className="text-sm text-slate-300">—</div>}
      <ul className="space-y-1.5">
        {(items || []).map((p, i) => (
          <li key={i} className="flex items-center justify-between gap-2 text-sm">
            <span className={"truncate " + color}>{p.name}</span>
            <span className="text-xs text-slate-400 shrink-0">{p.docs} doc{p.docs === 1 ? "" : "s"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// One agent-built custom widget (Phase 5.5): bar-list rendering fits all templates.
function CustomWidget({ w, onRemove }) {
  const rows = Array.isArray(w.data) ? w.data : null;
  const kpi = w.data && !rows ? w.data.n : null;
  const max = rows ? Math.max(1, ...rows.map((r) => r.n)) : 1;
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2 mb-3">
        <h2 className="text-sm font-semibold text-slate-800">
          {w.title}
          <span className="ml-2 chip bg-accent-500/10 border border-accent-500/30 text-accent-600">
            agent
          </span>
        </h2>
        <button
          className="text-slate-300 hover:text-red-500 text-sm leading-none"
          title="remove widget"
          onClick={onRemove}
        >
          ✕
        </button>
      </div>
      {w.error && <div className="text-xs text-red-600">{w.error}</div>}
      {kpi !== null && kpi !== undefined && (
        <div className="text-3xl font-semibold text-slate-900">{kpi}</div>
      )}
      {rows && !rows.length && <div className="text-sm text-slate-300">no data yet</div>}
      {rows && rows.length > 0 && (
        <div className="space-y-1.5">
          {rows.map((r, i) => (
            <div key={i}>
              <div className="flex justify-between text-sm text-slate-600 mb-0.5">
                <span className="truncate">{r.label}</span>
                <span className="text-slate-400 shrink-0 ml-2">{r.n}</span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent-500"
                  style={{ width: Math.round((r.n / max) * 100) + "%" }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [cfg, setCfg] = useState(DEFAULT_DASHBOARD);
  const [custom, setCustom] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (recompute) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/dashboard", { method: recompute ? "POST" : "GET" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "failed to load stats");
      setData(j);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }, []);

  // Per-user widget layout comes from the agent-managed config (Phase 5);
  // the stats themselves stay global and consistent.
  const loadCfg = useCallback(async () => {
    try {
      const r = await fetch("/api/preferences");
      const j = await r.json();
      if (r.ok && j.config && j.config.dashboard) setCfg(j.config.dashboard);
    } catch (e) { /* fall back to defaults */ }
  }, []);

  const loadCustom = useCallback(async () => {
    try {
      const r = await fetch("/api/widgets");
      const j = await r.json();
      if (r.ok) setCustom(j.widgets || []);
    } catch (e) { /* section just stays empty */ }
  }, []);

  const [env, setEnv] = useState([]);
  const loadEnv = useCallback(async () => {
    try {
      const r = await fetch("/api/metrics");
      const j = await r.json();
      if (r.ok) setEnv(j.metrics || []);
    } catch (e) { /* card shows "no sensors" */ }
  }, []);
  useEffect(() => {
    loadEnv();
    const t = setInterval(loadEnv, 15000); // live readings for the demo
    return () => clearInterval(t);
  }, [loadEnv]);

  const removeWidget = async (id) => {
    try {
      const r = await fetch("/api/widgets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remove: id }),
      });
      const j = await r.json();
      if (r.ok) setCustom(j.widgets || []);
    } catch (e) { /* keep current list */ }
  };

  useEffect(() => { load(false); loadCfg(); loadCustom(); }, [load, loadCfg, loadCustom]);

  const s = (data && data.stats) || null;
  const langs = s ? Object.entries(s.language_distribution || {}) : [];
  const langTotal = langs.reduce((sum, kv) => sum + kv[1], 0) || 1;
  const topN = cfg.top_n || 5;
  const widgets = (cfg.widgets && cfg.widgets.length ? cfg.widgets : DEFAULT_DASHBOARD.widgets)
    .filter((w) => DEFAULT_DASHBOARD.widgets.includes(w));

  const KPIS = s
    ? [
        { label: "Documents Processed", value: s.documents_processed },
        { label: "People Identified", value: s.people_identified },
        { label: "Organizations", value: s.organizations },
        { label: "Total Entities", value: s.total_entities },
      ]
    : [];

  // Widget renderers, keyed by the agent-configurable ids.
  const CARDS = {
    kpi_cards: () => (
      <div key="kpi_cards" className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {KPIS.map((k) => (
          <div key={k.label} className="card p-4">
            <div className="text-2xl font-semibold text-slate-900">{k.value}</div>
            <div className="text-xs text-slate-500 mt-1">{k.label}</div>
          </div>
        ))}
      </div>
    ),
    entity_distribution: () => (
      <div key="entity_distribution" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">Entity Distribution</h2>
        <Donut distribution={s.entity_distribution} />
      </div>
    ),
    top_entities: () => (
      <div key="top_entities" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">
          Top Mentioned Entities <span className="text-xs text-slate-400">(top {topN})</span>
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <TopList title="People" items={(s.top_people || []).slice(0, topN)} color="text-blue-700" />
          <TopList title="Organizations" items={(s.top_organizations || []).slice(0, topN)} color="text-green-700" />
        </div>
      </div>
    ),
    language_distribution: () => (
      <div key="language_distribution" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">Language Distribution</h2>
        {!langs.length && <div className="text-sm text-slate-300">—</div>}
        <div className="space-y-2">
          {langs.map(([lang, n]) => (
            <div key={lang}>
              <div className="flex justify-between text-sm text-slate-600 mb-0.5">
                <span>{lang}</span>
                <span className="text-slate-400">{n}</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-navy-700"
                  style={{ width: Math.round((n / langTotal) * 100) + "%" }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    ),
    recent_activity: () => (
      <div key="recent_activity" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">Recent Processing Activity</h2>
        {(!s.recent_activity || !s.recent_activity.length) && (
          <div className="text-sm text-slate-300">no documents yet</div>
        )}
        <ul className="space-y-2">
          {(s.recent_activity || []).map((d, i) => (
            <li key={i} className="flex items-center justify-between gap-2 text-sm">
              <Link
                href={d.id ? "/documents/" + d.id : "/documents"}
                className="truncate text-slate-700 hover:text-accent-600"
              >
                {d.filename}
              </Link>
              <span className="text-xs text-slate-400 shrink-0">
                {d.date_text ? d.date_text + " · " : ""}{d.entities} entities
              </span>
            </li>
          ))}
        </ul>
      </div>
    ),
    storage_env: () => (
      <div key="storage_env" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">
          Storage Environment{" "}
          <span className="text-xs font-normal text-slate-400">(IoT · live)</span>
        </h2>
        {(!env || !env.length) && (
          <div className="text-sm text-slate-300">
            no sensor data yet — POST readings to /webhook/metrics
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          {(env || []).map((m, i) => (
            <div key={i} className="rounded-xl border border-slate-200 p-3">
              <div className="text-xs text-slate-400">
                {METRIC_LABELS[m.metric] || m.metric}
                <span className="ml-1">· {m.sensor}</span>
              </div>
              <div className={"text-2xl font-semibold " + envStatus(m.metric, m.value)}>
                {Number(m.value).toFixed(1)}
                <span className="text-sm font-normal text-slate-400 ml-1">{m.unit}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">
                24ч: {m.min24 != null ? Number(m.min24).toFixed(1) : "—"} … {m.max24 != null ? Number(m.max24).toFixed(1) : "—"}
                {" · "}{new Date(m.at).toLocaleTimeString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    ),
    timeline: () => (
      <div key="timeline" className="card p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-3">Document Timeline</h2>
        {(!s.timeline || !s.timeline.length) && (
          <div className="text-sm text-slate-300">no dated documents yet</div>
        )}
        <ol className="relative border-l border-slate-200 ml-2 space-y-3">
          {(s.timeline || []).map((d, i) => (
            <li key={i} className="ml-4">
              <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-accent-500" />
              <Link
                href={d.id ? "/documents/" + d.id : "/documents"}
                className="text-sm text-slate-700 hover:text-accent-600"
              >
                <b>{d.date_text || d.date_parsed}</b> — {d.filename}
              </Link>
              {d.document_type && (
                <span className="chip bg-navy-800/5 border border-navy-800/20 text-navy-800 ml-2">
                  {d.document_type}
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>
    ),
  };

  // Full-width widgets stand alone; consecutive half-width ones flow into a 2-col grid.
  const FULL_WIDTH = new Set(["kpi_cards", "timeline"]);
  const blocks = [];
  let row = [];
  const flush = () => {
    if (row.length) {
      blocks.push(
        <div key={"row-" + blocks.length} className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {row}
        </div>
      );
      row = [];
    }
  };
  if (s) {
    for (const w of widgets) {
      if (!CARDS[w]) continue;
      if (FULL_WIDTH.has(w)) {
        flush();
        blocks.push(CARDS[w]());
      } else {
        row.push(CARDS[w]());
      }
    }
    flush();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            One source of truth — every number comes from the same computation
            {data && data.computed_at &&
              " · updated " + new Date(data.computed_at).toLocaleString()}
          </p>
        </div>
        <button className="btn-secondary" disabled={busy} onClick={() => load(true)}>
          {busy ? "Recomputing…" : "Recompute"}
        </button>
      </div>

      {error && (
        <div className="card p-4 text-sm text-red-700 bg-red-50 border-red-200 mb-4">{error}</div>
      )}
      {!s && !error && <div className="text-slate-400 py-16 text-center">Loading stats…</div>}

      {s && <div className="space-y-5">{blocks}</div>}

      {custom.length > 0 && (
        <div className="mt-5">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Custom widgets{" "}
            <span className="normal-case font-normal">— built by the agent, ask it for more</span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {custom.map((w) => (
              <CustomWidget key={w.id} w={w} onRemove={() => removeWidget(w.id)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
