"use client";
import React from "react";

/** Tiny classnames joiner. */
export function cn(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

// ── Button ──────────────────────────────────────────────────────────────────
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
export function Button(
  { variant = "primary", className, ...p }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }
) {
  const base = "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium px-4 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/50 disabled:opacity-50 disabled:cursor-not-allowed";
  const v: Record<BtnVariant, string> = {
    primary:   "bg-red-600 hover:bg-red-700 text-white shadow-sm",
    secondary: "bg-gray-100 dark:bg-slate-800 hover:bg-gray-200 dark:hover:bg-slate-700 text-gray-800 dark:text-slate-100",
    ghost:     "text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-800",
    danger:    "bg-red-600 hover:bg-red-700 text-white shadow-sm",
  };
  return <button className={cn(base, v[variant], className)} {...p} />;
}

// ── Card ────────────────────────────────────────────────────────────────────
export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-2xl shadow-sm", className)} {...p} />;
}

// ── Input ───────────────────────────────────────────────────────────────────
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...p }, ref) {
    return (
      <input ref={ref}
        className={cn("w-full border border-gray-200 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-gray-800 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 bg-gray-50 dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition", className)}
        {...p} />
    );
  }
);

// ── Badge ───────────────────────────────────────────────────────────────────
type Tone = "gray" | "red" | "green" | "amber" | "blue";
export function Badge({ tone = "gray", className, children }: { tone?: Tone; className?: string; children: React.ReactNode }) {
  const t: Record<Tone, string> = {
    gray:  "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700",
    red:   "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30",
    green: "bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/30",
    amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/30",
    blue:  "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/30",
  };
  return <span className={cn("inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border", t[tone], className)}>{children}</span>;
}

// ── Skeleton ────────────────────────────────────────────────────────────────
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

// ── Empty state ─────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, hint, action }:
  { icon?: React.ReactNode; title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      {icon && <div className="w-12 h-12 rounded-2xl bg-gray-100 dark:bg-slate-800 flex items-center justify-center text-gray-400 dark:text-slate-500 mb-3">{icon}</div>}
      <p className="text-sm font-semibold text-gray-700 dark:text-slate-200">{title}</p>
      {hint && <p className="text-xs text-gray-400 dark:text-slate-500 mt-1 max-w-xs leading-relaxed">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
