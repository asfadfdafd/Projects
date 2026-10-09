const STYLES = {
  uploaded: "bg-slate-100 text-slate-700 border border-slate-300",
  processing: "bg-sky-50 text-sky-700 border border-sky-200",
  processed: "bg-amber-50 text-amber-800 border border-amber-200",
  failed: "bg-red-50 text-red-700 border border-red-200",
  verified: "bg-emerald-50 text-emerald-700 border border-emerald-200",
};

const LABELS = {
  uploaded: "Uploaded",
  processing: "Processing…",
  processed: "Pending review",
  failed: "Failed",
  verified: "✓ Human Verified",
};

export default function StatusBadge({ status }) {
  const cls = STYLES[status] || STYLES.uploaded;
  return <span className={"chip " + cls}>{LABELS[status] || status}</span>;
}
