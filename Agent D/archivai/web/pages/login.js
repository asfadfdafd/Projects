// Phase 6 — local login (SSO-ready: an OIDC button lands here later).
import { useState } from "react";
import { useRouter } from "next/router";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    if (e) e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "login", email, password }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "login failed");
      router.push("/documents");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form onSubmit={submit} className="card p-8 w-full max-w-sm shadow-md">
        <div className="text-center mb-6">
          <div className="text-2xl font-semibold text-slate-900 tracking-tight">
            Archiv<span className="text-accent-500">AI</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">open-source archive intelligence</div>
        </div>
        {error && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-2.5 mb-3">
            {error}
          </div>
        )}
        <label className="block text-xs text-slate-500 mb-1">Email</label>
        <input
          className="input w-full mb-3"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
          required
        />
        <label className="block text-xs text-slate-500 mb-1">Пароль</label>
        <input
          className="input w-full mb-4"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button className="btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Входим…" : "Войти"}
        </button>
        <div className="text-[11px] text-slate-400 mt-4 text-center">
          Каждый вход фиксируется в журнале аудита (IP, время) — комплаенс-режим.
        </div>
      </form>
    </div>
  );
}
