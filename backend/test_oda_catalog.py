"""
ODA Component Catalog derived-status tests (Phase 6A — product/UI, NOT execution).

Locks the honesty rules for the catalog's derived availability flags produced by
oda.component_status() and surfaced by GET /oda/components:
  • supported_execution comes from the AUTHORITATIVE adapter gate (SUPPORTED_COMPONENTS),
    never a second hardcoded copy;
  • contract_available comes from the vendored canonical specs (canonical_path);
  • specification_available reflects a known canonical spec location.
It also proves the enrichment does NOT touch the verdict engine / adapter / jobs and does
not mutate the cached catalog.

Pure & offline. Run either way:
    python test_oda_catalog.py
    pytest test_oda_catalog.py
"""
import oda
import oda_component_contract as CONTRACT
import oda_ctk_jobs  # noqa: F401  (its adapter holds the authoritative SUPPORTED_COMPONENTS)

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL  {name}")


SUPPORTED = oda_ctk_jobs.oda_ctk_adapter.SUPPORTED_COMPONENTS

# ── component_status: derivation, never hardcoded ─────────────────────────────────────
s43 = oda.component_status({"code": "TMFC043", "spec_url": "http://x/TMFC043.yaml"}, SUPPORTED)
ok(s43["supported_execution"] is True, "TMFC043 supported_execution True (from authoritative gate)")
ok(s43["contract_available"] is True, "TMFC043 contract_available True (vendored canonical spec)")
ok(s43["specification_available"] is True, "TMFC043 specification_available True")

s01 = oda.component_status({"code": "TMFC001", "spec_url": "http://x/TMFC001.yaml"}, SUPPORTED)
ok(s01["supported_execution"] is False, "TMFC001 NOT execution-supported (honest)")
ok(s01["contract_available"] is True, "TMFC001 now has a vendored contract (Phase 6B corpus) yet stays NON-execution — Contract Available != Execution Ready")
ok(s01["specification_available"] is True, "TMFC001 spec available (spec_url known)")

# supported_execution must reflect the PASSED-IN set — proving it is not hardcoded to TMFC043.
alt = oda.component_status({"code": "TMFC001", "spec_url": "http://x"}, {"TMFC001"})
ok(alt["supported_execution"] is True, "supported_execution follows the passed set, not a hardcoded id")
none_set = oda.component_status({"code": "TMFC043", "spec_url": "http://x"}, set())
ok(none_set["supported_execution"] is False, "empty supported set -> no execution support")
ok(none_set["contract_available"] is True, "contract_available independent of the execution set")

# contract_available strictly mirrors canonical_path (deterministic filesystem resolution).
ok(CONTRACT.canonical_path("TMFC043") is not None, "canonical_path resolves the vendored TMFC043 spec")
ok(CONTRACT.canonical_path("TMFC001") is not None, "canonical_path resolves the now-vendored TMFC001 spec (Phase 6B)")
ok(CONTRACT.canonical_path("TMFC999") is None, "canonical_path returns None for a truly non-vendored component id")
unknown = oda.component_status({"code": "TMFC999", "spec_url": "http://x"}, SUPPORTED)
ok(unknown["contract_available"] is False and unknown["supported_execution"] is False,
   "unknown component: no contract, no execution")

# Case-insensitive id handling.
lower = oda.component_status({"code": "tmfc043", "spec_url": "http://x"}, SUPPORTED)
ok(lower["supported_execution"] is True and lower["contract_available"] is True,
   "component code is matched case-insensitively")

# specification_available true when a contract is vendored even if spec_url is absent;
# and honestly false when neither a spec_url nor a vendored contract exists.
ok(oda.component_status({"code": "TMFC043"}, SUPPORTED)["specification_available"] is True,
   "spec available via vendored contract even without spec_url")
bare = oda.component_status({"code": "TMFC999"}, SUPPORTED)
ok(bare["specification_available"] is False, "no spec_url + no contract -> specification_available False")

# ── Endpoint-shape composition (same as GET /oda/components) ───────────────────────────
cat = oda.catalog()
comps = [{**c, **oda.component_status(c, SUPPORTED)} for c in cat["components"]]
ok(len(comps) == 35, "catalog exposes all 35 ODA components")
ok(all("code" in c and "name" in c and "block" in c for c in comps), "existing catalog fields preserved (backward compatible)")
ok(all({"supported_execution", "contract_available", "specification_available"} <= set(c) for c in comps),
   "every component carries the three derived flags")
exec_ready = sorted(c["code"] for c in comps if c["supported_execution"])
contract_ok = sorted(c["code"] for c in comps if c["contract_available"])
ok(exec_ready == sorted(SUPPORTED), "exactly the authoritative supported set is execution-ready")
ok(exec_ready == ["TMFC043"], "execution stays TMFC043-only after Phase 6B (Contract != Execution)")
ok(contract_ok == sorted(c["code"] for c in comps) and len(contract_ok) == 35,
   "Phase 6B: all 35 catalog entries now advertise a vendored contract")
ok(all(c["specification_available"] for c in comps), "all catalog components have a known specification")
# No component ever fabricates execution without also being in the authoritative gate.
ok(not any(c["supported_execution"] and c["code"] not in SUPPORTED for c in comps),
   "no component claims execution support outside the authoritative gate")

# ── Enrichment must not mutate the cached catalog (no side effects on oda._CATALOG) ─────
cached = oda.catalog()["components"][0]
ok("supported_execution" not in cached,
   "enrichment builds fresh dicts; the cached catalog is never mutated")

print(f"\ntest_oda_catalog: {passed} passed, {failed} failed")
if failed:
    import sys
    sys.exit(1)
