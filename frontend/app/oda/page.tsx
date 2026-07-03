"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../components/AppShell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CompApi { name: string; segment: string; tmf: string; }
interface Comp {
  code: string; short: string; name: string; block: string;
  spec_url?: string; exposed?: CompApi[]; dependent?: { name: string; tmf: string }[];
}
interface ScoredApi { name: string; segment: string; tmf: string; resolved: boolean; score?: number; coverage?: number | null; api?: string; }
interface OdaReport {
  component: string;
  summary: { exposed_openapi: number; dependent_openapi: number; scored: number; avg_score: number; all_conformant: boolean };
  exposed: ScoredApi[]; dependent: { name: string; segment: string; tmf: string }[]; markdown: string;
}
interface Catalog {
  release: string; directory_url: string;
  blocks: Record<string, string>; components: Comp[];
}

// Functional-block accents (stable order, one colour each).
const BLOCKS: { key: string; color: string }[] = [
  { key: "CoreCommerce", color: "#dc2626" },
  { key: "Production", color: "#2563eb" },
  { key: "PartyManagement", color: "#7c3aed" },
  { key: "Revenue", color: "#d97706" },
  { key: "IntelligenceManagement", color: "#16a34a" },
  { key: "Common", color: "#0d9488" },
];
const blockColor = (k: string) => BLOCKS.find((b) => b.key === k)?.color || "#6b7280";

// ODA function-segment colours — same palette as the Conformance ODA tab.
const SEG: Record<string, { label: string; color: string }> = {
  coreFunction: { label: "Core Function", color: "#16a34a" },
  managementFunction: { label: "Management / Operations", color: "#2563eb" },
  securityFunction: { label: "Security", color: "#dc2626" },
  eventNotification: { label: "Notification / Reporting", color: "#d97706" },
  notification: { label: "Notification / Reporting", color: "#d97706" },
};
const segInfo = (s: string) => SEG[s] || { label: s, color: "#6b7280" };


function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function Hex({ color, size = 26 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="flex-shrink-0">
      <path d="M12 2.5l8.2 4.75v9.5L12 21.5l-8.2-4.75v-9.5z"
        fill={color + "1f"} stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export default function OdaPage() {
  const router = useRouter();
  const [cat, setCat] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [block, setBlock] = useState<string>("all");
  const [sel, setSel] = useState<Comp | null>(null);
  const [report, setReport] = useState<OdaReport | null>(null);
  const [checking, setChecking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const validate = async (file: File) => {
    setChecking(true);
    try {
      const content = await file.text();
      const r = await fetch(`${API}/conformance/component`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` })); throw new Error(d.detail || `HTTP ${r.status}`); }
      setSel(null);
      setReport(await r.json());
    } catch (e: any) {
      setError(e?.message || "Validation failed — is the backend running on port 8000?");
      setTimeout(() => setError(""), 6000);
    } finally { setChecking(false); }
  };

  useEffect(() => {
    fetch(`${API}/oda/components`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setCat)
      .catch(() => setError("Couldn't load the component map — is the backend running on port 8000?"))
      .finally(() => setLoading(false));
  }, []);

  // Esc closes the detail panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setReport(null); setSel(null); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    if (!cat) return [];
    const ql = q.trim().toLowerCase();
    return cat.components.filter((c) =>
      (block === "all" || c.block === block) &&
      (!ql || c.name.toLowerCase().includes(ql) || c.code.toLowerCase().includes(ql) || c.short.toLowerCase().includes(ql)));
  }, [cat, q, block]);

  const grouped = useMemo(() =>
    BLOCKS.map((b) => ({ ...b, label: cat?.blocks[b.key] || b.key, items: filtered.filter((c) => c.block === b.key) }))
      .filter((g) => g.items.length > 0),
  [filtered, cat]);

  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    cat?.components.forEach((c) => { m[c.block] = (m[c.block] || 0) + 1; });
    return m;
  }, [cat]);

  const askAI = (c: Comp) => {
    const question = `What is the ${c.name} ODA component (${c.code})? What is it responsible for, and which TM Forum Open APIs does it typically expose?`;
    router.push(`/?ask=${encodeURIComponent(question)}&scope=kb`);
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full bg-white dark:bg-slate-950">
        <header className="flex items-center justify-between px-6 py-3 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800 shadow-sm flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <span className="font-semibold text-gray-800 dark:text-slate-100 text-sm tracking-tight">ODA Components</span>
            {cat && (
              <span className="text-xs text-gray-400 dark:text-slate-500 bg-gray-100 dark:bg-slate-800 px-2.5 py-1 rounded-full hidden sm:inline-block">
                TM Forum {cat.release} · {cat.components.length} components
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            {cat && (
              <a href={cat.directory_url} target="_blank" rel="noreferrer"
                className="text-xs text-gray-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors hidden sm:block">
                tmforum.org directory ↗
              </a>
            )}
            <input ref={fileRef} type="file" accept=".yaml,.yml,.json" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) validate(f); e.currentTarget.value = ""; }} />
            <button onClick={() => fileRef.current?.click()} disabled={checking}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white transition-colors">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.6 2A9 9 0 1 1 12 3a9 9 0 0 1 9.6 9z" /></svg>
              {checking ? "Validating…" : "Validate a component"}
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="max-w-5xl mx-auto px-4 py-6">

            {/* Toolbar */}
            <div className="sticky top-0 z-10 -mx-4 px-4 pb-3 pt-1 bg-white/95 dark:bg-slate-950/95 backdrop-blur">
              <div className="flex flex-col sm:flex-row gap-2.5">
                <div className="relative flex-1">
                  <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="M21 21l-4.35-4.35" /></svg>
                  <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search components — name or TMFC code…"
                    className="w-full border border-gray-200 dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-sm text-gray-700 dark:text-slate-200 placeholder-gray-400 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-0.5">
                  <button onClick={() => setBlock("all")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap border transition-colors ${block === "all" ? "bg-gray-900 dark:bg-slate-100 text-white dark:text-slate-900 border-transparent" : "border-gray-200 dark:border-slate-700 text-gray-500 dark:text-slate-400 hover:border-gray-300"}`}>
                    All {cat ? `· ${cat.components.length}` : ""}
                  </button>
                  {BLOCKS.map((b) => (
                    <button key={b.key} onClick={() => setBlock(block === b.key ? "all" : b.key)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap border transition-colors ${block === b.key ? "text-white border-transparent" : "border-gray-200 dark:border-slate-700 text-gray-500 dark:text-slate-400 hover:border-gray-300"}`}
                      style={block === b.key ? { background: b.color } : {}}>
                      <span className="w-2 h-2 rounded-sm" style={{ background: block === b.key ? "rgba(255,255,255,.85)" : b.color }} />
                      {cat?.blocks[b.key] || b.key}{counts[b.key] ? ` · ${counts[b.key]}` : ""}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* States */}
            {loading && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-4">
                {Array.from({ length: 9 }).map((_, i) => (
                  <div key={i} className="h-[76px] rounded-xl bg-gray-100 dark:bg-slate-800/60 animate-pulse" />
                ))}
              </div>
            )}
            {error && !loading && (
              <p className="mt-6 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-xl px-4 py-2.5">{error}</p>
            )}
            {!loading && !error && filtered.length === 0 && (
              <div className="text-center py-16 text-sm text-gray-400">No components match “{q}”.</div>
            )}

            {/* Grouped grid */}
            {grouped.map((g) => (
              <section key={g.key} className="mt-6">
                <div className="flex items-center gap-2 mb-2.5">
                  <Hex color={g.color} size={18} />
                  <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: g.color }}>{g.label}</h2>
                  <span className="text-[11px] text-gray-400">{g.items.length}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {g.items.map((c) => (
                    <button key={c.code} onClick={() => setSel(c)}
                      className="text-left bg-white dark:bg-slate-900 rounded-xl border border-gray-200 dark:border-slate-800 shadow-sm p-3.5 hover:border-gray-300 dark:hover:border-slate-600 hover:shadow transition-all group">
                      <div className="flex items-start gap-3">
                        <Hex color={g.color} />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 leading-snug group-hover:text-red-600 dark:group-hover:text-red-400 transition-colors">{c.name}</div>
                          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                            <code className="text-[10.5px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-500 dark:text-slate-400 rounded px-1.5 py-0.5">{c.code}</code>
                            {!!c.exposed?.length && (
                              <span className="text-[10.5px] text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/30 rounded px-1.5 py-0.5">
                                reference impl · {c.exposed.length} APIs
                              </span>
                            )}
                          </div>
                        </div>
                        <svg className="w-4 h-4 text-gray-300 dark:text-slate-600 group-hover:text-gray-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}

            {!loading && !error && (
              <p className="text-center text-xs text-gray-400 dark:text-slate-500 mt-10 mb-4">
                Component map from the TM Forum ODA {cat?.release} release · click a component for details, Q&amp;A and validation.
              </p>
            )}
          </div>
        </main>

        {/* ── Detail slide-over ── */}
        {sel && (
          <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-black/30 backdrop-blur-[1px]" onClick={() => setSel(null)} style={{ animation: "fadeIn .15s ease-out" }} />
            <aside className="absolute inset-y-0 right-0 w-full max-w-md bg-white dark:bg-slate-900 shadow-2xl border-l border-gray-200 dark:border-slate-800 flex flex-col"
              style={{ animation: "slideIn .2s ease-out" }}>
              <style>{`@keyframes slideIn { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } } @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }`}</style>

              <div className="flex items-start gap-3 px-5 pt-5 pb-4 border-b border-gray-100 dark:border-slate-800">
                <Hex color={blockColor(sel.block)} size={34} />
                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-bold text-gray-900 dark:text-slate-100 leading-snug">{sel.name}</h2>
                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    <code className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 rounded px-1.5 py-0.5">{sel.code}</code>
                    <span className="text-[11px] rounded px-1.5 py-0.5 border" style={{ color: blockColor(sel.block), borderColor: blockColor(sel.block) + "55", background: blockColor(sel.block) + "12" }}>
                      {cat?.blocks[sel.block] || sel.block}
                    </span>
                  </div>
                </div>
                <button onClick={() => setSel(null)} aria-label="Close"
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
                  <svg className="w-4.5 h-4.5 w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
                {/* Actions */}
                <div className="space-y-2">
                  <button onClick={() => askAI(sel)}
                    className="w-full flex items-center justify-center gap-2 text-sm font-medium px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white transition-colors">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.9A7.96 7.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                    Ask AI about this component
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <a href={sel.spec_url} target="_blank" rel="noreferrer"
                      className="flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:border-gray-300 dark:hover:border-slate-500 transition-colors">
                      Specification ↗
                    </a>
                    <button onClick={() => fileRef.current?.click()}
                      className="flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:border-gray-300 dark:hover:border-slate-500 transition-colors">
                      Validate implementation
                    </button>
                  </div>
                </div>

                {/* APIs — only when we have real manifest data */}
                {sel.exposed?.length ? (
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Exposed Open APIs (reference implementation)</div>
                    <div className="space-y-1.5">
                      {sel.exposed.map((a, i) => (
                        <div key={i} className="flex items-center gap-2.5 rounded-lg border border-gray-100 dark:border-slate-800 px-3 py-2">
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: segInfo(a.segment).color }} />
                          <div className="min-w-0 flex-1">
                            <div className="text-xs font-medium text-gray-800 dark:text-slate-200 truncate">{a.name}</div>
                            <div className="text-[10.5px] text-gray-400">{segInfo(a.segment).label}</div>
                          </div>
                          {a.tmf && <code className="text-[10.5px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-500 dark:text-slate-400 rounded px-1.5 py-0.5 flex-shrink-0">{a.tmf}</code>}
                        </div>
                      ))}
                    </div>
                    {!!sel.dependent?.length && (
                      <div className="mt-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">Depends on</div>
                        <div className="flex flex-wrap gap-1.5">
                          {sel.dependent.map((d, i) => (
                            <code key={i} className="text-[11px] font-mono bg-gray-50 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 rounded px-1.5 py-0.5">{d.name}{d.tmf ? ` (${d.tmf})` : ""}</code>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-800/50 border border-gray-200 dark:border-slate-800 rounded-xl px-3.5 py-3 leading-relaxed">
                    The machine-readable API list for this component lives in its official specification (link above). Ask the AI for a grounded summary, or or click <span className="font-medium">Validate implementation</span> and drop your own <code className="font-mono">.component.yaml</code> to score it right here.
                  </div>
                )}

                <p className="text-[11px] text-gray-400 dark:text-slate-500">
                  Data: TM Forum ODA {cat?.release} component map. Validation runs SynaptDI's deterministic engine — no AI in the scoring.
                </p>
              </div>
            </aside>
          </div>
        )}

        {/* -- Component validation report -- */}
        {report && (
          <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-black/40 backdrop-blur-[1px]" onClick={() => setReport(null)} />
            <div className="absolute inset-x-0 top-[6vh] mx-auto w-full max-w-2xl px-4">
              <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 shadow-2xl max-h-[86vh] flex flex-col" style={{ animation: "fadeUp .2s ease-out" }}>
                <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(10px);} to {opacity:1; transform:none;} }`}</style>

                <div className="flex items-center gap-4 px-5 py-4 border-b border-gray-100 dark:border-slate-800">
                  <div className="relative flex-shrink-0 w-16 h-16 rounded-full flex items-center justify-center"
                    style={{ background: `conic-gradient(${report.summary.avg_score >= 90 ? "#16a34a" : report.summary.avg_score >= 60 ? "#d97706" : "#dc2626"} ${report.summary.avg_score * 3.6}deg, var(--ring-track, #e5e7eb) 0deg)` }}>
                    <div className="w-[52px] h-[52px] rounded-full bg-white dark:bg-slate-900 flex flex-col items-center justify-center">
                      <span className="text-lg font-extrabold text-gray-900 dark:text-slate-100">{report.summary.avg_score}</span>
                      <span className="text-[9px] text-gray-400 -mt-0.5">avg</span>
                    </div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">ODA Component conformance</div>
                    <h2 className="text-base font-bold text-gray-900 dark:text-slate-100 truncate">{report.component}</h2>
                    <div className="flex flex-wrap gap-1.5 mt-1 text-[11px]">
                      <span className={`px-2 py-0.5 rounded-full border ${report.summary.all_conformant ? "bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/30" : "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/30"}`}>
                        {report.summary.all_conformant ? "ODA-conformant" : "gaps found"}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300">{report.summary.exposed_openapi} exposed</span>
                      <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300">{report.summary.dependent_openapi} dependent</span>
                    </div>
                  </div>
                  <button onClick={() => setReport(null)} aria-label="Close"
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0">
                    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                  {Array.from(new Set(report.exposed.map((a) => a.segment))).map((seg) => {
                    const info = segInfo(seg);
                    const apis = report.exposed.filter((a) => a.segment === seg);
                    return (
                      <div key={seg}>
                        <div className="flex items-center gap-2 mb-2">
                          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: info.color }} />
                          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: info.color }}>{info.label}</span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                          {apis.map((a, i) => (
                            <div key={i} className="rounded-xl border border-gray-200 dark:border-slate-800 p-3.5" style={{ borderLeft: `3px solid ${info.color}` }}>
                              <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">{a.name}</div>
                                  <div className="text-[11px] text-gray-400">{a.tmf || "-"}{a.api ? ` · ${a.api}` : ""}</div>
                                </div>
                                {typeof a.score === "number"
                                  ? <span className="text-sm font-bold flex-shrink-0" style={{ color: a.score >= 90 ? "#16a34a" : a.score >= 60 ? "#d97706" : "#dc2626" }}>{a.score}<span className="text-gray-400 text-xs font-normal">/100</span></span>
                                  : <span className="text-[11px] text-gray-400 flex-shrink-0">spec not found</span>}
                              </div>
                              {typeof a.coverage === "number" && (
                                <div className="mt-2">
                                  <div className="flex justify-between text-[10px] text-gray-400 mb-0.5"><span>coverage vs canonical</span><span>{a.coverage}%</span></div>
                                  <div className="h-1.5 rounded-full bg-gray-100 dark:bg-slate-800 overflow-hidden">
                                    <div className="h-full rounded-full" style={{ width: `${a.coverage}%`, background: a.coverage >= 80 ? "#16a34a" : a.coverage >= 50 ? "#d97706" : "#dc2626" }} />
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}

                  {report.dependent.length > 0 && (
                    <div className="bg-gray-50 dark:bg-slate-800/40 rounded-xl border border-gray-200 dark:border-slate-800 px-4 py-3">
                      <div className="text-xs font-semibold text-gray-600 dark:text-slate-300 mb-1.5">Depends on</div>
                      <div className="flex flex-wrap gap-1.5">
                        {report.dependent.map((d, i) => (
                          <code key={i} className="text-[11px] font-mono bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 rounded px-1.5 py-0.5">{d.name} ({d.tmf || "?"})</code>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 dark:border-slate-800">
                  <p className="text-[11px] text-gray-400 dark:text-slate-500">Deterministic - no AI in the scoring.</p>
                  <div className="flex items-center gap-3">
                    <button onClick={() => fileRef.current?.click()} className="text-xs font-medium text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200">Check another</button>
                    <button onClick={() => download(`${report.component}-oda-conformance.md`, report.markdown)}
                      className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline underline-offset-2">Download report (.md)</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
