"""
Unit tests for the deterministic conformance + profile engines.

Pure & offline (no server, no Ollama). Run either way:
    python test_conformance.py          # plain runner, exits non-zero on failure
    pytest test_conformance.py          # if pytest is installed
Locks in the TMF630 rules, the auto-fixer, and profile-aware detection so future
edits can't silently regress them.
"""
import json
import os

import glob

import conformance
import tmf_profile
import xray

try:
    import yaml
except Exception:
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
CANON_641 = os.path.join(HERE, "data", "TMF641_ServiceOrder", "TMF641-Service_Ordering-v4.0.0.swagger.json")
BROKEN = os.path.join(HERE, "..", "vscode-extension", "examples", "product-ordering.broken.yaml")

# Build the profile index once, synchronously, so profile tests are deterministic.
tmf_profile.build_index(force=True)


def _load(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    try:
        return json.loads(text)
    except Exception:
        return yaml.safe_load(text)


# ── conformance (TMF630) ──────────────────────────────────────────────────────
def test_canonical_spec_scores_100():
    r = conformance.check_spec(_load(CANON_641))
    assert r["score"] == 100, r["score"]
    assert r["summary"]["failed"] == 0 and r["summary"]["warnings"] == 0


def test_broken_spec_scores_low_and_is_fixable():
    r = conformance.check_spec(_load(BROKEN))
    assert r["score"] == 0, r["score"]
    assert r["summary"]["failed"] == 3, r["summary"]
    assert r["fixable"] >= 6, r["fixable"]


def test_autofix_makes_broken_compliant():
    spec = _load(BROKEN)
    conformance.fix_spec(spec, None)
    assert conformance.check_spec(spec)["score"] == 100


def test_notification_endpoints_exempt():
    # /listener POST returns 204 (not 201) and /hub GET has no fields — must NOT be flagged.
    spec = {
        "openapi": "3.0.3", "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/resource": {"get": {"parameters": [{"name": "offset", "in": "query", "schema": {"type": "integer"}},
                                                  {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                                                  {"name": "fields", "in": "query", "schema": {"type": "string"}}],
                                   "responses": {"200": {"description": "ok"}}},
                          "post": {"responses": {"201": {"description": "c"}}}},
            "/hub": {"post": {"responses": {"201": {"description": "c"}}}},
            "/listener/resourceCreateEvent": {"post": {"responses": {"204": {"description": "ok"}}}},
        },
        "components": {"schemas": {"Error": {"properties": {"code": {}, "reason": {}}}}},
    }
    fails = {f["id"] for f in conformance.check_spec(spec)["findings"] if f["status"] == "fail"}
    assert "post-201" not in fails, fails
    assert "fields" not in fails, fails


def test_allof_error_structure_resolved():
    # Error defined via allOf (the TMF Extensible pattern) must still be detected.
    spec = {
        "openapi": "3.0.3", "info": {"title": "X", "version": "1.0"}, "paths": {},
        "components": {"schemas": {
            "Extensible": {"properties": {"@type": {"type": "string"}}},
            "Error": {"allOf": [{"$ref": "#/components/schemas/Extensible"},
                                {"properties": {"code": {"type": "string"}, "reason": {"type": "string"}}}]},
        }},
    }
    findings = {f["id"]: f for f in conformance.check_spec(spec)["findings"]}
    assert findings["error-structure"]["status"] == "pass"


def test_sort_is_advisory_not_scored():
    sort = next(f for f in conformance.check_spec(_load(BROKEN))["findings"] if f["id"] == "sort")
    assert sort["severity"] == "info"   # missing sort must never lower the score


def test_findings_carry_tmf_citation():
    for f in conformance.check_spec(_load(BROKEN))["findings"]:
        assert f.get("ref", "").startswith("TMF630"), f["id"]


def test_external_ref_does_not_crash():
    assert conformance._resolve_ref({}, "common.yaml#/Foo") == {}     # external ref → safe empty
    spec = {"openapi": "3.0.3", "info": {"title": "X", "version": "1.0"},
            "paths": {"/thing": {"get": {"parameters": [{"$ref": "external.yaml#/components/parameters/Fields"}],
                                          "responses": {"200": {"description": "ok"}}}}},
            "components": {"schemas": {}}}
    conformance.check_spec(spec)   # must not raise


# ── profile-aware conformance ─────────────────────────────────────────────────
def test_profile_detects_tmf641():
    user = {"openapi": "3.0.3", "info": {"title": "ACME Service Order API", "version": "1.0"},
            "paths": {"/serviceOrder": {"get": {"responses": {"200": {}}}, "post": {"responses": {"201": {}}}},
                      "/serviceOrder/{id}": {"get": {"responses": {"200": {}}}}},
            "components": {"schemas": {"ServiceOrder": {"properties": {"id": {}, "state": {}, "orderDate": {}}}}}}
    r = tmf_profile.compare_to_canonical(user)
    assert r["detected"] and r["detected"]["tmf"] == "TMF641"
    assert r["detected"]["confidence"] == "high"
    assert len(r["operations"]["missing"]) > 0 and len(r["resource"]["missing"]) > 0


def test_profile_self_consistency():
    # The exact spec the index points to, compared with itself, must be 100% / nothing missing.
    meta = tmf_profile.build_index()["serviceorder"]
    canon = _load(os.path.join(HERE, meta["file"]))
    r = tmf_profile.compare_to_canonical(canon)
    assert r["coverage"] == 100, r["coverage"]
    assert len(r["operations"]["missing"]) == 0 and len(r["resource"]["missing"]) == 0


def test_profile_older_version_is_subset():
    # v4.0.0 vs the indexed v4.1.0 is a meaningful, sub-100 coverage (versions differ).
    r = tmf_profile.compare_to_canonical(_load(CANON_641))
    assert r["detected"]["tmf"] == "TMF641" and 80 <= r["coverage"] < 100, r["coverage"]


def test_profile_unknown_resource_not_detected():
    spec = {"openapi": "3.0.3", "info": {"title": "Gadget API", "version": "1.0"},
            "paths": {"/gadgetWidget": {"get": {"responses": {"200": {}}}}},
            "components": {"schemas": {"GadgetWidget": {"properties": {"id": {}}}}}}
    assert tmf_profile.compare_to_canonical(spec)["detected"] is None


def test_profile_name_clash_is_not_high_confidence():
    # A non-TMF API whose resource name happens to collide must not be labelled "high".
    spec = {"openapi": "3.0.3", "info": {"title": "Internal Account Tool", "version": "1.0"},
            "paths": {"/account": {"get": {"responses": {"200": {}}}}},
            "components": {"schemas": {"Account": {"properties": {"foo": {}, "bar": {}}}}}}
    r = tmf_profile.compare_to_canonical(spec)
    assert r["detected"] is None or r["detected"]["confidence"] != "high", r["detected"]


# ── API estate X-ray ──────────────────────────────────────────────────────────
def test_xray_portfolio_rollup():
    estate = os.path.join(HERE, "..", "vscode-extension", "examples", "estate")
    items = [{"filename": os.path.basename(f), "content": open(f, encoding="utf-8").read()}
             for f in glob.glob(os.path.join(estate, "*.yaml"))]
    rep = xray.build_portfolio(items)
    assert rep["summary"]["apis"] == 3 and rep["summary"]["detected"] == 3, rep["summary"]
    covs = [r["profile"]["coverage"] for r in rep["rows"] if r["profile"]]
    assert covs == sorted(covs), covs            # worst coverage first
    md = xray.render_markdown(rep)
    assert "API estate X-ray" in md and "TMF641" in md


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
