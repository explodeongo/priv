"use client";
import { Card } from "../../components/ui";
import { JobState, stageStatuses, STAGE_LABEL } from "../../lib/odaCtk";

// Vertical execution timeline — only stages the backend confirms. No percentages, no
// faked progress. A failed run shows the failure explicitly.
export default function ODAJobTimeline({ state }: { state: JobState }) {
  const stages = stageStatuses(state);
  const failed = state === "FAILED_EXECUTION";

  const dot = (status: string) => {
    if (status === "done") return "bg-green-500 border-green-500";
    if (status === "active") return "bg-white dark:bg-slate-900 border-blue-500 animate-pulse";
    return "bg-white dark:bg-slate-900 border-gray-300 dark:border-slate-600";
  };

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-slate-100 mb-3">Execution</h3>
      <ol className="relative">
        {stages.map((s, i) => (
          <li key={s.state} className="flex items-start gap-3 pb-3 last:pb-0">
            <div className="flex flex-col items-center">
              <span className={`w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 ${dot(s.status)}`} />
              {i < stages.length - 1 && <span className={`w-px flex-1 min-h-[18px] ${s.status === "done" ? "bg-green-400/50" : "bg-gray-200 dark:bg-slate-700"}`} />}
            </div>
            <span className={`text-sm -mt-0.5 ${
              s.status === "active" ? "text-blue-700 dark:text-blue-300 font-medium"
              : s.status === "done" ? "text-gray-700 dark:text-slate-200"
              : "text-gray-400 dark:text-slate-500"}`}>
              {s.label}
            </span>
          </li>
        ))}
      </ol>
      {failed && (
        <div className="mt-1 flex items-center gap-2 text-sm text-gray-700 dark:text-slate-200 border-t border-gray-100 dark:border-slate-800 pt-3">
          <span className="w-3.5 h-3.5 rounded-full border-2 bg-gray-400 border-gray-400 flex-shrink-0" />
          {STAGE_LABEL.FAILED_EXECUTION}
        </div>
      )}
    </Card>
  );
}
