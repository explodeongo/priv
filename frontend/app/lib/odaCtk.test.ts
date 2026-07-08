// Unit tests for the ODA Component CTK display logic (pure, no React/DOM).
// Runner: compiled by the project's tsc → executed with node (see package.json test:oda).
// These lock the trust-boundary wording/styling the backend verdicts require.
import {
  verdictMeta, READY_META, readyTextIsSafe, stageStatuses, isTerminal,
  requirementChip, CONTRACT_ONLY_CHIP, outcomeChip, versionEvidence, versionTextIsSafe,
  STAGE_ORDER, PerRequirement, redactPaths, safeResultFile,
} from "./odaCtk";

let passed = 0;
let failed = 0;
function ok(cond: boolean, name: string) {
  if (cond) { passed++; } else { failed++; console.error("FAIL  " + name); }
}
function eq(a: unknown, b: unknown, name: string) { ok(JSON.stringify(a) === JSON.stringify(b), name + `  (got ${JSON.stringify(a)})`); }

// 1. READY_TO_EXECUTE never renders PASS/Conformant wording.
ok(readyTextIsSafe(READY_META.heading + " " + READY_META.copy), "ready copy free of pass/conformant wording");
ok(READY_META.copy.toLowerCase().includes("does not establish oda conformance"), "ready copy states not-conformant");
ok(READY_META.tone === "blue", "ready tone is neutral/blue (not green)");
ok(!readyTextIsSafe("Validation passed"), "guard catches 'Validation passed'");
ok(!readyTextIsSafe("Component is conformant"), "guard catches 'conformant'");

// 2. EXECUTION_ERROR is explicitly NOT a conformance failure and not styled as FAIL.
const ee = verdictMeta("EXECUTION_ERROR");
ok(ee.isConformanceFailure === false, "EXECUTION_ERROR is not a conformance failure");
ok(ee.description.toLowerCase().includes("not a conformance failure"), "EXECUTION_ERROR copy says not a conformance failure");
ok(ee.tone !== "red", "EXECUTION_ERROR is not red/FAIL styled");
ok(ee.label === "CTK Execution Error", "EXECUTION_ERROR label");

// 3. INCOMPLETE is distinct from FAIL (tone + label + description).
const inc = verdictMeta("INCOMPLETE");
const fail = verdictMeta("FAIL");
ok(inc.tone === "amber" && fail.tone === "red", "INCOMPLETE amber vs FAIL red");
ok(inc.label !== fail.label, "INCOMPLETE label differs from FAIL");
ok(fail.isConformanceFailure === true && inc.isConformanceFailure === false, "only FAIL is a conformance failure");
ok(verdictMeta("PASS").tone === "green", "PASS is green");

// 4. Optional NOT RUN is not styled as failure.
const notRun = outcomeChip("NOT_RUN");
ok(notRun.tone === "gray" && notRun.label === "NOT RUN", "NOT RUN is neutral, not failure-styled");
ok(outcomeChip("FAILED").tone === "red", "FAILED is red");
ok(outcomeChip("MISSING").tone === "amber", "MISSING is amber, not red");

// 5. MAJOR_ONLY must not render "Tested v4.0.0".
const row: PerRequirement = {
  id: "TMF642", segment: "CORE", requirement: "MANDATORY",
  declared_version: "v4.0.0", executed_major_version: "v4",
  version_match_precision: "MAJOR_ONLY", outcome: "PASSED",
};
const ve = versionEvidence(row);
eq(ve.declared, "v4.0.0", "declared shown as v4.0.0");
eq(ve.executed, "v4 major", "executed shown as v4 major");
eq(ve.precisionLabel, "Major version only", "precision label = Major version only");
ok(versionTextIsSafe(`Declared: ${ve.declared} · Execution evidence: ${ve.executed} · ${ve.precisionLabel}`, "v4.0.0"),
   "rendered version line does not claim 'Tested v4.0.0'");
ok(!versionTextIsSafe("Tested v4.0.0", "v4.0.0"), "guard catches 'Tested v4.0.0'");

// 6. Contract chips are neutral (never green PASS styling in the contract view).
ok(requirementChip("MANDATORY").tone !== "green", "MANDATORY chip is not green PASS");
ok(requirementChip("OPTIONAL").tone === "gray", "OPTIONAL chip is neutral");
ok(CONTRACT_ONLY_CHIP.label === "CONTRACT ONLY", "CONTRACT ONLY chip label");
ok(CONTRACT_ONLY_CHIP.tone === "gray", "CONTRACT ONLY chip is neutral");

// 7. Job timeline reflects only real backend states; nothing faked ahead of current.
const running = stageStatuses("RUNNING_CTK");
ok(running.find((s) => s.state === "RUNNING_CTK")!.status === "active", "current stage is active");
ok(running.find((s) => s.state === "NORMALIZING_RESULTS")!.status === "pending", "future stage is pending (not faked)");
ok(running.find((s) => s.state === "CREATED")!.status === "done", "earlier stage is done");
const failedTl = stageStatuses("FAILED_EXECUTION");
ok(failedTl.every((s) => s.status !== "active"), "failed run has no active stage");
ok(stageStatuses("COMPLETED").every((s) => s.status === "done"), "completed marks all stages done");
ok(!STAGE_ORDER.includes("FAILED_EXECUTION" as never), "FAILED_EXECUTION is not a progress stage");
ok(isTerminal("COMPLETED") && isTerminal("FAILED_EXECUTION") && !isTerminal("RUNNING_CTK"), "terminal-state detection");

// 8. Path redaction — the UI must never surface server/workspace filesystem paths, even
//    when a backend message embeds one. URLs must be preserved (they are not host paths).
const wsMsg = "CTK failed at /private/var/folders/bm/xx/T/synaptdi_odactk_4mopk88s/componentCTK/scripts/CTK_Executor.py while parsing";
ok(!redactPaths(wsMsg).includes("/private/var"), "redactPaths hides /private/var workspace path");
ok(!redactPaths(wsMsg).includes("synaptdi_odactk"), "redactPaths hides workspace dir name");
ok(redactPaths(wsMsg).includes("while parsing"), "redactPaths keeps the human-readable remainder");
ok(!redactPaths("see /Users/aryan/Downloads/SynaptDI/backend/x.py:35").includes("/Users/aryan"), "redactPaths hides /Users path");
ok(redactPaths("download from https://api.github.com/repos/x/y/contents") === "download from https://api.github.com/repos/x/y/contents",
   "redactPaths preserves URLs (not a host path)");
ok(!redactPaths("C:\\Users\\bob\\ws\\report.json present").includes("C:\\Users"), "redactPaths hides Windows path");
ok(redactPaths("") === "" && redactPaths(null) === "" && redactPaths(undefined) === "", "redactPaths handles empty/null");
const clean = "CTK executor requires Python 3.10+ (PEP 604 type hints); set ODA_CTK_PYTHON";
ok(redactPaths(clean) === clean, "redactPaths leaves path-free messages unchanged");

// 9. safeResultFile — legitimate evidence filename kept; absolute/workspace path collapsed to basename.
eq(safeResultFile("TMF642_v4/newman-report.json"), "TMF642_v4/newman-report.json", "relative evidence path kept as-is");
eq(safeResultFile("/private/var/folders/T/synaptdi_odactk_x/Reports/TMF642_v4/newman-report.json"), "newman-report.json",
   "absolute workspace path collapsed to basename");
eq(safeResultFile("C:\\ws\\Reports\\alarm.json"), "alarm.json", "windows path collapsed to basename");
eq(safeResultFile(""), "", "safeResultFile handles empty");

console.log(`\nodaCtk.test: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
