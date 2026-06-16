"use client";
import { useState, useRef } from "react";
import AppShell from "../components/AppShell";
import { useToast } from "../components/Toast";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Finding {
  id: string; title: string;
  severity: "error" | "warning" | "info";
  status: "pass" | "fail";
  detail: string; examples: string[];
}
interface Report {
  api: string; version: string; score: number; filename?: string;
  summary: { passed: number; failed: number; warnings: number; total: number };
  findings: Finding[];
}

const scoreTone = (s: number) =>
  s >= 85 ? { text: "text-green-600 dark:text-green-400", ring: "#16a34a", label: "Strong conformance" }
  : s >= 60 ? { text: "text-amber-600 dark:text-amber-400", ring: "#d97706", label: "Needs work" }
  : { text: "text-red-600 dark:text-red-400", ring: "#dc2626", label: "Major gaps" };

export default function ConformancePage() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const upload = async (file: File) => {
    setLoading(true); setError(""); setReport(null); setFileName(file.name);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch(`${API}/conformance`, { method: "POST", body: fd });
      if (!r.ok) {
        const d = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      setReport(data);
      toast(`Conformance score ${data.score}/100`, data.score >= 85 ? "success" : data.score >= 60 ? "warning" : "error");
    } catch (e: any) {
      const msg = e?.message || "Upload failed — is the backend running on port 8000?";
      setError(msg);
      toast(msg, "error");
    } finally { setLoading(false); }
  };

  const onPick = (f?: File | null) => { if (f) upload(f); };

  // fails first (errors, then warnings), then passes
  const sorted = report ? [...report.findings].sort((a, b) => {
    const rank = (f: Finding) => f.status === "fail" ? (f.severity === "error" ? 0 : 1) : 2;
    return rank(a) - rank(b);
  }) : [];

  const tone = report ? scoreTone(report.score) : null;

  return (
    <AppShell>
      <div className="flex flex-col h-full bg-white dark:bg-slate-950">
        <header className="flex items-center justify-between px-6 py-3 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800 shadow-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-gray-800 dark:text-slate-100 text-sm tracking-tight">TMF Conformance Check</span>
            <span className="text-xs text-gray-400 dark:text-slate-500 bg-gray-100 dark:bg-slate-800 px-2.5 py-1 rounded-full hidden sm:inline-block">TMF630 design rules</span>
          </div>
          {report && (
            <button onClick={() => { setReport(null); setError(""); setFileName(""); }}
              className="text-xs text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200 px-3 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
              Check another spec
            </button>
          )}
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-8">
          <div className="max-w-3xl mx-auto">

            {/* Upload state */}
            {!report && (
              <div className="flex flex-col items-center">
                <div className="text-center mb-6">
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">Check your API against TM Forum</h2>
                  <p className="text-gray-500 dark:text-slate-400 text-sm mt-1.5 max-w-md">
                    Upload your OpenAPI / Swagger spec and get a TMF630 conformance report — pagination, error format, polymorphism, naming and more.
                  </p>
                </div>

                <label
                  onDragOver={e => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={e => { e.preventDefault(); setDragging(false); onPick(e.dataTransfer.files?.[0]); }}
                  className={`w-full max-w-xl cursor-pointer rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all ${
                    dragging ? "border-red-400 bg-red-50 dark:bg-red-500/10"
                    : "border-gray-300 dark:border-slate-700 hover:border-red-300 dark:hover:border-slate-600 bg-gray-50 dark:bg-slate-900"
                  }`}>
                  <input ref={inputRef} type="file" accept=".json,.yaml,.yml" className="hidden"
                    onChange={e => onPick(e.target.files?.[0])} />
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3 transition-colors ${dragging ? "bg-red-100 dark:bg-red-500/20" : "bg-gray-100 dark:bg-slate-800"}`}>
                    {loading ? (
                      <span className="flex gap-1">{[0, 150, 300].map(d => <span key={d} className="w-2 h-2 rounded-full bg-red-500 animate-bounce" style={{ animationDelay: `${d}ms` }} />)}</span>
                    ) : (
                      <svg className="w-6 h-6 text-gray-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.9A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" /></svg>
                    )}
                  </div>
                  <p className="text-sm font-medium text-gray-700 dark:text-slate-200">
                    {loading ? `Analysing ${fileName}…` : "Drop your spec here, or click to choose"}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-slate-500 mt-1">OpenAPI 3 or Swagger 2 · JSON or YAML</p>
                </label>

                {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 rounded-xl px-4 py-2.5">{error}</p>}
              </div>
            )}

            {/* Report state */}
            {report && tone && (
              <div style={{ animation: "fadeUp 0.3s ease-out" }}>
                <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(10px);} to {opacity:1; transform:translateY(0);} }`}</style>

                {/* Score header */}
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-800 shadow-sm p-6 flex items-center gap-6">
                  <div className="relative flex-shrink-0 w-24 h-24 rounded-full flex items-center justify-center"
                    style={{ background: `conic-gradient(${tone.ring} ${report.score * 3.6}deg, var(--ring-track, #e5e7eb) 0deg)` }}>
                    <div className="w-[76px] h-[76px] rounded-full bg-white dark:bg-slate-900 flex flex-col items-center justify-center">
                      <span className={`text-2xl font-extrabold ${tone.text}`}>{report.score}</span>
                      <span className="text-[10px] text-gray-400 dark:text-slate-500 -mt-0.5">/ 100</span>
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className={`text-sm font-bold ${tone.text}`}>{tone.label}</div>
                    <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 truncate">{report.api}{report.version ? ` v${report.version}` : ""}</h2>
                    <div className="flex flex-wrap gap-2 mt-2 text-xs">
                      <span className="px-2 py-0.5 rounded-full bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/30">{report.summary.passed} passed</span>
                      <span className="px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30">{report.summary.failed} errors</span>
                      <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30">{report.summary.warnings} warnings</span>
                    </div>
                  </div>
                </div>

                {/* Findings */}
                <div className="mt-4 space-y-2.5">
                  {sorted.map(f => {
                    const pass = f.status === "pass";
                    const check = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>;
                    const cross = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>;
                    const bang  = <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v5m0 3h.01" /></svg>;
                    const tag = pass ? { c: "text-green-600 dark:text-green-400", b: "border-green-200 dark:border-green-500/30", i: check }
                      : f.severity === "error" ? { c: "text-red-600 dark:text-red-400", b: "border-red-200 dark:border-red-500/30", i: cross }
                      : { c: "text-amber-600 dark:text-amber-400", b: "border-amber-200 dark:border-amber-500/30", i: bang };
                    return (
                      <div key={f.id} className={`bg-white dark:bg-slate-900 rounded-xl border ${tag.b} shadow-sm p-4 flex gap-3`}>
                        <span className={`flex-shrink-0 w-6 h-6 rounded-full border ${tag.b} ${tag.c} flex items-center justify-center text-xs font-bold`}>{tag.i}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">{f.title}</span>
                            {!pass && <span className={`text-[10px] uppercase tracking-wide font-bold ${tag.c}`}>{f.severity}</span>}
                          </div>
                          <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 leading-relaxed">{f.detail}</p>
                          {f.examples?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {f.examples.map((ex, i) => (
                                <code key={i} className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded">{ex}</code>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <p className="text-center text-xs text-gray-400 dark:text-slate-500 mt-6">
                  Checks based on the TM Forum API Design Guidelines (TMF630). {report.filename}
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </AppShell>
  );
}
