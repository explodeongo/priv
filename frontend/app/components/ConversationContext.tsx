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

export interface Convo { id: string; title: string; count: number; updated: number; pinned?: boolean; project_id?: string; }
export interface Project { id: string; name: string; instructions: string; count: number; updated: number; }
// A one-shot signal the chat page reacts to (load a convo's messages, or clear for a new chat).
export type LoadSignal = { kind: "open"; id: string; nonce: number } | { kind: "new"; nonce: number } | null;

interface Ctx {
  convos: Convo[];
  activeId: string | null;
  setActiveId: (id: string | null) => void;
  refresh: () => void;
  open: (id: string, projectId?: string | null) => void;
  startNew: (projectId?: string | null) => void;
  remove: (id: string) => void;
  rename: (id: string, title: string) => Promise<void>;
  togglePin: (id: string, pinned: boolean) => Promise<void>;
  // ── Projects ──
  projects: Project[];
  activeProjectId: string | null;
  refreshProjects: () => void;
  createProject: (name: string, instructions?: string) => Promise<Project | null>;
  updateProject: (id: string, patch: { name?: string; instructions?: string }) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  assignConvo: (cid: string, projectId: string) => Promise<void>;
  loadSignal: LoadSignal;
  consume: () => void;
}

const C = createContext<Ctx | null>(null);

export function ConversationProvider({ children }: { children: ReactNode }) {
  const [convos, setConvos]                 = useState<Convo[]>([]);
  const [projects, setProjects]             = useState<Project[]>([]);
  const [activeId, setActiveId]             = useState<string | null>(null);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [loadSignal, setLoadSignal]         = useState<LoadSignal>(null);

  const refresh = useCallback(() => {
    fetch(`${API}/conversations`, { headers: authH() })
      .then(r => (r.ok ? r.json() : { conversations: [] }))
      .then(d => setConvos(d.conversations || []))
      .catch(() => {});
  }, []);
  const refreshProjects = useCallback(() => {
    fetch(`${API}/projects`, { headers: authH() })
      .then(r => (r.ok ? r.json() : { projects: [] }))
      .then(d => setProjects(d.projects || []))
      .catch(() => {});
  }, []);

  useEffect(() => { refresh(); refreshProjects(); }, [refresh, refreshProjects]);

  const open     = useCallback((id: string, projectId: string | null = null) => { setActiveId(id); setActiveProjectId(projectId); setLoadSignal({ kind: "open", id, nonce: Date.now() }); }, []);
  const startNew = useCallback((projectId: string | null = null) => { setActiveId(null); setActiveProjectId(projectId); setLoadSignal({ kind: "new", nonce: Date.now() }); }, []);
  const consume  = useCallback(() => setLoadSignal(null), []);

  const remove = useCallback(async (id: string) => {
    try { await fetch(`${API}/conversations/${id}`, { method: "DELETE", headers: authH() }); } catch {}
    setActiveId(prev => {
      if (prev === id) { setLoadSignal({ kind: "new", nonce: Date.now() }); return null; }
      return prev;
    });
    refresh();
  }, [refresh]);

  const rename = useCallback(async (id: string, title: string) => {
    setConvos(prev => prev.map(c => c.id === id ? { ...c, title } : c));   // optimistic
    try {
      await fetch(`${API}/conversations/${id}`, { method: "PUT", headers: authH(true),
        body: JSON.stringify({ title, rename: true }) });
    } catch {}
    refresh();
  }, [refresh]);

  const togglePin = useCallback(async (id: string, pinned: boolean) => {
    setConvos(prev => prev.map(c => c.id === id ? { ...c, pinned } : c));  // optimistic
    try {
      await fetch(`${API}/conversations/${id}`, { method: "PUT", headers: authH(true),
        body: JSON.stringify({ pinned }) });
    } catch {}
    refresh();
  }, [refresh]);

  // ── Projects ──
  const createProject = useCallback(async (name: string, instructions = ""): Promise<Project | null> => {
    try {
      const r = await fetch(`${API}/projects`, { method: "POST", headers: authH(true), body: JSON.stringify({ name, instructions }) });
      if (!r.ok) return null;
      const p = await r.json(); refreshProjects(); return p;
    } catch { return null; }
  }, [refreshProjects]);

  const updateProject = useCallback(async (id: string, patch: { name?: string; instructions?: string }) => {
    setProjects(prev => prev.map(p => p.id === id ? { ...p, ...patch } : p));   // optimistic
    try { await fetch(`${API}/projects/${id}`, { method: "PUT", headers: authH(true), body: JSON.stringify(patch) }); } catch {}
    refreshProjects();
  }, [refreshProjects]);

  const deleteProject = useCallback(async (id: string) => {
    try { await fetch(`${API}/projects/${id}`, { method: "DELETE", headers: authH() }); } catch {}
    setActiveProjectId(prev => (prev === id ? null : prev));
    refreshProjects(); refresh();   // chats in it become unfiled
  }, [refreshProjects, refresh]);

  const assignConvo = useCallback(async (cid: string, projectId: string) => {
    setConvos(prev => prev.map(c => c.id === cid ? { ...c, project_id: projectId } : c));  // optimistic
    try { await fetch(`${API}/conversations/${cid}`, { method: "PUT", headers: authH(true), body: JSON.stringify({ project_id: projectId }) }); } catch {}
    refresh(); refreshProjects();
  }, [refresh, refreshProjects]);

  return (
    <C.Provider value={{
      convos, activeId, setActiveId, refresh, open, startNew, remove, rename, togglePin,
      projects, activeProjectId, refreshProjects, createProject, updateProject, deleteProject, assignConvo,
      loadSignal, consume,
    }}>
      {children}
    </C.Provider>
  );
}

export function useConvos() {
  const ctx = useContext(C);
  if (!ctx) throw new Error("useConvos must be inside ConversationProvider");
  return ctx;
}
