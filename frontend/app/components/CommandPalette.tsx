"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { useTheme } from "./ThemeContext";
import { useConvos } from "./ConversationContext";

// ── Command definitions ───────────────────────────────────────────────────────
interface Command {
  label: string;
  desc: string;
  icon: React.ReactNode;
  href?: string;                  // navigation command
  action?: () => void;            // action command
  keepOpen?: boolean;             // keep palette open after running (e.g. theme cycle)
  adminOnly?: boolean;
  keywords?: string;
}

const IChat = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
);
const IDocs = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
);
const IChart = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
  </svg>
);
const IUsers = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
  </svg>
);
const IShield = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  </svg>
);
const IPalette = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/>
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>
  </svg>
);
const IGear = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
);
const ILock = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
  </svg>
);
const IUser = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
  </svg>
);
const ICheckP = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
  </svg>
);
const INew = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const ITheme = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3a6 6 0 0 0 0 12 6 6 0 0 1 0 6 9 9 0 1 1 0-18z"/>
  </svg>
);

const NAV_COMMANDS: Command[] = [
  { label: "Chat",                    desc: "Open the AI assistant",                  href: "/",           icon: <IChat />,    keywords: "ask question query" },
  { label: "Documents",               desc: "Browse your document library",           href: "/documents",  icon: <IDocs />,    keywords: "files pdf library" },
  { label: "TMF Conformance Check",   desc: "Audit an OpenAPI spec against TMF630",    href: "/conformance", icon: <ICheckP />,  keywords: "conformance compliance openapi swagger audit validate tmf630 spec" },
  { label: "Document Performance",    desc: "Analytics and relevance metrics",        href: "/documents?tab=performance", icon: <IChart />,   keywords: "analytics metrics stats" },
  { label: "Admin — User Management", desc: "Invite and manage team members",         href: "/admin",      icon: <IUsers />,   adminOnly: true, keywords: "users invite team" },
  { label: "Admin — Branding",        desc: "Customize logo, colors and name",        href: "/admin?tab=branding",  icon: <IPalette />, adminOnly: true, keywords: "logo color design" },
  { label: "Admin — RBAC",            desc: "Configure role-based permissions",       href: "/admin?tab=rbac",      icon: <IShield />,  adminOnly: true, keywords: "roles permissions access" },
  { label: "Settings — Profile",      desc: "Update your name and job title",         href: "/settings",   icon: <IUser />,    keywords: "profile name avatar" },
  { label: "Settings — Security",     desc: "Change password and manage 2FA",         href: "/settings?tab=security", icon: <ILock />,    keywords: "password 2fa sessions" },
  { label: "Settings — Preferences",  desc: "Query results and notifications",        href: "/settings?tab=preferences", icon: <IGear />, keywords: "preferences notifications" },
];

// ── Component ─────────────────────────────────────────────────────────────────
export default function CommandPalette() {
  const [open, setOpen]       = useState(false);
  const [query, setQuery]     = useState("");
  const [selected, setSelected] = useState(0);
  const { user } = useAuth();
  const { theme, cycle } = useTheme();
  const { startNew } = useConvos();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef  = useRef<HTMLDivElement>(null);

  const close = useCallback(() => { setOpen(false); setQuery(""); setSelected(0); }, []);

  // Action commands (defined here so they can use hooks). Listed first.
  const ACTION_COMMANDS: Command[] = [
    { label: "New chat", desc: "Start a fresh conversation", icon: <INew />, keywords: "new clear reset conversation",
      action: () => { startNew(); router.push("/"); } },
    { label: `Toggle theme — currently ${theme}`, desc: "Switch light · dark · system", icon: <ITheme />, keywords: "theme dark light mode appearance color",
      action: () => cycle(), keepOpen: true },
  ];

  // Global keyboard listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setOpen(v => !v); setQuery(""); setSelected(0); }
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 40);
      return () => clearTimeout(t);
    }
  }, [open]);

  const commands = [...ACTION_COMMANDS, ...NAV_COMMANDS].filter(c => {
    if (c.adminOnly && user?.role !== "admin") return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q) || (c.keywords ?? "").includes(q);
  });

  useEffect(() => { setSelected(0); }, [query]);

  const run = useCallback((cmd: Command) => {
    if (cmd.action) { cmd.action(); if (!cmd.keepOpen) close(); }
    else if (cmd.href) { router.push(cmd.href); close(); }
  }, [router, close]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSelected(s => Math.min(s + 1, commands.length - 1)); }
    if (e.key === "ArrowUp")   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && commands[selected]) run(commands[selected]);
  };

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${selected}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[150]" onClick={close} />

      <div className="fixed top-[18%] left-1/2 -translate-x-1/2 w-full max-w-lg z-[160]"
        style={{ animation: "paletteIn 0.15s ease-out" }}>
        <style>{`
          @keyframes paletteIn {
            from { opacity: 0; transform: translateX(-50%) translateY(-8px) scale(0.97); }
            to   { opacity: 1; transform: translateX(-50%) translateY(0)     scale(1); }
          }
        `}</style>

        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-slate-700 overflow-hidden">
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-gray-100 dark:border-slate-800">
            <svg className="w-4 h-4 text-gray-400 dark:text-slate-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search pages and actions…"
              className="flex-1 text-sm text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 outline-none bg-transparent"
            />
            <kbd className="text-[10px] text-gray-400 dark:text-slate-500 bg-gray-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono border border-gray-200 dark:border-slate-700">Esc</kbd>
          </div>

          {/* Results */}
          <div ref={listRef} className="max-h-72 overflow-y-auto py-1.5">
            {commands.length === 0 ? (
              <div className="text-center py-10 text-sm text-gray-400 dark:text-slate-500">No results for "<span className="text-gray-600 dark:text-slate-300">{query}</span>"</div>
            ) : (
              commands.map((cmd, i) => (
                <button
                  key={cmd.label}
                  data-idx={i}
                  onClick={() => run(cmd)}
                  onMouseEnter={() => setSelected(i)}
                  className={`w-full text-left flex items-center gap-3 px-4 py-2.5 transition-colors ${
                    selected === i ? "bg-red-50 dark:bg-red-500/10" : "hover:bg-gray-50 dark:hover:bg-slate-800"
                  }`}
                >
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                    selected === i ? "bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400" : "bg-gray-100 dark:bg-slate-800 text-gray-500 dark:text-slate-400"
                  }`}>
                    {cmd.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm font-medium transition-colors ${selected === i ? "text-red-700 dark:text-red-400" : "text-gray-800 dark:text-slate-200"}`}>
                      {cmd.label}
                    </div>
                    <div className="text-xs text-gray-400 dark:text-slate-500 truncate">{cmd.desc}</div>
                  </div>
                  {selected === i && (
                    <kbd className="text-[10px] text-gray-400 dark:text-slate-500 bg-gray-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono border border-gray-200 dark:border-slate-700 flex-shrink-0">↵</kbd>
                  )}
                </button>
              ))
            )}
          </div>

          {/* Footer hint */}
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-slate-800 bg-gray-50 dark:bg-slate-950/40">
            <div className="flex items-center gap-3 text-[11px] text-gray-400 dark:text-slate-500">
              <span className="flex items-center gap-1"><kbd className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded px-1 font-mono">↑</kbd><kbd className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded px-1 font-mono">↓</kbd> Navigate</span>
              <span><kbd className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded px-1 font-mono">↵</kbd> Open</span>
            </div>
            <span className="text-[11px] text-gray-400 dark:text-slate-500">{commands.length} result{commands.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>
    </>
  );
}
