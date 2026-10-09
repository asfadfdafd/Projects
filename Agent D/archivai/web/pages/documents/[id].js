import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import StatusBadge from "../../components/StatusBadge";

const GROUPS = [
  { type: "person", label: "People", dot: "bg-blue-500" },
  { type: "organization", label: "Organizations", dot: "bg-green-500" },
  { type: "date", label: "Dates", dot: "bg-amber-500" },
  { type: "place", label: "Places", dot: "bg-purple-500" },
  { type: "quantity", label: "Quantities", dot: "bg-slate-400" },
];

function EntityPill({ entity, type, onRename, onRemove, busy }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entity.name);

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <input
          className="input py-1 px-2 text-xs w-44"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { setEditing(false); onRename(entity, value); }
            if (e.key === "Escape") { setEditing(false); setValue(entity.name); }
          }}
        />
        <button
          className="chip bg-emerald-600 text-white cursor-pointer"
          disabled={busy}
          onClick={() => { setEditing(false); onRename(entity, value); }}
        >
          Save
        </button>
        <button
          className="chip bg-slate-200 text-slate-600 cursor-pointer"
          onClick={() => { setEditing(false); setValue(entity.name); }}
        >
          Cancel
        </button>
      </span>
    );
  }

  return (
    <span className={"pill-" + type} title={entity.role || "click to edit"}>
      <span onClick={() => setEditing(true)}>{entity.name}</span>
      <button
        className="ml-0.5 opacity-40 hover:opacity-100"
        title="Remove from this document"
        disabled={busy}
        onClick={() => onRemove(entity)}
      >
        ×
      </button>
    </span>
  );
}

function EntityGroup({ group, items, onAdd, onRename, onRemove, busy }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");

  const submit = () => {
    if (name.trim()) onAdd(group.type, name, role);
    setAdding(false);
    setName("");
    setRole("");
  };

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <span className={"h-2 w-2 rounded-full " + group.dot} />
        <span className="text-sm font-medium text-slate-700">{group.label}</span>
        <span className="text-xs text-slate-400">({items.length})</span>
        <button
          className="text-xs text-accent-600 hover:underline ml-auto"
          onClick={() => setAdding(!adding)}
        >
          + Add
        </button>
      </div>
      {adding && (
        <div className="flex items-center gap-2 mb-2">
          <input
            className="input py-1 px-2 text-xs w-44"
            placeholder="Name"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <input
            className="input py-1 px-2 text-xs w-40"
            placeholder="Role (optional)"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <button className="chip bg-emerald-600 text-white cursor-pointer" disabled={busy} onClick={submit}>
            Save
          </button>
          <button className="chip bg-slate-200 text-slate-600 cursor-pointer" onClick={() => setAdding(false)}>
            Cancel
          </button>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {items.length === 0 && !adding && (
          <span className="text-xs text-slate-300">none extracted</span>
        )}
        {items.map((e) => (
          <EntityPill
            key={e.id}
            entity={e}
            type={group.type}
            onRename={onRename}
            onRemove={onRemove}
            busy={busy}
          />
        ))}
      </div>
    </div>
  );
}

export default function DocumentDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [pageIdx, setPageIdx] = useState(0);
  const [zoom, setZoom] = useState(false);
  const [textTab, setTextTab] = useState("all");
  // Reading order is the natural view; the layout variant is for tables, forms and
  // stamped margins — and it degrades on PDFs that draw overlapping text runs.
  const [layout, setLayout] = useState(false);
  const [busy, setBusy] = useState(false);
  const [imgErr, setImgErr] = useState(false);

  useEffect(() => { setImgErr(false); }, [pageIdx, data]);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const r = await fetch("/api/documents/" + id);
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "failed to load");
      setData(j);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Ingest is async — poll while the pipeline is still working on this document.
  useEffect(() => {
    if (!data) return;
    const st = data.document.status;
    if (st !== "processing" && st !== "uploaded") return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [data, load]);

  const api = async (method, url, body) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "request failed");
      await load();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const onAdd = (type, name, role) =>
    api("POST", "/api/documents/" + id + "/entities", { type, name, role });
  const onRename = (entity, newName) => {
    if (newName.trim() && newName.trim() !== entity.name) {
      api("PATCH", "/api/documents/" + id + "/entities", {
        entity_id: entity.id,
        new_name: newName,
      });
    }
  };
  const onRemove = (entity) =>
    api("DELETE", "/api/documents/" + id + "/entities", { entity_id: entity.id });
  const onVerify = () => api("POST", "/api/documents/" + id + "/verify");

  if (error && !data) {
    return <div className="card p-6 text-red-700 bg-red-50 border-red-200">{error}</div>;
  }
  if (!data) {
    return <div className="text-slate-400 py-20 text-center">Loading document…</div>;
  }

  const doc = data.document;
  const pages = data.pages;
  const page = pages[pageIdx] || null;
  // For a PDF the original is the file itself, not an image — never feed it to <img>;
  // its rendered pages are what the viewer shows, and the file is offered as a link.
  const originalIsPdf = /\.pdf($|\?)/i.test(doc.original || "");
  const viewerSrc = (page && page.image) || (originalIsPdf ? null : doc.original) || null;
  // Two variants per page: reading order (what search and the models consume) and
  // the layout-preserving one (columns/indentation kept as spaces — PDF text layer
  // only). "All pages" concatenates the layout pages so the whole document can be
  // read as it was typeset.
  const pageOf = (n) => pages.find((p) => p.page_no === n) || {};
  const hasLayout = pages.some((p) => (p.layout_text || "").trim());
  const layoutOn = layout && hasLayout;
  const currentText = layoutOn
    ? textTab === "all"
      ? pages.map((p) => p.layout_text || p.ocr_text || "").join("\n\n")
      : (pageOf(textTab).layout_text || pageOf(textTab).ocr_text || "")
    : textTab === "all"
    ? doc.full_text
    : (pageOf(textTab).ocr_text || "");

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <div className="min-w-0">
          <Link href="/documents" className="text-xs text-slate-400 hover:text-accent-600">
            ← Document Archive
          </Link>
          <h1 className="text-lg font-semibold text-slate-900 truncate max-w-xl">{doc.filename}</h1>
        </div>
        <div className="flex items-center gap-2">
          {doc.status === "processed" && (
            <button className="btn-verify" disabled={busy} onClick={onVerify}>
              ✓ Mark as Verified
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="card p-3 mb-4 text-sm text-red-700 bg-red-50 border-red-200">{error}</div>
      )}
      {doc.status === "failed" && (
        <div className="card p-3 mb-4 text-sm text-red-700 bg-red-50 border-red-200">
          Processing failed: {doc.process_error || "unknown error"}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* left: scan viewer */}
        <div>
          <div className="card p-3 sticky top-4">
            <div
              className={
                "relative bg-slate-200 rounded-lg overflow-hidden flex items-center justify-center min-h-[420px]" +
                (viewerSrc && !imgErr ? " cursor-zoom-in" : "")
              }
              onClick={() => viewerSrc && !imgErr && setZoom(true)}
              title={viewerSrc && !imgErr ? "Click to zoom" : undefined}
            >
              {viewerSrc && !imgErr ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={viewerSrc}
                  alt={"page " + (pageIdx + 1)}
                  className="max-h-[70vh] w-auto object-contain"
                  onError={() => setImgErr(true)}
                />
              ) : (
                <div className="text-slate-400 text-sm py-24 text-center px-6">
                  <div className="text-3xl mb-2">{originalIsPdf ? "📄" : "🖼️"}</div>
                  {viewerSrc
                    ? "scan image not found in object storage"
                    : originalIsPdf
                    ? "PDF pages are still being rendered"
                    : "no scan image for this document"}
                </div>
              )}
            </div>
            {originalIsPdf && (
              <div className="mt-2 text-xs text-slate-400">
                Source: PDF ·{" "}
                <a
                  href={doc.original}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent-600 underline"
                >
                  open original file
                </a>
              </div>
            )}
            {pages.length > 0 && (
              <div className="flex items-center justify-between mt-3 text-sm text-slate-600">
                <button
                  className="btn-secondary"
                  disabled={pageIdx <= 0}
                  onClick={() => setPageIdx(pageIdx - 1)}
                >
                  ← Prev
                </button>
                <span>
                  Page {pageIdx + 1} of {pages.length}
                  {!imgErr && <span className="text-slate-300"> · click image to zoom</span>}
                </span>
                <button
                  className="btn-secondary"
                  disabled={pageIdx >= pages.length - 1}
                  onClick={() => setPageIdx(pageIdx + 1)}
                >
                  Next →
                </button>
              </div>
            )}
          </div>
        </div>

        {/* right: extraction panel */}
        <div>
          <div className="card p-4 mb-4">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {doc.document_type && (
                <span className="chip bg-navy-800/5 border border-navy-800/20 text-navy-800">
                  {doc.document_type}
                </span>
              )}
              {doc.date_text && (
                <span className="chip bg-amber-50 border border-amber-200 text-amber-800">
                  {doc.date_text}
                </span>
              )}
              {doc.language && (
                <span className="chip bg-sky-50 border border-sky-200 text-sky-800">
                  {doc.language}
                </span>
              )}
              <StatusBadge status={doc.status} />
            </div>
            <div className="text-[11px] text-slate-400 mb-3">
              OCR: {doc.ocr_backend || "—"} · extraction: {doc.extract_backend || "—"}
              {doc.ocr_confidence != null &&
                " · confidence " + Math.round(doc.ocr_confidence * 100) + "%"}
              {doc.verified_at && " · verified " + new Date(doc.verified_at).toLocaleString()}
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">Sender</div>
                <div className="text-sm font-medium text-slate-800">{doc.sender_name || "—"}</div>
                <div className="text-xs text-slate-500">{doc.sender_role || ""}</div>
              </div>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">Recipient</div>
                <div className="text-sm font-medium text-slate-800">{doc.recipient_name || "—"}</div>
                <div className="text-xs text-slate-500">{doc.recipient_role || ""}</div>
              </div>
            </div>

            <div className="rounded-lg bg-navy-900 text-slate-200 p-3">
              <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">
                ArchivAI Summary
              </div>
              <p className="text-sm leading-relaxed">{doc.ai_summary || "No summary yet."}</p>
            </div>
          </div>

          <div className="card p-4 mb-4">
            <h2 className="text-sm font-semibold text-slate-800 mb-3">
              Extracted Entities
              <span className="text-xs font-normal text-slate-400 ml-2">
                click a name to correct it — changes are audit-logged
              </span>
            </h2>
            {GROUPS.map((g) => (
              <EntityGroup
                key={g.type}
                group={g}
                items={data.entities[g.type] || []}
                onAdd={onAdd}
                onRename={onRename}
                onRemove={onRemove}
                busy={busy}
              />
            ))}
          </div>

          <div className="card p-4">
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <h2 className="text-sm font-semibold text-slate-800 mr-2">Full Extracted Text</h2>
              <button
                className={
                  "chip cursor-pointer " +
                  (textTab === "all"
                    ? "bg-navy-800 text-white"
                    : "bg-white border border-slate-300 text-slate-600")
                }
                onClick={() => setTextTab("all")}
              >
                All pages
              </button>
              {pages.map((p) => (
                <button
                  key={p.page_no}
                  className={
                    "chip cursor-pointer " +
                    (textTab === p.page_no
                      ? "bg-navy-800 text-white"
                      : "bg-white border border-slate-300 text-slate-600")
                  }
                  onClick={() => setTextTab(p.page_no)}
                >
                  Page {p.page_no}
                </button>
              ))}
              {hasLayout && (
                <label
                  className="ml-auto flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer"
                  title="Keep columns and indentation exactly as they are on the page (PDF text layer)"
                >
                  <input
                    type="checkbox"
                    checked={layout}
                    onChange={(e) => setLayout(e.target.checked)}
                  />
                  keep page layout
                </label>
              )}
            </div>
            <pre
              className={
                "text-sm text-slate-700 leading-relaxed max-h-96 overflow-auto " +
                (layoutOn
                  ? "whitespace-pre font-mono text-xs"   // columns only line up in a monospace font
                  : "whitespace-pre-wrap font-sans")
              }
            >
              {currentText || "—"}
            </pre>
            {layoutOn && (
              <div className="text-xs text-slate-400 mt-2">
                Layout view — scroll sideways for wide pages. Search and the AI use the
                reading-order text (uncheck to see it).
              </div>
            )}
          </div>
        </div>
      </div>

      {/* zoom modal */}
      {zoom && viewerSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-start justify-center overflow-auto p-6 cursor-zoom-out"
          onClick={() => setZoom(false)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={viewerSrc} alt="zoomed scan" className="max-w-none w-[1200px]" />
        </div>
      )}
    </div>
  );
}
