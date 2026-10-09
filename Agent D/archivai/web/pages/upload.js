import { useRef, useState } from "react";
import Link from "next/link";

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [combine, setCombine] = useState(false);
  const [title, setTitle] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const addFiles = (list) => {
    const arr = Array.from(list || []).filter((f) => f && f.name);
    if (arr.length) setFiles((prev) => [...prev, ...arr]);
  };

  const removeAt = (i) => setFiles((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!files.length || uploading) return;
    setUploading(true);
    setError(null);
    setResults(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("combine", combine ? "1" : "0");
      if (combine && title.trim()) fd.append("title", title.trim());
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "upload failed");
      setResults(j.results);
      setFiles([]);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setUploading(false);
    }
  };

  const [pulling, setPulling] = useState(false);
  const [pullResult, setPullResult] = useState(null);
  const pullNow = async () => {
    if (pulling) return;
    setPulling(true);
    setPullResult(null);
    try {
      const r = await fetch("/api/connector", { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "pull failed");
      setPullResult(`Найдено в хранилище: ${j.found}, отправлено в обработку: ${j.dispatched}`);
    } catch (e) {
      setPullResult("⚠ " + String(e.message || e));
    } finally {
      setPulling(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between gap-3 mb-1">
        <h1 className="text-xl font-semibold text-slate-900">Upload scans</h1>
        <button className="btn-secondary shrink-0" disabled={pulling} onClick={pullNow}
                title="Bulk-ingest new files from the connected storage bucket (Phase 7 connector)">
          {pulling ? "Pulling…" : "⇩ Pull from storage"}
        </button>
      </div>
      <p className="text-sm text-slate-500 mb-2">
        Images (PNG/JPG/TIFF) and PDFs are stored in object storage, then the n8n pipeline
        runs OCR + extraction. A PDF is split into one page per document page; if it already
        has a text layer, that text is used instead of OCR. In stub mode any file works —
        the AI output is deterministic.
      </p>
      {pullResult && (
        <div className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-2.5 mb-3">
          {pullResult} <span className="text-slate-400">· автозабор каждые 5 минут</span>
        </div>
      )}

      <div
        className={
          "card border-2 border-dashed p-10 text-center transition-colors cursor-pointer " +
          (dragOver ? "border-accent-500 bg-orange-50" : "border-slate-300")
        }
        onClick={() => inputRef.current && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <div className="text-4xl mb-2 text-slate-300">⇪</div>
        <div className="text-sm text-slate-600">
          Drag &amp; drop scans or PDFs here, or{" "}
          <span className="text-accent-600 underline">browse</span>
        </div>
        <div className="text-xs text-slate-400 mt-1">PNG · JPG · TIFF · WEBP · BMP · PDF</div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.pdf,application/pdf"
          className="hidden"
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

      {files.length > 0 && (
        <div className="card p-4 mt-4">
          <div className="text-sm font-medium text-slate-700 mb-2">
            {files.length} file{files.length === 1 ? "" : "s"} ready
          </div>
          <ul className="text-sm text-slate-600 space-y-1 mb-4 max-h-52 overflow-auto">
            {files.map((f, i) => (
              <li key={i} className="flex items-center justify-between gap-3">
                <span className="truncate">{f.name}</span>
                <span className="text-xs text-slate-400 shrink-0">
                  {(f.size / 1024).toFixed(0)} KB
                  <button
                    className="ml-3 text-red-400 hover:text-red-600"
                    onClick={() => removeAt(i)}
                  >
                    remove
                  </button>
                </span>
              </li>
            ))}
          </ul>

          <label className="flex items-center gap-2 text-sm text-slate-600 mb-3">
            <input
              type="checkbox"
              checked={combine}
              onChange={(e) => setCombine(e.target.checked)}
            />
            Combine all files into <b>one multi-page document</b> (sorted by filename)
          </label>
          {combine && (
            <input
              className="input w-full mb-3"
              placeholder="Document title (optional — defaults to first filename)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          )}

          <button className="btn-primary" disabled={uploading} onClick={submit}>
            {uploading ? "Uploading & processing…" : "Upload & process"}
          </button>
          {uploading && (
            <span className="text-xs text-slate-400 ml-3">
              with real models this can take a while per page
            </span>
          )}
        </div>
      )}

      {error && (
        <div className="card p-4 mt-4 text-sm text-red-700 bg-red-50 border-red-200">{error}</div>
      )}

      {results && (
        <div className="card p-4 mt-4">
          <div className="text-sm font-medium text-slate-700 mb-3">Results</div>
          <ul className="space-y-2">
            {results.map((r, i) => (
              <li key={i} className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate">
                  {r.ok ? "✅" : "❌"} {r.filename}
                  {r.pages > 1 ? " (" + r.pages + " pages)" : ""}
                  {r.truncated ? (
                    <span className="text-xs text-amber-600 ml-2">
                      first {r.pages} of {r.page_count} pages
                    </span>
                  ) : null}
                  {r.text_layer_pages > 0 ? (
                    <span className="text-xs text-slate-400 ml-2">
                      · {r.text_layer_pages} page{r.text_layer_pages === 1 ? "" : "s"} from PDF text layer
                    </span>
                  ) : null}
                </span>
                {r.ok && r.doc_id ? (
                  <Link href={"/documents/" + r.doc_id} className="text-accent-600 underline shrink-0">
                    open document →
                  </Link>
                ) : (
                  <span className="text-xs text-red-500 shrink-0">{r.error}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
