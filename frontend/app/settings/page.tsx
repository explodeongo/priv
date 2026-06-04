"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import AppShell from "../components/AppShell";
import { useAuth } from "../components/AuthProvider";
import { useToast } from "../components/Toast";

// ── Preferences helpers (shared with chat page) ───────────────────────────────
const PREFS_KEY = "synaptdi_prefs";
export interface Prefs { topK: number; showSrc: boolean; emailN: boolean; sysAl: boolean; indexN: boolean; }
export const DEFAULT_PREFS: Prefs = { topK: 5, showSrc: true, emailN: true, sysAl: true, indexN: false };
export function loadPrefs(): Prefs {
  try { return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch { return DEFAULT_PREFS; }
}
export function savePrefs(p: Prefs) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch {}
}

type Tab = "profile" | "security" | "preferences";

// ── Page title ────────────────────────────────────────────────────────────────
function usePageTitle(t: string) {
  useEffect(() => { document.title = `${t} · SynaptDI`; return () => { document.title = "SynaptDI"; }; }, [t]);
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function SavedBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-green-600">
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
      Saved
    </span>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button onClick={onChange} role="switch" aria-checked={on}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none flex-shrink-0 ${on ? "bg-red-600" : "bg-gray-200"}`}>
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${on ? "translate-x-6" : "translate-x-1"}`} />
    </button>
  );
}

function SectionCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-5 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

// ── Profile Tab ───────────────────────────────────────────────────────────────
function ProfileTab() {
  const { user, updateUser } = useAuth();
  const toast    = useToast();
  const fileRef  = useRef<HTMLInputElement>(null);
  const [name,   setName]  = useState(user?.name ?? "");
  const [title,  setTitle] = useState(user?.title ?? "");
  const [dept,   setDept]  = useState(user?.department ?? "");
  const [avatar, setAvatar]= useState<string | undefined>(user?.avatar);
  const [uploading, setUploading] = useState(false);

  const initials = name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();

  const save = () => {
    updateUser({ name, title, department: dept, avatar });
    toast("Profile updated successfully");
  };

  // Handle profile photo file selection
  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast("Image must be under 2 MB", "error"); return; }
    if (!file.type.startsWith("image/")) { toast("Please select an image file", "error"); return; }

    setUploading(true);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      setAvatar(dataUrl);
      updateUser({ avatar: dataUrl });   // persist immediately
      setUploading(false);
      toast("Profile photo updated");
    };
    reader.onerror = () => { setUploading(false); toast("Failed to read file", "error"); };
    reader.readAsDataURL(file);
    e.target.value = "";                 // reset so same file can be re-selected
  };

  const removePhoto = () => {
    setAvatar(undefined);
    updateUser({ avatar: undefined });
    toast("Profile photo removed");
  };

  const roleBadge: Record<string, string> = {
    admin: "bg-red-100 text-red-700",
    analyst: "bg-blue-100 text-blue-700",
    viewer: "bg-gray-100 text-gray-600",
  };

  return (
    <div className="space-y-5">
      {/* Hidden file input */}
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden" onChange={handlePhotoSelect} />

      {/* Avatar */}
      <SectionCard title="Profile Photo">
        <div className="flex items-center gap-5">
          {/* Avatar preview */}
          <div className="relative flex-shrink-0">
            {avatar ? (
              <img src={avatar} alt="Profile"
                className="w-16 h-16 rounded-2xl object-cover shadow-md border-2 border-white ring-2 ring-gray-100" />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-red-600 flex items-center justify-center text-white text-2xl font-bold shadow-md select-none">
                {initials || "?"}
              </div>
            )}
            {uploading && (
              <div className="absolute inset-0 rounded-2xl bg-black/40 flex items-center justify-center">
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center gap-3">
              <button onClick={() => fileRef.current?.click()} disabled={uploading}
                className="text-sm font-semibold text-red-600 hover:text-red-700 transition-colors disabled:opacity-50">
                {avatar ? "Change photo" : "Upload photo"}
              </button>
              {avatar && (
                <button onClick={removePhoto}
                  className="text-sm text-gray-400 hover:text-red-500 transition-colors">
                  Remove
                </button>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-1">JPG, PNG, GIF or WebP · max 2 MB</p>
          </div>
        </div>
      </SectionCard>

      {/* Personal info */}
      <SectionCard title="Personal Information">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { label: "Full name", value: name, setter: setName, disabled: false, placeholder: "Your full name" },
            { label: "Email address", value: user?.email ?? "", setter: () => {}, disabled: true, placeholder: "" },
            { label: "Job title", value: title, setter: setTitle, disabled: false, placeholder: "e.g. Solutions Architect" },
            { label: "Department", value: dept, setter: setDept, disabled: false, placeholder: "e.g. Network Architecture" },
          ].map(f => (
            <div key={f.label}>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">{f.label}</label>
              <input value={f.value} onChange={e => !f.disabled && f.setter(e.target.value)}
                placeholder={f.placeholder} disabled={f.disabled}
                className={`w-full border rounded-xl px-3.5 py-2.5 text-sm transition-all focus:outline-none ${
                  f.disabled
                    ? "border-gray-100 bg-gray-50 text-gray-400 cursor-not-allowed"
                    : "border-gray-200 bg-white text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-red-500 focus:border-transparent"
                }`} />
              {f.disabled && <p className="text-[11px] text-gray-400 mt-1">Contact your admin to change email</p>}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-5 pt-5 border-t border-gray-100">
          <button onClick={save}
            className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-colors shadow-sm">
            Save changes
          </button>
        </div>
      </SectionCard>

      {/* Account info */}
      <SectionCard title="Account Details">
        <div className="divide-y divide-gray-100">
          {[
            {
              label: "Role",
              value: <span className={`text-xs font-bold px-2.5 py-1 rounded-full capitalize ${roleBadge[user?.role ?? "viewer"]}`}>{user?.role}</span>
            },
            {
              label: "Member since",
              value: <span className="text-sm font-medium text-gray-800">{(() => {
                const raw = user?.id ? localStorage.getItem("synaptdi_joined_" + user.id) : null;
                if (!raw) return "—";
                return new Date(raw).toLocaleDateString("en-US", { month: "long", year: "numeric" });
              })()}</span>
            },
            {
              label: "Last sign-in",
              value: <span className="text-sm text-gray-500">{(() => {
                const raw = localStorage.getItem("synaptdi_last_login");
                if (!raw) return "—";
                const d = new Date(raw);
                const now = new Date();
                const diffMs = now.getTime() - d.getTime();
                const diffMin = Math.floor(diffMs / 60000);
                if (diffMin < 1) return "Just now";
                if (diffMin < 60) return `${diffMin} minutes ago`;
                if (diffMin < 120) return "1 hour ago";
                if (d.toDateString() === now.toDateString()) return `Today at ${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
                return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " at " + d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
              })()}</span>
            },
          ].map(row => (
            <div key={row.label} className="flex items-center justify-between py-3">
              <span className="text-sm text-gray-500">{row.label}</span>
              {row.value}
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

// ── Security Tab ──────────────────────────────────────────────────────────────
function getDeviceLabel(): string {
  if (typeof navigator === "undefined") return "Unknown device";
  const ua = navigator.userAgent;
  let browser = "Browser";
  if (ua.includes("Chrome") && !ua.includes("Edg")) browser = "Chrome";
  else if (ua.includes("Edg")) browser = "Edge";
  else if (ua.includes("Firefox")) browser = "Firefox";
  else if (ua.includes("Safari") && !ua.includes("Chrome")) browser = "Safari";
  let os = "Unknown OS";
  if (ua.includes("Macintosh")) os = "Mac";
  else if (ua.includes("Windows")) os = "Windows";
  else if (ua.includes("iPhone")) os = "iPhone";
  else if (ua.includes("iPad")) os = "iPad";
  else if (ua.includes("Android")) os = "Android";
  else if (ua.includes("Linux")) os = "Linux";
  return `${os} — ${browser}`;
}

function SecurityTab() {
  const { user } = useAuth();
  const toast = useToast();
  const [cur, setCur]       = useState("");
  const [nw, setNw]         = useState("");
  const [conf, setConf]     = useState("");
  const [twoFA, setTwoFA]   = useState(false);
  const [pwErr, setPwErr]   = useState("");
  const [revoked, setRev]   = useState<number[]>([]);

  const changePw = (e: React.FormEvent) => {
    e.preventDefault();
    if (!cur) { setPwErr("Enter your current password."); return; }
    if (nw.length < 8) { setPwErr("New password must be at least 8 characters."); return; }
    if (nw !== conf) { setPwErr("Passwords do not match."); return; }
    setPwErr("");
    setCur(""); setNw(""); setConf("");
    toast("Password updated successfully");
  };

  const lastLogin = (() => {
    const raw = localStorage.getItem("synaptdi_last_login");
    if (!raw) return "Unknown";
    const d = new Date(raw);
    return `Today at ${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
  })();

  const sessions = [
    { id: 1, device: getDeviceLabel(), location: "Local machine", time: `${lastLogin} · Current session`, current: true },
  ];

  return (
    <div className="space-y-5">
      <SectionCard title="Change Password" subtitle="Minimum 8 characters. Use a mix of letters, numbers and symbols.">
        <form onSubmit={changePw} className="space-y-4">
          {pwErr && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 px-4 py-3 rounded-xl">{pwErr}</div>
          )}
          {[
            { label: "Current password", val: cur, set: setCur, ph: "Enter current password" },
            { label: "New password",     val: nw,  set: setNw,  ph: "Min. 8 characters" },
            { label: "Confirm new password", val: conf, set: setConf, ph: "Repeat new password" },
          ].map(f => (
            <div key={f.label}>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">{f.label}</label>
              <input type="password" value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                className="w-full border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all" />
            </div>
          ))}
          <div className="pt-1">
            <button type="submit"
              className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-colors">
              Update password
            </button>
          </div>
        </form>
      </SectionCard>

      <SectionCard title="Two-Factor Authentication" subtitle="Require a verification code in addition to your password.">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-800">Authenticator app</p>
            <p className="text-xs text-gray-400 mt-0.5">{twoFA ? "2FA is enabled on your account" : "Add an extra layer of security"}</p>
          </div>
          <Toggle on={twoFA} onChange={() => setTwoFA(v => !v)} />
        </div>
        {twoFA && (
          <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800">
            <p className="font-semibold mb-1">Setup required</p>
            <p className="text-xs">Scan the QR code with Google Authenticator, Authy, or any TOTP app to complete 2FA setup.</p>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Active Sessions" subtitle="Devices currently signed in to your account.">
        <div className="divide-y divide-gray-100">
          {sessions.filter(s => !revoked.includes(s.id)).map(s => (
            <div key={s.id} className="flex items-center justify-between py-3.5 first:pt-0 last:pb-0">
              <div className="flex items-start gap-3 min-w-0">
                <div className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${s.current ? "bg-green-100" : "bg-gray-100"}`}>
                  <svg className={`w-4 h-4 ${s.current ? "text-green-600" : "text-gray-400"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                    <line x1="8" y1="21" x2="16" y2="21"/>
                    <line x1="12" y1="17" x2="12" y2="21"/>
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-800">{s.device}</span>
                    {s.current && <span className="text-[11px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold">Active</span>}
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">{s.location} · {s.time}</p>
                </div>
              </div>
              {!s.current && (
                <button onClick={() => setRev(r => [...r, s.id])}
                  className="text-xs font-semibold text-red-500 hover:text-red-700 transition-colors flex-shrink-0 ml-3">
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

// ── Preferences Tab ───────────────────────────────────────────────────────────
function PreferencesTab() {
  const toast = useToast();
  const [topK, setTopK]         = useState(String(DEFAULT_PREFS.topK));
  const [showSrc, setShowSrc]   = useState(DEFAULT_PREFS.showSrc);
  const [emailN, setEmailN]     = useState(DEFAULT_PREFS.emailN);
  const [sysAl, setSysAl]       = useState(DEFAULT_PREFS.sysAl);
  const [indexN, setIndexN]     = useState(DEFAULT_PREFS.indexN);

  useEffect(() => {
    const p = loadPrefs();
    setTopK(String(p.topK));
    setShowSrc(p.showSrc);
    setEmailN(p.emailN);
    setSysAl(p.sysAl);
    setIndexN(p.indexN);
  }, []);

  const save = () => {
    savePrefs({ topK: parseInt(topK) || 5, showSrc, emailN, sysAl, indexN });
    toast("Preferences saved");
  };

  return (
    <div className="space-y-5">
      <SectionCard title="Query Preferences" subtitle="Control how the chat interface retrieves and displays results.">
        <div className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Show source previews</p>
              <p className="text-xs text-gray-400 mt-0.5">Display retrieved document chunks alongside each answer</p>
            </div>
            <Toggle on={showSrc} onChange={() => setShowSrc(v => !v)} />
          </div>
          <div className="flex items-center justify-between gap-4 pt-4 border-t border-gray-100">
            <div>
              <p className="text-sm font-medium text-gray-800">Results per query</p>
              <p className="text-xs text-gray-400 mt-0.5">Number of document chunks to retrieve for each question</p>
            </div>
            <select value={topK} onChange={e => setTopK(e.target.value)}
              className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white min-w-[110px]">
              <option value="3">3 chunks</option>
              <option value="5">5 chunks</option>
              <option value="10">10 chunks</option>
            </select>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Notifications" subtitle="Choose which notifications you'd like to receive.">
        <div className="space-y-5">
          {[
            { label: "Email digests",     desc: "Weekly summaries of your query activity",            val: emailN, set: setEmailN },
            { label: "System alerts",     desc: "In-app notifications for errors and status changes", val: sysAl,  set: setSysAl },
            { label: "Index updates",     desc: "Alert when new documents are added to the index",    val: indexN, set: setIndexN },
          ].map((n, i) => (
            <div key={n.label} className={`flex items-center justify-between gap-4 ${i > 0 ? "pt-5 border-t border-gray-100" : ""}`}>
              <div>
                <p className="text-sm font-medium text-gray-800">{n.label}</p>
                <p className="text-xs text-gray-400 mt-0.5">{n.desc}</p>
              </div>
              <Toggle on={n.val} onChange={() => n.set(v => !v)} />
            </div>
          ))}
        </div>
      </SectionCard>

      <div className="flex items-center gap-3">
        <button onClick={save}
          className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-sm transition-colors">
          Save preferences
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("profile");
  usePageTitle("Settings");

  const tabs: { id: Tab; label: string }[] = [
    { id: "profile",     label: "Profile" },
    { id: "security",    label: "Security" },
    { id: "preferences", label: "Preferences" },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-gray-900">Settings</h1>
            <p className="text-xs text-gray-400 mt-0.5">Manage your account and preferences</p>
          </div>
        </header>

        {/* Tab bar — consistent underline style */}
        <div className="flex border-b border-gray-200 bg-white px-6 flex-shrink-0">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-all -mb-px ${
                tab === t.id ? "border-red-600 text-red-600" : "border-transparent text-gray-500 hover:text-gray-800"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto bg-gray-50">
          <div className="max-w-2xl mx-auto px-6 py-8">
            {tab === "profile"     && <ProfileTab />}
            {tab === "security"    && <SecurityTab />}
            {tab === "preferences" && <PreferencesTab />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
