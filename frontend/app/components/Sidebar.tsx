"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { useAuth } from "./AuthProvider";
import { useBranding } from "./BrandingContext";
import { useConvos } from "./ConversationContext";
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
const NAV = [
  { label: "Chat",      href: "/",          icon: <IChat />,     exact: true  },
  { label: "Documents", href: "/documents", icon: <IDocs />,     exact: false },
  { label: "Admin",     href: "/admin",     icon: <IAdmin />,    exact: false, adminOnly: true },
  { label: "Settings",  href: "/settings",  icon: <ISettings />, exact: false },
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

// ── Component ────────────────────────────────────────────────────────────────
export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [logo, setLogo] = useState<string | undefined>();
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { branding } = useBranding();
  const { convos, activeId, open, startNew, remove } = useConvos();
  const { theme, cycle } = useTheme();

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
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600 px-3 pt-3 pb-1">Recent</div>
            <div className="flex-1 overflow-y-auto space-y-0.5 pr-0.5">
              {convos.length === 0 && <p className="text-xs text-slate-600 px-3 py-1.5">No chats yet.</p>}
              {convos.map(c => {
                const active = pathname === "/" && c.id === activeId;
                return (
                  <div key={c.id} onClick={() => { open(c.id); router.push("/"); }}
                    className={`group flex items-center justify-between rounded-lg pl-3 pr-2 py-2 text-sm cursor-pointer transition-colors ${
                      active ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white hover:bg-slate-800/70"
                    }`}>
                    <span className="truncate">{c.title || "Untitled"}</span>
                    <button onClick={e => { e.stopPropagation(); remove(c.id); }}
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 ml-1 flex-shrink-0 transition-opacity" title="Delete chat">×</button>
                  </div>
                );
              })}
            </div>
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
    </aside>
  );
}
