"use client";
import { Card, Badge } from "../../components/ui";
import { Job, NormalizedResult, verdictMeta, redactPaths, safeResultFile } from "../../lib/odaCtk";
import ODARequirementResults from "./ODARequirementResults";

const BANNER: Record<string, string> = {
  green: "border-green-300 dark:border-green-500/40 bg-green-50 dark:bg-green-500/10",
  red: "border-red-300 dark:border-red-500/40 bg-red-50 dark:bg-red-500/10",
  amber: "border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10",
  gray: "border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-800/60",
};
const HEAD: Record<string, string> = {
  green: "text-green-700 dark:text-green-300",
  red: "text-red-700 dark:text-red-300",
  amber: "text-amber-700 dark:text-amber-300",
  gray: "text-slate-700 dark:text-slate-200",
};

function CoverageCell({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-gray-200 dark:border-slate-800 p-3 text-center">
      <div className={`text-xl font-extrabold ${tone || "text-gray-900 dark:text-slate-100"}`}>{value}</div>
      <div className="text-[11px] text-gray-400 dark:text-slate-500">{label}</div>
    </div>
  );
}

export default function ODACTKVerdict({ job }: { job: Job }) {
  const result: NormalizedResult | null = job.result;
  const status = (result?.overall_status) || "EXECUTION_ERROR";
  const meta = verdictMeta(status);
  const isError = status === "EXECUTION_ERROR";
  const err = job.execution_error || {};

  return (
    <div className="space-y-4">
      {/* Verdict banner */}
      <div className={`rounded-2xl border ${BANNER[meta.tone]} px-5 py-4`}>
        <div className={`text-base font-bold ${HEAD[meta.tone]}`}>{meta.label}</div>
        <p className="text-sm text-gray-700 dark:text-slate-300 mt-1">{meta.description}</p>
        {result && (
          <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-500 dark:text-slate-400">
            <span>Component <span className="font-mono font-semibold text-gray-700 dark:text-slate-200">{result.component_id}</span></span>
            <span>Version <span className="font-mono font-semibold text-gray-700 dark:text-slate-200">{result.component_version}</span></span>
            {result.ctk_version && <span>CTK <span className="font-mono">{result.ctk_version}</span></span>}
          </div>
        )}
      </div>

      {/* Execution-error detail — explicitly NOT a conformance failure; no paths/secrets */}
      {isError && (
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-2">
            <Badge tone="gray">Execution error</Badge>
            {err.category && <span className="font-mono text-xs text-gray-600 dark:text-slate-300">{err.category}</span>}
          </div>
          <p className="text-sm text-gray-700 dark:text-slate-200">Execution could not start or complete.</p>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">This is not an ODA conformance failure.</p>
          {(err.message || (err.messages && err.messages.length > 0)) && (
            <div className="mt-3 text-xs font-mono text-gray-600 dark:text-slate-300 bg-gray-50 dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700 rounded-lg px-3 py-2 break-words">
              {redactPaths(err.message || (err.messages || []).join("; "))}
            </div>
          )}
        </Card>
      )}

      {/* Coverage summary + per-requirement + evidence — only when a result exists */}
      {result && !isError && (
        <>
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-slate-100 mb-3">Mandatory requirement coverage</h3>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
              <CoverageCell label="Total" value={result.mandatory_total} />
              <CoverageCell label="Executed" value={result.mandatory_executed} />
              <CoverageCell label="Passed" value={result.mandatory_passed} tone={result.mandatory_passed ? "text-green-600 dark:text-green-400" : undefined} />
              <CoverageCell label="Failed" value={result.mandatory_failed} tone={result.mandatory_failed ? "text-red-600 dark:text-red-400" : undefined} />
              <CoverageCell label="Missing" value={result.mandatory_missing} tone={result.mandatory_missing ? "text-amber-600 dark:text-amber-400" : undefined} />
            </div>
          </Card>

          <ODARequirementResults rows={result.per_requirement_results} />

          {result.failed_tests?.length > 0 && (
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-red-700 dark:text-red-300 mb-3">Failed checks</h3>
              <div className="space-y-2">
                {result.failed_tests.map((f, i) => (
                  <div key={i} className="text-xs bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-lg px-3 py-2">
                    <div className="font-medium text-red-800 dark:text-red-300">
                      {f.api ? `${f.api}${f.version ? " " + f.version : ""}` : f.baseline ? `${f.baseline} baseline` : "check"}
                      {typeof f.failed === "number" && <span className="font-normal"> — {f.failed}{typeof f.total === "number" ? `/${f.total}` : ""} failed</span>}
                    </div>
                    {f.detail && <div className="text-red-700/80 dark:text-red-300/80 mt-0.5">{redactPaths(f.detail)}</div>}
                    {f.result_file && <div className="font-mono text-red-600/70 dark:text-red-400/70 mt-0.5">{safeResultFile(f.result_file)}</div>}
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-gray-400 dark:text-slate-500 mt-2">Deterministic CTK evidence only — no AI interpretation.</p>
            </Card>
          )}
        </>
      )}

      {/* Warnings (preserve backend semantics; never alter the verdict) */}
      {result && result.warnings.length > 0 && (
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-300 mb-2">Warnings</h3>
          <ul className="text-xs text-gray-600 dark:text-slate-400 list-disc list-inside space-y-1">
            {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </Card>
      )}

      {/* Trust explanation */}
      <div className="text-xs text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-800/40 border border-gray-200 dark:border-slate-800 rounded-xl px-4 py-3">
        <div className="font-semibold text-gray-600 dark:text-slate-300 mb-1">How this verdict is determined</div>
        SynaptDI resolves the canonical TM Forum ODA Component contract, runs the TM Forum Component CTK against the
        configured deployment, and derives the verdict deterministically from CTK execution evidence. AI does not decide
        the conformance result.
      </div>
    </div>
  );
}
