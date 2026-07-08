"use client";
import { Card, Button, Badge } from "../../components/ui";
import { DryRun, READY_META } from "../../lib/odaCtk";

// Dry-run result. READY_TO_EXECUTE is an informational/blue state — NEVER a PASS/conformant
// state. Missing prerequisites render as an amber warning. Run is offered but honestly gated.
export default function ODAValidationResult({
  dryRun, onRun, running, runDisabledReason,
}: {
  dryRun: DryRun;
  onRun: () => void;
  running: boolean;
  runDisabledReason?: string | null;
}) {
  const ready = dryRun.status === "READY_TO_EXECUTE";
  const missing = dryRun.missing_prerequisites || [];

  return (
    <Card className="p-5">
      {ready ? (
        <div className="rounded-xl border border-blue-200 dark:border-blue-500/30 bg-blue-50 dark:bg-blue-500/10 px-4 py-3">
          <div className="flex items-center gap-2">
            <Badge tone="blue">{READY_META.heading}</Badge>
            <span className="text-sm font-medium text-blue-800 dark:text-blue-300">Configuration valid</span>
          </div>
          <ul className="mt-2 text-xs text-blue-900/80 dark:text-blue-200/80 space-y-0.5">
            <li>Canonical contract resolved</li>
            <li>CTK framework verified</li>
            <li>Mandatory CTKs expected: {dryRun.expected_mandatory_ctks.map((k) => k.replace("_v", " v")).join(", ")}</li>
          </ul>
          <p className="mt-2 text-xs text-blue-900/80 dark:text-blue-200/80">{READY_META.copy}</p>
        </div>
      ) : (
        <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-4 py-3">
          <span className="text-sm font-medium text-red-800 dark:text-red-300">Configuration is not ready</span>
          <ul className="mt-1.5 text-xs text-red-900/80 dark:text-red-200/80 list-disc list-inside space-y-0.5">
            {(dryRun.errors || []).map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {/* Infrastructure prerequisites (separate from configuration validity) */}
      <div className="mt-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-1.5">
          Infrastructure prerequisites
        </div>
        {missing.length > 0 ? (
          <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-4 py-2.5">
            <span className="text-sm font-medium text-amber-800 dark:text-amber-300">Execution prerequisites missing</span>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {missing.map((p) => <code key={p} className="text-[11px] font-mono bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-200 px-1.5 py-0.5 rounded">{p}</code>)}
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(dryRun.prerequisites || {}).map(([k, ok]) => (
              <Badge key={k} tone={ok ? "green" : "amber"}>{k}{ok ? "" : " missing"}</Badge>
            ))}
          </div>
        )}
      </div>

      <div className="mt-5 flex items-center gap-3 flex-wrap">
        <Button variant="primary" onClick={onRun} disabled={running || !!runDisabledReason}>
          {running ? "Starting…" : "Run Component CTK"}
        </Button>
        {missing.length > 0 && (
          <span className="text-xs text-amber-700 dark:text-amber-400">
            Prerequisites are missing — execution will be attempted honestly and may report an execution error.
          </span>
        )}
        {runDisabledReason && <span className="text-xs text-gray-400">{runDisabledReason}</span>}
      </div>
    </Card>
  );
}
