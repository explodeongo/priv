"""
Phase 4 — trust-boundary audit regression tests (execution-backed ODA Component CTK).

Covers the CONFIRMED findings fixed in this phase:
  1. Public API responses must never carry a host filesystem path, the isolated CTK
     workspace path, or a raw secret value — even when embedded inside stdout/stderr,
     an exception message, a result warning, a failed-test detail, a result_file, or a
     per-requirement reason (oda_ctk_sanitize.py — the centralized boundary).
  2. `result.raw_result_path` (a host workspace path set on every completed execution,
     not only on error) must be removed from the public result entirely.
  3. Job read/list access is bound to the creating user (or an admin) — no other
     authenticated user can read another user's job by job_id (oda_ctk_jobs._owned()).
  4. release_name/namespace DNS-1123 validation must not be bypassable by a trailing
     newline (Python's `re.match` + a '$'-terminated pattern quirk).

Pure & offline — no Canvas, no Docker, no kube, no live CTK run, no HTTP layer (FastAPI
dependency wiring is exercised separately by reading main.py's route signatures, not
re-tested here). Run either way:
    python test_oda_ctk_phase4_audit.py
    pytest test_oda_ctk_phase4_audit.py
"""
import oda_ctk_adapter as ADAPTER
import oda_ctk_jobs as JOBS
import oda_ctk_sanitize as SANITIZE

# Real leaked strings observed during live manual testing (Phase 4, Part 1) — used
# verbatim as regression fixtures so the exact confirmed leaks stay fixed.
REAL_WORKSPACE_LEAK = ("CTK failed at /private/var/folders/bm/109h55vs5vz_bk7d9hlnjq2w0000gn/T/"
                       "synaptdi_odactk_4mopk88s/componentCTK/scripts/CTK_Executor.py while parsing")
REAL_INTERPRETER_LEAK = ("/Users/aryan/Downloads/SynaptDI/backend/venv/lib/python3.9/site-packages/"
                         "urllib3/__init__.py:35: NotOpenSSLWarning: urllib3 v2 only supports OpenSSL")
REAL_FRAMEWORK_SRC_LEAK = "CTK framework not found at /Users/aryan/Downloads/CTK/componentCTK"
SECRET_BEARER = "Bearer sk-super-secret-token-do-not-leak-999"

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL  " + name)


# ── 1. sanitize_text / sanitize_filename — path scrubbing on real observed leaks ──────
ok("/private/var" not in SANITIZE.sanitize_text(REAL_WORKSPACE_LEAK), "sanitize_text hides /private/var workspace path")
ok("synaptdi_odactk" not in SANITIZE.sanitize_text(REAL_WORKSPACE_LEAK), "sanitize_text hides workspace dir name")
ok("while parsing" in SANITIZE.sanitize_text(REAL_WORKSPACE_LEAK), "sanitize_text preserves human-readable remainder")
ok("/Users/aryan" not in SANITIZE.sanitize_text(REAL_INTERPRETER_LEAK), "sanitize_text hides /Users/<name> interpreter path")
ok("aryan" not in SANITIZE.sanitize_text(REAL_INTERPRETER_LEAK), "sanitize_text hides the host username")
ok("/Users/aryan" not in SANITIZE.sanitize_text(REAL_FRAMEWORK_SRC_LEAK), "sanitize_text hides FRAMEWORK_SRC path")
ok(SANITIZE.sanitize_text(None) is None, "sanitize_text handles None")
ok(SANITIZE.sanitize_filename("TMF642_v4.json") == "TMF642_v4.json", "sanitize_filename keeps a legit bare filename")
ok(SANITIZE.sanitize_filename("/private/var/.../synaptdi_odactk_x/Reports/TMF642_v4.json") == "TMF642_v4.json",
   "sanitize_filename collapses an absolute workspace path to its basename")

# ── 2. sanitize_job_view — every rendered field, for a job carrying hostile content ────
hostile_job = {
    "job_id": "abc123", "component_id": "TMFC043", "component_version": "1.0.0",
    "state": "FAILED_EXECUTION", "created_at": "t", "started_at": "t", "completed_at": "t",
    "execution_error": {"category": "DEPENDENCY_ERROR", "message": REAL_WORKSPACE_LEAK,
                        "messages": [REAL_FRAMEWORK_SRC_LEAK]},
    "config_snapshot": {"ctkconfig": {"headers": {"Authorization": SECRET_BEARER}}},
    "result": {
        "component_id": "TMFC043", "overall_status": "EXECUTION_ERROR",
        "raw_result_path": "/private/var/folders/x/synaptdi_odactk_y/componentCTK/resources/consolidatedResults.json",
        "warnings": [f"result componentName 'x' looks like {REAL_WORKSPACE_LEAK}"],
        "failed_tests": [{"api": "TMF642", "detail": REAL_INTERPRETER_LEAK,
                          "result_file": "/private/var/.../synaptdi_odactk_z/Reports/TMF642_v4.json"}],
        "per_requirement_results": [{"id": "TMF642", "outcome": "FAILED", "reason": REAL_WORKSPACE_LEAK,
                                     "result_file": "/private/var/.../synaptdi_odactk_z/TMF669_v4.json"}],
        "evidence": {"execution_error": REAL_FRAMEWORK_SRC_LEAK, "api_ctk_result_files": [
            "/private/var/.../synaptdi_odactk_z/TMF642_v4.json"]},
    },
    "stdout_tail": f"npm install\n{REAL_INTERPRETER_LEAK}\nAuthorization: {SECRET_BEARER}",
    "stderr_tail": REAL_WORKSPACE_LEAK,
    "_workspace": "/private/var/folders/x/synaptdi_odactk_y",   # private — must never be a top-level key
    "_request": {"release_name": "rc-1"},
    "_owner_id": "user-1",
}


def _blob(d):
    import json
    return json.dumps(d, default=str)


non_admin = SANITIZE.sanitize_job_view(hostile_job, is_admin=False)
admin = SANITIZE.sanitize_job_view(hostile_job, is_admin=True)

for label, view in (("non-admin", non_admin), ("admin", admin)):
    b = _blob(view)
    ok("/Users/aryan" not in b, f"{label} view: no /Users/<name> path anywhere")
    ok("/private/var" not in b, f"{label} view: no /private/var path anywhere")
    ok("synaptdi_odactk" not in b, f"{label} view: no workspace dir name anywhere")
    ok(SECRET_BEARER not in b, f"{label} view: raw Authorization secret never present")
    ok("raw_result_path" not in view.get("result", {}), f"{label} view: raw_result_path removed from result")
    ok(not any(k.startswith("_") for k in view), f"{label} view: no private ('_'-prefixed) keys leak")
    # Verdict fields must survive untouched — sanitization must never alter the verdict.
    ok(view["result"]["overall_status"] == "EXECUTION_ERROR", f"{label} view: verdict unchanged")
    ok(view["result"]["failed_tests"][0]["api"] == "TMF642", f"{label} view: failed_tests api id unchanged")
    ok(view["result"]["per_requirement_results"][0]["outcome"] == "FAILED", f"{label} view: per-requirement outcome unchanged")

ok("stdout_tail" not in non_admin, "non-admin view: stdout_tail removed entirely")
ok("stderr_tail" not in non_admin, "non-admin view: stderr_tail removed entirely")
ok("stdout_tail" in admin and admin["stdout_tail"] is not None, "admin view: stdout_tail present (path-scrubbed)")
ok(SECRET_BEARER not in admin.get("stdout_tail", ""), "admin view: stdout_tail secret still redacted even for admin")
ok("npm install" in admin.get("stdout_tail", ""), "admin view: stdout_tail keeps non-sensitive content")

# ── 3. sanitize_dry_run / sanitize_reason — the other two confirmed leak sites ────────
hostile_dry_run = {"status": "NOT_READY", "errors": [REAL_FRAMEWORK_SRC_LEAK, "release_name is required"],
                   "generated_change_me": {"ctkconfig": {"headers": {"Authorization": SECRET_BEARER}}}}
clean_dry_run = SANITIZE.sanitize_dry_run(hostile_dry_run)
ok("/Users/aryan" not in _blob(clean_dry_run), "sanitize_dry_run hides FRAMEWORK_SRC path in errors[]")
ok("release_name is required" in clean_dry_run["errors"], "sanitize_dry_run preserves clean validation errors")
ok(SECRET_BEARER not in _blob(clean_dry_run), "sanitize_dry_run redacts secrets in generated_change_me")

ok("/Users/aryan" not in SANITIZE.sanitize_reason("YAML parse failed: while parsing /Users/aryan/Downloads/SynaptDI/backend/oda_ctk_assets/x.yaml"),
   "sanitize_reason hides a PARSE_ERROR path (contract endpoint)")

# ── 4. Job ownership binding — no cross-user access, admin can read any job ───────────
job_a = JOBS.create_execution_job(
    {"component_id": "TMFC043", "release_name": "rc-1", "namespace": "components",
     "ctkconfig": {}}, owner_id="user-A")
jid = job_a["job_id"]

ok(JOBS.get_job(jid, requester_id="user-A", is_admin=False) is not None, "owner can read their own job")
ok(JOBS.get_job(jid, requester_id="user-B", is_admin=False) is None, "a different non-admin user CANNOT read another user's job")
ok(JOBS.get_job(jid, requester_id=None, is_admin=False) is None, "an unauthenticated/unknown requester cannot read a job")
ok(JOBS.get_job(jid, requester_id="user-B", is_admin=True) is not None, "an admin can read any user's job")
ok(JOBS.get_results(jid, requester_id="user-B", is_admin=False) is None, "results endpoint enforces the same ownership boundary")
ok(JOBS.get_results(jid, requester_id="user-A", is_admin=False) is not None, "owner can read their own results")
ok(JOBS.get_job("does-not-exist", requester_id="user-A", is_admin=False) is None, "nonexistent job_id returns None (same as non-owned — no existence oracle)")

# ── 5. DNS-1123 validation — trailing-newline bypass is closed ────────────────────────
ok(ADAPTER._valid_k8s_name("myrelease") is True, "valid release name still accepted")
ok(ADAPTER._valid_k8s_name("myrelease\n") is False, "trailing-newline release name REJECTED (regression: was previously accepted)")
ok(ADAPTER._valid_k8s_name("a" * 64) is False, "release name over 63 chars rejected (DNS-1123 label limit)")
ok(ADAPTER._valid_k8s_name("a" * 63) is True, "release name at exactly 63 chars accepted")
errs = ADAPTER.validate_request({"component_id": "TMFC043", "release_name": "rc-1\n", "namespace": "components"})
ok(any("DNS-1123" in e for e in errs), "validate_request rejects a newline-suffixed release_name end-to-end")
ok(ADAPTER._COMPONENT_ID.fullmatch("TMFC043\n") is None, "component_id newline bypass also closed (defense-in-depth)")

print(f"\ntest_oda_ctk_phase4_audit: {passed} passed, {failed} failed")
if failed:
    import sys
    sys.exit(1)
