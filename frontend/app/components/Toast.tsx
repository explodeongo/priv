"use client";
import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
type ToastType = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  exiting?: boolean;
}

interface ToastCtx {
  toast: (message: string, type?: ToastType) => void;
}

// ── Context ───────────────────────────────────────────────────────────────────
const ToastContext = createContext<ToastCtx | null>(null);

// ── Icons ─────────────────────────────────────────────────────────────────────
const ICONS: Record<ToastType, React.ReactNode> = {
  success: (
    <div className="w-7 h-7 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0">
      <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>
  ),
  error: (
    <div className="w-7 h-7 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0">
      <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </div>
  ),
  warning: (
    <div className="w-7 h-7 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0">
      <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
  ),
  info: (
    <div className="w-7 h-7 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0">
      <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
    </div>
  ),
};

// ── Single toast ──────────────────────────────────────────────────────────────
function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  return (
    <div
      className="flex items-center gap-3 bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 shadow-2xl text-sm min-w-[280px] max-w-sm pointer-events-auto"
      style={{
        animation: item.exiting
          ? "toastOut 0.25s ease-in forwards"
          : "toastIn 0.3s cubic-bezier(0.21,1.02,0.73,1) forwards",
      }}
    >
      {ICONS[item.type]}
      <span className="text-slate-100 flex-1 leading-snug">{item.message}</span>
      <button
        onClick={() => onDismiss(item.id)}
        className="text-slate-500 hover:text-slate-300 transition-colors ml-1 flex-shrink-0"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>
  );
}

// ── Provider ──────────────────────────────────────────────────────────────────
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    // Mark as exiting first for animation
    setToasts(ts => ts.map(t => t.id === id ? { ...t, exiting: true } : t));
    setTimeout(() => setToasts(ts => ts.filter(t => t.id !== id)), 260);
  }, []);

  const toast = useCallback((message: string, type: ToastType = "success") => {
    const id = Date.now() + Math.random();
    setToasts(ts => [...ts, { id, message, type }]);
    setTimeout(() => dismiss(id), 3800);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      <style>{`
        @keyframes toastIn {
          from { opacity: 0; transform: translateY(12px) scale(0.95); }
          to   { opacity: 1; transform: translateY(0)     scale(1); }
        }
        @keyframes toastOut {
          from { opacity: 1; transform: translateY(0)     scale(1);    max-height: 80px; }
          to   { opacity: 0; transform: translateY(6px)   scale(0.97); max-height: 0;    margin-bottom: 0; }
        }
      `}</style>
      {children}
      <div className="fixed bottom-5 right-5 z-[200] flex flex-col gap-2.5 items-end pointer-events-none">
        {toasts.map(t => (
          <Toast key={t.id} item={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be within ToastProvider");
  return ctx.toast;
}
