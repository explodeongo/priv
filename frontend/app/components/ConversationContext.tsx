"use client";
import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authH(json = false): Record<string, string> {
  const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

export interface Convo { id: string; title: string; count: number; updated: number; }
// A one-shot signal the chat page reacts to (load a convo's messages, or clear for a new chat).
export type LoadSignal = { kind: "open"; id: string; nonce: number } | { kind: "new"; nonce: number } | null;

interface Ctx {
  convos: Convo[];
  activeId: string | null;
  setActiveId: (id: string | null) => void;
  refresh: () => void;
  open: (id: string) => void;
  startNew: () => void;
  remove: (id: string) => void;
  loadSignal: LoadSignal;
  consume: () => void;
}

const C = createContext<Ctx | null>(null);

export function ConversationProvider({ children }: { children: ReactNode }) {
  const [convos, setConvos]         = useState<Convo[]>([]);
  const [activeId, setActiveId]     = useState<string | null>(null);
  const [loadSignal, setLoadSignal] = useState<LoadSignal>(null);

  const refresh = useCallback(() => {
    fetch(`${API}/conversations`, { headers: authH() })
      .then(r => (r.ok ? r.json() : { conversations: [] }))
      .then(d => setConvos(d.conversations || []))
      .catch(() => {});
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const open     = useCallback((id: string) => { setActiveId(id); setLoadSignal({ kind: "open", id, nonce: Date.now() }); }, []);
  const startNew = useCallback(() => { setActiveId(null); setLoadSignal({ kind: "new", nonce: Date.now() }); }, []);
  const consume  = useCallback(() => setLoadSignal(null), []);

  const remove = useCallback(async (id: string) => {
    try { await fetch(`${API}/conversations/${id}`, { method: "DELETE", headers: authH() }); } catch {}
    setActiveId(prev => {
      if (prev === id) { setLoadSignal({ kind: "new", nonce: Date.now() }); return null; }
      return prev;
    });
    refresh();
  }, [refresh]);

  return (
    <C.Provider value={{ convos, activeId, setActiveId, refresh, open, startNew, remove, loadSignal, consume }}>
      {children}
    </C.Provider>
  );
}

export function useConvos() {
  const ctx = useContext(C);
  if (!ctx) throw new Error("useConvos must be inside ConversationProvider");
  return ctx;
}
