export default function ComingSoon({ title, phase, children }) {
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold text-slate-900 mb-1">{title}</h1>
      <div className="card p-8 mt-4 text-center">
        <div className="text-3xl mb-2">🚧</div>
        <div className="text-sm text-slate-600">
          Built in <b>{phase}</b> — the backend for this screen is already wired.
        </div>
        {children && <div className="text-xs text-slate-400 mt-2">{children}</div>}
      </div>
    </div>
  );
}
