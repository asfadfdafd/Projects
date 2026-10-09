import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

const NODE_COLORS = { person: "#3b82f6", organization: "#22c55e", place: "#a855f7" };
const TYPE_CHIP = {
  person: "bg-blue-50 border-blue-200 text-blue-800",
  organization: "bg-green-50 border-green-200 text-green-800",
  date: "bg-amber-50 border-amber-200 text-amber-800",
  place: "bg-purple-50 border-purple-200 text-purple-800",
  quantity: "bg-slate-100 border-slate-300 text-slate-700",
};
const TABS = [
  { key: "", label: "All" },
  { key: "person", label: "People" },
  { key: "organization", label: "Organizations" },
  { key: "place", label: "Places" },
  { key: "date", label: "Dates" },
  { key: "quantity", label: "Quantities" },
];

// Dependency-free force-directed layout (deterministic: seeded by index).
function computeLayout(nodes, edges, W, H) {
  const pos = {};
  const n = nodes.length || 1;
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n;
    const rr = Math.min(W, H) * 0.36 * (0.6 + 0.4 * ((i * 7919) % 97) / 97);
    pos[node.id] = { x: W / 2 + rr * Math.cos(angle), y: H / 2 + rr * Math.sin(angle) };
  });
  const byId = {};
  nodes.forEach((node) => { byId[node.id] = node; });
  const springs = edges.filter((e) => byId[e.a] && byId[e.b]);
  for (let iter = 0; iter < 260; iter++) {
    const t = 1 - iter / 260;
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const A = pos[nodes[i].id];
        const B = pos[nodes[j].id];
        let dx = A.x - B.x;
        let dy = A.y - B.y;
        const d2 = dx * dx + dy * dy + 0.01;
        const d = Math.sqrt(d2);
        const f = (2600 / d2) * t;
        dx = (dx / d) * f;
        dy = (dy / d) * f;
        A.x += dx; A.y += dy; B.x -= dx; B.y -= dy;
      }
    }
    // springs
    springs.forEach((e) => {
      const A = pos[e.a];
      const B = pos[e.b];
      let dx = B.x - A.x;
      let dy = B.y - A.y;
      const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const rest = 120;
      const f = ((d - rest) / d) * 0.02 * Math.min(4, e.weight) * t;
      dx *= f; dy *= f;
      A.x += dx; A.y += dy; B.x -= dx; B.y -= dy;
    });
    // gravity + bounds
    nodes.forEach((node) => {
      const P = pos[node.id];
      P.x += (W / 2 - P.x) * 0.012 * t;
      P.y += (H / 2 - P.y) * 0.012 * t;
      P.x = Math.max(30, Math.min(W - 30, P.x));
      P.y = Math.max(24, Math.min(H - 24, P.y));
    });
  }
  return pos;
}

function KnowledgeGraph({ data, onPick }) {
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState(null);
  const W = 860;
  const H = 560;
  const pos = useMemo(
    () => (data ? computeLayout(data.nodes, data.edges, W, H) : {}),
    [data]
  );
  if (!data) return <div className="text-sm text-slate-400 py-16 text-center">Loading graph…</div>;
  if (!data.nodes.length) {
    return (
      <div className="text-sm text-slate-400 py-16 text-center">
        No linked entities yet — ingest a few documents first.
      </div>
    );
  }
  const vw = W / zoom;
  const vh = H / zoom;
  const vx = (W - vw) / 2;
  const vy = (H - vh) / 2;
  const neighbors = new Set();
  if (selected) {
    data.edges.forEach((e) => {
      if (e.a === selected) neighbors.add(e.b);
      if (e.b === selected) neighbors.add(e.a);
    });
  }
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex items-center gap-3 text-xs text-slate-500 mr-auto">
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS.person }} /> Person</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS.organization }} /> Organization</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: NODE_COLORS.place }} /> Place</span>
          <span className="text-slate-300">· edges = shared documents</span>
        </div>
        <button className="btn-secondary px-2 py-1" onClick={() => setZoom(Math.min(3, zoom * 1.3))}>+</button>
        <button className="btn-secondary px-2 py-1" onClick={() => setZoom(Math.max(0.7, zoom / 1.3))}>−</button>
        <button className="btn-secondary px-2 py-1" onClick={() => { setZoom(1); setSelected(null); }}>Reset</button>
      </div>
      <svg
        viewBox={vx + " " + vy + " " + vw + " " + vh}
        className="w-full rounded-lg bg-navy-950"
        style={{ aspectRatio: "860 / 560" }}
      >
        {data.edges.map((e, i) => {
          const A = pos[e.a];
          const B = pos[e.b];
          if (!A || !B) return null;
          const hot = selected && (e.a === selected || e.b === selected);
          return (
            <line
              key={i}
              x1={A.x} y1={A.y} x2={B.x} y2={B.y}
              stroke={hot ? "#f97316" : "#334a7d"}
              strokeOpacity={selected && !hot ? 0.25 : 0.7}
              strokeWidth={Math.min(4, 0.6 + e.weight * 0.7)}
            />
          );
        })}
        {data.nodes.map((node) => {
          const P = pos[node.id];
          if (!P) return null;
          const r = 5 + Math.min(9, node.document_count * 1.6);
          const dim = selected && node.id !== selected && !neighbors.has(node.id);
          return (
            <g
              key={node.id}
              transform={"translate(" + P.x + "," + P.y + ")"}
              opacity={dim ? 0.3 : 1}
              className="cursor-pointer"
              onClick={() => {
                const next = selected === node.id ? null : node.id;
                setSelected(next);
                if (next && onPick) onPick(node);
              }}
            >
              <circle
                r={r}
                fill={NODE_COLORS[node.type] || "#94a3b8"}
                stroke={selected === node.id ? "#f97316" : "#0b1426"}
                strokeWidth={selected === node.id ? 2.5 : 1}
              />
              <text
                y={r + 11}
                textAnchor="middle"
                fontSize="10"
                fill="#c7d2e8"
              >
                {node.name.length > 20 ? node.name.slice(0, 19) + "…" : node.name}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="text-[11px] text-slate-400 mt-1">
        Click a node to highlight its connections and filter the table below.
      </div>
    </div>
  );
}

export default function Entities() {
  const [tab, setTab] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [graph, setGraph] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [error, setError] = useState(null);
  const [resolving, setResolving] = useState(false);
  const [report, setReport] = useState(null);

  const load = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ page: String(page), size: "50" });
      if (tab) qs.set("type", tab);
      if (filter.trim()) qs.set("filter", filter.trim());
      const r = await fetch("/api/entities?" + qs.toString());
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "failed to load entities");
      setData(j);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [tab, filter, page]);

  const loadGraph = useCallback(async () => {
    try {
      const r = await fetch("/api/entities/graph?limit=60");
      const j = await r.json();
      if (r.ok) setGraph(j);
    } catch (e) { /* graph is non-critical */ }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadGraph(); }, [loadGraph]);

  const toggleDocs = async (id) => {
    if (expanded[id]) {
      setExpanded((prev) => {
        const nxt = Object.assign({}, prev);
        delete nxt[id];
        return nxt;
      });
      return;
    }
    setExpanded((prev) => Object.assign({}, prev, { [id]: { loading: true } }));
    try {
      const r = await fetch("/api/entities/" + id + "/documents");
      const j = await r.json();
      setExpanded((prev) => Object.assign({}, prev, { [id]: { documents: j.documents || [] } }));
    } catch (e) {
      setExpanded((prev) => Object.assign({}, prev, { [id]: { documents: [] } }));
    }
  };

  const runResolution = async () => {
    setResolving(true);
    setError(null);
    setReport(null);
    try {
      const r = await fetch("/api/entities/resolve", { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "resolution failed");
      setReport(j);
      await load();
      await loadGraph();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setResolving(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Entity Relationships</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Canonical entities with aliases — duplicates are merged by the resolution
            workflow (a gap in Agent D).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary" disabled={resolving} onClick={runResolution}>
            {resolving ? "Resolving…" : "⟲ Run entity resolution"}
          </button>
          <a className="btn-primary" href="/api/entities/export">Export CSV</a>
        </div>
      </div>

      {error && (
        <div className="card p-4 text-sm text-red-700 bg-red-50 border-red-200 mb-4">{error}</div>
      )}
      {report && (
        <div className="card p-4 text-sm mb-4 bg-emerald-50 border-emerald-200 text-emerald-800">
          Resolution merged <b>{report.merged}</b> duplicate entit{report.merged === 1 ? "y" : "ies"}.
          {(report.details || []).slice(0, 6).map((d, i) => (
            <div key={i} className="text-xs mt-1">
              «{d.merged}» → «{d.kept}» <span className="opacity-60">({d.type}, pass {d.pass})</span>
            </div>
          ))}
        </div>
      )}

      <div className="card p-4 mb-5">
        <KnowledgeGraph
          data={graph}
          onPick={(node) => { setTab(""); setPage(1); setFilter(node.name); }}
        />
      </div>

      <div className="flex gap-2 mb-3 flex-wrap items-center">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setPage(1); setTab(t.key); }}
            className={
              "chip cursor-pointer " +
              (tab === t.key
                ? "bg-navy-800 text-white"
                : "bg-white border border-slate-300 text-slate-600 hover:bg-slate-50")
            }
          >
            {t.label}
            {data && data.tabs && (
              <span className="opacity-60 ml-1">
                {t.key === "" ? data.tabs.all || 0 : data.tabs[t.key] || 0}
              </span>
            )}
          </button>
        ))}
        <input
          className="input ml-auto w-60"
          placeholder="Filter entities…"
          value={filter}
          onChange={(e) => { setPage(1); setFilter(e.target.value); }}
        />
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 bg-slate-50">
              <th className="px-4 py-3">Entity</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Role / Description</th>
              <th className="px-4 py-3">Documents</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {!data && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">Loading…</td></tr>
            )}
            {data && data.entities.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">No entities match.</td></tr>
            )}
            {data && data.entities.map((e) => (
              <Fragment key={e.id}>
                <tr className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{e.name}</div>
                    {e.aliases && e.aliases.length > 0 && (
                      <div className="text-xs text-slate-400 truncate max-w-[280px]">
                        also: {e.aliases.join(", ")}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={"chip border " + (TYPE_CHIP[e.type] || "")}>{e.type}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-600 max-w-[300px] truncate">{e.role || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{e.document_count}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="text-accent-600 text-xs hover:underline"
                      onClick={() => toggleDocs(e.id)}
                    >
                      {expanded[e.id] ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
                {expanded[e.id] && (
                  <tr className="border-b border-slate-100 bg-slate-50/60">
                    <td colSpan={5} className="px-6 py-3">
                      {expanded[e.id].loading && (
                        <div className="text-xs text-slate-400">loading documents…</div>
                      )}
                      <div className="grid gap-2">
                        {(expanded[e.id].documents || []).map((d) => (
                          <Link
                            key={d.id}
                            href={"/documents/" + d.id}
                            className="flex items-center gap-3 rounded-lg bg-white border border-slate-200 p-2 hover:border-accent-500"
                          >
                            <div className="h-10 w-8 rounded bg-slate-100 border border-slate-200 overflow-hidden shrink-0">
                              {d.thumb && (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={d.thumb}
                                  alt=""
                                  className="h-full w-full object-cover"
                                  onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
                                />
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-slate-700 truncate">
                                {d.filename}
                                {d.date_text && <span className="text-slate-400 font-normal"> · {d.date_text}</span>}
                              </div>
                              <div className="text-xs text-slate-500 truncate">{d.snippet}</div>
                            </div>
                          </Link>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {data && totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-slate-600">
          <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ← Previous
          </button>
          <span>Page {page} of {totalPages}</span>
          <button className="btn-secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
