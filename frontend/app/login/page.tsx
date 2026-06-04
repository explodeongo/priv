"use client";
import { useState } from "react";
import { useAuth } from "../components/AuthProvider";

export default function LoginPage() {
  const { login, user, isLoading } = useAuth();
  const [email, setEmail]       = useState("admin@synaptdi.com");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [remember, setRemember] = useState(false);
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) { setError("Please enter your email and password."); return; }
    setError("");
    setBusy(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  // Redirect is handled by AuthProvider — don't render form while loading/redirecting
  if (isLoading || user) return null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Ambient glows */}
      <div className="absolute -top-48 -right-48 w-96 h-96 bg-red-600/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-48 -left-48 w-96 h-96 bg-red-600/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-[420px]">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Top accent bar */}
          <div className="h-1 bg-gradient-to-r from-red-700 via-red-500 to-red-700" />

          <div className="px-8 pt-8 pb-6">
            {/* Brand header */}
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-14 h-14 bg-red-600 rounded-2xl mb-4 shadow-lg">
                <span className="text-white font-extrabold text-2xl select-none">S</span>
              </div>
              <h1 className="text-[22px] font-bold text-gray-900 tracking-tight">Welcome back</h1>
              <p className="text-gray-400 text-sm mt-1">Sign in to SynaptDI</p>
            </div>

            {/* Error banner */}
            {error && (
              <div className="mb-5 flex items-start gap-2.5 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
                </svg>
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email */}
              <div>
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                  Email address
                </label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  autoComplete="email" placeholder="you@company.com"
                  className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all" />
              </div>

              {/* Password */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide">Password</label>
                  <button type="button" className="text-xs font-medium text-red-600 hover:text-red-700 transition-colors">
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <input type={showPw ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)}
                    autoComplete="current-password" placeholder="••••••••"
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 pr-11 text-sm text-gray-900 placeholder-gray-400 bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all" />
                  <button type="button" onClick={() => setShowPw(v => !v)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors">
                    {showPw ? (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/>
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Remember me */}
              <div className="flex items-center gap-2.5">
                <button type="button" onClick={() => setRemember(v => !v)}
                  className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                    remember ? "bg-red-600 border-red-600" : "border-gray-300 bg-white"
                  }`}>
                  {remember && (
                    <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3.5">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  )}
                </button>
                <label onClick={() => setRemember(v => !v)} className="text-sm text-gray-600 cursor-pointer select-none">
                  Keep me signed in
                </label>
              </div>

              {/* Submit */}
              <button type="submit" disabled={busy}
                className="w-full mt-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl text-sm transition-all shadow-sm flex items-center justify-center gap-2">
                {busy ? (
                  <>
                    <div className="w-4 h-4 border-[2.5px] border-white/30 border-t-white rounded-full animate-spin" />
                    Signing in…
                  </>
                ) : "Sign in"}
              </button>
            </form>
          </div>

          {/* Demo credentials panel */}
          <div className="mx-6 mb-6 p-4 bg-slate-50 rounded-xl border border-slate-200">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-2.5">Demo credentials</p>
            <div className="space-y-1.5">
              {[
                { role: "Admin",   email: "admin@synaptdi.com",   pw: "admin123",   color: "bg-red-100 text-red-700" },
                { role: "Analyst", email: "analyst@synaptdi.com", pw: "analyst123", color: "bg-blue-100 text-blue-700" },
                { role: "Viewer",  email: "lisa@synaptdi.com",    pw: "viewer123",  color: "bg-gray-100 text-gray-600" },
              ].map(c => (
                <button key={c.email} type="button"
                  onClick={() => { setEmail(c.email); setPassword(c.pw); setError(""); }}
                  className="w-full text-left flex items-center gap-2.5 px-2.5 py-2 rounded-lg hover:bg-white transition-all group border border-transparent hover:border-slate-200 hover:shadow-sm">
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md flex-shrink-0 ${c.color}`}>{c.role}</span>
                  <span className="text-xs text-slate-500 font-mono truncate group-hover:text-slate-700 transition-colors">{c.email}</span>
                  <span className="text-xs text-slate-300 font-mono ml-auto flex-shrink-0">{c.pw}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-3.5 bg-gray-50 border-t border-gray-100 text-center">
            <p className="text-[11px] text-gray-400">© 2025 SynaptDI · Enterprise Domain Intelligence Platform</p>
          </div>
        </div>
      </div>
    </div>
  );
}
