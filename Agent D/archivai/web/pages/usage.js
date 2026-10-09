// Phase 6 — admin compliance/usage analytics: searches, top docs, users, IPs.
import { useEffect, useState } from "react";
import Link from "next/link";

function Card({ title, children }) {
  return (
    <div className="card p-4">
      <h2 className="text-sm font-semibold text-slate-800 mb-3">{title}</h2>
      {children}
    </div>
  );
}

function BarList({ rows, labelKey, nKey }) {
  if (!rows || !rows.length) return <div className="text-sm text-slate-300">—</div>;
  const max = Math.max(1, ...rows.map((r) => r[nKey]));
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => (
        <div key={i}>
          <div className="flex justify-between text-sm text-slate-600 mb-0.5">
            <span className="truncate">{r[labelKey]}</span>
            <span className="text-slate-400 shrink-0 ml-2">{r[nKey]}</span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full bg-navy-700"
                 style={{ width: Math.round((r[nKey] / max) * 100) + "%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Usage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/usage")
      .then(async (r) => {
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "failed");
        setStats(j.stats);
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const t = (stats && stats.totals) || {};
  const KPIS = stats
    ? [
        { label: "Users", value: t.users },
        { label: "Searches", value: t.searches },
        { label: "Document views", value: t.doc_views },
        { label: "Logins", value: t.logins },
      ]
    : [];

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-slate-900">Usage &amp; Compliance</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Who searched what, which documents are used, who is online, and from which
          IPs — every row comes from the audit trail.
        </p>
      </div>

      {error && (
        <div className="card p-4 text-sm text-red-700 bg-red-50 border-red-200 mb-4">{error}</div>
      )}
      {!stats && !error && <div className="text-slate-400 py-16 text-center">Loading…</div>}

      {stats && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {KPIS.map((k) => (
              <div key={k.label} className="card p-4">
                <div className="text-2xl font-semibold text-slate-900">{k.value}</div>
                <div className="text-xs text-slate-500 mt-1">{k.label}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <Card title="Searches per day (14d)">
              <BarList rows={stats.searches_per_day} labelKey="day" nKey="n" />
            </Card>
            <Card title="Top queries (30d)">
              <BarList rows={stats.top_queries} labelKey="query" nKey="n" />
            </Card>
            <Card title="Most viewed documents (30d)">
              {(!stats.top_documents || !stats.top_documents.length) && (
                <div className="text-sm text-slate-300">—</div>
              )}
              <ul className="space-y-1.5">
                {(stats.top_documents || []).map((d, i) => (
                  <li key={i} className="flex justify-between gap-2 text-sm">
                    <Link href={"/documents/" + d.document_id}
                          className="truncate text-slate-700 hover:text-accent-600">
                      {d.filename}
                    </Link>
                    <span className="text-xs text-slate-400 shrink-0">{d.n} views</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Active sessions">
              {(!stats.active_sessions || !stats.active_sessions.length) && (
                <div className="text-sm text-slate-300">—</div>
              )}
              <ul className="space-y-1.5">
                {(stats.active_sessions || []).map((s, i) => (
                  <li key={i} className="flex justify-between gap-2 text-sm">
                    <span className="truncate text-slate-700">
                      {s.email} <span className="text-xs text-slate-400">({s.role})</span>
                    </span>
                    <span className="text-xs text-slate-400 shrink-0">{s.ip || "—"}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card title="Recent logins (incl. failed)">
            {(!stats.recent_logins || !stats.recent_logins.length) && (
              <div className="text-sm text-slate-300">—</div>
            )}
            <table className="w-full text-sm">
              <tbody>
                {(stats.recent_logins || []).map((l, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-600">{new Date(l.at).toLocaleString()}</td>
                    <td className="py-1.5 truncate text-slate-700">{l.email || "—"}</td>
                    <td className="py-1.5 text-slate-400">{l.ip || "—"}</td>
                    <td className={"py-1.5 text-right " + (l.ok ? "text-emerald-600" : "text-red-600")}>
                      {l.ok ? "ok" : "failed"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}
