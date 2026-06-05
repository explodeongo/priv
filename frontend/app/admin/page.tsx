"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import AppShell from "../components/AppShell";
import { useAuth } from "../components/AuthProvider";
import { useToast } from "../components/Toast";
import { useBranding, Branding } from "../components/BrandingContext";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Attach the stored session token so admin-only endpoints accept the request.
function authHeaders(json = false): Record<string, string> {
  const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

function usePageTitle(t: string) {
  useEffect(() => {
    document.title = `${t} · SynaptDI`;
    return () => { document.title = "SynaptDI"; };
  }, [t]);
}

// ── Types ─────────────────────────────────────────────────────────────────────
type AdminTab   = "users" | "branding" | "rbac";
type UserRole   = "admin" | "analyst" | "viewer";
type UserStatus = "active" | "away" | "inactive";

interface AppUser {
  id: string; name: string; email: string;
  role: UserRole; status: UserStatus; lastActive: string;
}

// ── Shared helpers ─────────────────────────────────────────────────────────────
function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button onClick={onChange}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${on ? "bg-red-600" : "bg-gray-200"}`}>
      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${on ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}

const ROLE_BADGE: Record<UserRole, string> = {
  admin:   "bg-red-100 text-red-700",
  analyst: "bg-blue-100 text-blue-700",
  viewer:  "bg-gray-100 text-gray-600",
};
const STATUS_DOT: Record<UserStatus, string> = {
  active:   "bg-green-500",
  away:     "bg-amber-400",
  inactive: "bg-gray-300",
};

// ══════════════════════════════════════════════════════════════════════════════
// User Management Tab — real backend
// ══════════════════════════════════════════════════════════════════════════════
function UserManagementTab() {
  const toast = useToast();
  const [users, setUsers]       = useState<AppUser[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [filter, setFilter]     = useState<UserRole | "all">("all");
  const [showInvite, setShowInvite] = useState(false);
  const [editRole, setEditRole] = useState<string | null>(null);

  // Invite form
  const [invName,  setInvName]  = useState("");
  const [invEmail, setInvEmail] = useState("");
  const [invRole,  setInvRole]  = useState<UserRole>("viewer");
  const [invBusy,  setInvBusy]  = useState(false);

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchUsers = useCallback(async () => {
    try {
      const r = await fetch(`${API}/users`);
      if (!r.ok) throw new Error("Failed to load users");
      const data = await r.json();
      setUsers(data.users ?? []);
    } catch {
      toast("Failed to load users", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const visible = users.filter(u =>
    (filter === "all" || u.role === filter) &&
    (u.name.toLowerCase().includes(search.toLowerCase()) ||
     u.email.toLowerCase().includes(search.toLowerCase()))
  );

  const stats = {
    total:   users.length,
    active:  users.filter(u => u.status === "active").length,
    admins:  users.filter(u => u.role === "admin").length,
    viewers: users.filter(u => u.role === "viewer").length,
  };

  // ── Change role ────────────────────────────────────────────────────────────
  const changeRole = async (userId: string, role: UserRole) => {
    const prev = users.find(u => u.id === userId);
    setUsers(u => u.map(usr => usr.id === userId ? { ...usr, role } : usr));
    setEditRole(null);
    try {
      const r = await fetch(`${API}/users/${userId}`, {
        method: "PUT",
        headers: authHeaders(true),
        body: JSON.stringify({ role }),
      });
      if (!r.ok) throw new Error("Failed");
      toast(`Role updated to ${role}`);
    } catch {
      // Revert
      if (prev) setUsers(u => u.map(usr => usr.id === userId ? prev : usr));
      toast("Failed to update role", "error");
    }
  };

  // ── Remove user ────────────────────────────────────────────────────────────
  const removeUser = async (userId: string) => {
    const prev = users.find(u => u.id === userId);
    setUsers(u => u.filter(usr => usr.id !== userId));
    try {
      const r = await fetch(`${API}/users/${userId}`, { method: "DELETE", headers: authHeaders() });
      if (!r.ok) throw new Error("Failed");
      toast(`${prev?.name ?? "User"} removed`);
    } catch {
      if (prev) setUsers(u => [prev, ...u]);
      toast("Failed to remove user", "error");
    }
  };

  // ── Invite ─────────────────────────────────────────────────────────────────
  const sendInvite = async () => {
    if (!invName.trim() || !invEmail.trim()) {
      toast("Please fill in all fields", "warning");
      return;
    }
    setInvBusy(true);
    try {
      const r = await fetch(`${API}/users`, {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({ name: invName, email: invEmail, role: invRole }),
      });
      if (!r.ok) throw new Error("Failed");
      const newUser = await r.json();
      setUsers(u => [...u, newUser]);
      toast(`Invitation sent to ${invEmail}`);
      setInvName(""); setInvEmail(""); setInvRole("viewer"); setShowInvite(false);
    } catch {
      toast("Failed to add user", "error");
    } finally {
      setInvBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total users",  value: stats.total,   color: "text-gray-900" },
          { label: "Active now",   value: stats.active,  color: "text-green-600" },
          { label: "Admins",       value: stats.admins,  color: "text-red-600" },
          { label: "Viewers",      value: stats.viewers, color: "text-gray-500" },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-2xl border border-gray-200 shadow-sm px-5 py-4">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-400 mt-0.5 font-medium">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search users…"
              className="border border-gray-200 rounded-xl pl-9 pr-4 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white w-56" />
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {(["all","admin","analyst","viewer"] as const).map(r => (
              <button key={r} onClick={() => setFilter(r)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize ${
                  filter === r ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}>{r}</button>
            ))}
          </div>
        </div>
        <button onClick={() => setShowInvite(v => !v)}
          className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-4 py-2 rounded-xl transition-colors shadow-sm">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Invite user
        </button>
      </div>

      {/* Invite panel */}
      {showInvite && (
        <div className="bg-white rounded-2xl border border-red-200 shadow-md p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Invite new user</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input value={invName} onChange={e => setInvName(e.target.value)} placeholder="Full name"
              className="border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
            <input value={invEmail} onChange={e => setInvEmail(e.target.value)} placeholder="Email address"
              className="border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
            <div className="flex gap-2">
              <select value={invRole} onChange={e => setInvRole(e.target.value as UserRole)}
                className="flex-1 border border-gray-200 rounded-xl px-3 py-2.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white">
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
              <button onClick={sendInvite} disabled={invBusy}
                className="bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors flex items-center gap-1.5">
                {invBusy && <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-400">Loading users…</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                {["User","Role","Status","Last active","Actions"].map(h => (
                  <th key={h} className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-5 py-3.5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {visible.map(u => {
                const init = u.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
                return (
                  <tr key={u.id} className="hover:bg-gray-50/70 transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-red-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">{init}</div>
                        <div>
                          <div className="text-sm font-semibold text-gray-900">{u.name}</div>
                          <div className="text-xs text-gray-400">{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      {editRole === u.id ? (
                        <div className="flex items-center gap-1.5">
                          <select defaultValue={u.role} onChange={e => changeRole(u.id, e.target.value as UserRole)}
                            className="border border-gray-200 rounded-lg px-2 py-1 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-red-500 bg-white">
                            <option value="viewer">Viewer</option>
                            <option value="analyst">Analyst</option>
                            <option value="admin">Admin</option>
                          </select>
                          <button onClick={() => setEditRole(null)} className="text-gray-400 hover:text-gray-600">
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                          </button>
                        </div>
                      ) : (
                        <span
                          className={`text-xs font-bold px-2.5 py-1 rounded-full capitalize ${ROLE_BADGE[u.role]} ${u.role !== "admin" ? "cursor-pointer hover:opacity-80" : ""}`}
                          onClick={() => u.role !== "admin" && setEditRole(u.id)}
                          title={u.role !== "admin" ? "Click to change role" : ""}
                        >{u.role}</span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${STATUS_DOT[u.status]}`} />
                        <span className="text-xs text-gray-500 capitalize">{u.status}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4"><span className="text-xs text-gray-500">{u.lastActive}</span></td>
                    <td className="px-5 py-4">
                      {u.role !== "admin" && (
                        <button onClick={() => removeUser(u.id)}
                          className="text-xs font-semibold text-gray-400 hover:text-red-600 transition-colors">
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {!loading && visible.length === 0 && (
          <div className="text-center py-12 text-gray-400 text-sm">No users match your search.</div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Branding Tab — real backend + live BrandingContext
// ══════════════════════════════════════════════════════════════════════════════
const PRESET_COLORS = [
  { name: "Synapt Red",   hex: "#dc2626" },
  { name: "Slate Blue",   hex: "#3b82f6" },
  { name: "Forest Green", hex: "#16a34a" },
  { name: "Royal Purple", hex: "#7c3aed" },
  { name: "Amber Gold",   hex: "#d97706" },
  { name: "Midnight",     hex: "#0f172a" },
];

function BrandingTab() {
  const toast = useToast();
  const { branding: live, saveBranding } = useBranding();
  const logoRef = useRef<HTMLInputElement>(null);

  const [company,  setCompany]  = useState(live.companyName);
  const [tagline,  setTagline]  = useState(live.tagline);
  const [color,    setColor]    = useState(live.primaryColor);
  const [busy,     setBusy]     = useState(false);
  const [logo,     setLogo]     = useState<string | undefined>();

  useEffect(() => {
    try { const l = localStorage.getItem("synaptdi_logo"); if (l) setLogo(l); } catch {}
  }, []);

  const handleLogoFile = (file: File) => {
    if (file.size > 2 * 1024 * 1024) { toast("Logo must be under 2 MB", "error"); return; }
    if (!file.type.startsWith("image/")) { toast("Please select an image file", "error"); return; }
    const reader = new FileReader();
    reader.onload = ev => {
      const url = ev.target?.result as string;
      setLogo(url);
      try { localStorage.setItem("synaptdi_logo", url); } catch {}
      toast("Logo updated — visible in sidebar");
    };
    reader.readAsDataURL(file);
  };

  const removeLogo = () => {
    setLogo(undefined);
    try { localStorage.removeItem("synaptdi_logo"); } catch {}
    toast("Logo removed");
  };

  // Sync local state when live branding loads from backend
  useEffect(() => {
    setCompany(live.companyName);
    setTagline(live.tagline);
    setColor(live.primaryColor);
  }, [live.companyName, live.tagline, live.primaryColor]);

  const save = async () => {
    setBusy(true);
    try {
      await saveBranding({ companyName: company, tagline, primaryColor: color });
      toast("Branding saved — sidebar updated");
    } catch {
      toast("Failed to save branding", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Identity */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Brand Identity</h2>
          <p className="text-xs text-gray-400 mt-0.5">Name and tagline shown across the platform</p>
        </div>
        <div className="px-6 py-5 space-y-4">
          {[
            { label: "Platform name", val: company, set: setCompany, ph: "Your company name" },
            { label: "Tagline",       val: tagline, set: setTagline, ph: "Short description" },
          ].map(f => (
            <div key={f.label}>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">{f.label}</label>
              <input value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                className="w-full border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all" />
            </div>
          ))}
        </div>
      </div>

      {/* Logo */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Logo</h2>
          <p className="text-xs text-gray-400 mt-0.5">Replaces the letter icon in the sidebar</p>
        </div>
        <div className="px-6 py-5">
          <input ref={logoRef} type="file" accept="image/png,image/svg+xml,image/jpeg,image/webp"
            className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handleLogoFile(f); e.target.value = ""; }} />
          {logo ? (
            <div className="flex items-center gap-4">
              <img src={logo} alt="Logo preview" className="w-16 h-16 rounded-xl object-contain border border-gray-200 bg-gray-50" />
              <div>
                <p className="text-sm font-medium text-gray-800">Logo uploaded</p>
                <p className="text-xs text-gray-400 mt-0.5">Shown in the sidebar instead of the letter icon</p>
                <div className="flex gap-3 mt-2">
                  <button onClick={() => logoRef.current?.click()} className="text-sm font-semibold text-red-600 hover:text-red-700 transition-colors">Change</button>
                  <button onClick={removeLogo} className="text-sm text-gray-400 hover:text-red-500 transition-colors">Remove</button>
                </div>
              </div>
            </div>
          ) : (
            <div
              onClick={() => logoRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleLogoFile(f); }}
              className="border-2 border-dashed border-gray-200 rounded-2xl p-8 text-center hover:border-red-300 hover:bg-red-50/30 transition-all cursor-pointer group"
            >
              <div className="w-12 h-12 bg-gray-100 group-hover:bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-3 transition-colors">
                <svg className="w-6 h-6 text-gray-400 group-hover:text-red-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-600 group-hover:text-red-600 transition-colors">Drop your logo here, or click to browse</p>
              <p className="text-xs text-gray-400 mt-1">PNG, SVG, JPG · max 2 MB</p>
            </div>
          )}
        </div>
      </div>

      {/* Primary color */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Primary Color</h2>
          <p className="text-xs text-gray-400 mt-0.5">Updates buttons, badges and accents platform-wide in real-time</p>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="flex flex-wrap gap-2.5">
            {PRESET_COLORS.map(p => (
              <button key={p.hex} onClick={() => setColor(p.hex)} title={p.name}
                className={`w-9 h-9 rounded-xl transition-all ${color === p.hex ? "ring-2 ring-offset-2 ring-gray-400 scale-110" : "hover:scale-105"}`}
                style={{ backgroundColor: p.hex }} />
            ))}
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-500 font-medium flex-shrink-0">Custom hex</label>
            <div className="flex items-center gap-2 border border-gray-200 rounded-xl px-3 py-2 bg-white">
              <input type="color" value={color} onChange={e => setColor(e.target.value)}
                className="w-5 h-5 rounded cursor-pointer border-0 bg-transparent" />
              <span className="text-sm font-mono text-gray-600">{color.toUpperCase()}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Live preview */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Live Preview</h2>
          <p className="text-xs text-gray-400 mt-0.5">This is what the header will look like</p>
        </div>
        <div className="px-6 py-5">
          <div className="border border-gray-100 rounded-xl overflow-hidden shadow-sm">
            <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-100">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-extrabold shadow-sm"
                  style={{ backgroundColor: color }}>
                  {(company || "S")[0].toUpperCase()}
                </div>
                <div>
                  <div className="font-bold text-gray-900 text-sm">{company || "Your Company"}</div>
                  <div className="text-gray-400 text-xs">{tagline || "Your tagline"}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="text-white text-xs font-semibold px-3 py-1.5 rounded-lg"
                  style={{ backgroundColor: color }}>Ask →</button>
              </div>
            </div>
            <div className="bg-gray-50 px-4 py-8 text-center">
              <div className="text-xl font-bold text-gray-800">{company || "Your Company"}</div>
              <div className="text-gray-400 text-sm mt-1">{tagline || "Your tagline here"}</div>
            </div>
          </div>
        </div>
      </div>

      <button onClick={save} disabled={busy}
        className="flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-colors">
        {busy && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
        Save branding
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// RBAC Tab — localStorage-backed
// ══════════════════════════════════════════════════════════════════════════════
type PermKey = "chat" | "view_docs" | "upload_docs" | "delete_docs" | "manage_users" | "manage_roles" | "manage_branding" | "view_analytics" | "export";

const PERMISSIONS: { key: PermKey; label: string; desc: string }[] = [
  { key: "chat",            label: "Chat & Query",      desc: "Ask questions and search the knowledge base" },
  { key: "view_docs",       label: "View Documents",    desc: "Browse and read the document library" },
  { key: "upload_docs",     label: "Upload Documents",  desc: "Add new documents and trigger indexing" },
  { key: "delete_docs",     label: "Delete Documents",  desc: "Permanently remove documents" },
  { key: "manage_users",    label: "Manage Users",      desc: "Invite, edit, and remove user accounts" },
  { key: "manage_roles",    label: "Manage RBAC",       desc: "Create and modify role permissions" },
  { key: "manage_branding", label: "Manage Branding",   desc: "Update logos, colors and platform name" },
  { key: "view_analytics",  label: "View Analytics",    desc: "Access document performance metrics" },
  { key: "export",          label: "Export Data",       desc: "Export query results and usage reports" },
];

const DEFAULT_PERMS: Record<UserRole, PermKey[]> = {
  admin:   PERMISSIONS.map(p => p.key),
  analyst: ["chat","view_docs","upload_docs","view_analytics","export"],
  viewer:  ["chat","view_docs"],
};

function loadPerms(): Record<UserRole, Set<PermKey>> {
  try {
    const s = localStorage.getItem("synaptdi_rbac");
    if (s) {
      const obj = JSON.parse(s);
      return {
        admin:   new Set(obj.admin   ?? DEFAULT_PERMS.admin),
        analyst: new Set(obj.analyst ?? DEFAULT_PERMS.analyst),
        viewer:  new Set(obj.viewer  ?? DEFAULT_PERMS.viewer),
      };
    }
  } catch {}
  return {
    admin:   new Set(DEFAULT_PERMS.admin),
    analyst: new Set(DEFAULT_PERMS.analyst),
    viewer:  new Set(DEFAULT_PERMS.viewer),
  };
}

function savePerms(m: Record<UserRole, Set<PermKey>>) {
  localStorage.setItem("synaptdi_rbac", JSON.stringify({
    admin:   [...m.admin],
    analyst: [...m.analyst],
    viewer:  [...m.viewer],
  }));
}

function RBACTab() {
  const toast = useToast();
  const [matrix, setMatrix] = useState<Record<UserRole, Set<PermKey>>>(() => loadPerms());
  const [counts, setCounts] = useState<Record<UserRole, number>>({ admin: 0, analyst: 0, viewer: 0 });

  useEffect(() => {
    fetch(`${API}/users`)
      .then(r => r.json())
      .then(data => {
        const c: Record<UserRole, number> = { admin: 0, analyst: 0, viewer: 0 };
        for (const u of data.users ?? []) if (u.role in c) c[u.role as UserRole]++;
        setCounts(c);
      })
      .catch(() => {});
  }, []);

  const toggle = (role: UserRole, perm: PermKey) => {
    if (role === "admin") return;
    setMatrix(m => {
      const next = { ...m, [role]: new Set(m[role]) };
      if (next[role].has(perm)) next[role].delete(perm); else next[role].add(perm);
      return next;
    });
  };

  const save = () => {
    savePerms(matrix);
    toast("Role permissions saved");
  };

  const roleMeta: Record<UserRole, { desc: string; color: string }> = {
    admin:   { desc: "Full platform access. Cannot be restricted.", color: "border-red-200 bg-red-50" },
    analyst: { desc: "Query, upload documents and view analytics.",  color: "border-blue-200 bg-blue-50" },
    viewer:  { desc: "Read-only access to chat and documents.",      color: "border-gray-200 bg-gray-50" },
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {(["admin","analyst","viewer"] as UserRole[]).map(r => (
          <div key={r} className={`rounded-2xl border p-5 ${roleMeta[r].color}`}>
            <div className={`text-xs font-bold px-2 py-0.5 rounded-full capitalize w-fit mb-2 ${ROLE_BADGE[r]}`}>{r}</div>
            <p className="text-xs text-gray-500">{roleMeta[r].desc}</p>
            <p className="text-xs text-gray-400 mt-2">{counts[r]} user{counts[r] !== 1 ? "s" : ""}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Permissions Matrix</h2>
          <p className="text-xs text-gray-400 mt-0.5">Analyst and Viewer permissions are editable. Click Save to persist.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-6 py-3.5 w-1/2">Permission</th>
                {(["admin","analyst","viewer"] as UserRole[]).map(r => (
                  <th key={r} className="text-center text-[11px] font-bold uppercase tracking-widest px-4 py-3.5">
                    <span className={`px-2.5 py-1 rounded-full ${ROLE_BADGE[r]}`}>{r}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {PERMISSIONS.map(p => (
                <tr key={p.key} className="hover:bg-gray-50/60 transition-colors">
                  <td className="px-6 py-3.5">
                    <div className="text-sm font-medium text-gray-800">{p.label}</div>
                    <div className="text-xs text-gray-400">{p.desc}</div>
                  </td>
                  {(["admin","analyst","viewer"] as UserRole[]).map(r => {
                    const checked = matrix[r].has(p.key);
                    const locked  = r === "admin";
                    return (
                      <td key={r} className="px-4 py-3.5 text-center">
                        <button onClick={() => toggle(r, p.key)} disabled={locked}
                          className={`w-5 h-5 rounded-md border-2 flex items-center justify-center mx-auto transition-all ${
                            locked   ? "cursor-not-allowed bg-red-500 border-red-500 opacity-70" :
                            checked  ? "bg-red-600 border-red-600 hover:bg-red-700" :
                                       "border-gray-300 bg-white hover:border-red-400"
                          }`}>
                          {checked && (
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3.5">
                              <polyline points="20 6 9 17 4 12"/>
                            </svg>
                          )}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <button onClick={save}
        className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-colors">
        Save permissions
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Page
// ══════════════════════════════════════════════════════════════════════════════
export default function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<AdminTab>("users");
  usePageTitle("Admin");

  if (user?.role !== "admin") {
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center bg-gray-50 h-full">
          <div className="text-center">
            <div className="w-16 h-16 bg-red-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.962-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Access restricted</h2>
            <p className="text-sm text-gray-400 mt-1">You need Admin role to view this page.</p>
          </div>
        </div>
      </AppShell>
    );
  }

  const tabs: { id: AdminTab; label: string }[] = [
    { id: "users",    label: "User Management" },
    { id: "branding", label: "Branding" },
    { id: "rbac",     label: "RBAC" },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-gray-900">Administration</h1>
            <p className="text-xs text-gray-400 mt-0.5">Manage users, branding and access control</p>
          </div>
          <span className="text-[11px] font-bold bg-red-100 text-red-700 px-2.5 py-1 rounded-full">Admin only</span>
        </header>

        <div className="flex border-b border-gray-200 bg-white px-6 flex-shrink-0">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-all -mb-px ${
                tab === t.id ? "border-red-600 text-red-600" : "border-transparent text-gray-500 hover:text-gray-800"
              }`}>{t.label}</button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50">
          <div className="max-w-5xl mx-auto px-6 py-8">
            {tab === "users"    && <UserManagementTab />}
            {tab === "branding" && <BrandingTab />}
            {tab === "rbac"     && <RBACTab />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
