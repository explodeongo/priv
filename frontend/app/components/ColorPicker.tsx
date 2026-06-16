"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/*
 * ColorPicker — a real color wheel for branding.
 *  · Hue/saturation wheel (drag anywhere on it) + lightness slider
 *  · Editable hex field (paste any #RGB / #RRGGBB)
 *  · Brand presets, harmony suggestions, eyedropper (Chrome), logo-extracted palette
 *  · White-text contrast guard so buttons never become unreadable
 */

// ── Color math ────────────────────────────────────────────────────────────────
function normHex(input: string): string | null {
  let h = input.trim().replace(/^#/, "").toLowerCase();
  if (/^[0-9a-f]{3}$/.test(h)) h = h.split("").map(c => c + c).join("");
  return /^[0-9a-f]{6}$/.test(h) ? `#${h}` : null;
}
function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
}
function hexToHsl(hex: string): [number, number, number] {
  const [r0, g0, b0] = hexToRgb(hex).map(v => v / 255);
  const max = Math.max(r0, g0, b0), min = Math.min(r0, g0, b0);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r0)      h = ((g0 - b0) / d + (g0 < b0 ? 6 : 0)) / 6;
  else if (max === g0) h = ((b0 - r0) / d + 2) / 6;
  else                 h = ((r0 - g0) / d + 4) / 6;
  return [h * 360, s * 100, l * 100];
}
function hslToHex(h: number, s: number, l: number): string {
  h = ((h % 360) + 360) % 360; s /= 100; l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] =
    h < 60  ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] :
    h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
}
function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map(v => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastWithWhite(hex: string): number {
  return 1.05 / (luminance(hex) + 0.05);
}

// ── Logo palette extraction ───────────────────────────────────────────────────
function extractPalette(dataUrl: string): Promise<string[]> {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        const size = 48;
        c.width = size; c.height = size;
        const ctx = c.getContext("2d");
        if (!ctx) return resolve([]);
        ctx.drawImage(img, 0, 0, size, size);
        const data = ctx.getImageData(0, 0, size, size).data;
        const buckets: Record<string, { n: number; r: number; g: number; b: number }> = {};
        for (let i = 0; i < data.length; i += 4) {
          const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
          if (a < 200) continue;
          const max = Math.max(r, g, b), min = Math.min(r, g, b);
          if (max > 235 && min > 235) continue;            // near-white
          if (max < 35) continue;                          // near-black
          if (max - min < 24) continue;                    // grey / low saturation
          const key = `${r >> 5}-${g >> 5}-${b >> 5}`;
          const bk = buckets[key] ?? (buckets[key] = { n: 0, r: 0, g: 0, b: 0 });
          bk.n++; bk.r += r; bk.g += g; bk.b += b;
        }
        const top = Object.values(buckets).sort((a, b) => b.n - a.n).slice(0, 5)
          .map(bk => rgbToHex(bk.r / bk.n, bk.g / bk.n, bk.b / bk.n));
        resolve([...new Set(top)]);
      } catch { resolve([]); }
    };
    img.onerror = () => resolve([]);
    img.src = dataUrl;
  });
}

const PRESETS = [
  { name: "Synapt Red",   hex: "#dc2626" },
  { name: "Slate Blue",   hex: "#3b82f6" },
  { name: "Forest Green", hex: "#16a34a" },
  { name: "Royal Purple", hex: "#7c3aed" },
  { name: "Amber Gold",   hex: "#d97706" },
  { name: "Teal",         hex: "#0d9488" },
  { name: "Rose",         hex: "#e11d48" },
  { name: "Midnight",     hex: "#0f172a" },
];

const WHEEL = 176; // px

export default function ColorPicker({ value, onChange, logo }:
  { value: string; onChange: (hex: string) => void; logo?: string }) {
  const safe = normHex(value) ?? "#dc2626";
  const [h, s, l] = useMemo(() => hexToHsl(safe), [safe]);
  const [hexText, setHexText] = useState(safe);
  const [logoColors, setLogoColors] = useState<string[]>([]);
  const wheelRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Keep the hex field in sync unless the user is mid-typing an invalid value
  useEffect(() => { setHexText(safe); }, [safe]);

  useEffect(() => {
    if (logo) extractPalette(logo).then(setLogoColors);
    else setLogoColors([]);
  }, [logo]);

  const pickFromEvent = useCallback((e: PointerEvent | React.PointerEvent) => {
    const el = wheelRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const r = rect.width / 2;
    const dx = e.clientX - (rect.left + r);
    const dy = e.clientY - (rect.top + r);
    const hue = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
    const sat = Math.min(1, Math.sqrt(dx * dx + dy * dy) / r) * 100;
    onChange(hslToHex(hue, sat, l));
  }, [l, onChange]);

  useEffect(() => {
    const move = (e: PointerEvent) => { if (dragging.current) pickFromEvent(e); };
    const up = () => { dragging.current = false; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [pickFromEvent]);

  // Handle position on the wheel
  const rad = (h * Math.PI) / 180;
  const dist = (s / 100) * (WHEEL / 2 - 8);
  const hx = WHEEL / 2 + Math.cos(rad) * dist;
  const hy = WHEEL / 2 + Math.sin(rad) * dist;

  const contrast = contrastWithWhite(safe);
  const harmony = [
    { label: "Complementary", hex: hslToHex(h + 180, s, l) },
    { label: "Analogous −",   hex: hslToHex(h - 30, s, l) },
    { label: "Analogous +",   hex: hslToHex(h + 30, s, l) },
    { label: "Triadic",       hex: hslToHex(h + 120, s, l) },
  ];
  const hasEyedropper = typeof window !== "undefined" && "EyeDropper" in window;

  const Swatch = ({ hex, title }: { hex: string; title: string }) => (
    <button type="button" onClick={() => onChange(hex)} title={`${title} · ${hex.toUpperCase()}`}
      className={`w-8 h-8 rounded-lg transition-all border border-black/10 dark:border-white/10 ${
        safe.toLowerCase() === hex.toLowerCase() ? "ring-2 ring-offset-2 ring-gray-400 dark:ring-offset-slate-900 scale-110" : "hover:scale-110"
      }`}
      style={{ backgroundColor: hex }} />
  );

  return (
    <div className="flex flex-col sm:flex-row gap-6">
      {/* Wheel + lightness */}
      <div className="flex flex-col items-center gap-3 flex-shrink-0">
        <div
          ref={wheelRef}
          onPointerDown={e => { dragging.current = true; pickFromEvent(e); }}
          className="relative rounded-full cursor-crosshair select-none shadow-inner touch-none"
          style={{
            width: WHEEL, height: WHEEL,
            background: `radial-gradient(circle at 50% 50%, hsl(0 0% ${l}%) 0%, transparent 70%),
                         conic-gradient(from 90deg,
                           hsl(0 100% ${l}%), hsl(60 100% ${l}%), hsl(120 100% ${l}%),
                           hsl(180 100% ${l}%), hsl(240 100% ${l}%), hsl(300 100% ${l}%), hsl(360 100% ${l}%))`,
          }}
        >
          <div className="absolute w-5 h-5 rounded-full border-[3px] border-white shadow-md pointer-events-none"
            style={{ left: hx - 10, top: hy - 10, backgroundColor: safe }} />
        </div>

        <div className="w-full px-1">
          <input
            type="range" min={12} max={92} value={Math.round(l)}
            onChange={e => onChange(hslToHex(h, s, parseInt(e.target.value, 10)))}
            className="w-full h-2.5 rounded-full appearance-none cursor-pointer outline-none
                       [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                       [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow
                       [&::-webkit-slider-thumb]:border [&::-webkit-slider-thumb]:border-gray-300"
            style={{ background: `linear-gradient(to right, #000, ${hslToHex(h, s, 50)}, #fff)` }}
            aria-label="Lightness"
          />
          <div className="text-[10px] text-gray-400 text-center mt-1">Lightness</div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* Hex + eyedropper + contrast */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 border border-gray-200 dark:border-slate-700 rounded-xl pl-3 pr-2 py-2 bg-white dark:bg-slate-800">
            <span className="w-5 h-5 rounded-md border border-black/10 dark:border-white/10 flex-shrink-0" style={{ backgroundColor: safe }} />
            <input
              value={hexText.toUpperCase()}
              onChange={e => {
                setHexText(e.target.value);
                const ok = normHex(e.target.value);
                if (ok) onChange(ok);
              }}
              spellCheck={false}
              className="w-24 text-sm font-mono text-gray-700 dark:text-slate-200 bg-transparent outline-none"
              aria-label="Hex color"
            />
          </div>
          {hasEyedropper && (
            <button type="button"
              onClick={async () => {
                try {
                  const res = await new (window as any).EyeDropper().open();
                  if (res?.sRGBHex) onChange(res.sRGBHex);
                } catch { /* user cancelled */ }
              }}
              title="Pick a color from anywhere on screen"
              className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-slate-300 border border-gray-200 dark:border-slate-700 rounded-xl px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path d="m2 22 1-1h3l9-9M3 21v-3l9-9m6.5-6.5a2.12 2.12 0 0 1 3 3L19 8l-3-3 2.5-2.5z" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Eyedropper
            </button>
          )}
          {contrast < 3 && (
            <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-lg px-2 py-1">
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
              Too light — white button text will be hard to read
            </span>
          )}
        </div>

        {/* Presets */}
        <div>
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">Presets</div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map(p => <Swatch key={p.hex} hex={p.hex} title={p.name} />)}
          </div>
        </div>

        {/* From your logo */}
        {logoColors.length > 0 && (
          <div>
            <div className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">From your logo</div>
            <div className="flex flex-wrap gap-2">
              {logoColors.map(c => <Swatch key={c} hex={c} title="Logo color" />)}
            </div>
          </div>
        )}

        {/* Harmony */}
        <div>
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">Goes well with</div>
          <div className="flex flex-wrap gap-2">
            {harmony.map(hm => <Swatch key={hm.label} hex={hm.hex} title={hm.label} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
