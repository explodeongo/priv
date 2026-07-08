"""
Execution-backed ODA Component CTK conformance — Phase 1 (TMFC043 golden path).

Pure & offline (no Canvas, no Docker, no kube, no live CTK run). Run either way:
    python test_oda_ctk.py          # plain runner, exits non-zero on failure
    pytest test_oda_ctk.py

Uses the REAL vendored canonical TMFC043 YAML and consolidatedResults.json fixtures
shaped exactly like CTK_Executor.py :: consolidate_results_to_json + src/index.js
parseCtkResult. The canonical contract is never mocked into a fake shape.
"""
import oda_component_contract as CONTRACT
import oda_ctk_results as RESULTS
import oda_ctk_adapter as ADAPTER

TMFC043 = "TMFC043"
_DONE = {"execution_completed": True}


# ── Fixture builders (real CTK result shapes) ─────────────────────────────────────────
def _newman(total, failed):
    return {"run": {"stats": {"assertions": {"total": total, "failed": failed}}}}


def _cypress(tests, failures):
    return {"stats": {"tests": tests, "failures": failures, "passes": tests - failures}}


def _consolidated(api_entries, config_failures=0, deploy_failures=0,
                  config_tests=6, deploy_tests=9):
    """A consolidatedResults.json with the exact top-level keys CTK_Executor writes.
    Baseline mocha reports carry tests>0 (a real completed run always runs them — index.js
    throws otherwise), so a passing baseline is present by default for PASS scenarios."""
    return {
        "resultsSummary": {"coreFunctionResults": [], "securityFunctionResults": []},
        "apiCtkResults": list(api_entries),
        "configurationReport": {"stats": {"tests": config_tests, "failures": config_failures}},
        "deploymentReport": {"stats": {"tests": deploy_tests, "failures": deploy_failures}},
        "bddResults": None,
        "bddPayloads": {},
    }


def _entry(api_id, major, report):
    return {"file": f"{api_id}_v{major}.0.0.json", "data": report}


def _contract():
    c = CONTRACT.resolve_contract(TMFC043)
    assert c["status"] == "RESOLVED"
    return c


# ── Canonical contract (tests 1–8) ────────────────────────────────────────────────────
def test_tmfc043_resolves_v1_0_0():
    c = _contract()
    assert c["component"]["id"] == "TMFC043"
    assert c["resolved_version"] == "1.0.0" and c["component"]["version"] == "1.0.0"
    assert c["component"]["format"] == "oda.tmforum.org/v1"
    assert c["exhaustive"] is True


def _find(c, api_id):
    return next((r for r in c["requirements"]["exposed"] if r["id"] == api_id), None)


def test_tmf642_mandatory_core_v4():
    r = _find(_contract(), "TMF642")
    assert r and r["requirement_status"] == "MANDATORY" and r["segment"] == "CORE"
    assert r["declared_version"] == "v4.0.0" and r["api_type"] == "openapi"


def test_tmf669_mandatory_security_v4():
    r = _find(_contract(), "TMF669")
    assert r and r["requirement_status"] == "MANDATORY" and r["segment"] == "SECURITY"
    assert r["declared_version"] == "v4.0.0" and r["api_type"] == "openapi"


def test_tmf656_optional():
    r = _find(_contract(), "TMF656")
    assert r and r["requirement_status"] == "OPTIONAL" and r["segment"] == "CORE"


def test_tmf701_optional():
    r = _find(_contract(), "TMF701")
    assert r and r["requirement_status"] == "OPTIONAL" and r["segment"] == "CORE"


def test_metrics_optional_management_prometheus():
    c = _contract()
    r = next((x for x in c["requirements"]["exposed"] if x["name"] == "metrics"), None)
    assert r and r["requirement_status"] == "OPTIONAL" and r["segment"] == "MANAGEMENT"
    assert r["api_type"] == "prometheus"
    assert r["is_placeholder"] is False           # a real (if templated-id) management entry
    # …and it is NOT counted as mandatory openapi coverage.
    assert "metrics" not in [m["id"] for m in CONTRACT.mandatory_api_coverage(c)]


def test_placeholder_dependent_not_a_real_dependency():
    c = _contract()
    ph = next((r for r in c["requirements"]["dependent"] if r["id"] == "dependentAPI_id"), None)
    assert ph is not None and ph["is_placeholder"] is True
    assert ph not in c["requirements"]["real_dependent"]


def test_tmfc043_has_zero_real_dependent_apis():
    assert _contract()["requirements"]["real_dependent"] == []


def test_mandatory_coverage_is_exactly_tmf642_and_tmf669():
    ids = sorted(m["id"] for m in CONTRACT.mandatory_api_coverage(_contract()))
    assert ids == ["TMF642", "TMF669"]


# ── Result normalization (tests 9–17) ─────────────────────────────────────────────────
def test_missing_tmf642_result_is_incomplete():
    c = _contract()
    cons = _consolidated([_entry("TMF669", "4", _cypress(15, 0))])   # TMF642 absent
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.INCOMPLETE
    assert out["mandatory_missing"] == 1 and out["mandatory_failed"] == 0


def test_missing_tmf669_result_is_incomplete():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0))])    # TMF669 absent
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.INCOMPLETE
    assert out["mandatory_missing"] == 1


def test_tmf642_failed_is_fail():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 3)), _entry("TMF669", "4", _cypress(15, 0))])
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.FAIL and out["mandatory_failed"] == 1
    assert any(f.get("api") == "TMF642" for f in out["failed_tests"])


def test_tmf669_failed_is_fail():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0)), _entry("TMF669", "4", _cypress(15, 2))])
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.FAIL and out["mandatory_failed"] == 1


def test_both_mandatory_passed_is_pass():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0)), _entry("TMF669", "4", _cypress(15, 0))])
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.PASS
    assert out["mandatory_total"] == 2 and out["mandatory_passed"] == 2 and out["mandatory_missing"] == 0


def test_optional_tmf656_not_run_does_not_fail_or_incomplete():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0)), _entry("TMF669", "4", _cypress(15, 0))])
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.PASS       # TMF656/TMF701 absent → still PASS
    assert out["optional_executed"] == 0


def test_optional_tmf701_failure_does_not_change_mandatory_verdict():
    # Even if an optional API CTK is present and FAILS, mandatory verdict stays PASS.
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0)), _entry("TMF669", "4", _cypress(15, 0)),
                          _entry("TMF656", "4", _newman(10, 4))])
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.PASS
    assert out["optional_executed"] == 1


def test_executor_failure_is_execution_error_not_fail():
    c = _contract()
    exec_state = {"execution_completed": False, "execution_error": {"category": "COMPONENT_NOT_DEPLOYED"}}
    out = RESULTS.normalize(None, c, exec_state)
    assert out["overall_status"] == RESULTS.EXECUTION_ERROR
    assert out["overall_status"] != RESULTS.FAIL


def test_missing_consolidated_after_completion_is_execution_error():
    c = _contract()
    out = RESULTS.normalize_from_path("/no/such/consolidatedResults.json", c, dict(_DONE))
    assert out["overall_status"] == RESULTS.EXECUTION_ERROR


def test_malformed_top_level_is_execution_error():
    c = _contract()
    out = RESULTS.normalize({"totally": "unexpected"}, c, _DONE)
    assert out["overall_status"] == RESULTS.EXECUTION_ERROR


def test_baseline_deployment_failure_is_fail():
    c = _contract()
    cons = _consolidated([_entry("TMF642", "4", _newman(20, 0)), _entry("TMF669", "4", _cypress(15, 0))],
                         deploy_failures=2)
    out = RESULTS.normalize(cons, c, _DONE)
    assert out["overall_status"] == RESULTS.FAIL


# ── Adapter: dry run, generated config, redaction (tests 18–20) ───────────────────────
_REQ = {
    "component_id": "TMFC043", "release_name": "rc-1", "namespace": "components",
    "ctkconfig": {"company_name": "Acme", "product_name": "FaultMgr",
                  "headers": {"Accept": "application/json", "Authorization": "Bearer SECRET-XYZ"}},
}


def test_dry_run_does_not_invoke_subprocess():
    d = ADAPTER.dry_run(dict(_REQ))
    assert d["subprocess_invoked"] is False
    assert d["status"] == "READY_TO_EXECUTE"
    assert d["errors"] == []
    assert sorted(d["expected_mandatory_ctks"]) == ["TMF642_v4", "TMF669_v4"]
    assert d["framework_files_ok"] is True
    # READY_TO_EXECUTE must never be conflated with ODA-conformant.
    assert "not" in d["note"].lower() and "conformant" in d["note"].lower()


def test_generated_change_me_uses_real_framework_structure():
    cm = ADAPTER.generate_change_me(dict(_REQ))
    # Exact top-level keys the provided CHANGE_ME.json declares.
    for k in ("releaseName", "component_to_run", "component_namespace", "standardComponentPath",
              "ctk_name_mapping", "runExposedOptional", "runDependentOptional", "runSecurityOptional",
              "ctkVersion", "apiVersionUnderTest", "apiVersionOverrides", "ctkLogging",
              "download_sslVerify", "standardComponentDownload", "ctkconfig", "dependentStubs",
              "bddPayloads", "retrySettings"):
        assert k in cm, f"missing key {k}"
    assert cm["component_to_run"] == "TMFC043" and cm["releaseName"] == "rc-1"
    assert cm["standardComponentDownload"]["repoOwner"] == "tmforum-rand"
    assert cm["standardComponentDownload"]["gitBranch"] == "v1.0.0"
    assert cm["dependentStubs"] == {} and cm["bddPayloads"] == {}   # TMFC043 has 0 dependent APIs
    for sub in ("companyName", "productName", "productUrl", "productVersion",
                "componentUrl", "headers", "payloads", "rejectUnauthorized"):
        assert sub in cm["ctkconfig"], f"missing ctkconfig.{sub}"


def test_secrets_redacted_in_snapshot_and_logs():
    # Redaction of the config snapshot (what jobs persist / APIs return).
    cm = ADAPTER.generate_change_me(dict(_REQ))
    red = ADAPTER.redact(cm)
    assert red["ctkconfig"]["headers"]["Authorization"] == "***REDACTED***"
    assert cm["ctkconfig"]["headers"]["Authorization"] == "Bearer SECRET-XYZ"   # original untouched
    # Redaction of captured log text.
    assert "SECRET" not in ADAPTER._redact_text("Authorization: Bearer SECRET-XYZ")
    # A validation-failed job never persists a raw secret in its config_snapshot.
    import oda_ctk_jobs
    job = oda_ctk_jobs._new_job(dict(_REQ))
    assert job["config_snapshot"]["ctkconfig"]["headers"]["Authorization"] == "***REDACTED***"


def test_invalid_release_name_rejected():
    bad = {**_REQ, "release_name": "Bad Name!!"}
    assert ADAPTER.validate_request(bad)                       # non-empty error list
    d = ADAPTER.dry_run(bad)
    assert d["status"] == "NOT_READY" and d["errors"]


def test_unsupported_component_rejected():
    d = ADAPTER.dry_run({**_REQ, "component_id": "TMFC999"})
    assert d["status"] == "NOT_READY" and any("not supported" in e for e in d["errors"])


def test_execution_failures_classified_by_category():
    """Infra/executor failures are classified into distinct categories — never FAIL."""
    # Python 3.10+ requirement (real failure seen when the host interpreter is 3.9).
    py = ADAPTER._classify_failure(1, "", "TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'", False)
    assert py["category"] == ADAPTER.DEPENDENCY_ERROR
    # Component not deployed (helm cannot get manifest).
    nd = ADAPTER._classify_failure(1, "Aborting CTK run due to missing manifest for: rc-1", "", False)
    assert nd["category"] == ADAPTER.COMPONENT_NOT_DEPLOYED
    # Missing helm/kubectl binary.
    hk = ADAPTER._classify_failure(1, "", "FileNotFoundError: [Errno 2] No such file or directory: 'helm'", False)
    assert hk["category"] == ADAPTER.DEPENDENCY_ERROR
    # Timeout.
    to = ADAPTER._classify_failure(None, "", "", True)
    assert to["category"] == ADAPTER.TIMEOUT_ERROR


# ══════════════════════════════════════════════════════════════════════════════════════
# PHASE 2 — ADVERSARIAL NORMALIZER VALIDATION
# Prove oda_ctk_results.py cannot produce PASS from malformed/ambiguous/partial/
# contradictory/unexpected CTK output. PASS requires positive, unambiguous evidence.
# All fixtures use only shapes plausibly emitted by the inspected CTK source.
# ══════════════════════════════════════════════════════════════════════════════════════
_C = _contract()   # resolved once; shared read-only


def _status(consolidated, execution=None):
    return RESULTS.normalize(consolidated, _C, execution or dict(_DONE))["overall_status"]


def _pass_pair():
    """Both mandatory APIs positively passing (real major-only filenames)."""
    return [{"file": "TMF642_v4.json", "data": _newman(20, 0)},
            {"file": "TMF669_v4.json", "data": _cypress(15, 0)}]


# ── A–F: empty / shape / null-data ────────────────────────────────────────────────────
def test_adv_A_empty_object_is_execution_error():
    assert _status({}) == RESULTS.EXECUTION_ERROR


def test_adv_B_valid_keys_empty_apictk_is_incomplete():
    assert _status(_consolidated([])) == RESULTS.INCOMPLETE


def test_adv_C_tmf642_present_tmf669_absent_incomplete():
    assert _status(_consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)}])) == RESULTS.INCOMPLETE


def test_adv_D_tmf669_present_tmf642_absent_incomplete():
    assert _status(_consolidated([{"file": "TMF669_v4.json", "data": _cypress(15, 0)}])) == RESULTS.INCOMPLETE


def test_adv_E_data_null_is_incomplete_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": None}, {"file": "TMF669_v4.json", "data": None}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_F_data_empty_object_is_incomplete_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {}}, {"file": "TMF669_v4.json", "data": {}}])
    assert _status(cons) == RESULTS.INCOMPLETE


# ── G–N: Newman / Cypress stat shapes ─────────────────────────────────────────────────
def test_adv_G_newman_missing_assertions_incomplete():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"run": {"stats": {}}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_H_newman_zero_tests_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(0, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE     # zero executed tests ≠ success


def test_adv_I_newman_positive_pass_contributes_to_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": _newman(10, 0)}])
    assert _status(cons) == RESULTS.PASS


def test_adv_J_newman_failures_is_fail():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 2)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.FAIL


def test_adv_K_cypress_missing_stats_incomplete():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"stats": {}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_L_cypress_zero_tests_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(0, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_M_cypress_positive_pass_contributes_to_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _cypress(20, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.PASS


def test_adv_N_cypress_failures_is_fail():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 3)}])
    assert _status(cons) == RESULTS.FAIL


# ── O–P: summary vs raw contradiction ─────────────────────────────────────────────────
def test_adv_O_summary_pass_but_raw_failures_is_fail():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 4)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    cons["resultsSummary"]["coreFunctionResults"] = [{"apiName": "TMF642 alarm (v4) - Mandatory", "hasPassed": True}]
    assert _status(cons) == RESULTS.FAIL           # raw is authoritative


def test_adv_P_summary_fail_but_raw_zero_failures_is_not_pass():
    cons = _consolidated(_pass_pair())
    cons["resultsSummary"]["coreFunctionResults"] = [{"apiName": "TMF642 alarm (v4) - Mandatory", "hasPassed": False}]
    assert _status(cons) == RESULTS.INCOMPLETE     # contradiction → never PASS


# ── Q–R: duplicate contradictory results ──────────────────────────────────────────────
def test_adv_Q_duplicate_tmf642_contradictory_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF642_v4.0.0.json", "data": _newman(20, 5)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.FAIL           # a real failure among duplicates → not PASS


def test_adv_Q2_duplicate_tmf642_both_pass_is_ambiguous_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF642_v4.0.0.json", "data": _newman(18, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE     # duplicate → cannot attribute a clean pass


def test_adv_R_duplicate_tmf669_contradictory_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)},
                          {"file": "TMF669_v4.0.0.json", "data": _cypress(15, 4)}])
    assert _status(cons) == RESULTS.FAIL


# ── S–U: wrong / similar / malformed filenames must not satisfy coverage ───────────────
def test_adv_S_wrong_version_result_does_not_satisfy_mandatory():
    cons = _consolidated([{"file": "TMF642_v5.json", "data": _newman(20, 0)},   # v5, canonical needs v4
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE
    per = {r["id"]: r for r in RESULTS.normalize(cons, _C, dict(_DONE))["per_requirement_results"]}
    assert per["TMF642"]["outcome"] == "MISSING"


def test_adv_T_similar_names_do_not_match():
    for bad in ("XTMF642_v4.json", "TMF6420_v4.json", "TMF642_backup_v4.json", "TMF642_v41.json"):
        assert RESULTS._matches_api_version(bad, "TMF642", "4") is False, bad
    assert RESULTS._matches_api_version("TMF642_v4.json", "TMF642", "4") is True
    assert RESULTS._matches_api_version("TMF642_v4.0.0.json", "TMF642", "4") is True


def test_adv_U_malformed_filename_is_missing():
    cons = _consolidated([{"file": "garbage.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


# ── V: apiCtkResults wrong type ───────────────────────────────────────────────────────
def test_adv_V_apictk_not_array_is_execution_error():
    assert _status({"apiCtkResults": "oops", "resultsSummary": {}}) == RESULTS.EXECUTION_ERROR
    assert _status({"apiCtkResults": {"file": "x"}, "resultsSummary": {}}) == RESULTS.EXECUTION_ERROR


# ── W–AB: baseline requirement ────────────────────────────────────────────────────────
def test_adv_W_config_report_missing_is_not_pass():
    cons = _consolidated(_pass_pair())
    del cons["configurationReport"]
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_X_deployment_report_missing_is_not_pass():
    cons = _consolidated(_pass_pair())
    del cons["deploymentReport"]
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_Y_config_stats_missing_is_not_pass():
    cons = _consolidated(_pass_pair())
    cons["configurationReport"] = {}
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_Z_deployment_stats_missing_is_not_pass():
    cons = _consolidated(_pass_pair())
    cons["deploymentReport"] = {}
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AA_baseline_zero_tests_is_not_pass():
    cons = _consolidated(_pass_pair(), config_tests=0, deploy_tests=0)
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AB_baseline_passes_with_tests_contributes_to_pass():
    assert _status(_consolidated(_pass_pair(), config_tests=6, deploy_tests=9)) == RESULTS.PASS


# ── AC–AE: resultsSummary edge cases ──────────────────────────────────────────────────
def test_adv_AC_results_summary_missing_but_raw_positive_is_pass():
    cons = _consolidated(_pass_pair())
    del cons["resultsSummary"]                     # raw apiCtkResults are authoritative
    cons["apiCtkResults"] = _pass_pair()           # ensure apiCtkResults key still present
    out = RESULTS.normalize(cons, _C, dict(_DONE))
    assert out["overall_status"] == RESULTS.PASS


def test_adv_AD_summary_contradicts_apictk_raw_wins():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 3)},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    cons["resultsSummary"]["coreFunctionResults"] = [{"apiName": "TMF642 alarm (v4) - Mandatory", "hasPassed": True}]
    cons["resultsSummary"]["securityFunctionResults"] = [{"apiName": "TMF669 party (v4) - Mandatory", "hasPassed": True}]
    assert _status(cons) == RESULTS.FAIL


def test_adv_AE_one_pass_one_ambiguous_is_incomplete():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(20, 0)},
                          {"file": "TMF669_v4.json", "data": {"weird": "structure"}}])
    assert _status(cons) == RESULTS.INCOMPLETE


# ── AF–AH: optional/unknown must not satisfy or break mandatory ───────────────────────
def test_adv_AF_optional_present_but_mandatory_absent_is_incomplete():
    cons = _consolidated([{"file": "TMF656_v4.json", "data": _newman(10, 0)}])   # optional only
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AG_optional_failure_with_mandatory_pass_is_pass():
    cons = _consolidated(_pass_pair() + [{"file": "TMF656_v4.json", "data": _newman(10, 5)}])
    assert _status(cons) == RESULTS.PASS


def test_adv_AH_unknown_api_failure_with_mandatory_pass_is_pass():
    cons = _consolidated(_pass_pair() + [{"file": "TMF999_v4.json", "data": _newman(10, 9)}])
    assert _status(cons) == RESULTS.PASS


# ── AI–AK: JSON-level malformation ────────────────────────────────────────────────────
def test_adv_AI_malformed_json_is_execution_error():
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".json")
    os.write(fd, b"{ not valid json ]"); os.close(fd)
    try:
        assert RESULTS.normalize_from_path(p, _C, dict(_DONE))["overall_status"] == RESULTS.EXECUTION_ERROR
    finally:
        os.remove(p)


def test_adv_AJ_top_level_array_is_execution_error():
    assert _status([]) == RESULTS.EXECUTION_ERROR


def test_adv_AK_top_level_string_is_execution_error():
    assert _status("PASS") == RESULTS.EXECUTION_ERROR


# ── AL–AR: impossible / weird numeric shapes ──────────────────────────────────────────
def test_adv_AL_deeply_nested_unexpected_is_incomplete():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"a": {"b": {"c": [1, 2, 3]}}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AM_boolean_where_numeric_expected_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"run": {"stats": {"assertions": {"total": True, "failed": False}}}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE
    assert RESULTS.parse_ctk_report({"run": {"stats": {"assertions": {"total": True, "failed": False}}}})["format"] == "malformed"


def test_adv_AN_negative_counts_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"run": {"stats": {"assertions": {"total": -5, "failed": -1}}}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AO_cypress_failures_gt_tests_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"stats": {"tests": 5, "failures": 10}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE
    assert RESULTS.parse_ctk_report({"stats": {"tests": 5, "failures": 10}})["format"] == "malformed"


def test_adv_AP_newman_failed_gt_total_is_not_pass():
    cons = _consolidated([{"file": "TMF642_v4.json", "data": {"run": {"stats": {"assertions": {"total": 5, "failed": 10}}}}},
                          {"file": "TMF669_v4.json", "data": _cypress(15, 0)}])
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AQ_duplicate_json_fields_parse_deterministically():
    import tempfile, os
    # Duplicate "failed" keys — json.load keeps the last (10) → failure → not PASS, deterministic.
    raw = ('{"apiCtkResults":[{"file":"TMF642_v4.json","data":{"run":{"stats":{"assertions":'
           '{"total":20,"failed":0,"failed":10}}}}},{"file":"TMF669_v4.json","data":'
           '{"stats":{"tests":15,"failures":0}}}],"resultsSummary":{},'
           '"configurationReport":{"stats":{"tests":6,"failures":0}},'
           '"deploymentReport":{"stats":{"tests":9,"failures":0}}}')
    fd, p = tempfile.mkstemp(suffix=".json"); os.write(fd, raw.encode()); os.close(fd)
    try:
        s1 = RESULTS.normalize_from_path(p, _C, dict(_DONE))["overall_status"]
        s2 = RESULTS.normalize_from_path(p, _C, dict(_DONE))["overall_status"]
        assert s1 == s2 == RESULTS.FAIL           # last value (failed=10) wins; deterministic
    finally:
        os.remove(p)


def test_adv_AR_very_large_valid_counts_ok():
    big = 10 ** 15
    cons = _consolidated([{"file": "TMF642_v4.json", "data": _newman(big, 0)},
                          {"file": "TMF669_v4.json", "data": _cypress(big, 0)}])
    assert _status(cons) == RESULTS.PASS          # large but sane → still positive pass


# ── AS–AU: identity + summary-only claims ─────────────────────────────────────────────
def test_adv_AS_missing_identity_in_result_binds_to_job_context():
    cons = _consolidated(_pass_pair())            # carries no componentName/version
    out = RESULTS.normalize(cons, _C, dict(_DONE))
    assert out["component_id"] == "TMFC043" and out["component_version"] == "1.0.0"


def test_adv_AT_summary_claims_pass_but_no_raw_artifact_is_not_pass():
    cons = _consolidated([{"file": "TMF669_v4.json", "data": _cypress(15, 0)}])   # no TMF642 raw
    cons["resultsSummary"]["coreFunctionResults"] = [{"apiName": "TMF642 alarm (v4) - Mandatory", "hasPassed": True}]
    assert _status(cons) == RESULTS.INCOMPLETE


def test_adv_AU_summary_claims_both_pass_but_apictk_empty_is_not_pass():
    cons = _consolidated([])
    cons["resultsSummary"]["coreFunctionResults"] = [{"apiName": "TMF642 alarm (v4) - Mandatory", "hasPassed": True}]
    cons["resultsSummary"]["securityFunctionResults"] = [{"apiName": "TMF669 party (v4) - Mandatory", "hasPassed": True}]
    assert _status(cons) == RESULTS.INCOMPLETE


# ── PASS invariants (task 4) ──────────────────────────────────────────────────────────
def test_invariant_pass_requires_every_mandatory_matched_and_executed():
    out = RESULTS.normalize(_consolidated(_pass_pair()), _C, dict(_DONE))
    assert out["overall_status"] == RESULTS.PASS
    assert out["mandatory_total"] == 2 and out["mandatory_passed"] == 2
    assert out["mandatory_missing"] == 0 and out["mandatory_ambiguous"] == 0 and out["mandatory_failed"] == 0
    # Removing either mandatory API breaks PASS.
    for drop in ("TMF642_v4.json", "TMF669_v4.json"):
        cons = _consolidated([e for e in _pass_pair() if e["file"] != drop])
        assert RESULTS.normalize(cons, _C, dict(_DONE))["overall_status"] != RESULTS.PASS


def test_invariant_version_precision_is_major_only():
    out = RESULTS.normalize(_consolidated(_pass_pair()), _C, dict(_DONE))
    for r in out["per_requirement_results"]:
        if r["requirement"] == "MANDATORY":
            assert r["declared_version"] in ("v4.0.0",)
            assert r["executed_major_version"] == "v4"
            assert r["version_match_precision"] == "MAJOR_ONLY"
    assert out["evidence"]["version_match_precision"] == "MAJOR_ONLY"


def test_invariant_result_fixture_cannot_change_component_identity():
    # A hostile result claiming a different component/version cannot rebind identity.
    cons = _consolidated(_pass_pair())
    cons["resultsSummary"]["componentName"] = "TMFC999-EvilComponent"
    cons["resultsSummary"]["version"] = "9.9.9"
    out = RESULTS.normalize(cons, _C, dict(_DONE))
    assert out["component_id"] == "TMFC043" and out["component_version"] == "1.0.0"
    assert out["identity_binding"]["component_id"] == "TMFC043"


# ── Stale-artifact hardening (task 6) ─────────────────────────────────────────────────
def test_stale_artifact_purge_and_freshness_guards():
    import tempfile, os, time
    # purge only touches paths inside our workspace prefix.
    ws = tempfile.mkdtemp(prefix="synaptdi_odactk_")
    cctk = os.path.join(ws, "componentCTK"); os.makedirs(os.path.join(cctk, "resources"))
    stale = os.path.join(cctk, "resources", "consolidatedResults.json")
    open(stale, "w").write("{}")
    assert os.path.exists(stale)
    ADAPTER.purge_result_paths(ws, cctk)
    assert not os.path.exists(stale), "stale consolidatedResults.json must be purged pre-run"
    # freshness: a file older than the execution window is rejected.
    open(stale, "w").write("{}")
    future = time.time() + 100
    assert ADAPTER._is_fresh(stale, future) is False
    assert ADAPTER._is_fresh(stale, time.time() - 100) is True
    shutil_ok = os.path.isdir(ws)
    import shutil
    shutil.rmtree(ws, ignore_errors=True)
    # purge never touches a non-workspace path.
    outside = tempfile.mkdtemp(prefix="not_ours_")
    victim = os.path.join(outside, "Reports"); os.makedirs(victim)
    ADAPTER.purge_result_paths(outside, outside)          # wrong prefix → no-op
    assert os.path.isdir(victim), "purge must never delete outside the synaptdi workspace"
    shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    import sys
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  " + name)
            passed += 1
        except AssertionError as e:
            print("FAIL  " + name + "  — " + str(e))
            failed += 1
        except Exception as e:
            print("ERROR " + name + "  — " + type(e).__name__ + ": " + str(e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
