"use client";
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Branding {
  companyName:  string;
  tagline:      string;
  primaryColor: string;
}

const DEFAULTS: Branding = {
  companyName:  "SynaptDI",
  tagline:      "Enterprise domains at your fingertips",
  primaryColor: "#dc2626",
};

interface BrandingCtx {
  branding:      Branding;
  setBranding:   (b: Branding) => void;
  saveBranding:  (b: Branding) => Promise<void>;
  isLoading:     boolean;
}

const Ctx = createContext<BrandingCtx | null>(null);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, _setBranding] = useState<Branding>(DEFAULTS);
  const [isLoading, setIsLoading] = useState(true);

  // Apply CSS custom property so all red-* Tailwind classes update in real-time
  const applyColor = useCallback((color: string) => {
    const root = document.documentElement;
    // Tailwind v4 uses CSS vars for colors — override the red palette
    root.style.setProperty("--color-red-600", color);
    // Darken ~10% for hover states
    root.style.setProperty("--color-red-700", darken(color, 0.1));
    root.style.setProperty("--color-red-500", lighten(color, 0.1));
    root.style.setProperty("--color-red-400", lighten(color, 0.2));
    root.style.setProperty("--color-red-50",  lighten(color, 0.85));
    root.style.setProperty("--color-red-100", lighten(color, 0.7));
    root.style.setProperty("--color-red-200", lighten(color, 0.5));
    root.style.setProperty("--color-red-300", lighten(color, 0.35));
  }, []);

  const setBranding = useCallback((b: Branding) => {
    _setBranding(b);
    applyColor(b.primaryColor);
    // Persist locally so the sidebar updates before API responds
    try { localStorage.setItem("synaptdi_branding", JSON.stringify(b)); } catch {}
  }, [applyColor]);

  // Fetch from backend on mount (latest saved wins)
  useEffect(() => {
    // Apply local cache immediately to avoid flash
    try {
      const cached = localStorage.getItem("synaptdi_branding");
      if (cached) {
        const b = JSON.parse(cached) as Branding;
        _setBranding(b);
        applyColor(b.primaryColor);
      }
    } catch {}

    fetch(`${API}/branding`)
      .then(r => r.json())
      .then((b: Branding) => {
        setBranding(b);
      })
      .catch(() => {/* use defaults */})
      .finally(() => setIsLoading(false));
  }, [applyColor, setBranding]);

  const saveBranding = useCallback(async (b: Branding) => {
    setBranding(b); // apply immediately
    const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
    await fetch(`${API}/branding`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: JSON.stringify(b),
    });
  }, [setBranding]);

  return (
    <Ctx.Provider value={{ branding, setBranding, saveBranding, isLoading }}>
      {children}
    </Ctx.Provider>
  );
}

export function useBranding() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useBranding must be inside BrandingProvider");
  return ctx;
}

// ── Colour math helpers ───────────────────────────────────────────────────────
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map(c => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
}

function darken(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r * (1 - amount), g * (1 - amount), b * (1 - amount));
}

function lighten(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount);
}
