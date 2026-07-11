"""
Phase 7E tests — authority model, availability, relationship semantics (incl. the ODA
dependency-direction invariant), claim/evidence contracts, constraint precision, and the
governance orchestrator's decisions. Also pins the DEFAULT-PROCEED guarantee that protects
Phase 7C entity-scoped correctness. Pure & offline (no Ollama, no ChromaDB writes).

Run:  venv/bin/python test_authority_engine.py   (or pytest)
"""
import knowledge_authority as A
import knowledge_relationships as Rl
import knowledge_claims as Cl
import knowledge_governance as G
import knowledge_router as R

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print(f"FAIL  {name}")

def decide(q):
    """Router-first, then governance — exactly as the pipeline does."""
    kdec = R.route(q)
    if kdec.get("kind") in ("answer", "abstain"):
        return {"action": kdec["kind"], "answer": kdec.get("answer", ""), "via": "router"}
    g = G.govern(q, kdec); g["via"] = "gov"; return g

# ── Authority model + semantics ─────────────────────────────────────────────────────────
ok(len(list(A.Authority)) == 10, "10 authority classes (closed set)")
ok(A.Authority.OPENAPI_SCHEMA in A.AUTHORITATIVE_FOR, "OPENAPI_SCHEMA has semantics")
ok("SID ABE definitions" in A.NOT_AUTHORITATIVE_FOR[A.Authority.OPENAPI_SCHEMA],
   "OpenAPI schema is NOT authoritative for SID ABEs")
ok("runtime invocation by every operation" in A.NOT_AUTHORITATIVE_FOR[A.Authority.ODA_COMPONENT_CONTRACT],
   "ODA contract is NOT authoritative for runtime-by-every-operation")

# ── Availability inventory (deterministic, reflects Phase 7D reality) ────────────────────
ok(A.is_present(A.Authority.OPENAPI_SCHEMA), "OpenAPI schema AVAILABLE")
ok(A.is_present(A.Authority.ODA_COMPONENT_CONTRACT), "ODA contract AVAILABLE")
ok(not A.is_present(A.Authority.SID_INFORMATION_FRAMEWORK), "SID UNAVAILABLE (7D)")
ok(not A.is_present(A.Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK), "eTOM UNAVAILABLE (7D)")
ok(not A.is_present(A.Authority.TMF_DESIGN_GUIDANCE), "TMF design guidance UNAVAILABLE (not tmf_guidance/Canvas)")
ok(A.authority_available(A.Authority.EXPLICIT_INTEGRATION_EVIDENCE) is A.Availability.CONDITIONAL,
   "explicit integration evidence is CONDITIONAL")
ok(A.inventory_report()["SID_INFORMATION_FRAMEWORK"] == "UNAVAILABLE", "inventory_report serialises")

# ── resolve_required_authority (Task 3 examples) ────────────────────────────────────────
import knowledge_entities as E
def ra(q): return A.resolve_required_authority(q, E.extract_entities(q), "")
ok(ra("What is the SID ABE for customer data?")["required_authority"] is A.Authority.SID_INFORMATION_FRAMEWORK,
   "SID question → SID authority")
ok(ra("Does TMF629 define the Customer ABE?")["required_authority"] is A.Authority.SID_INFORMATION_FRAMEWORK,
   "SID question naming an Open API id still → SID authority (not TMF629)")
ok(ra("How should pagination work in TM Forum Open APIs?")["required_authority"] is A.Authority.TMF_DESIGN_GUIDANCE,
   "global pagination → design guidance")
ok(ra("How should pagination work in TM Forum Open APIs?")["scope"] is A.Scope.GLOBAL, "global scope")
ok(ra("What business process covers order capture?")["required_authority"] is A.Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK,
   "business process → eTOM")
ok(ra("What operations exist in TMF669 v4?")["allow_fallback"] is True,
   "entity-scoped operations question allows RAG fallback")
ok(ra("What is the SID ABE for customer data?")["allow_fallback"] is False,
   "framework-authority question forbids lower-authority fallback")

# ── Relationship intent classification (Task 6) ─────────────────────────────────────────
RI = Rl.RelationshipIntent
ok(Rl.classify_relationship_intent("Does TMF621 call TMF624?") is RI.RUNTIME_CALL_INTENT, "call → RUNTIME")
ok(Rl.classify_relationship_intent("Does TMF621 orchestrate other APIs?") is RI.INTEGRATION_INTENT, "orchestrate → INTEGRATION")
ok(Rl.classify_relationship_intent("Which APIs does TMF621 depend on?") is RI.DEPENDENCY_INTENT, "depend → DEPENDENCY")
ok(Rl.classify_relationship_intent("Which ODA components expose TMF621?") is RI.EXPOSURE_INTENT, "expose+components → EXPOSURE")
ok(Rl.classify_relationship_intent("How does TMF621 interact with other APIs?") is RI.AMBIGUOUS_INTERACTION_INTENT,
   "interact with other APIs → AMBIGUOUS (never generic RAG)")
ok(Rl.classify_relationship_intent("What does relatedEntity represent?") is RI.ENTITY_ASSOCIATION_INTENT, "relatedEntity → ASSOCIATION")

# ── Structural evidence + the DIRECTION INVARIANT (Task 5/7) ─────────────────────────────
ok([r["code"] for r in Rl.components_depending_on("TMF621")] == ["TMFC050"], "TMFC050 depends on TMF621")
ok(Rl.components_exposing("TMF621") == [], "no component exposes TMF621")
ok("TMFC043" in [r["code"] for r in Rl.components_exposing("TMF642")], "TMF642 exposed by TMFC043")
_rel = Rl.oda_relationships_for_component("TMFC050")
ok(_rel["status"] == "RESOLVED" and any(d["id"] == "TMF621" for d in _rel["dependent"]),
   "TMFC050 contract lists TMF621 as dependent (component→API)")

# ── Claim classification + evidence contracts (Task 8) ──────────────────────────────────
CT = Cl.ClaimType
ok(Cl.classify_claim("Is ProductOrder.id a UUID?", E.extract_entities("Is ProductOrder.id a UUID?")) is CT.PROPERTY_FORMAT_CLAIM,
   "UUID question → PROPERTY_FORMAT_CLAIM")
ok(Cl.classify_claim("What is the SID ABE?", {}) is CT.SID_FRAMEWORK_CLAIM, "SID → SID_FRAMEWORK_CLAIM")
ok(Cl.required_authority_for_claim(CT.API_DEPENDENCY_CLAIM) is A.Authority.ODA_COMPONENT_CONTRACT,
   "dependency claim requires ODA contract")
ok(Cl.required_authority_for_claim(CT.RUNTIME_CALL_CLAIM) is A.Authority.EXPLICIT_INTEGRATION_EVIDENCE,
   "runtime-call claim requires explicit integration evidence")
ok("NOT sufficient" in Cl.ACCEPTABLE_EVIDENCE[CT.PROPERTY_FORMAT_CLAIM], "format: type:string NOT sufficient (documented)")

# ── Constraint precision (Task 9): absent constraints are never invented ─────────────────
cp = Cl.constraint_precision("Is ProductOrder.id a UUID in TMF622 v4?", E.extract_entities("Is ProductOrder.id a UUID in TMF622 v4?"))
ok(cp.get("resolved") and cp["property"].lower() == "id", "ProductOrder.id resolved from canonical schema")
ok(cp.get("resolved") and cp["satisfied"].get("format") is False, "ProductOrder.id has NO explicit format (not UUID)")
for adv in ["Does Alarm.id in TMF642 v4 follow a UUID format?",
            "Does TMF622 v4 define a regex pattern for id?",
            "What is the enum of valid values for ProductOrder.id in TMF622 v4?"]:
    _cp = Cl.constraint_precision(adv, E.extract_entities(adv))
    if _cp.get("resolved"):
        ok(not all(_cp["satisfied"].values()), f"absent-constraint not fabricated: {adv[:40]}")

# ── Governance decisions (the Phase 7D failure classes → correct action) ─────────────────
ok(decide("What is the SID ABE for customer data?")["action"] == "abstain", "SID ABE → abstain")
ok(decide("Does TMF629 define the Customer ABE in the SID?")["action"] == "abstain", "TMF629-as-SID → abstain")
ok(decide("What eTOM process handles trouble tickets?")["action"] == "abstain", "eTOM → abstain")
ok(decide("How do I handle pagination in TM Forum Open APIs?")["action"] == "abstain", "global pagination → abstain/scope")
ok(decide("Do all TM Forum APIs use limit and offset?")["action"] == "abstain", "global generalization → abstain")
ok(decide("Which ODA components depend on TMF621?")["action"] == "answer", "reverse dependency → deterministic answer")
ok(decide("Which ODA components expose TMF621?")["action"] == "answer", "reverse exposure (none) → deterministic answer")
ok(decide("Is a mandatory API the same as a dependent API in ODA?")["action"] == "answer", "mandatory≠dependent → answer")
ok(decide("Does relatedEntity mean TMF621 calls the related entity's API?")["action"] == "answer", "relatedEntity→call → refuse")
ok(decide("How does Trouble Ticket Open API interact with other APIs?")["action"] == "answer", "ambiguous interaction → structured answer")

# Direction is preserved and never inverted in the deterministic text.
_inv = decide("Does TMFC050 depending on TMF621 mean TMF621 relies on Product Recommendation?")
ok(_inv["action"] == "answer", "direction-inversion bait → deterministic answer")
ok("tmf621 relies on product recommendation" not in _inv["answer"].lower(), "never affirms inverted direction")
_rev = decide("Which ODA components depend on TMF621?")
ok("component → api" in _rev["answer"].lower() or "component → tmf621" in _rev["answer"].lower(),
   "reverse-dependency answer states component→API direction")

# Deterministic answers must not embed the false-claim trigger phrasing.
def _ans(q): return decide(q).get("answer", "").lower()
ok("0-based" not in _ans("Are offsets zero-based in TM Forum APIs?"), "global refusal avoids '0-based' phrasing")
ok("uuid" not in _ans("Is ProductOrder.id a UUID in TMF622 v4?"), "constraint-absent answer avoids 'uuid' phrasing")
ok(not _ans("Does TMF621 call TMF624?").startswith("yes"), "runtime refusal never opens with yes")

# ── DEFAULT-PROCEED guarantee — Phase 7C entity-scoped questions untouched ───────────────
for q in ["What operations exist in TMF669 v4?",
          "How does pagination work in TMF622 v4?",
          "Does TMF642 v4 define a limit query parameter?",
          "What are the mandatory attributes of an Alarm in TMF642 v4?",
          "Is ProductOrder.id required in TMF622 v4?",
          "How does TMF669 relate to TMFC043?",
          "Which ODA component owns fault management?"]:
    d = decide(q)
    ok(d["action"] in ("proceed", "answer") and d.get("via") in ("gov", "router"),
       f"7C-preserved (not abstained/refused): {q[:44]}")
# The ones above that reach governance must PROCEED (RAG), not be intercepted.
for q in ["What operations exist in TMF669 v4?", "How does pagination work in TMF622 v4?",
          "Does TMF642 v4 define a limit query parameter?"]:
    ok(decide(q)["action"] == "proceed", f"governance PROCEEDs on entity-scoped: {q[:40]}")

print(f"\ntest_authority_engine: {passed} passed, {failed} failed")
if failed:
    import sys; sys.exit(1)
