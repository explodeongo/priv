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
BROKEN = os.path.join(HERE, "..", "examples", "1-single-api-check", "product-ordering.broken.yaml")

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
    estate = os.path.join(HERE, "..", "examples", "2-portfolio-xray")
    items = [{"filename": os.path.basename(f), "content": open(f, encoding="utf-8").read()}
             for f in glob.glob(os.path.join(estate, "*.yaml"))]
    rep = xray.build_portfolio(items)
    assert rep["summary"]["apis"] == 3 and rep["summary"]["detected"] == 3, rep["summary"]
    covs = [r["profile"]["coverage"] for r in rep["rows"] if r["profile"]]
    assert covs == sorted(covs), covs            # worst coverage first
    md = xray.render_markdown(rep)
    assert "API estate X-ray" in md and "TMF641" in md


def test_scaffold_raises_coverage_and_is_clean():
    user = {"openapi": "3.0.3", "info": {"title": "ACME Service Order API", "version": "1.0"},
            "paths": {"/serviceOrder": {"get": {"responses": {"200": {}}}, "post": {"responses": {"201": {}}}}},
            "components": {"schemas": {"ServiceOrder": {"type": "object", "properties": {"id": {"type": "string"}}}}}}
    r = tmf_profile.scaffold_from_canonical(user)
    assert r["detected"]["tmf"] == "TMF641", r["detected"]
    assert r["coverage_after"] > r["coverage_before"], (r["coverage_before"], r["coverage_after"])
    assert len(r["added"]["operations"]) > 0 and len(r["added"]["fields"]) > 0, r["added"]
    out = r["spec"]
    assert "definitions" not in out                      # normalised to the user's OAS3 convention
    refs = []

    def _walk(n):
        if isinstance(n, dict):
            if isinstance(n.get("$ref"), str):
                refs.append(n["$ref"])
            for v in n.values():
                _walk(v)
        elif isinstance(n, list):
            for v in n:
                _walk(v)

    def _resolves(rf):
        if not rf.startswith("#/"):
            return True
        node = out
        for p in rf.lstrip("#/").split("/"):
            node = node.get(p) if isinstance(node, dict) else None
            if node is None:
                return False
        return True

    _walk(out)
    assert all(_resolves(x) for x in refs), [x for x in refs if not _resolves(x)]   # no dangling refs
    conformance.check_spec(out)                          # merged spec still scores without crashing


# ── ODA Component conformance ─────────────────────────────────────────────────
def test_oda_component_parse():
    import oda
    manifest = """
apiVersion: oda.tmforum.org/v1
kind: Component
metadata:
  name: test-comp
spec:
  name: test-comp
  coreFunction:
    exposedAPIs:
    - name: productinventory
      apiType: openapi
      specification:
      - url: https://x/TMF637-ProductInventory-v4.0.0.swagger.json
    dependentAPIs:
    - name: party
      apiType: openapi
      specification:
      - url: https://x/TMF632-Party-v4.0.0.swagger.json
  securityFunction:
    exposedAPIs:
    - name: partyrole
      apiType: openapi
      specification:
      - url: https://x/TMF669-PartyRole-v4.0.0.swagger.json
"""
    r = oda.check_component(manifest)
    assert r["component"] == "test-comp", r
    ex = r["exposed"]
    assert any(e["tmf"] == "TMF637" and e["segment"] == "coreFunction" for e in ex), ex
    assert any(e["tmf"] == "TMF669" and e["segment"] == "securityFunction" for e in ex), ex
    assert any(d["tmf"] == "TMF632" for d in r["dependent"]), r["dependent"]
    assert "ODA Component conformance" in oda.render_markdown(r)


def test_spec_facts_required_fields():
    """The deterministic answerer must read required fields straight from the spec —
    locking in the fix for the RAG chat that hallucinated 'productOffering' as required
    and mislabeled 'id' on the wrong schema."""
    import spec_facts, tmf_profile
    tmf_profile.build_index()
    r = spec_facts.answer("What mandatory fields does TMF622 Product Order require?")
    assert r, "should answer deterministically"
    a = r["answer"]
    assert "productOrderItem" in a                 # the real required field
    assert "action" in a and "id" in a             # the item's real required fields (expanded)
    assert "productOffering" not in a              # the original LLM hallucination must not appear
    assert r["tmf"] == "TMF622"
    # A different API resolves independently and correctly.
    s = spec_facts.answer("required fields for TMF641 service order")
    assert s and "serviceOrderItem" in s["answer"]
    # Conceptual questions are NOT owned here — they defer to the LLM.
    assert spec_facts.answer("what is TMF622 used for") is None
    assert spec_facts.answer("how does pagination work") is None


def test_spec_facts_oda_component():
    """ODA 'which component handles X' must be answered from OFFICIAL DATA only — the
    component list + each component's declared TMF APIs + canonical spec titles. No
    synonym tables, no invented names (the 'Trouble Ticket Management System /
    Customer Journey Management' hallucination)."""
    import re, spec_facts, tmf_profile
    tmf_profile.build_index()
    assert not hasattr(spec_facts, "_ODA_CONCEPT")          # the hardcoded synonym map is gone

    # 'trouble tickets' resolves via the canonical TMF621 title, and reports what the
    # official map actually says: nobody exposes it; TMFC050 depends on it.
    r = spec_facts.answer("Which ODA component handles trouble tickets?")
    assert r, "should answer deterministically"
    a = r["answer"]
    assert "TMF621" in a
    assert "no component exposes" in a.lower()
    assert "TMFC050" in a                                    # dependent per official spec
    assert "Trouble Ticket Management System" not in a       # fabricated name must not appear
    assert "Customer Journey Management" not in a            # fabricated domain must not appear

    # API-title path: alarms → TMF642 → its real exposers include Fault Management.
    r2 = spec_facts.answer("which component handles alarms?")
    assert r2 and "TMF642" in r2["answer"] and "TMFC043" in r2["answer"]

    # Name path still exact.
    r3 = spec_facts.answer("what ODA component is responsible for product catalog?")
    assert r3 and "TMFC001" in r3["answer"]

    # Nonsense must refuse — and may only ever mention codes from the real catalog.
    n = spec_facts.answer("which ODA component handles quantum teleportation?")
    assert n and "won't guess" in n["answer"].lower()
    import oda
    real = {c["code"] for c in oda.catalog()["components"]}
    assert set(re.findall(r"TMFC\d{3}", n["answer"])) <= real

    # The LLM fallback grounding pins the model to the real list.
    g = spec_facts.oda_grounding("tell me about ODA components for billing")
    assert "TMFC001" in g and "Never invent" in g
    assert spec_facts.oda_grounding("how does pagination work") == ""


def test_oda_catalog():
    import oda
    c = oda.catalog()
    codes = [x["code"] for x in c["components"]]
    assert len(codes) == 35 and len(set(codes)) == 35, len(codes)          # full official map, no dupes
    assert set(x["block"] for x in c["components"]) <= set(c["blocks"])    # every block labelled
    assert all(x["spec_url"].startswith("https://") for x in c["components"])
    # Every component now carries its official exposed-API list (from TM Forum's specs).
    enriched = [x for x in c["components"] if x.get("exposed")]
    assert len(enriched) == 35, f"only {len(enriched)}/35 enriched from official data"
    tmfc043 = next(x for x in c["components"] if x["code"] == "TMFC043")
    assert {"TMF642", "TMF656"} <= {a["tmf"] for a in tmfc043["exposed"]}


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
