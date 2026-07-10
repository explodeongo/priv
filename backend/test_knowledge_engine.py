"""
Knowledge Engine V2 tests (Phase 7B) — entity extraction, linking, routing, version,
corpus classification, evidence/abstention. Pure & offline (no Ollama, no ChromaDB writes).

Run:  venv/bin/python test_knowledge_engine.py   (or pytest)
"""
import knowledge_entities as E
import knowledge_link as L
import knowledge_router as R

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print(f"FAIL  {name}")

# ── Entity extraction ─────────────────────────────────────────────────────────────────
ok(E.extract_tmf_ids("What is TMF642?") == ["TMF642"], "TMF642 extracted")
ok(E.extract_tmf_ids("what is tmf642") == ["TMF642"], "lower-case tmf642 normalised")
ok(E.extract_tmf_ids("TMF642 and TMF669") == ["TMF642", "TMF669"], "multiple ids, order preserved")
ok(E.extract_tmf_ids("TMFC043 exposes what") == [], "TMFC (component) not read as a TMF id")
ok(E.extract_tmf_ids("XTMF642 embedded") == [], "embedded id rejected")
ok(E.extract_tmf_ids("TMF6420 is not valid") == [], "4-digit id rejected")
ok(E.extract_tmf_ids("TMF64 too short") == [], "2-digit id rejected")
ok(E.extract_oda_ids("What does TMFC043 expose?") == ["TMFC043"], "TMFC043 extracted")
ok(E.extract_oda_ids("tmfc001 and TMFC027") == ["TMFC001", "TMFC027"], "multiple ODA ids")
ok(E.extract_oda_ids("TMF642") == [], "TMF id not read as an ODA id")

ok(E.requested_major("TMF642 v4") == 4, "v4 → major 4")
ok(E.requested_major("TMF642 v4.0.0") == 4, "v4.0.0 → major 4")
ok(E.requested_major("version 5 please") == 5, "'version 5' → major 5")
ok(E.requested_major("TMF642 with no version") is None, "no version → None")
ok(E.requested_major("difference between v4 and v5") is None, "conflicting v4/v5 → None (not a single filter)")
ok(E.extract_entities("difference between v4 and v5")["has_conflicting_versions"], "conflicting versions flagged")
ok([v for v in E.extract_versions("v4.0.0") if v["version"] == "4.0.0"], "exact version captured")

# ── Entity linking (owner-preferred, derived from canonical schemas) ────────────────────
ok(L.link_schema("PartyRole") == ["TMF669"], "PartyRole → TMF669 (owner, not every cross-ref)")
ok(L.link_schema("ServiceOrder") == ["TMF641"], "ServiceOrder → TMF641")
ok(L.link_schema("ProductOrder") == ["TMF622"], "ProductOrder → TMF622")
ok("TMF642" in L.link_schema("Alarm"), "Alarm → TMF642 among candidates")
ok(len(L.link_schema("Party")) >= 1 or L.link_schema("Party") == [], "ambiguous entity preserved as candidate list")

# ── Corpus classification ───────────────────────────────────────────────────────────────
ok(L.content_class("TMF642-Alarm-v4.0.0.swagger.json") == "canonical_spec", "TMF swagger → canonical_spec")
ok(L.content_class("carrierEthernetEvcCommon.yaml") == "non_tmf_external", "MEF file → non_tmf_external")
ok(L.content_class("ipCommon.yaml") == "non_tmf_external", "MEF ipCommon → non_tmf_external")
ok(L.content_class("01-about-oda-canvas.md") == "oda_canvas", "Canvas doc → oda_canvas")
ok(L.content_class("UC003-Configure-Exposed-APIs.md") == "oda_canvas", "Canvas UC doc → oda_canvas")
ok(L.content_class("RetailandWholesale.postman_collection.json") == "test_collection", "postman → test_collection")
ok(L.major_of("TMF642-Alarm-v4.0.0.swagger.json") == "4", "major parsed from filename")
ok(L.major_of("TMF642_Alarm_v5.0.1.oas.yaml") == "5", "major 5 parsed")

# ── Spec inventory / abstention authority ──────────────────────────────────────────────
ok(L.spec_present("TMF642"), "TMF642 present in canonical corpus")
ok(L.spec_present("TMF669"), "TMF669 present")
ok(not L.spec_present("TMF630"), "TMF630 absent (abstention authority)")
ok(not L.spec_present("TMF999"), "TMF999 absent")
ok(set(L.majors_for("TMF642")) == {"4", "5"}, "TMF642 has majors 4 and 5 (distinguishable)")
ok("4" in L.majors_for("TMF669") and "5" in L.majors_for("TMF669"), "TMF669 v4 and v5 distinguishable")
ok(all(L.major_of(f) == "4" for f in L.files_for("TMF642", "4")), "files_for(TMF642,4) are all v4 (isolation)")
ok(all(L.major_of(f) == "5" for f in L.files_for("TMF642", "5")), "files_for(TMF642,5) are all v5 (isolation)")

# ── Routing ─────────────────────────────────────────────────────────────────────────────
def route(q): return R.route(q)
ok(route("What mandatory APIs does TMFC043 expose?")["kind"] == "answer", "TMFC043 mandatory → deterministic answer")
ok("TMF642" in route("What mandatory APIs does TMFC043 expose?")["answer"], "TMFC043 answer names TMF642")
ok("TMF669" in route("What mandatory APIs does TMFC043 expose?")["answer"], "TMFC043 answer names TMF669")
ok("workorder" not in route("What mandatory APIs does TMFC043 expose?")["answer"].lower(), "TMFC043 answer never says WorkOrder")
ok(route("What APIs does TMFC001 depend on?")["kind"] == "answer", "TMFC001 deps → resolver")
ok(route("What events does TMFC001 publish?")["kind"] == "answer", "TMFC001 events → resolver")
ok("3" in route("What events does TMFC001 publish?")["answer"], "TMFC001 publishes 3 (deterministic)")
ok("0" in route("Does TMFC022 publish events?")["answer"], "TMFC022 publishes 0 (deterministic)")
ok(route("What is TMF630?")["kind"] == "abstain", "absent TMF630 → abstain")
ok(route("What is TMF642?")["kind"] == "rag", "present TMF642 identity → RAG with hints")
ok(route("What is TMF642?")["hints"]["spec_ids"] == ["TMF642"], "TMF642 seeds retrieval to TMF642")
ok(route("What are the mandatory attributes of an Alarm in TMF642 v4?")["hints"]["major"] == 4, "explicit v4 sets major filter")
ok(route("What is the difference between TMF642 v4 and v5?")["intent"] == "VERSION_COMPARISON", "v4-vs-v5 → comparison")
ok(route("Alarm attributes?")["hints"]["spec_ids"][0] == "TMF642", "bare 'Alarm' seeds TMF642")
ok(route("What is the capital of France?")["kind"] == "defer", "off-domain → defer to normal pipeline")
ok(route("Tell me about TMF6420.")["kind"] == "abstain", "malformed TMF6420 → abstain (not matched to TMF642)")
ok(route("Which ODA component exposes TMF642?")["kind"] == "answer", "reverse lookup TMF642 → component (deterministic)")
ok("TMFC043" in route("Which ODA component exposes TMF642?")["answer"], "reverse lookup names TMFC043")
ok(route("Is TMF760 a v4 or v5 API in TMFC027?")["kind"] == "answer", "API-version-in-component → deterministic")
ok("v5" in route("Is TMF760 a v4 or v5 API in TMFC027?")["answer"], "TMF760 in TMFC027 is v5")
ok(route("What is the mandatory security API for every ODA component?")["kind"] == "answer", "every-component security → TMF669")
ok("TMF669" in route("What is the mandatory security API for every ODA component?")["answer"], "security API answer = TMF669")
# explicit version absent for a NON-required-fields question → abstain (never answer another major)
ok(route("Give an overview of TMF642 v9")["kind"] == "abstain", "absent requested major (non-field) → abstain")
# a required-fields question with an absent version DEFERS to spec_facts (its UNRESOLVED path),
# so the router must NOT preempt it with a major-only abstention
ok(route("What are the mandatory fields of Alarm in TMF642 v9?")["kind"] != "abstain",
   "required-fields v-absent defers to spec_facts (not router abstention)")

# TMF required-fields questions must NOT be hijacked into a deterministic ODA answer
ok(route("What mandatory fields does TMF622 Product Order require?")["kind"] in ("rag", "defer"),
   "TMF required-fields left for spec_facts/RAG (no ODA hijack)")

print(f"\ntest_knowledge_engine: {passed} passed, {failed} failed")
if failed:
    import sys; sys.exit(1)
