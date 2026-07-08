"""
Deterministic ODA Component CTK result normalizer (execution-backed conformance, layer B)
════════════════════════════════════════════════════════════════════════════════════════
Turns the raw resources/consolidatedResults.json a live TM Forum Component CTK writes
into a SynaptDI conformance verdict — deterministically, cross-checked against the
canonical contract. No LLM ever decides PASS/FAIL/INCOMPLETE.

SAFETY INVARIANT (Phase 2): PASS REQUIRES POSITIVE, UNAMBIGUOUS EVIDENCE.
Absence of failure is not success. Zero executed tests is not success. Unknown/malformed
structure is not success. A summary claiming PASS cannot override missing raw mandatory
evidence. Contradictory or duplicated evidence never passes.

Raw consolidatedResults.json schema (from CTK_Executor.py :: consolidate_results_to_json
and src/index.js — NOT invented):
  { resultsSummary: <results/reportData.json>,       # Node summary (.core/.securityFunctionResults[].{apiName,hasPassed})
    apiCtkResults: [ {file:"TMF642_v4.json", data:<raw newman|cypress report>} ],   # file id is MAJOR-ONLY
    configurationReport: <baseline-ctk/Configuration-report.json>,   # mocha (REQUIRED by index.js — not optional)
    deploymentReport:    <baseline-ctk/deployment-report.json>,      # mocha (REQUIRED)
    bddResults, bddPayloads }

Evidence precedence: the raw apiCtkResults[].data statistics are AUTHORITATIVE. The
resultsSummary hasPassed flag is a derived convenience that can only ever DOWNGRADE (flag
a contradiction / absence) — never establish PASS on its own. If raw and summary
contradict, the requirement does not pass.
"""
import json
import os
import re

# ── Verdict vocabulary (never collapsed) ──────────────────────────────────────────────
PASS = "PASS"
FAIL = "FAIL"
INCOMPLETE = "INCOMPLETE"
EXECUTION_ERROR = "EXECUTION_ERROR"

# Per-mandatory-requirement evidence outcomes (internal).
_PASSED, _FAILED, _MISSING, _AMBIGUOUS = "PASSED", "FAILED", "MISSING", "AMBIGUOUS"

_APINAME = re.compile(r"^\s*(TMF\d{3,4})\b.*?\(v(\d+)", re.I)   # "TMF642 alarm ... (v4) - Mandatory"


def _sane_count(x):
    """A trustworthy CTK count is a non-negative int and NOT a bool (bool ⊂ int in Python)."""
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def parse_ctk_report(report) -> dict:
    """{total, passed, failed, format} for one raw API-CTK report — same v4-Newman /
    v5-Cypress discrimination as src/index.js, PLUS sanity validation: counts must be
    non-negative ints with failed <= total, else format='malformed' (never trusted as a
    pass). format='unknown' when the report is neither shape."""
    if not isinstance(report, dict):
        return {"total": 0, "passed": 0, "failed": 0, "format": "unknown"}
    run = report.get("run")
    if isinstance(run, dict) and isinstance(run.get("stats"), dict) and isinstance(run["stats"].get("assertions"), dict):
        a = run["stats"]["assertions"]
        total, failed = a.get("total"), a.get("failed")
        if not (_sane_count(total) and _sane_count(failed)) or failed > total:
            return {"total": total, "passed": None, "failed": failed, "format": "malformed"}
        return {"total": total, "passed": total - failed, "failed": failed, "format": "v4-newman"}
    stats = report.get("stats")
    if isinstance(stats, dict) and "tests" in stats:
        total, failed = stats.get("tests"), stats.get("failures")
        if not (_sane_count(total) and _sane_count(failed)) or failed > total:
            return {"total": total, "passed": None, "failed": failed, "format": "malformed"}
        passes = stats.get("passes")
        passed = passes if _sane_count(passes) else total - failed
        return {"total": total, "passed": passed, "failed": failed, "format": "v5-cypress"}
    return {"total": 0, "passed": 0, "failed": 0, "format": "unknown"}


def _major(version) -> str:
    m = re.search(r"v?(\d+)", str(version or ""))
    return m.group(1) if m else ""


def _stem(fname: str) -> str:
    return re.sub(r"\.json$", "", str(fname or ""), flags=re.I)


def _matches_api_version(fname: str, api_id: str, major: str) -> bool:
    """EXACT id + MAJOR-version match against a result filename. The producer emits
    exactly `{id}_v{major}.json` (deployment.js); a full-semver variant `{id}_v{major}.x.y`
    is also accepted. Rejects wrong majors (v5, v41), similar ids (XTMF642, TMF6420),
    and suffixed/backup names (TMF642_v4_backup, TMF642_backup_v4)."""
    if not api_id or not major:
        return False
    return bool(re.fullmatch(rf"{re.escape(api_id)}_v{re.escape(major)}(?:\.\d+){{0,2}}", _stem(fname), re.I))


def _find_api_ctks(consolidated: dict, api_id: str, major: str) -> list:
    """ALL raw CTK entries whose filename exactly matches api_id@major (0, 1, or many —
    duplicates are surfaced, not silently collapsed to the first)."""
    out = []
    for entry in (consolidated.get("apiCtkResults") or []):
        if isinstance(entry, dict) and _matches_api_version(entry.get("file"), api_id, major):
            out.append(entry)
    return out


def _summary_hint(consolidated: dict, api_id: str, major: str):
    """resultsSummary.{core,security}FunctionResults[].hasPassed for api_id@major →
    True/False/None. A DERIVED flag — used only to detect contradiction/absence, never to
    establish PASS."""
    summary = consolidated.get("resultsSummary")
    if not isinstance(summary, dict):
        return None
    for key in ("coreFunctionResults", "securityFunctionResults"):
        for r in (summary.get(key) or []):
            if not isinstance(r, dict):
                continue
            m = _APINAME.match(str(r.get("apiName") or ""))
            if m and m.group(1).upper() == api_id.upper() and m.group(2) == major:
                return r.get("hasPassed")
    return None


def _resolve_mandatory(consolidated: dict, api_id: str, major: str) -> dict:
    """Positive-evidence resolution for one mandatory API. Returns {outcome, ...} where
    outcome ∈ {PASSED, FAILED, MISSING, AMBIGUOUS}. Only PASSED counts toward coverage.

    PASSED requires: exactly one matching raw result, a KNOWN format, total>0 (tests
    actually ran), failed==0, and no contradicting summary flag."""
    matches = _find_api_ctks(consolidated, api_id, major)
    hint = _summary_hint(consolidated, api_id, major)
    parsed = [(m, parse_ctk_report(m.get("data"))) for m in matches]

    # Positive failure evidence anywhere wins (a real executed check failed).
    failing = [(m, p) for m, p in parsed if p["format"] in ("v4-newman", "v5-cypress") and p["failed"] > 0]
    if failing:
        m, p = failing[0]
        return {"outcome": _FAILED, "result_file": m.get("file"), "format": p["format"],
                "total": p["total"], "failed": p["failed"], "reason": "mandatory API CTK reported failures"}

    if not matches:
        if hint is True:
            return {"outcome": _AMBIGUOUS, "reason": "resultsSummary claims passed but no raw API CTK artifact present"}
        if hint is False:
            return {"outcome": _AMBIGUOUS, "reason": "resultsSummary claims failed but no raw API CTK artifact present"}
        return {"outcome": _MISSING, "reason": "no matching API CTK result for the mandatory version"}

    if len(matches) > 1:
        return {"outcome": _AMBIGUOUS, "result_files": [m.get("file") for m in matches],
                "reason": "duplicate result files for one mandatory API/version — cannot attribute a single verdict"}

    m, p = parsed[0]
    if p["format"] not in ("v4-newman", "v5-cypress"):
        return {"outcome": _AMBIGUOUS, "result_file": m.get("file"), "format": p["format"],
                "reason": f"unusable API CTK result ({p['format']})"}
    if not _sane_count(p["total"]) or p["total"] <= 0:
        return {"outcome": _AMBIGUOUS, "result_file": m.get("file"), "format": p["format"], "total": p["total"],
                "reason": "no tests executed (zero-test result is not positive pass evidence)"}
    if p["failed"] != 0:
        return {"outcome": _AMBIGUOUS, "result_file": m.get("file"), "reason": "unexpected non-zero failures"}
    if hint is False:
        return {"outcome": _AMBIGUOUS, "result_file": m.get("file"),
                "reason": "raw result passes but resultsSummary flags it failed (contradiction)"}
    return {"outcome": _PASSED, "result_file": m.get("file"), "format": p["format"],
            "total": p["total"], "failed": 0}


def _baseline(consolidated: dict, key: str) -> dict:
    """Mocha baseline (configuration/deployment) evidence → {present, passed, tests, failures}.
    index.js REQUIRES these reports (it throws without them), so they are NOT optional: a
    legitimate completed run always carries them with tests>0."""
    rep = consolidated.get(key)
    if not isinstance(rep, dict):
        return {"present": False, "passed": False, "tests": None, "failures": None}
    stats = rep.get("stats")
    if not isinstance(stats, dict):
        return {"present": True, "passed": False, "tests": None, "failures": None, "reason": "stats missing"}
    tests, failures = stats.get("tests"), stats.get("failures")
    ok = _sane_count(tests) and tests > 0 and _sane_count(failures) and failures == 0
    return {"present": True, "passed": ok, "tests": tests, "failures": failures,
            "failed": _sane_count(failures) and failures > 0}


_EXPECTED_TOP_KEYS = ("apiCtkResults", "resultsSummary")


def normalize(consolidated, contract: dict, execution: dict = None) -> dict:
    """Deterministic normalized result. `execution` (from the adapter) carries
    `execution_completed` (bool) and optional `execution_error`. Component identity is
    ALWAYS bound to the job/contract context, never inferred from the result."""
    execution = execution or {}
    contract = contract or {}
    component = contract.get("component", {}) or {}
    # Identity binding: authoritative from the contract/job, never from the result artifact.
    base = {
        "component_id": component.get("id") or contract.get("component_id"),
        "component_version": component.get("version"),
        "contract_version": component.get("version"),
        "ctk_version": execution.get("ctk_version"),
        "execution_completed": bool(execution.get("execution_completed")),
        "mandatory_total": 0, "mandatory_executed": 0, "mandatory_passed": 0,
        "mandatory_failed": 0, "mandatory_missing": 0, "mandatory_ambiguous": 0,
        "optional_executed": 0, "per_requirement_results": [], "failed_tests": [],
        "warnings": [], "evidence": {}, "raw_result_path": execution.get("raw_result_path"),
        "identity_binding": {
            "source": "job/contract context (not the result artifact)",
            "component_id": component.get("id") or contract.get("component_id"),
            "component_version": component.get("version"),
        },
    }

    # ── EXECUTION_ERROR: the artifact itself is unusable / the framework didn't finish ──
    if execution.get("execution_error") or not execution.get("execution_completed", False):
        return {**base, "overall_status": EXECUTION_ERROR,
                "evidence": {"execution_error": _short(execution.get("execution_error"))
                             or "CTK execution did not complete"}}
    if not isinstance(consolidated, dict):
        return {**base, "overall_status": EXECUTION_ERROR,
                "evidence": {"result_parse_error": f"consolidatedResults.json is a {type(consolidated).__name__}, not an object"}}
    if not any(k in consolidated for k in _EXPECTED_TOP_KEYS):
        return {**base, "overall_status": EXECUTION_ERROR,
                "evidence": {"result_parse_error": "consolidatedResults.json missing expected CTK top-level keys"}}
    if "apiCtkResults" in consolidated and not isinstance(consolidated.get("apiCtkResults"), list):
        return {**base, "overall_status": EXECUTION_ERROR,
                "evidence": {"result_parse_error": "apiCtkResults is not an array (impossible CTK structure)"}}

    import oda_component_contract
    mandatory = oda_component_contract.mandatory_api_coverage(contract)
    optional_openapi = [r for r in contract.get("requirements", {}).get("optional_exposed", [])
                        if (r.get("api_type") or "").lower() == "openapi"]

    per, failed_tests = [], []
    m_pass = m_fail = m_missing = m_amb = 0
    for req in mandatory:
        api_id, major = req["id"], _major(req["declared_version"])
        ev = _resolve_mandatory(consolidated, api_id, major)
        row = {"id": api_id, "segment": req["segment"], "requirement": "MANDATORY",
               "declared_version": req["declared_version"],
               "executed_major_version": f"v{major}" if major else None,
               "version_match_precision": "MAJOR_ONLY",   # the CTK artifact filename carries major only
               "outcome": ev["outcome"], **{k: v for k, v in ev.items() if k != "outcome"}}
        per.append(row)
        if ev["outcome"] == _PASSED:
            m_pass += 1
        elif ev["outcome"] == _FAILED:
            m_fail += 1
            failed_tests.append({"api": api_id, "requirement": "MANDATORY",
                                 "version": req["declared_version"], "result_file": ev.get("result_file"),
                                 "failed": ev.get("failed"), "total": ev.get("total"),
                                 "detail": ev.get("reason")})
        elif ev["outcome"] == _MISSING:
            m_missing += 1
        else:
            m_amb += 1

    opt_exec = 0
    for req in optional_openapi:
        api_id, major = req["id"], _major(req["declared_version"])
        matches = _find_api_ctks(consolidated, api_id, major)
        if not matches:
            per.append({"id": api_id, "segment": req["segment"], "requirement": "OPTIONAL",
                        "declared_version": req["declared_version"], "outcome": "NOT_RUN"})
            continue
        opt_exec += 1
        p = parse_ctk_report(matches[0].get("data"))
        failed = p["format"] in ("v4-newman", "v5-cypress") and p["failed"] > 0
        per.append({"id": api_id, "segment": req["segment"], "requirement": "OPTIONAL",
                    "declared_version": req["declared_version"], "outcome": "FAILED" if failed else "EXECUTED",
                    "result_file": matches[0].get("file"), "total": p["total"], "failed": p["failed"]})
        if failed:
            failed_tests.append({"api": api_id, "requirement": "OPTIONAL", "version": req["declared_version"],
                                 "result_file": matches[0].get("file"),
                                 "detail": "optional API CTK failed (does not affect the mandatory verdict)"})

    # ── Baseline (config + deployment) — required for a positive PASS ─────────────────
    warnings = []
    cfg, dep = _baseline(consolidated, "configurationReport"), _baseline(consolidated, "deploymentReport")
    baseline_failed = cfg.get("failed") or dep.get("failed")
    baseline_passed = cfg.get("passed") and dep.get("passed")
    if not cfg["present"]:
        warnings.append("configuration baseline report absent (required for a completed CTK run)")
    if not dep["present"]:
        warnings.append("deployment baseline report absent (required for a completed CTK run)")

    # Identity mismatch check (result-declared name/version vs bound contract) — warn only.
    summary = consolidated.get("resultsSummary") if isinstance(consolidated.get("resultsSummary"), dict) else {}
    res_name, res_ver = summary.get("componentName"), summary.get("version")
    if res_name and base["component_id"] and str(res_name).upper().replace("-", "").find(base["component_id"].replace("TMFC", "")) < 0 \
       and base["component_id"].upper() not in str(res_name).upper():
        warnings.append(f"result componentName '{res_name}' does not obviously match bound {base['component_id']} (identity stays bound to job context)")

    # ── Deterministic verdict (positive evidence required for PASS) ───────────────────
    if m_fail > 0 or baseline_failed:
        status = FAIL
    elif len(mandatory) == 0:
        status = INCOMPLETE
        warnings.append("no mandatory openapi coverage defined by the canonical contract")
    elif m_pass == len(mandatory) and m_missing == 0 and m_amb == 0 and baseline_passed:
        status = PASS
    else:
        status = INCOMPLETE

    return {**base,
            "overall_status": status,
            "mandatory_total": len(mandatory), "mandatory_executed": m_pass + m_fail,
            "mandatory_passed": m_pass, "mandatory_failed": m_fail,
            "mandatory_missing": m_missing, "mandatory_ambiguous": m_amb,
            "optional_executed": opt_exec,
            "per_requirement_results": per, "failed_tests": failed_tests,
            "warnings": warnings + base["warnings"] if base.get("warnings") else warnings,
            "baseline": {"configuration": cfg, "deployment": dep,
                         "passed": bool(baseline_passed), "failed": bool(baseline_failed)},
            "evidence": {
                "mandatory_coverage": [f"{r['id']} {r['declared_version']}" for r in mandatory],
                "version_match_precision": "MAJOR_ONLY",
                "baseline_required": True,
                "api_ctk_result_files": [e.get("file") for e in (consolidated.get("apiCtkResults") or [])
                                         if isinstance(e, dict)],
            }}


def normalize_from_path(path: str, contract: dict, execution: dict = None) -> dict:
    """Load consolidatedResults.json from `path` and normalize. Missing/malformed after a
    'completed' subprocess is EXECUTION_ERROR (never FAIL)."""
    execution = dict(execution or {})
    execution.setdefault("raw_result_path", path)
    if not path or not os.path.exists(path):
        execution["execution_error"] = execution.get("execution_error") or \
            "consolidatedResults.json not found after CTK execution"
        return normalize(None, contract, execution)
    try:
        consolidated = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        execution["execution_error"] = f"malformed consolidatedResults.json: {e}"
        return normalize(None, contract, execution)
    return normalize(consolidated, contract, execution)


def _short(v, limit: int = 500):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s[:limit]
