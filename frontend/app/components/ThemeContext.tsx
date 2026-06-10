"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";

export type Theme = "light" | "dark" | "system";
interface ThemeCtxValue {
  theme: Theme;                       // the user's chosen mode
  resolved: "light" | "dark";         // what's actually applied right now
  setTheme: (t: Theme) => void;
  cycle: () => void;                  // light → dark → system → light
}

const ThemeCtx = createContext<ThemeCtxValue | null>(null);
const KEY = "synaptdi_theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme: Theme): "light" | "dark" {
  const dark = theme === "dark" || (theme === "system" && systemPrefersDark());
  if (typeof document !== "undefined") document.documentElement.classList.toggle("dark", dark);
  return dark ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");

  // Hydrate from storage + keep "system" in sync with the OS preference.
  useEffect(() => {
    const stored = ((typeof localStorage !== "undefined" && localStorage.getItem(KEY)) as Theme) || "system";
    setThemeState(stored);
    setResolved(applyTheme(stored));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const cur = (localStorage.getItem(KEY) as Theme) || "system";
      if (cur === "system") setResolved(applyTheme("system"));
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    try { localStorage.setItem(KEY, t); } catch {}
    setThemeState(t);
    setResolved(applyTheme(t));
  }, []);

  const cycle = useCallback(() => {
    setThemeState(prev => {
      const next: Theme = prev === "light" ? "dark" : prev === "dark" ? "system" : "light";
      try { localStorage.setItem(KEY, next); } catch {}
      setResolved(applyTheme(next));
      return next;
    });
  }, []);

  return (
    <ThemeCtx.Provider value={{ theme, resolved, setTheme, cycle }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export function useTheme(): ThemeCtxValue {
  const c = useContext(ThemeCtx);
  if (!c) throw new Error("useTheme must be used within ThemeProvider");
  return c;
}
