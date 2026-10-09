import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import StatusBadge from "../../components/StatusBadge";

const FILTERS = [
  { key: "", label: "All" },
  { key: "processing", label: "Processing" },
  { key: "processed", label: "Pending review" },
  { key: "verified", label: "Verified" },
  { key: "failed", label: "Failed" },
];

export default function DocumentArchive() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  const load = useCallback(async (p, s, silent) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ page: String(p), size: "20" });
      if (s) qs.set("status", s);
      const r = await fetch("/api/documents?" + qs.toString());
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "failed to load");
      setData(j);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(page, status, false);
  }, [page, status, load]);

  // poll while anything is still processing
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    const anyProcessing =
      data && data.documents.some((d) => d.status === "processing" || d.status === "uploaded");
    if (anyProcessing) {
      timer.current = setInterval(() => load(page, status, true), 5000);
    }
    return () => timer.current && clearInterval(timer.current);
  }, [data, page, status, load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Document Archive</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data ? data.total + " document" + (data.total === 1 ? "" : "s") : "…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary" onClick={() => load(page, status, false)}>
            Refresh
          </button>
          <Link href="/upload" className="btn-primary">+ Upload</Link>
        </div>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => { setPage(1); setStatus(f.key); }}
            className={
              "chip cursor-pointer " +
              (status === f.key
                ? "bg-navy-800 text-white"
                : "bg-white border border-slate-300 text-slate-600 hover:bg-slate-50")
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="card p-4 text-sm text-red-700 bg-red-50 border-red-200 mb-4">
          {error}
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200 bg-slate-50">
              <th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Language</th>
              <th className="px-4 py-3">Entities</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && !data && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Loading…</td></tr>
            )}
            {data && data.documents.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400">
                  No documents yet — <Link href="/upload" className="text-accent-600 underline">upload scans</Link> to get started.
                </td>
              </tr>
            )}
            {data && data.documents.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link href={"/documents/" + d.id} className="flex items-center gap-3 group">
                    <div className="h-12 w-9 rounded border border-slate-200 bg-slate-100 overflow-hidden shrink-0">
                      {d.thumb ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={d.thumb}
                          alt=""
                          className="h-full w-full object-cover"
                          onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
                        />
                      ) : (
                        <div className="h-full w-full flex items-center justify-center text-slate-300 text-lg">·</div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="font-medium text-slate-800 group-hover:text-accent-600 truncate max-w-[260px]">
                        {d.filename}
                      </div>
                      <div className="text-xs text-slate-400">
                        {d.page_count} page{d.page_count === 1 ? "" : "s"}
                      </div>
                    </div>
                  </Link>
                </td>
                <td className="px-4 py-3">
                  {d.document_type ? (
                    <span className="chip bg-navy-800/5 border border-navy-800/20 text-navy-800">
                      {d.document_type}
                    </span>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-600">{d.date_text || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{d.language || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{d.entity_count}</td>
                <td className="px-4 py-3"><StatusBadge status={d.status} /></td>
              </tr>
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
