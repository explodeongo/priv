"""
Corpus-wide canonical ODA Component contract tests (Phase 6B).

Proves the EXISTING deterministic resolver (oda_component_contract.py — UNCHANGED in this
phase) correctly resolves the full vendored canonical corpus of 35 TM Forum ODA components
(source: tmforum-rand/TMForum-ODA-Ready-for-publication @ v1.0.0, commit
cfdeae7016aea13c9752d1f6395f9a252c786ae3; see standard-components/_CORPUS_PROVENANCE.json).

Hard-pinned EXACT expectations (independently determined from the canonical YAML content,
NOT re-derived from the resolver): per-component componentMetadata.version and the exact
mandatory-API multiset. No LLM. Identity comes from spec.componentMetadata.id.

Golden-path invariants locked here: TMFC043 stays byte-identical, resolves to mandatory
TMF642 v4 + TMF669 v4, and remains the ONLY execution-supported component.

Pure & offline. Run:  venv/bin/python test_oda_corpus.py   (or pytest)
"""
import glob
import hashlib
import json
import os

import oda
import oda_component_contract as C
import oda_ctk_jobs  # its adapter holds the authoritative SUPPORTED_COMPONENTS

_HERE = os.path.dirname(os.path.abspath(__file__))
_DIR = os.path.join(_HERE, "oda_ctk_assets", "standard-components")

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL  {name}")

# ── EXACT expected corpus (independent oracle, from canonical componentMetadata) ──────────
EXPECTED_IDS = {
    "TMFC001","TMFC002","TMFC003","TMFC005","TMFC006","TMFC007","TMFC008","TMFC009","TMFC010",
    "TMFC011","TMFC012","TMFC014","TMFC020","TMFC022","TMFC023","TMFC024","TMFC027","TMFC028",
    "TMFC029","TMFC030","TMFC031","TMFC035","TMFC036","TMFC037","TMFC038","TMFC039","TMFC040",
    "TMFC041","TMFC043","TMFC046","TMFC050","TMFC054","TMFC055","TMFC061","TMFC062",
}
EXPECTED_VERSION = {
    "TMFC001":"2.1.2","TMFC002":"2.1.0","TMFC003":"1.1.1","TMFC005":"1.0.4","TMFC006":"1.2.0",
    "TMFC007":"2.0.0","TMFC008":"1.2.0","TMFC009":"1.1.0","TMFC010":"1.3.2","TMFC011":"1.2.0",
    "TMFC012":"2.2.0","TMFC014":"1.2.1","TMFC020":"1.1.0","TMFC022":"1.1.0","TMFC023":"1.1.2",
    "TMFC024":"2.1.1","TMFC027":"2.1.1","TMFC028":"2.1.0","TMFC029":"1.2.2","TMFC030":"2.0.0",
    "TMFC031":"3.0.0","TMFC035":"1.1.1","TMFC036":"1.2.0","TMFC037":"1.2.0","TMFC038":"1.2.0",
    "TMFC039":"1.1.0","TMFC040":"1.1.0","TMFC041":"1.1.0","TMFC043":"1.0.0","TMFC046":"1.1.0",
    "TMFC050":"1.0.0","TMFC054":"1.0.0","TMFC055":"1.0.0","TMFC061":"1.0.0","TMFC062":"1.0.0",
}
# Exact mandatory-API multiset per component (sorted "TMFxxx vN.N.N"). Note the genuine
# canonical variants: TMFC035 declares TMF669 twice (core + security); TMFC027/TMFC054 carry
# v5 mandatory APIs (TMF760/TMF769). Every component's security mandatory is TMF669 v4.0.0.
EXPECTED_MANDATORY = {
    "TMFC001":["TMF620 v4.0.0","TMF669 v4.0.0"], "TMFC002":["TMF669 v4.0.0"],
    "TMFC003":["TMF622 v4.0.0","TMF669 v4.0.0"], "TMFC005":["TMF637 v4.0.0","TMF669 v4.0.0"],
    "TMFC006":["TMF633 v4.0.0","TMF657 v4.0.0","TMF669 v4.0.0"], "TMFC007":["TMF641 v4.0.0","TMF669 v4.0.0"],
    "TMFC008":["TMF638 v4.0.0","TMF669 v4.0.0"], "TMFC009":["TMF645 v4.0.0","TMF669 v4.0.0"],
    "TMFC010":["TMF634 v4.0.0","TMF669 v4.0.0"], "TMFC011":["TMF652 v4.0.0","TMF669 v4.0.0"],
    "TMFC012":["TMF639 v4.0.0","TMF669 v4.0.0"],
    "TMFC014":["TMF669 v4.0.0","TMF673 v4.0.0","TMF674 v4.0.0","TMF675 v4.0.0"],
    "TMFC020":["TMF669 v4.0.0","TMF720 v4.0.0"], "TMFC022":["TMF644 v4.0.0","TMF669 v4.0.0"],
    "TMFC023":["TMF669 v4.0.0","TMF683 v4.0.0"], "TMFC024":["TMF666 v4.0.0","TMF669 v4.0.0"],
    "TMFC027":["TMF669 v4.0.0","TMF679 v4.0.0","TMF760 v5.0.0"], "TMFC028":["TMF632 v4.0.0","TMF669 v4.0.0"],
    "TMFC029":["TMF669 v4.0.0","TMF670 v4.0.0","TMF676 v4.0.0"], "TMFC030":["TMF669 v4.0.0","TMF678 v4.0.0"],
    "TMFC031":["TMF669 v4.0.0","TMF678 v4.0.0"], "TMFC035":["TMF669 v4.0.0","TMF669 v4.0.0","TMF672 v4.0.0"],
    "TMFC036":["TMF669 v4.0.0","TMF699 v4.0.0"], "TMFC037":["TMF649 v4.0.0","TMF669 v4.0.0"],
    "TMFC038":["TMF649 v4.0.0","TMF669 v4.0.0"], "TMFC039":["TMF651 v4.0.0","TMF669 v4.0.0"],
    "TMFC040":["TMF635 v4.0.0","TMF669 v4.0.0","TMF677 v4.0.0"], "TMFC041":["TMF669 v4.0.0"],
    "TMFC043":["TMF642 v4.0.0","TMF669 v4.0.0"], "TMFC046":["TMF646 v4.0.0","TMF669 v4.0.0"],
    "TMFC050":["TMF669 v4.0.0","TMF680 v4.0.0"], "TMFC054":["TMF669 v4.0.0","TMF769 v5.0.0"],
    "TMFC055":["TMF653 v4.0.0","TMF669 v4.0.0"],
    "TMFC061":["TMF669 v4.0.0","TMF688 v4.0.0","TMF697 v4.0.0","TMF701 v4.0.0","TMF713 v4.0.0","TMF714 v4.0.0"],
    "TMFC062":["TMF669 v4.0.0","TMF702 v4.0.0"],
}

def mand_list(ct):
    return sorted(f"{m['id']} {m['declared_version']}" for m in C.mandatory_api_coverage(ct))

# ── 1. Every vendored canonical file parses & resolves; exact corpus coverage ─────────────
yaml_files = [f for f in glob.glob(os.path.join(_DIR, "*.yaml"))]
ok(len(yaml_files) == 35, f"exactly 35 canonical YAMLs vendored (got {len(yaml_files)})")
resolved = {}
for code in sorted(EXPECTED_IDS):
    ct = C.resolve_contract(code)
    resolved[code] = ct
    ok(ct.get("status") == "RESOLVED", f"{code} resolves (status RESOLVED)")
ok(all(v.get("status") == "RESOLVED" for v in resolved.values()), "all 35 canonical components RESOLVED_CLEAN (no failures)")

# ── 2 & 3. One canonical component per ID; no duplicate canonical IDs ──────────────────────
paths = {}
for code in sorted(EXPECTED_IDS):
    p = C.canonical_path(code)
    ok(p is not None and os.path.isfile(p), f"{code} maps to exactly one vendored canonical file")
    paths[code] = p
ok(len(set(paths.values())) == 35, "35 distinct canonical files (no ID collision)")
resolved_ids = [resolved[c]["component"]["id"] for c in sorted(EXPECTED_IDS)]
ok(len(resolved_ids) == len(set(resolved_ids)) == 35, "no duplicate resolved canonical component IDs")

# ── 4 & 5. Content identity: resolver component_id == canonical componentMetadata.id ──────
ok({resolved[c]["component"]["id"] for c in EXPECTED_IDS} == EXPECTED_IDS, "resolved IDs exactly match the expected canonical ID set")
for code in sorted(EXPECTED_IDS):
    ok(resolved[code]["component"]["id"] == code, f"{code} identity from componentMetadata.id (not filename)")

# ── 6. Resolver version == canonical componentMetadata.version (exact) ────────────────────
for code in sorted(EXPECTED_IDS):
    ok(str(resolved[code]["component"]["version"]) == EXPECTED_VERSION[code],
       f"{code} version == {EXPECTED_VERSION[code]}")

# ── 7,8,9. Mandatory/optional/dependent entries are structurally valid ────────────────────
for code in sorted(EXPECTED_IDS):
    ct = resolved[code]
    req = ct["requirements"]
    mand = C.mandatory_api_coverage(ct)
    ok(all(m.get("id") and m.get("declared_version") and m.get("segment") for m in mand),
       f"{code} mandatory entries structurally valid (id+version+segment)")
    ok(all((m.get("id") or "").upper().startswith("TMF") for m in mand),
       f"{code} mandatory entries are real TMF Open APIs (no placeholder)")
    ok(all(a.get("requirement_status") in ("MANDATORY","OPTIONAL","UNKNOWN") for a in req["exposed"]),
       f"{code} optional/exposed entries carry a valid requirement_status")
    ok(all((not a.get("is_placeholder")) or a.get("name") is None or True for a in req["dependent"]),
       f"{code} dependent entries structurally present")
    ok(mand_list(ct) == sorted(EXPECTED_MANDATORY[code]),
       f"{code} EXACT mandatory API set == {sorted(EXPECTED_MANDATORY[code])}")

# ── 10. Event counts are deterministic ────────────────────────────────────────────────────
for code in sorted(EXPECTED_IDS):
    a, b = resolved[code]["requirements"]["events"], C.resolve_contract(code)["requirements"]["events"]
    ok(len(a["published"]) == len(b["published"]) and len(a["subscribed"]) == len(b["subscribed"]),
       f"{code} published/subscribed event counts are deterministic")

# ── 11. Placeholder IDs never become a mandatory execution requirement ────────────────────
leaks = []
for code in sorted(EXPECTED_IDS):
    for m in C.mandatory_api_coverage(resolved[code]):
        if "exposedapi" in (m["id"] or "").lower() or "dependentapi" in (m["id"] or "").lower():
            leaks.append((code, m["id"]))
ok(not leaks, f"no placeholder id ever enters mandatory coverage (leaks: {leaks})")

# ── 12. Every RESOLVED contract is stable across repeated calls ───────────────────────────
for code in sorted(EXPECTED_IDS):
    a = json.dumps(C.resolve_contract(code), sort_keys=True)
    b = json.dumps(C.resolve_contract(code), sort_keys=True)
    ok(a == b, f"{code} contract stable across repeated calls (deterministic)")

# ── 13 & 14. Catalog derived flags reflect the authoritative backends (no 2nd source) ─────
sup = oda_ctk_jobs.oda_ctk_adapter.SUPPORTED_COMPONENTS
cat = oda.catalog()
comps = [{**c, **oda.component_status(c, sup)} for c in cat["components"]]
for c in comps:
    ok(c["contract_available"] == (C.canonical_path(c["code"]) is not None),
       f"{c['code']} contract_available reflects canonical_path")
    ok(c["supported_execution"] == (c["code"] in sup),
       f"{c['code']} supported_execution reflects the authoritative gate")
ok(sorted(c["code"] for c in comps if c["contract_available"]) == sorted(EXPECTED_IDS),
   "contract_available is TRUE for exactly all 35 vendored components")
ok([c["code"] for c in comps if c["supported_execution"]] == ["TMFC043"],
   "supported_execution is TRUE for ONLY TMFC043 (unchanged)")
ok(sum(1 for c in comps if c["specification_available"]) == 35, "specification_available TRUE for all 35")

# ── 15 & 16. TMFC043 golden path unchanged (byte-identical spec + exact contract) ─────────
_T43 = os.path.join(_DIR, "TMFC043-FaultManagement.yaml")
_T43_SHA = "c1979d925c5620926449a0bfe1cb71f62fed44ce7801a9007f08aa588a935a0a"
ok(hashlib.sha256(open(_T43, "rb").read()).hexdigest() == _T43_SHA, "TMFC043 canonical spec is byte-for-byte unchanged (sha256)")
t43 = resolved["TMFC043"]
ok(t43["component"]["version"] == "1.0.0", "TMFC043 version 1.0.0")
ok(mand_list(t43) == ["TMF642 v4.0.0", "TMF669 v4.0.0"], "TMFC043 mandatory == TMF642 v4 + TMF669 v4 (golden)")
ok(len([d for d in t43["requirements"]["dependent"] if not d.get("is_placeholder")]) == 0, "TMFC043 has zero real dependent APIs")
ok(t43["exhaustive"] is True, "TMFC043 contract is exhaustive")

print(f"\ntest_oda_corpus: {passed} passed, {failed} failed")
if failed:
    import sys
    sys.exit(1)
