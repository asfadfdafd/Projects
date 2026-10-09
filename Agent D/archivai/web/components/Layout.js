import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "M3 13h4v8H3zM10 3h4v18h-4zM17 8h4v13h-4z" },
  { href: "/documents", label: "Documents", icon: "M6 2h9l5 5v15H6zM14 2v6h6" },
  { href: "/search", label: "Search", icon: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM21 21l-4.3-4.3" },
  { href: "/entities", label: "Entities", icon: "M12 3a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM5 15a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM19 15a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM12 9v3M7 15l3-3M17 15l-3-3" },
  { href: "/chat", label: "Ask ArchivAI", icon: "M4 5h16v11H8l-4 4zM8 9h8M8 12h5" },
  { href: "/agent", label: "Agent", icon: "M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8z" },
];
const ADMIN_NAV = [
  { href: "/usage", label: "Usage", icon: "M3 3v18h18M7 15l4-4 3 3 5-6" },
];

function Icon({ d }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

export default function Layout({ children }) {
  const router = useRouter();
  const [user, setUser] = useState(undefined); // undefined = loading, null = anon

  useEffect(() => {
    let alive = true;
    fetch("/api/auth")
      .then((r) => r.json())
      .then((j) => {
        if (!alive) return;
        setUser(j.user || null);
        if (!j.user && router.pathname !== "/login") router.replace("/login");
      })
      .catch(() => alive && setUser(null));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.pathname]);

  const logout = async () => {
    await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "logout" }),
    });
    router.replace("/login");
  };

  // The login page renders bare (no sidebar).
  if (router.pathname === "/login") return children;
  if (user === undefined) {
    return <div className="min-h-screen flex items-center justify-center text-slate-300">…</div>;
  }
  if (user === null) return null; // redirect in flight

  const nav = user.role === "admin" ? NAV.concat(ADMIN_NAV) : NAV;

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 bg-navy-900 text-slate-300 flex flex-col sticky top-0 h-screen self-start">
        <div className="px-5 py-5 border-b border-navy-700">
          <Link href="/documents" className="block">
            <div className="text-white font-semibold text-lg tracking-tight">
              Archiv<span className="text-accent-500">AI</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-0.5">
              open-source archive intelligence
            </div>
          </Link>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {nav.map((item) => {
            const active = router.pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors " +
                  (active
                    ? "bg-navy-700 text-white"
                    : "hover:bg-navy-800 hover:text-white")
                }
              >
                <Icon d={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="px-3 pb-5">
          <Link href="/upload" className="btn-primary w-full justify-center">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
            </svg>
            Upload
          </Link>
          <div className="mt-3 flex items-center justify-between px-1">
            <div className="text-[11px] text-slate-500 min-w-0">
              <div className="truncate text-slate-400">{user.display_name || user.email}</div>
              <div>{user.role}</div>
            </div>
            <button
              onClick={logout}
              className="text-[11px] text-slate-500 hover:text-white shrink-0"
              title="log out"
            >
              logout
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
