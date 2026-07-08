"""
Regression test over the FIRST REAL Component CTK artifact (Phase 5).

`test_fixtures/oda_ctk/tmfc043_real_consolidatedResults.json` is a genuine, unedited
resources/consolidatedResults.json produced by the official TM Forum Component CTK running
against a real deployed TMFC043 demo on local k3s (see that folder's README for full
provenance + SHA-256). This test locks in that SynaptDI's deterministic normalizer produces
the honest verdict PASS from that real evidence — and that the artifact stays byte-for-byte
unmodified.

Pure & offline. Run either way:
    python test_oda_ctk_real_artifact.py
    pytest test_oda_ctk_real_artifact.py
"""
import hashlib
import json
import os

import oda_component_contract as CONTRACT
import oda_ctk_results as RESULTS

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURE = os.path.join(_HERE, "test_fixtures", "oda_ctk", "tmfc043_real_consolidatedResults.json")
_EXPECTED_SHA256 = "6c7db5fb41ee65468b1507a6aa3ffb4dbba4ef8dea10606808d4a4f34d2790b0"

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL  " + name)


# The artifact must remain the exact bytes the real CTK wrote (no edits to obtain PASS).
_raw = open(_FIXTURE, "rb").read()
ok(hashlib.sha256(_raw).hexdigest() == _EXPECTED_SHA256, "real artifact is byte-for-byte unmodified (sha256)")

# It must genuinely have the real CTK shape (not a hand-authored stub).
_c = json.loads(_raw)
ok(isinstance(_c.get("apiCtkResults"), list) and len(_c["apiCtkResults"]) == 2, "artifact carries 2 real apiCtkResults")
ok(isinstance(_c.get("configurationReport"), dict) and isinstance(_c.get("deploymentReport"), dict),
   "artifact carries both real mocha baseline reports")
_files = {e.get("file") for e in _c["apiCtkResults"]}
ok(_files == {"TMF642_v4.json", "TMF669_v4.json"}, "artifact contains exactly the TMF642_v4 + TMF669_v4 results")
# The raw Newman evidence really is fully-passing (0 failed assertions).
for e in _c["apiCtkResults"]:
    a = e["data"]["run"]["stats"]["assertions"]
    ok(a["total"] > 0 and a["failed"] == 0, f"{e['file']} raw newman evidence: {a['total']} assertions, 0 failed")

# The deterministic verdict over the REAL artifact, bound to the canonical TMFC043 contract.
contract = CONTRACT.resolve_contract("TMFC043")
ok(contract.get("status") == "RESOLVED", "canonical TMFC043 contract resolves")
norm = RESULTS.normalize_from_path(_FIXTURE, contract, {"execution_completed": True})

ok(norm["overall_status"] == RESULTS.PASS, "deterministic verdict over the real artifact is PASS")
ok(norm["mandatory_total"] == 2, "mandatory_total == 2 (TMF642 + TMF669)")
ok(norm["mandatory_passed"] == 2, "mandatory_passed == 2")
ok(norm["mandatory_failed"] == 0, "mandatory_failed == 0")
ok(norm["mandatory_missing"] == 0, "mandatory_missing == 0")
ok(norm.get("mandatory_ambiguous", 0) == 0, "mandatory_ambiguous == 0")
ok(norm.get("baseline", {}).get("passed") is True, "baseline (configuration + deployment) passed")

by_id = {r["id"]: r for r in norm["per_requirement_results"] if r.get("requirement") == "MANDATORY"}
ok(by_id.get("TMF642", {}).get("outcome") == "PASSED", "TMF642 mandatory outcome PASSED")
ok(by_id.get("TMF669", {}).get("outcome") == "PASSED", "TMF669 mandatory outcome PASSED")
# Version precision stays honest even on a real full pass (major-only, never exact-semver).
ok(by_id.get("TMF642", {}).get("version_match_precision") == "MAJOR_ONLY", "TMF642 precision MAJOR_ONLY")

# ── The FAIL counterpart: a second REAL artifact from a deliberately non-conformant deploy
#    of the same component (alarm API omits the mandatory `state` attribute). Same cluster,
#    same baselines pass — the only difference is genuine conformance, and SynaptDI must
#    report an honest FAIL (never PASS, never dressed up as an execution error). ────────────
_BROKEN = os.path.join(_HERE, "test_fixtures", "oda_ctk", "tmfc043_broken_consolidatedResults.json")
_BROKEN_SHA256 = "ac5e1ed08544ace1b18556f0ad096087c7cdc3962a6c83a598403cc33bc0c4e6"
_braw = open(_BROKEN, "rb").read()
ok(hashlib.sha256(_braw).hexdigest() == _BROKEN_SHA256, "broken artifact is byte-for-byte unmodified (sha256)")
bn = RESULTS.normalize_from_path(_BROKEN, contract, {"execution_completed": True})
ok(bn["overall_status"] == RESULTS.FAIL, "deterministic verdict over the broken artifact is FAIL")
ok(bn["mandatory_failed"] == 1 and bn["mandatory_passed"] == 1, "broken: 1 mandatory failed, 1 passed")
_bby = {r["id"]: r for r in bn["per_requirement_results"] if r.get("requirement") == "MANDATORY"}
ok(_bby.get("TMF642", {}).get("outcome") == "FAILED", "broken: TMF642 outcome FAILED (missing mandatory state)")
ok((_bby.get("TMF642", {}).get("failed") or 0) > 0, "broken: TMF642 carries a real non-zero failed-assertion count")
ok(_bby.get("TMF669", {}).get("outcome") == "PASSED", "broken: TMF669 still PASSED (only alarm API is broken)")
# The baselines still pass in the broken run — the component IS deployed; it just isn't conformant.
ok(bn.get("baseline", {}).get("passed") is True, "broken: baseline still passed (deployed, but non-conformant)")

print(f"\ntest_oda_ctk_real_artifact: {passed} passed, {failed} failed")
if failed:
    import sys
    sys.exit(1)
