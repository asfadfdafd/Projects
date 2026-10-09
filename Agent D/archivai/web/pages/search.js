import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

export default function Search() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async (text) => {
    const qv = (text !== undefined ? text : query).trim();
    if (!qv || loading) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: qv }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "search failed");
      setData(j);
    } catch (e) {
      setError(String(e.message || e));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  // Autorun links from the agent (open_search command): /search?q=…
  useEffect(() => {
    if (!router.isReady) return;
    const q0 = typeof router.query.q === "string" ? router.query.q.trim() : "";
    if (q0) {
      setQuery(q0);
      run(q0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady]);

  // Recent searches per user (Phase 6 personalization v1)
  const [recent, setRecent] = useState([]);
  useEffect(() => {
    fetch("/api/search")
      .then((r) => (r.ok ? r.json() : { recent: [] }))
      .then((j) => setRecent(j.recent || []))
      .catch(() => {});
  }, []);

  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-semibold text-slate-900 mb-1">Search</h1>
      <p className="text-sm text-slate-500 mb-5">
        Hybrid semantic + keyword search — ask in natural language (Russian, Kazakh or English),
        or search for people, organizations and places.
      </p>

      <div className="flex gap-2 mb-6">
        <input
          className="input flex-1"
          placeholder="Search documents, people, organizations, places…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          autoFocus
        />
        <button className="btn-primary" disabled={loading || !query.trim()} onClick={() => run()}>
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {!data && recent.length > 0 && (
        <div className="mb-6">
          <div className="text-xs text-slate-400 mb-1.5">Недавние запросы</div>
          <div className="flex flex-wrap gap-1.5">
            {recent.map((r, i) => (
              <button
                key={i}
                className="chip bg-white border border-slate-300 text-slate-600 hover:border-accent-500 cursor-pointer"
                onClick={() => { setQuery(r.query); run(r.query); }}
              >
                {r.query}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="card p-4 text-sm text-red-700 bg-red-50 border-red-200 mb-4">{error}</div>
      )}

      {data && (
        <div>
          <div className="text-sm text-slate-500 mb-3">
            Found <b>{data.count}</b> document{data.count === 1 ? "" : "s"} matching
            {" "}&ldquo;{data.query}&rdquo;
          </div>
          {data.count === 0 && (
            <div className="card p-8 text-center text-sm text-slate-400">
              Nothing matched. Try different wording — semantic search also finds
              related documents without exact keywords.
            </div>
          )}
          <div className="space-y-3">
            {(data.results || []).map((r) => (
              <Link
                key={r.document_id}
                href={"/documents/" + r.document_id}
                className="card p-4 block hover:border-accent-500 transition-colors"
              >
                <div className="flex items-center justify-between gap-3 mb-1">
                  <div className="font-medium text-slate-800 truncate">{r.filename}</div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.document_type && (
                      <span className="chip bg-navy-800/5 border border-navy-800/20 text-navy-800">
                        {r.document_type}
                      </span>
                    )}
                    <span
                      className="chip bg-emerald-50 border border-emerald-200 text-emerald-700"
                      title="relevance score"
                    >
                      {typeof r.score === "number" ? r.score.toFixed(2) : r.score}
                    </span>
                  </div>
                </div>
                {r.date_text && <div className="text-xs text-slate-400 mb-1">{r.date_text}</div>}
                <p className="text-sm text-slate-600 line-clamp-2">{r.snippet || ""}</p>
              </Link>
            ))}
          </div>
        </div>
      )}

      {!data && !error && (
        <div className="text-xs text-slate-400">
          Examples: «памятник Амангельды Иманову» · «письма о юбилее Абая» · «отчёты обкома 1940»
        </div>
      )}
    </div>
  );
}
