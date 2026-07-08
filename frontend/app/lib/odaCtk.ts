// Pure display logic + types for the ODA Component CTK conformance UI.
// No React, no side effects — every mapping here is unit-tested (odaCtk.test.ts) to
// lock the trust-boundary wording/styling the backend verdicts require. The backend is
// the sole authority for the verdict; this file only decides how to *present* it.

// ── Backend response types (mirrors backend/main.py + oda_ctk_results.py) ──────────────
export type RequirementStatus = "MANDATORY" | "OPTIONAL" | "UNKNOWN";
export type Segment = "CORE" | "SECURITY" | "MANAGEMENT";

export interface ContractApi {
  id: string;
  name: string;
  segment: Segment;
  kind: "exposed" | "dependent";
  api_type: string;
  declared_version: string | null;
  requirement_status: RequirementStatus;
  is_placeholder: boolean;
  id_is_placeholder?: boolean;
}
export interface Contract {
  status: string;
  source: string;
  component_id: string;
  resolved_version: string;
  exhaustive: boolean;
  component: {
    id: string; name: string; version: string; status: string;
    publicationDate: string | null; functionalBlock: string; format: string;
  };
  requirements: {
    exposed: ContractApi[];
    dependent: ContractApi[];
    mandatory_exposed: ContractApi[];
    optional_exposed: ContractApi[];
    real_dependent: ContractApi[];
    events: { published: { name: string; resources: string[] }[]; subscribed: { name: string; resources: string[] }[] };
  };
}

export interface DryRun {
  status: "READY_TO_EXECUTE" | "NOT_READY";
  subprocess_invoked: boolean;
  errors: string[];
  contract_status: string;
  framework_files_ok: boolean;
  expected_mandatory_ctks: string[];
  prerequisites: Record<string, boolean>;
  missing_prerequisites: string[];
  note: string;
}

export type JobState =
  | "CREATED" | "VALIDATING" | "READY" | "PREPARING_WORKSPACE"
  | "RUNNING_CTK" | "NORMALIZING_RESULTS" | "COMPLETED" | "FAILED_EXECUTION";

export type Verdict = "PASS" | "FAIL" | "INCOMPLETE" | "EXECUTION_ERROR";

export interface PerRequirement {
  id: string;
  segment: Segment;
  requirement: "MANDATORY" | "OPTIONAL";
  declared_version: string | null;
  executed_major_version?: string | null;
  version_match_precision?: string;
  outcome: string;                       // PASSED | FAILED | MISSING | AMBIGUOUS | NOT_RUN | EXECUTED
  result_file?: string | null;
  total?: number; failed?: number; reason?: string;
}
export interface FailedTest {
  api?: string; requirement?: string; version?: string; result_file?: string | null;
  failed?: number; total?: number; detail?: string; baseline?: string; failures?: number;
}
export interface NormalizedResult {
  component_id: string;
  component_version: string;
  ctk_version?: string | null;
  overall_status: Verdict;
  mandatory_total: number; mandatory_executed: number; mandatory_passed: number;
  mandatory_failed: number; mandatory_missing: number; mandatory_ambiguous?: number;
  optional_executed: number;
  per_requirement_results: PerRequirement[];
  failed_tests: FailedTest[];
  warnings: string[];
  evidence?: Record<string, unknown>;
  identity_binding?: { source: string; component_id: string; component_version: string };
}
export interface Job {
  job_id: string;
  component_id: string;
  component_version: string | null;
  state: JobState;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  execution_error: { category?: string; message?: string; messages?: string[] } | null;
  result: NormalizedResult | null;
}

// ── Badge tone vocabulary (matches components/ui.tsx Badge) ────────────────────────────
export type Tone = "gray" | "red" | "green" | "amber" | "blue";

// ── Verdict → presentation. Trust boundary is enforced HERE. ───────────────────────────
export interface VerdictMeta { label: string; description: string; tone: Tone; isConformanceFailure: boolean; }
export function verdictMeta(v: Verdict): VerdictMeta {
  switch (v) {
    case "PASS":
      return { label: "ODA Component CTK — PASS", tone: "green", isConformanceFailure: false,
        description: "All mandatory executable CTK requirements were positively executed and passed." };
    case "FAIL":
      return { label: "ODA Component CTK — FAIL", tone: "red", isConformanceFailure: true,
        description: "One or more executed mandatory conformance checks failed." };
    case "INCOMPLETE":
      return { label: "ODA Component CTK — INCOMPLETE", tone: "amber", isConformanceFailure: false,
        description: "CTK output was produced, but mandatory conformance coverage could not be fully proven." };
    case "EXECUTION_ERROR":
    default:
      return { label: "CTK Execution Error", tone: "gray", isConformanceFailure: false,
        description: "The CTK framework or execution environment did not complete successfully. This is not a conformance failure." };
  }
}

// READY_TO_EXECUTE is an informational (neutral/blue) state — NEVER a PASS/conformant state.
export const READY_META = {
  tone: "blue" as Tone,
  heading: "Ready to execute",
  copy: "Configuration is valid, but this does not establish ODA conformance. CTK execution is required.",
};
// Wording explicitly forbidden for a READY / dry-run state (guards against PASS creep).
export const FORBIDDEN_READY_WORDS = ["conformant", "passed", "pass", "compliant", "validation passed"];
export function readyTextIsSafe(text: string): boolean {
  const t = text.toLowerCase();
  return !FORBIDDEN_READY_WORDS.some((w) => t.includes(w));
}

// ── Job stage timeline (only real backend states) ──────────────────────────────────────
export const STAGE_ORDER: JobState[] = [
  "CREATED", "VALIDATING", "READY", "PREPARING_WORKSPACE",
  "RUNNING_CTK", "NORMALIZING_RESULTS", "COMPLETED",
];
export const STAGE_LABEL: Record<JobState, string> = {
  CREATED: "Created",
  VALIDATING: "Validating configuration",
  READY: "Ready",
  PREPARING_WORKSPACE: "Preparing isolated CTK workspace",
  RUNNING_CTK: "Running TM Forum Component CTK",
  NORMALIZING_RESULTS: "Normalizing CTK results",
  COMPLETED: "Completed",
  FAILED_EXECUTION: "Execution failed",
};
export type StageStatus = "done" | "active" | "pending" | "failed";
/** For a given current job state, classify each ordered stage. Only stages the backend
 *  actually reached are 'done'; nothing is faked ahead of the real state. */
export function stageStatuses(current: JobState): { state: JobState; label: string; status: StageStatus }[] {
  const failed = current === "FAILED_EXECUTION";
  const idx = STAGE_ORDER.indexOf(current);
  return STAGE_ORDER.map((s, i) => {
    let status: StageStatus;
    if (current === "COMPLETED") status = "done";
    else if (failed) status = i === 0 ? "done" : "pending";
    else if (i < idx) status = "done";
    else if (i === idx) status = "active";
    else status = "pending";
    return { state: s, label: STAGE_LABEL[s], status };
  });
}
export function isTerminal(s: JobState): boolean {
  return s === "COMPLETED" || s === "FAILED_EXECUTION";
}

// ── Contract requirement chips (neutral — contract view is requirements, not results) ──
export function requirementChip(status: RequirementStatus): { tone: Tone; label: string } {
  if (status === "MANDATORY") return { tone: "blue", label: "MANDATORY" };
  if (status === "OPTIONAL") return { tone: "gray", label: "OPTIONAL" };
  return { tone: "gray", label: "UNKNOWN" };
}
export const CONTRACT_ONLY_CHIP: { tone: Tone; label: string } = { tone: "gray", label: "CONTRACT ONLY" };

// ── Per-requirement result presentation ───────────────────────────────────────────────
export function outcomeChip(outcome: string): { tone: Tone; label: string } {
  switch (outcome) {
    case "PASSED": return { tone: "green", label: "PASSED" };
    case "FAILED": return { tone: "red", label: "FAILED" };
    case "MISSING": return { tone: "amber", label: "MISSING" };
    case "AMBIGUOUS": return { tone: "amber", label: "AMBIGUOUS" };
    case "EXECUTED": return { tone: "green", label: "EXECUTED" };
    case "NOT_RUN": return { tone: "gray", label: "NOT RUN" };
    default: return { tone: "gray", label: outcome };
  }
}

// Version evidence — MAJOR_ONLY must never render as "Tested v4.0.0".
export interface VersionEvidence { declared: string; executed: string; precisionLabel: string; }
export function versionEvidence(row: PerRequirement): VersionEvidence {
  const declared = row.declared_version || "—";
  const major = row.executed_major_version || null;
  const majorOnly = (row.version_match_precision || "").toUpperCase() === "MAJOR_ONLY";
  return {
    declared,
    executed: major ? `${major} major` : "—",
    precisionLabel: majorOnly ? "Major version only" : (row.version_match_precision || "—"),
  };
}
// Guard: text produced for a MAJOR_ONLY row must not claim exact-semver execution.
export function versionTextIsSafe(text: string, declared: string): boolean {
  return !new RegExp(`tested\\s+${declared.replace(/\./g, "\\.")}`, "i").test(text);
}

// ── Path redaction (defense-in-depth) ──────────────────────────────────────────────────
// The UI must NEVER surface server filesystem paths or the isolated CTK workspace path,
// even if a backend message unexpectedly embeds one. These are pure so they are unit-tested.
// URLs (scheme://host/path) are deliberately preserved — only OS/workspace paths are hidden.
const SENSITIVE_ROOT = "(?:Users|home|root|private|var|tmp|opt|etc|srv|mnt|Applications|proc|dev)";
export function redactPaths(text: string | null | undefined): string {
  if (!text) return "";
  return text
    // POSIX absolute paths under a sensitive root (incl. /private/var/.../synaptdi_odactk_*)
    .replace(new RegExp(`(^|[\\s"'(\\[=,])\\/${SENSITIVE_ROOT}\\/[^\\s"')\\]]*`, "g"), "$1‹path hidden›")
    // any lingering reference to the isolated workspace dir name
    .replace(/synaptdi_odactk_[A-Za-z0-9_]+/g, "‹workspace›")
    // Windows absolute paths
    .replace(/[A-Za-z]:\\[^\s"']+/g, "‹path hidden›");
}
// A CTK result file is legitimate evidence to show, but never as an absolute/host path —
// collapse anything path-like to its trailing file name; leave clean relative names intact.
export function safeResultFile(name?: string | null): string {
  if (!name) return "";
  const looksAbsolute = name.startsWith("/") || /synaptdi_odactk_/.test(name)
    || new RegExp(`\\/${SENSITIVE_ROOT}\\/`).test(name) || /^[A-Za-z]:\\/.test(name);
  if (looksAbsolute) {
    const parts = name.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] || "report";
  }
  return name;
}
