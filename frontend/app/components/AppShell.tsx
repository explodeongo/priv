"use client";
import { useState, useEffect } from "react";
import { useAuth } from "./AuthProvider";
import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Poll the backend so a crash / slow start shows a calm banner instead of scary errors.
function useBackendHealth() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setTimeout>;
    const ping = async () => {
      let ok = false;
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(`${API}/health`, { signal: ctrl.signal });
        clearTimeout(t); ok = r.ok;
      } catch { ok = false; }
      if (stop) return;
      setOnline(ok);
      timer = setTimeout(ping, ok ? 20000 : 3000);   // healthy → relax; down → check often
    };
    ping();
    return () => { stop = true; clearTimeout(timer); };
  }, []);
  return online;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const online = useBackendHealth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-white dark:bg-slate-950">
        <div className="text-center">
          <div className="flex items-center gap-1.5 justify-center mb-3">
            {[0, 150, 300].map(d => (
              <div key={d} className="w-2.5 h-2.5 bg-red-500 rounded-full animate-bounce"
                style={{ animationDelay: `${d}ms` }} />
            ))}
          </div>
          <p className="text-gray-400 text-sm font-medium">Loading SynaptDI…</p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex h-screen bg-white dark:bg-slate-950 overflow-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {!online && (
          <div className="flex items-center justify-center gap-2 bg-amber-500 text-white text-xs font-medium py-1.5 px-4 flex-shrink-0">
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeOpacity="0.3" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            Reconnecting to SynaptDI — the server may be starting up…
          </div>
        )}
        {children}
      </div>
      <CommandPalette />
    </div>
  );
}
