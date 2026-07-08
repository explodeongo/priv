"use client";
import { Card, Badge } from "../../components/ui";
import { PerRequirement, outcomeChip, versionEvidence, redactPaths } from "../../lib/odaCtk";

// Per-requirement execution results. Version precision is rendered honestly:
// declared v4.0.0 / execution evidence v4 major / precision "Major version only" — never
// "Tested v4.0.0". Optional NOT-RUN is neutral, never failure-styled.
export default function ODARequirementResults({ rows }: { rows: PerRequirement[] }) {
  if (!rows?.length) return null;
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-slate-100 mb-3">Per-requirement results</h3>
      <div className="divide-y divide-gray-100 dark:divide-slate-800">
        {rows.map((r) => {
          const chip = outcomeChip(r.outcome);
          const ve = versionEvidence(r);
          return (
            <div key={r.id + r.segment} className="py-3 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-sm font-semibold text-gray-900 dark:text-slate-100">{r.id}</span>
                  <Badge tone="gray">{r.segment}</Badge>
                  <Badge tone={r.requirement === "MANDATORY" ? "blue" : "gray"}>{r.requirement}</Badge>
                </div>
                <div className="text-xs text-gray-500 dark:text-slate-400 mt-1 space-y-0.5">
                  <div>Declared: <span className="font-mono">{ve.declared}</span></div>
                  {r.outcome !== "NOT_RUN" && (
                    <>
                      <div>Execution evidence: <span className="font-mono">{ve.executed}</span></div>
                      <div>Version evidence precision: {ve.precisionLabel}</div>
                    </>
                  )}
                  {typeof r.total === "number" && (
                    <div>{r.total} check(s){typeof r.failed === "number" ? `, ${r.failed} failed` : ""}</div>
                  )}
                  {r.reason && <div className="text-gray-400 dark:text-slate-500">{redactPaths(r.reason)}</div>}
                </div>
              </div>
              <Badge tone={chip.tone}>{chip.label}</Badge>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
