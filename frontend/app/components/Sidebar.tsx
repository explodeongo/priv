"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect, Fragment } from "react";
import { useAuth } from "./AuthProvider";
import { useBranding } from "./BrandingContext";
import { useConvos, type Convo, type Project, type ConvoMatch } from "./ConversationContext";
import { useTheme } from "./ThemeContext";

// ── Icons ────────────────────────────────────────────────────────────────────
const IChat = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
);
const IDocs = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
  </svg>
);
const IAdmin = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  </svg>
);
const ISettings = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
);
const ILogout = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
    <polyline points="16 17 21 12 16 7"/>
    <line x1="21" y1="12" x2="9" y2="12"/>
  </svg>
);
const IChevron = ({ flipped }: { flipped?: boolean }) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: flipped ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
    <polyline points="15 18 9 12 15 6"/>
  </svg>
);
const ISun = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
  </svg>
);
const IMoon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
  </svg>
);
const IMonitor = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
  </svg>
);

// ── Nav config ───────────────────────────────────────────────────────────────
const ICheckSpec = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
  </svg>
);

const IHex = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
    <path d="M12 2.5l8.2 4.75v9.5L12 21.5l-8.2-4.75v-9.5z"/>
  </svg>
);

const NAV = [
  { label: "Chat",        href: "/",            icon: <IChat />,      exact: true  },
  { label: "Documents",   href: "/documents",   icon: <IDocs />,      exact: false },
  { label: "Conformance", href: "/conformance", icon: <ICheckSpec />, exact: false },
  { label: "ODA Map",     href: "/oda",         icon: <IHex />,       exact: false },
  { label: "Admin",       href: "/admin",       icon: <IAdmin />,     exact: false, adminOnly: true },
  { label: "Settings",    href: "/settings",    icon: <ISettings />,  exact: false },
];

// ── Shared avatar bubble ──────────────────────────────────────────────────────
function AvatarBubble({ avatar, initials, size = 32 }: { avatar?: string; initials: string; size?: number }) {
  const s = `${size}px`;
  if (avatar) {
    return (
      <img src={avatar} alt="Profile"
        className="rounded-full object-cover flex-shrink-0 ring-2 ring-slate-700"
        style={{ width: s, height: s }} />
    );
  }
  return (
    <div className="rounded-full bg-red-600 flex items-center justify-center text-white font-bold flex-shrink-0"
      style={{ width: s, height: s, fontSize: size < 36 ? "11px" : "14px" }}>
      {initials}
    </div>
  );
}

// Bucket chats into Today / Yesterday / Previous 7 Days / 30 Days / Older.
function groupByDate(list: Convo[]): { label: string; items: Convo[] }[] {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const b = [
    { label: "Today", cut: startToday, items: [] as Convo[] },
    { label: "Yesterday", cut: startToday - 86400, items: [] as Convo[] },
    { label: "Previous 7 Days", cut: startToday - 7 * 86400, items: [] as Convo[] },
    { label: "Previous 30 Days", cut: startToday - 30 * 86400, items: [] as Convo[] },
    { label: "Older", cut: -Infinity, items: [] as Convo[] },
  ];
  for (const c of list) {
    const u = c.updated || 0;
    for (const g of b) { if (u >= g.cut) { g.items.push(c); break; } }
  }
  return b.filter(g => g.items.length);
}

// ── Component ────────────────────────────────────────────────────────────────
export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [logo, setLogo] = useState<string | undefined>();
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { branding } = useBranding();
  const { convos, activeId, open, startNew, remove, rename, togglePin,
          projects, createProject, updateProject, deleteProject, assignConvo, searchConvos } = useConvos();
  const { theme, cycle } = useTheme();
  const [convoQuery, setConvoQuery] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const [moveMenuFor, setMoveMenuFor] = useState<string | null>(null);   // chat id whose "move to project" menu is open
  const [searchResults, setSearchResults] = useState<ConvoMatch[] | null>(null);   // full-text results (null = not searching)

  // Debounced full-text search across chat titles + message content.
  useEffect(() => {
    const ql = convoQuery.trim();
    if (ql.length < 2) { setSearchResults(null); return; }
    let alive = true;
    const t = setTimeout(() => { searchConvos(ql).then(r => { if (alive) setSearchResults(r); }); }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [convoQuery, searchConvos]);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [projInstr, setProjInstr] = useState("");
  const startRename = (id: string, title: string) => { setRenamingId(id); setRenameVal(title); };
  const commitRename = () => { if (renamingId) rename(renamingId, renameVal.trim() || "Untitled"); setRenamingId(null); };
  const toggleProject = (id: string) => setExpandedProjects(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const newProject = async () => {
    const name = (prompt("New project name:") || "").trim();
    if (!name) return;
    const p = await createProject(name);
    if (p) setExpandedProjects(s => { const n = new Set(s); n.add(p.id); return n; });
  };
  const openInstr = (p: Project) => { setEditingProject(p); setProjInstr(p.instructions || ""); };
  const saveInstr = () => { if (editingProject) updateProject(editingProject.id, { instructions: projInstr }); setEditingProject(null); };

  // One chat row — shared by the Projects section and the Recent/Pinned list.
  const Row = (c: Convo) => {
    const active = pathname === "/" && c.id === activeId;
    const editing = renamingId === c.id;
    return (
      <div key={c.id}>
        <div onClick={() => { if (!editing) { setMoveMenuFor(null); open(c.id, c.project_id || null); router.push("/"); } }}
          className={`group flex items-center gap-1 rounded-lg pl-3 pr-1.5 py-2 text-sm cursor-pointer transition-colors ${
            active ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white hover:bg-slate-800/70"
          }`}>
          {c.pinned && !editing && <svg className="w-3 h-3 flex-shrink-0 text-amber-400/80" fill="currentColor" viewBox="0 0 24 24"><path d="M16 3v2l-1 1v4l3 3v2h-5v5l-1 1-1-1v-5H5v-2l3-3V6L7 5V3z" /></svg>}
          {editing ? (
            <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)}
              onClick={e => e.stopPropagation()}
              onKeyDown={e => { if (e.key === "Enter") commitRename(); if (e.key === "Escape") setRenamingId(null); }}
              onBlur={commitRename}
              className="flex-1 min-w-0 bg-slate-900 border border-red-500 rounded px-1.5 py-0.5 text-sm text-white focus:outline-none" />
          ) : (
            <span className="truncate flex-1">{c.title || "Untitled"}</span>
          )}
          {!editing && (
            <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <button onClick={e => { e.stopPropagation(); setMoveMenuFor(m => m === c.id ? null : c.id); }} title="Move to project" className="p-1 text-slate-500 hover:text-violet-400">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" /></svg>
              </button>
              <button onClick={e => { e.stopPropagation(); togglePin(c.id, !c.pinned); }} title={c.pinned ? "Unpin" : "Pin"} className="p-1 text-slate-500 hover:text-amber-400">
                <svg className="w-3.5 h-3.5" fill={c.pinned ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M16 3v2l-1 1v4l3 3v2h-5v5l-1 1-1-1v-5H5v-2l3-3V6L7 5V3z" /></svg>
              </button>
              <button onClick={e => { e.stopPropagation(); startRename(c.id, c.title || ""); }} title="Rename" className="p-1 text-slate-500 hover:text-white">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
              </button>
              <button onClick={e => { e.stopPropagation(); remove(c.id); }} title="Delete" className="p-1 text-slate-500 hover:text-red-400">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
              </button>
            </div>
          )}
        </div>
        {moveMenuFor === c.id && (
          <div className="ml-6 mr-1 mb-1 rounded-lg bg-slate-800 border border-slate-700 p-1 shadow-lg" onClick={e => e.stopPropagation()}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 px-2 py-1">Move to project</div>
            {projects.length === 0 && <div className="text-[11px] text-slate-500 px-2 py-1">No projects yet — create one above.</div>}
            <div className="max-h-40 overflow-y-auto">
              {projects.map(p => (
                <button key={p.id} onClick={() => { assignConvo(c.id, p.id); setMoveMenuFor(null); setExpandedProjects(s => { const n = new Set(s); n.add(p.id); return n; }); }}
                  className={`w-full text-left text-xs px-2 py-1.5 rounded hover:bg-slate-700 transition-colors truncate ${(c.project_id || "") === p.id ? "text-violet-300 font-medium" : "text-slate-300"}`}>
                  {p.name}
                </button>
              ))}
            </div>
            {c.project_id && (
              <button onClick={() => { assignConvo(c.id, ""); setMoveMenuFor(null); }}
                className="w-full text-left text-xs px-2 py-1.5 rounded text-slate-400 hover:bg-slate-700 transition-colors border-t border-slate-700/60 mt-0.5 pt-1.5">Remove from project</button>
            )}
          </div>
        )}
      </div>
    );
  };

  useEffect(() => {
    const load = () => {
      try { const l = localStorage.getItem("synaptdi_logo"); setLogo(l ?? undefined); } catch {}
    };
    load();
    window.addEventListener("storage", load);
    return () => window.removeEventListener("storage", load);
  }, []);

  const initials = (user?.name ?? "?").split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  const items = NAV.filter(n => !n.adminOnly || user?.role === "admin");
  const firstLetter = (branding.companyName || "S")[0].toUpperCase();

  const isActive = (href: string, exact: boolean) =>
    exact ? pathname === href : pathname.startsWith(href);

  return (
    <aside
      className="flex flex-col h-full bg-slate-900 border-r border-slate-800 transition-[width] duration-200 ease-in-out flex-shrink-0 z-20"
      style={{ width: collapsed ? 64 : 216 }}
    >
      {/* Logo — reflects live branding */}
      <div className={`flex items-center gap-3 px-4 py-[18px] border-b border-slate-800 overflow-hidden ${collapsed ? "justify-center" : ""}`}>
        {logo ? (
          <img src={logo} alt="Logo" className="w-8 h-8 rounded-lg object-contain flex-shrink-0 shadow-sm bg-white" />
        ) : (
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 shadow-sm"
            style={{ backgroundColor: branding.primaryColor }}>
            <span className="text-white font-extrabold text-sm select-none">{firstLetter}</span>
          </div>
        )}
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-white font-bold text-sm leading-none whitespace-nowrap truncate max-w-[130px]">
              {branding.companyName}
            </div>
            <div className="text-slate-500 text-[11px] mt-[3px] whitespace-nowrap">Domain Intelligence</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 pt-4 pb-2 flex flex-col overflow-hidden">
        <div className="space-y-0.5">
          {items.map(item => {
            const active = isActive(item.href, item.exact ?? false);
            return (
              <Link key={item.href} href={item.href} title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap overflow-hidden ${
                  active
                    ? "bg-red-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                } ${collapsed ? "justify-center" : ""}`}>
                <span className="flex-shrink-0">{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </div>

        {/* Conversation history */}
        {!collapsed && (
          <div className="mt-4 flex flex-col min-h-0 flex-1">
            <button onClick={() => { startNew(); router.push("/"); }}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-all">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              New chat
            </button>
            {/* Projects — group chats + shared memory */}
            <div className="mt-3">
              <div className="flex items-center justify-between px-3 pb-0.5">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Projects</span>
                <button onClick={newProject} title="New project" className="p-0.5 text-slate-500 hover:text-white transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
              </div>
              {projects.length === 0 && <p className="text-[11px] text-slate-600 px-3 pb-1">Create one to group chats + give them shared memory.</p>}
              {projects.map(p => {
                const exp = expandedProjects.has(p.id);
                const pchats = convos.filter(c => (c.project_id || "") === p.id);
                return (
                  <div key={p.id}>
                    <div onClick={() => toggleProject(p.id)}
                      className="group flex items-center gap-1.5 rounded-lg pl-2 pr-1.5 py-1.5 text-sm cursor-pointer text-slate-300 hover:bg-slate-800/70 transition-colors">
                      <svg className={`w-3 h-3 flex-shrink-0 text-slate-500 transition-transform ${exp ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                      <svg className="w-4 h-4 flex-shrink-0 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>
                      <span className="truncate flex-1 font-medium">{p.name}</span>
                      <span className="text-[10px] text-slate-600 group-hover:hidden">{p.count || ""}</span>
                      <div className="hidden group-hover:flex items-center flex-shrink-0">
                        <button onClick={e => { e.stopPropagation(); startNew(p.id); router.push("/"); }} title="New chat in this project" className="p-1 text-slate-500 hover:text-white">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        </button>
                        <button onClick={e => { e.stopPropagation(); openInstr(p); }} title="Project instructions / memory" className="p-1 text-slate-500 hover:text-white">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h10"/></svg>
                        </button>
                        <button onClick={e => { e.stopPropagation(); if (confirm(`Delete project "${p.name}"? Its chats are kept (moved out of the project).`)) deleteProject(p.id); }} title="Delete project" className="p-1 text-slate-500 hover:text-red-400">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        </button>
                      </div>
                    </div>
                    {exp && (
                      <div className="ml-3.5 border-l border-slate-800 pl-1 mb-1">
                        {pchats.length === 0 && <p className="text-[11px] text-slate-600 px-2 py-1">No chats yet — use the + above</p>}
                        {pchats.map(Row)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {convos.filter(c => !c.project_id).length > 4 && (
              <div className="relative px-1 mt-2">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
                <input value={convoQuery} onChange={e => setConvoQuery(e.target.value)} placeholder="Search chats"
                  className="w-full bg-slate-800/60 border border-slate-700 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-red-500" />
              </div>
            )}

            {(() => {
              const searching = convoQuery.trim().length >= 2;
              if (searching) {
                return (
                  <div className="flex-1 overflow-y-auto pr-0.5 mt-1">
                    {searchResults === null && <p className="text-xs text-slate-600 px-3 py-1.5">Searching…</p>}
                    {searchResults !== null && searchResults.length === 0 && <p className="text-xs text-slate-600 px-3 py-1.5">No chats match “{convoQuery.trim()}”.</p>}
                    {(searchResults || []).map(r => (
                      <div key={r.id} onClick={() => { setMoveMenuFor(null); open(r.id, r.project_id || null); router.push("/"); }}
                        className="rounded-lg px-3 py-2 cursor-pointer text-slate-300 hover:bg-slate-800/70 transition-colors">
                        <div className="text-sm truncate flex items-center gap-1.5">
                          {r.pinned && <svg className="w-3 h-3 flex-shrink-0 text-amber-400/80" fill="currentColor" viewBox="0 0 24 24"><path d="M16 3v2l-1 1v4l3 3v2h-5v5l-1 1-1-1v-5H5v-2l3-3V6L7 5V3z" /></svg>}
                          <span className="truncate">{r.title || "Untitled"}</span>
                        </div>
                        {r.snippet && <div className="text-[11px] text-slate-500 truncate mt-0.5">{r.snippet}</div>}
                      </div>
                    ))}
                  </div>
                );
              }
              const unfiled = convos.filter(c => !c.project_id);
              const pinned = unfiled.filter(c => c.pinned);
              const recent = unfiled.filter(c => !c.pinned);
              const groups = groupByDate(recent);
              return (
                <div className="flex-1 overflow-y-auto space-y-0.5 pr-0.5 mt-1">
                  {pinned.length > 0 && <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600 px-3 pt-2 pb-1">Pinned</div>}
                  {pinned.map(Row)}
                  {groups.map(g => (
                    <Fragment key={g.label}>
                      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600 px-3 pt-2 pb-1">{g.label}</div>
                      {g.items.map(Row)}
                    </Fragment>
                  ))}
                  {unfiled.length === 0 && <p className="text-xs text-slate-600 px-3 py-1.5">No chats yet.</p>}
                </div>
              );
            })()}
          </div>
        )}
      </nav>

      {/* ⌘K hint + collapse */}
      <div className="px-2 pb-2 space-y-0.5">
        {!collapsed && (
          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition-all group"
          >
            <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <span className="text-xs flex-1 text-left">Quick search</span>
            <span className="text-[10px] bg-slate-800 group-hover:bg-slate-700 text-slate-500 px-1.5 py-0.5 rounded font-mono border border-slate-700 transition-colors">⌘K</span>
          </button>
        )}
        <button onClick={cycle} title={`Theme: ${theme} — click to change`}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition-all ${collapsed ? "justify-center" : ""}`}>
          <span className="flex-shrink-0">{theme === "light" ? <ISun /> : theme === "dark" ? <IMoon /> : <IMonitor />}</span>
          {!collapsed && <span className="text-xs flex-1 text-left capitalize">{theme} theme</span>}
        </button>
        <button onClick={() => setCollapsed(c => !c)} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition-all text-xs ${collapsed ? "justify-center" : ""}`}>
          <IChevron flipped={collapsed} />
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>

      {/* User footer */}
      <div className="border-t border-slate-800 p-3 overflow-hidden">
        {collapsed ? (
          <div className="flex flex-col items-center gap-2.5">
            <AvatarBubble avatar={user?.avatar} initials={initials} size={32} />
            <button onClick={logout} title="Sign out" className="text-slate-600 hover:text-red-400 transition-colors">
              <ILogout />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 min-w-0">
            <AvatarBubble avatar={user?.avatar} initials={initials} size={32} />
            <div className="flex-1 min-w-0">
              <div className="text-white text-xs font-semibold truncate leading-none">{user?.name}</div>
              <div className="text-slate-500 text-[11px] mt-0.5 capitalize">{user?.role}</div>
            </div>
            <button onClick={logout} title="Sign out" className="text-slate-600 hover:text-red-400 transition-colors flex-shrink-0 ml-1">
              <ILogout />
            </button>
          </div>
        )}
      </div>

      {/* Project instructions / memory editor */}
      {editingProject && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setEditingProject(null)}>
          <div onClick={e => e.stopPropagation()} className="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-2xl p-5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Project memory — {editingProject.name}</h3>
            <p className="text-xs text-gray-400 mt-0.5 mb-3">Standing notes the assistant keeps in mind for every chat in this project. Facts still come from your knowledge base — this just steers the context.</p>
            <textarea value={projInstr} onChange={e => setProjInstr(e.target.value)} rows={6} maxLength={4000} autoFocus
              placeholder="e.g. We're migrating from TMF622 v4 to v5 — prefer v5 answers and always flag breaking changes."
              className="w-full border border-gray-200 dark:border-slate-700 rounded-lg p-2.5 text-sm bg-gray-50 dark:bg-slate-800 text-gray-800 dark:text-slate-100 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-red-500 resize-none" />
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setEditingProject(null)} className="text-sm px-3 py-1.5 text-gray-500 hover:text-gray-800 dark:hover:text-slate-200">Cancel</button>
              <button onClick={saveInstr} className="text-sm font-semibold px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white">Save</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
