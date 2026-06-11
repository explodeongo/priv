"use client";
import { Card, Button, Badge } from "./ui";

export interface Coverage {
  chunks: number;
  spec_count: number;
  domains: { domain: string; specs: string[] }[];
}

const STARTERS = [
  "What mandatory fields does TMF622 Product Order require?",
  "Difference between TMF620 and TMF633?",
  "How do I paginate TM Forum Open APIs?",
];

const IBook = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
);

/** Compact "what I know" strip for the chat empty state. */
export function CoverageStrip({ coverage }: { coverage: Coverage | null }) {
  if (!coverage || coverage.spec_count <= 0) return null;
  return (
    <div className="w-full max-w-2xl">
      <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-gray-500 dark:text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-gray-400 dark:text-slate-500"><IBook /></span>
          <span><b className="text-gray-700 dark:text-slate-200">{coverage.spec_count}</b> specs indexed across</span>
        </span>
        {coverage.domains.map(d => (
          <Badge key={d.domain} tone="gray">{d.domain} · {d.specs.length}</Badge>
        ))}
      </div>
    </div>
  );
}

/** First-run welcome modal. */
export function WelcomeModal(
  { coverage, onAsk, onClose }:
  { coverage: Coverage | null; onAsk: (q: string) => void; onClose: () => void }
) {
  return (
    <>
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[200]" onClick={onClose} />
      <div className="fixed inset-0 z-[210] flex items-center justify-center p-4 pointer-events-none">
        <Card className="w-full max-w-lg overflow-hidden pointer-events-auto" >
          <div style={{ animation: "wIn .22s ease-out" }}>
            <style>{`@keyframes wIn{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}`}</style>

            {/* Header */}
            <div className="px-6 pt-6 pb-4 border-b border-gray-100 dark:border-slate-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-600 flex items-center justify-center text-white font-extrabold text-lg shadow-sm">S</div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 leading-tight">Welcome to SynaptDI</h2>
                  <p className="text-xs text-gray-400 dark:text-slate-500">Cited answers from your TM Forum knowledge base</p>
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="px-6 py-5 space-y-4">
              <p className="text-sm text-gray-600 dark:text-slate-300 leading-relaxed">
                Ask anything about TM Forum APIs, ODA, MEF, eTOM or SID and get a grounded, cited answer — no hunting through PDFs.
              </p>

              <div className="space-y-2">
                {[
                  ["Ask in plain English", "e.g. “mandatory fields for TMF622 Product Order”"],
                  ["Every answer is cited", "click a [n] to see the exact spec chunk it came from"],
                  ["Fast navigation", "press ⌘K anywhere, or / to focus the question box"],
                ].map(([t, d]) => (
                  <div key={t} className="flex gap-2.5">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
                    <p className="text-sm text-gray-700 dark:text-slate-300"><span className="font-semibold text-gray-900 dark:text-slate-100">{t}</span> — {d}</p>
                  </div>
                ))}
              </div>

              {coverage && coverage.spec_count > 0 && (
                <div className="rounded-xl bg-gray-50 dark:bg-slate-800/60 border border-gray-100 dark:border-slate-800 px-3.5 py-3">
                  <p className="text-xs text-gray-500 dark:text-slate-400 mb-2">
                    Ready to go — <b className="text-gray-700 dark:text-slate-200">{coverage.spec_count} specs</b> ({coverage.chunks.toLocaleString()} chunks) indexed:
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {coverage.domains.map(d => <Badge key={d.domain} tone="red">{d.domain} · {d.specs.length}</Badge>)}
                  </div>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-2">Try one</p>
                <div className="space-y-1.5">
                  {STARTERS.map(q => (
                    <button key={q} onClick={() => onAsk(q)}
                      className="w-full text-left text-sm text-gray-600 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-red-50 dark:hover:bg-slate-700 hover:text-red-700 dark:hover:text-red-300 border border-gray-200 dark:border-slate-700 hover:border-red-200 dark:hover:border-slate-600 rounded-lg px-3.5 py-2.5 transition-all flex items-center gap-2.5">
                      <span className="text-red-400">→</span><span className="flex-1">{q}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-100 dark:border-slate-800 flex justify-end">
              <Button onClick={onClose}>Get started</Button>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
