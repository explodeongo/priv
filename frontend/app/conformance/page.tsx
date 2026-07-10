"use client";
import { useState, useRef, useEffect, Fragment } from "react";
import AppShell from "../components/AppShell";
import { useToast } from "../components/Toast";
import ODACatalogFlow from "./oda/ODACatalogFlow";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Finding {
  id: string; title: string;
  severity: "error" | "warning" | "info";
  status: "pass" | "fail";
  detail: string; ref?: string; examples: string[];
}
interface Profile {
  detected: null | { tmf: string; title: string; version: string; confidence: string };
  coverage?: number;
  operations?: { total: number; present: number; missing: { method: string; path: string }[] };
  resource?: { name: string; user_attrs: number; canonical_attrs: number; missing: string[] };
}
interface Report {
  api: string; version: string; score: number; fixable?: number; filename?: string;
  summary: { passed: number; failed: number; warnings: number; total: number };
  findings: Finding[]; profile?: Profile;
}
interface Row {
  file: string; api: string; structural: number; errors: number; warnings: number; fixable: number;
  failing?: string[];
  profile: null | { tmf: string; version: string; coverage: number; missing_ops: number; missing_fields: number;
    top_fields: string[]; resource?: string; operations?: string[]; fields?: string[] };
}
interface Portfolio {
  generated: string;
  summary: { apis: number; detected: number; avg_structural: number; avg_coverage: number; fully_compliant: number };
  rows: Row[]; markdown: string;
}

const tone = (s: number) =>
  s >= 85 ? { text: "text-green-600 dark:text-green-400", ring: "#16a34a", label: "Strong conformance" }
  : s >= 60 ? { text: "text-amber-600 dark:text-amber-400", ring: "#d97706", label: "Needs work" }
  : { text: "text-red-600 dark:text-red-400", ring: "#dc2626", label: "Major gaps" };

const covColor = (c: number) => (c >= 80 ? "#16a34a" : c >= 50 ? "#d97706" : "#dc2626");

function download(name: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

export default function ConformancePage() {
  const [mode, setMode] = useState<"single" | "portfolio" | "odactk">("single");
  const [report, setReport] = useState<Report | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [openRows, setOpenRows] = useState<Set<number>>(new Set());
  const [specText, setSpecText] = useState("");
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixed, setFixed] = useState<{ score: number; fixed: string[]; content: string; format: string } | null>(null);
  const [scaffolding, setScaffolding] = useState(false);
  const [scaffolded, setScaffolded] = useState<{ before: number; after: number; ops: number; fields: number; content: string; format: string } | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const multiRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const reset = () => { setReport(null); setPortfolio(null); setError(""); setFileName(""); setFixed(null); setScaffolded(null); setSpecText(""); };

  // Deep-link: /conformance?mode=portfolio
  useEffect(() => {
    const m = new URLSearchParams(window.location.search).get("mode");
    if (m === "portfolio" || m === "single" || m === "odactk") setMode(m);
  }, []);

  const checkSingle = async (file: File) => {
    setLoading(true); setError(""); setReport(null); setFixed(null); setScaffolded(null); setFileName(file.name);
    try {
      const content = await file.text();
      setSpecText(content);
      const r = await fetch(`${API}/conformance/text`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, filename: file.name }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` })); throw new Error(d.detail || `HTTP ${r.status}`); }
      const data: Report = await r.json();
      setReport(data);
      toast(`Conformance ${data.score}/100`, data.score >= 85 ? "success" : data.score >= 60 ? "warning" : "error");
    } catch (e: any) {
      const m = e?.message || "Check failed — is the backend running on port 8000?";
      setError(m); toast(m, "error");
    } finally { setLoading(false); }
  };

  const autofix = async () => {
    if (!specText) return;
    setFixing(true);
    try {
      const r = await fetch(`${API}/conformance/fix`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: specText }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const out = await r.json();
      if (!out.fixed?.length) { toast("Nothing here can be auto-fixed.", "warning"); return; }
      setFixed({ score: out.score, fixed: out.fixed, content: out.content, format: out.format });
      setSpecText(out.content);
      // re-check the fixed spec so the whole report updates
      const rc = await fetch(`${API}/conformance/text`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: out.content, filename: fileName }),
      });
      if (rc.ok) setReport(await rc.json());
      toast(`Auto-fixed ${out.fixed.length} issue(s) → ${out.score}/100`, "success");
    } catch (e: any) {
      toast(e?.message || "Auto-fix failed — is the backend running?", "error");
    } finally { setFixing(false); }
  };

  const scaffold = async () => {
    if (!specText) return;
    setScaffolding(true);
    try {
      const r = await fetch(`${API}/conformance/scaffold`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: specText }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` })); throw new Error(d.detail || `HTTP ${r.status}`); }
      const out = await r.json();
      const ops = out.added?.operations?.length || 0;
      const fields = out.added?.fields?.length || 0;
      if (!ops && !fields) { toast("Already complete — nothing to scaffold.", "warning"); return; }
      setScaffolded({ before: out.coverage_before, after: out.coverage_after, ops, fields, content: out.content, format: out.format });
      toast(`Scaffolded +${ops} ops, +${fields} fields → ${out.coverage_after}% coverage`, "success");
    } catch (e: any) {
      toast(e?.message || "Scaffold failed — is the backend running?", "error");
    } finally { setScaffolding(false); }
  };

  const checkPortfolio = async (files: File[]) => {
    setLoading(true); setError(""); setPortfolio(null);
    try {
      const specs = await Promise.all(files.slice(0, 300).map(async (f) => ({ filename: f.name, content: await f.text() })));
      const r = await fetch(`${API}/conformance/portfolio`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ specs }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: Portfolio = await r.json();
      setPortfolio(data);
      toast(`X-ray: ${data.summary.apis} API(s), avg coverage ${data.summary.avg_coverage}%`, "success");
    } catch (e: any) {
      const m = e?.message || "X-ray failed — is the backend running on port 8000?";
      setError(m); toast(m, "error");
    } finally { setLoading(false); }
  };

  const sorted = report ? [...report.findings].sort((a, b) => {
    const rank = (f: Finding) => (f.status === "fail" ? (f.severity === "error" ? 0 : 1) : 2);
    return rank(a) - rank(b);
  }) : [];
  const t = report ? tone(report.score) : null;
  const prof = report?.profile;
  const det = prof?.detected;
  const showProfile = !!det && det.confidence === "high";

  return (
    <AppShell>
      <div className="flex flex-col h-full bg-white dark:bg-slate-950">
        <header className="flex items-center justify-between px-6 py-3 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800 shadow-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-gray-800 dark:text-slate-100 text-sm tracking-tight">TMF Conformance &amp; X-ray</span>
            <div className="hidden sm:flex items-center gap-1 bg-gray-100 dark:bg-slate-800 rounded-lg p-0.5 text-xs">
              {(["single", "portfolio", "odactk"] as const).map((m) => (
                <button key={m} onClick={() => { setMode(m); reset(); }}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${mode === m ? "bg-white dark:bg-slate-700 text-gray-900 dark:text-white shadow-sm" : "text-gray-500 dark:text-slate-400"}`}>
                  {m === "single" ? "Single spec" : m === "portfolio" ? "Portfolio X-ray" : "ODA Component CTK"}
                </button>
              ))}
            </div>
          </div>
          {(report || portfolio) && (
            <button onClick={reset}
              className="text-xs text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
              Start over
            </button>
          )}
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-8">
          <div className="max-w-3xl mx-auto">

            {/* ── ODA Component Catalog → details → existing execution UI (Phase 6A) ── */}
            {mode === "odactk" && <ODACatalogFlow />}

            {/* ── Upload ── */}
            {mode !== "odactk" && !report && !portfolio && (
              <div className="flex flex-col items-center">
                <div className="text-center mb-6">
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                    {mode === "single" ? "Check your API against TM Forum" : "X-ray your whole API estate"}
                  </h2>
                  <p className="text-gray-500 dark:text-slate-400 text-sm mt-1.5 max-w-md">
                    {mode === "single"
                      ? "Upload one OpenAPI / Swagger spec for a TMF630 structural score and a coverage check against the real TM Forum API."
                      : "Select many specs (or a whole folder's worth) for a portfolio report — structural score and TMF coverage per API."}
                  </p>
                </div>

                <label
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault(); setDragging(false);
                    const files = Array.from(e.dataTransfer.files || []);
                    if (!files.length) return;
                    if (mode === "single") checkSingle(files[0]); else checkPortfolio(files);
                  }}
                  className={`w-full max-w-xl cursor-pointer rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all ${
                    dragging ? "border-red-400 bg-red-50 dark:bg-red-500/10"
                    : "border-gray-300 dark:border-slate-700 hover:border-red-300 dark:hover:border-slate-600 bg-gray-50 dark:bg-slate-900"
                  }`}>
                  <input ref={inputRef} type="file" accept=".json,.yaml,.yml" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) checkSingle(f); }} />
                  <input ref={multiRef} type="file" accept=".json,.yaml,.yml" multiple className="hidden"
                    onChange={(e) => { const fs = Array.from(e.target.files || []); if (fs.length) checkPortfolio(fs); }} />
                  <div
                    onClick={(e) => { e.preventDefault(); (mode === "single" ? inputRef : multiRef).current?.click(); }}
                    className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3 transition-colors ${dragging ? "bg-red-100 dark:bg-red-500/20" : "bg-gray-100 dark:bg-slate-800"}`}>
                    {loading ? (
                      <span className="flex gap-1">{[0, 150, 300].map((d) => <span key={d} className="w-2 h-2 rounded-full bg-red-500 animate-bounce" style={{ animationDelay: `${d}ms` }} />)}</span>
                    ) : (
                      <svg className="w-6 h-6 text-gray-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.9A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" /></svg>
                    )}
                  </div>
                  <p className="text-sm font-medium text-gray-700 dark:text-slate-200"
                    onClick={(e) => { e.preventDefault(); (mode === "single" ? inputRef : multiRef).current?.click(); }}>
                    {loading ? `Analysing ${fileName || "specs"}…` : mode === "single" ? "Drop your spec here, or click to choose" : "Drop your specs here, or click to choose several"}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-slate-500 mt-1">"OpenAPI 3 or Swagger 2 · JSON or YAML"</p>
                </label>

                {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-xl px-4 py-2.5">{error}</p>}
              </div>
            )}

            {/* ── Single-spec report ── */}
            {report && t && (
              <div style={{ animation: "fadeUp 0.3s ease-out" }}>
                <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(10px);} to {opacity:1; transform:translateY(0);} }`}</style>

                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 shadow-sm p-6 flex items-center gap-6">
                  <div className="relative flex-shrink-0 w-24 h-24 rounded-full flex items-center justify-center"
                    style={{ background: `conic-gradient(${t.ring} ${report.score * 3.6}deg, var(--ring-track, #e5e7eb) 0deg)` }}>
                    <div className="w-[76px] h-[76px] rounded-full bg-white dark:bg-slate-900 flex flex-col items-center justify-center">
                      <span className={`text-2xl font-extrabold ${t.text}`}>{report.score}</span>
                      <span className="text-[10px] text-gray-400 dark:text-slate-500 -mt-0.5">/ 100</span>
                    </div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className={`text-sm font-bold ${t.text}`}>{t.label}</div>
                    <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 truncate">{report.api}{report.version ? ` v${report.version}` : ""}</h2>
                    <div className="flex flex-wrap gap-2 mt-2 text-xs">
                      <span className="px-2 py-0.5 rounded-full bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/30">{report.summary.passed} passed</span>
                      <span className="px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30">{report.summary.failed} errors</span>
                      <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30">{report.summary.warnings} warnings</span>
                    </div>
                  </div>
                  {!!report.fixable && report.fixable > 0 && (
                    <button onClick={autofix} disabled={fixing}
                      className="flex-shrink-0 text-sm font-medium px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white transition-colors">
                      {fixing ? "Fixing…" : `Auto-fix ${report.fixable}`}
                    </button>
                  )}
                </div>

                {fixed && (
                  <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 px-4 py-2.5">
                    <span className="text-xs text-green-800 dark:text-green-300">Auto-fixed: {fixed.fixed.join(", ")} → {fixed.score}/100</span>
                    <button onClick={() => download(`fixed-${fileName || "spec." + fixed.format}`, fixed.content, "text/plain")}
                      className="text-xs font-medium text-green-700 dark:text-green-300 underline underline-offset-2">Download corrected spec</button>
                  </div>
                )}

                {scaffolded && (
                  <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 px-4 py-2.5">
                    <span className="text-xs text-green-800 dark:text-green-300">
                      Scaffolded: <span className="font-semibold">+{scaffolded.ops} operations, +{scaffolded.fields} fields</span> — coverage <span className="font-bold">{scaffolded.before}% → {scaffolded.after}%</span>
                    </span>
                    <button onClick={() => download(`scaffolded-${fileName || "spec." + scaffolded.format}`, scaffolded.content, "text/plain")}
                      className="text-xs font-medium text-green-700 dark:text-green-300 underline underline-offset-2 whitespace-nowrap">Download completed spec</button>
                  </div>
                )}

                {/* Profile coverage vs the real TMF spec */}
                {showProfile && det && prof && (
                  <div className="mt-4 bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 shadow-sm p-5">
                    <div className="flex items-center justify-between gap-3 mb-3">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">Measured against the real spec</div>
                        <h3 className="text-base font-bold text-gray-900 dark:text-slate-100">{det.tmf} · {det.title} <span className="font-normal text-gray-400">v{det.version}</span></h3>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="text-2xl font-extrabold" style={{ color: covColor(prof.coverage ?? 0) }}>{prof.coverage ?? 0}%</div>
                        <div className="text-[10px] text-gray-400 dark:text-slate-500">reference coverage</div>
                        {((prof.operations?.missing.length ?? 0) + (prof.resource?.missing.length ?? 0)) > 0 && (
                          <button onClick={scaffold} disabled={scaffolding}
                            className="mt-2 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white transition-colors whitespace-nowrap">
                            {scaffolding ? "Scaffolding…" : "Complete with Scaffold"}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 dark:bg-slate-800 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${prof.coverage ?? 0}%`, background: covColor(prof.coverage ?? 0) }} />
                    </div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 mt-2">
                      {prof.operations ? `${prof.operations.present}/${prof.operations.total} operations` : ""}
                      {prof.resource ? ` · ${prof.resource.canonical_attrs - prof.resource.missing.length}/${prof.resource.canonical_attrs} ${prof.resource.name} attributes implemented` : ""}
                    </div>

                    {!!prof.operations?.missing.length && (
                      <div className="mt-3">
                        <div className="text-xs font-semibold text-gray-600 dark:text-slate-300 mb-1">Missing operations</div>
                        <div className="flex flex-wrap gap-1.5">
                          {prof.operations.missing.slice(0, 10).map((o, i) => (
                            <code key={i} className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded">{o.method} {o.path}</code>
                          ))}
                        </div>
                      </div>
                    )}
                    {!!prof.resource?.missing.length && (
                      <div className="mt-3">
                        <div className="text-xs font-semibold text-gray-600 dark:text-slate-300 mb-1">Missing {prof.resource.name} attributes ({prof.resource.missing.length})</div>
                        <div className="flex flex-wrap gap-1.5">
                          {prof.resource.missing.slice(0, 18).map((f, i) => (
                            <code key={i} className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded">{f}</code>
                          ))}
                          {prof.resource.missing.length > 18 && <span className="text-[11px] text-gray-400">+{prof.resource.missing.length - 18} more</span>}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Findings */}
                <div className="mt-4 space-y-2.5">
                  {sorted.map((f) => {
                    const pass = f.status === "pass";
                    const check = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>;
                    const cross = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>;
                    const bang = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v5m0 3h.01" /></svg>;
                    const tg = pass ? { c: "text-green-600 dark:text-green-400", b: "border-green-200 dark:border-green-500/30", i: check }
                      : f.severity === "error" ? { c: "text-red-600 dark:text-red-400", b: "border-red-200 dark:border-red-500/30", i: cross }
                      : { c: "text-amber-600 dark:text-amber-400", b: "border-amber-200 dark:border-amber-500/30", i: bang };
                    return (
                      <div key={f.id} className={`bg-white dark:bg-slate-900 rounded-xl border ${tg.b} shadow-sm p-4 flex gap-3`}>
                        <span className={`flex-shrink-0 w-6 h-6 rounded-full border ${tg.b} ${tg.c} flex items-center justify-center text-xs font-bold`}>{tg.i}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">{f.title}</span>
                            {!pass && <span className={`text-[10px] uppercase tracking-wide font-bold ${tg.c}`}>{f.severity}</span>}
                          </div>
                          <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 leading-relaxed">{f.detail}</p>
                          {f.examples?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {f.examples.map((ex, i) => (
                                <code key={i} className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded">{ex}</code>
                              ))}
                            </div>
                          )}
                          {f.ref && <p className="text-[11px] text-gray-400 dark:text-slate-500 mt-1.5">↳ {f.ref}</p>}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <p className="text-center text-xs text-gray-400 dark:text-slate-500 mt-6">
                  Structure = TMF630 design rules · Coverage = match against TM Forum's published spec. {report.filename}
                </p>
              </div>
            )}

            {/* ── Portfolio X-ray ── */}
            {portfolio && (
              <div style={{ animation: "fadeUp 0.3s ease-out" }}>
                <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(10px);} to {opacity:1; transform:translateY(0);} }`}</style>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                  {[
                    { k: "APIs analysed", v: portfolio.summary.apis },
                    { k: "Avg structure", v: `${portfolio.summary.avg_structural}/100` },
                    { k: "Avg TMF coverage", v: `${portfolio.summary.avg_coverage}%` },
                    { k: "Fully compliant", v: portfolio.summary.fully_compliant },
                  ].map((s) => (
                    <div key={s.k} className="bg-white dark:bg-slate-900 rounded-xl border border-gray-200 dark:border-slate-800 shadow-sm p-3">
                      <div className="text-lg font-extrabold text-gray-900 dark:text-slate-100">{s.v}</div>
                      <div className="text-[11px] text-gray-400 dark:text-slate-500">{s.k}</div>
                    </div>
                  ))}
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 shadow-sm overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-slate-800/60 text-gray-500 dark:text-slate-400 text-xs">
                      <tr>
                        <th className="text-left font-medium px-4 py-2.5">API</th>
                        <th className="text-left font-medium px-3 py-2.5">Structure</th>
                        <th className="text-left font-medium px-3 py-2.5">TMF profile</th>
                        <th className="text-left font-medium px-3 py-2.5">Coverage</th>
                        <th className="text-left font-medium px-4 py-2.5 hidden sm:table-cell">Gaps (click a row)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {portfolio.rows.map((r, i) => {
                        const p = r.profile;
                        const isOpen = openRows.has(i);
                        const gaps = p ? p.missing_ops + p.missing_fields : 0;
                        return (
                          <Fragment key={i}>
                            <tr onClick={() => setOpenRows(s => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; })}
                              className="border-t border-gray-100 dark:border-slate-800 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-800/40">
                              <td className="px-4 py-2.5">
                                <div className="flex items-center gap-1.5">
                                  <svg className={`w-3 h-3 flex-shrink-0 text-gray-400 transition-transform ${isOpen ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                  <div className="min-w-0">
                                    <div className="font-medium text-gray-900 dark:text-slate-100 truncate max-w-[170px]">{r.api}</div>
                                    <div className="text-[11px] text-gray-400 dark:text-slate-500 truncate max-w-[170px]">{r.file}</div>
                                  </div>
                                </div>
                              </td>
                              <td className="px-3 py-2.5"><span className="font-semibold" style={{ color: tone(r.structural).ring }}>{r.structural}</span><span className="text-gray-400 text-xs">/100</span></td>
                              <td className="px-3 py-2.5 text-xs text-gray-600 dark:text-slate-300">{p ? `${p.tmf} v${p.version}` : "—"}</td>
                              <td className="px-3 py-2.5">{p ? <span className="font-semibold" style={{ color: covColor(p.coverage) }}>{p.coverage}%</span> : <span className="text-gray-400">—</span>}</td>
                              <td className="px-4 py-2.5 text-[11px] text-gray-500 dark:text-slate-400 hidden sm:table-cell">
                                {p ? `${p.missing_ops} ops · ${p.missing_fields} fields` : "—"}
                                {gaps > 0 && <span className="text-red-600 dark:text-red-400 font-medium"> · {isOpen ? "hide" : "view all"}</span>}
                              </td>
                            </tr>
                            {isOpen && (
                              <tr className="bg-gray-50/70 dark:bg-slate-800/30">
                                <td colSpan={5} className="px-4 pb-4 pt-1">
                                  {!p ? (
                                    <div className="text-xs text-gray-500 dark:text-slate-400">No TMF profile matched for this spec — generic TMF630 checks only.</div>
                                  ) : (
                                    <div className="space-y-3">
                                      {r.failing && r.failing.length > 0 && (
                                        <div>
                                          <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1">Structure issues ({r.failing.length})</div>
                                          <div className="flex flex-wrap gap-1.5">{r.failing.map((f, k) => <span key={k} className="text-[11px] bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 rounded px-1.5 py-0.5">{f}</span>)}</div>
                                        </div>
                                      )}
                                      {p.operations && p.operations.length > 0 && (
                                        <div>
                                          <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1">Missing operations ({p.operations.length})</div>
                                          <div className="flex flex-wrap gap-1.5">{p.operations.map((o, k) => <code key={k} className="text-[11px] font-mono bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-700 dark:text-slate-300 rounded px-1.5 py-0.5">{o}</code>)}</div>
                                        </div>
                                      )}
                                      {p.fields && p.fields.length > 0 && (
                                        <div>
                                          <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1">Missing {p.resource || "resource"} attributes ({p.fields.length})</div>
                                          <div className="flex flex-wrap gap-1.5">{p.fields.map((f, k) => <code key={k} className="text-[11px] font-mono bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-700 dark:text-slate-300 rounded px-1.5 py-0.5">{f}</code>)}</div>
                                        </div>
                                      )}
                                      <div className="text-[11px] text-gray-500 dark:text-slate-400">
                                        <span className="font-semibold">Remediation:</span> {r.fixable ? `run Auto-fix (${r.fixable} mechanical fix${r.fixable === 1 ? "" : "es"})` : ""}{r.fixable && gaps ? "; " : ""}{gaps ? `scaffold the ${gaps} missing operations/fields from ${p.tmf}` : ""}{!r.fixable && !gaps ? "already aligned — no action needed." : "."}
                                      </div>
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between mt-4">
                  <p className="text-xs text-gray-400 dark:text-slate-500">Generated {portfolio.generated} · deterministic, no AI · sorted by coverage</p>
                  <button onClick={() => download("synaptdi-xray.md", portfolio.markdown, "text/markdown")}
                    className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline underline-offset-2">Download report (.md)</button>
                </div>
              </div>
            )}

          </div>
        </main>
      </div>
    </AppShell>
  );
}
