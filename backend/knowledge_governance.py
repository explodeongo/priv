"""
Knowledge Engine V2 — authority + relationship governance orchestrator (Phase 7E)
════════════════════════════════════════════════════════════════════════════════
The single deterministic gate that composes knowledge_authority + knowledge_relationships
+ knowledge_claims into ONE decision for a question, so /query and /query/stream can never
diverge. It runs AFTER knowledge_router (which already answers/abstains for named ODA
components and absent specs) and BEFORE the spec_facts governance route and general RAG.

Posture: DEFAULT-PROCEED. It intervenes ONLY on the question shapes Phase 7D proved
defective — framework-authority substitution (SID/eTOM), global-normative generalization,
relationship-type promotion (schema-ref/association → dependency/runtime/integration), ODA
dependency-direction inversion, and constraint speculation — leaving every entity-scoped API
fact (the Phase 7C-correct path) untouched. Returns:

  action: "answer"   — a deterministic answer (return as-is)
          "abstain"  — honest evidence-absence (return as-is)
          "constrain"— proceed to RAG, but with a generation guard + confidence cap
          "proceed"  — nothing to add; normal pipeline

Pure & offline. No Ollama, no ChromaDB, no network.
"""
from __future__ import annotations
import re

import knowledge_entities as E
import knowledge_link as L
import knowledge_authority as A
import knowledge_relationships as Rl
import knowledge_claims as Cl

_CONCEPT = re.compile(r"\bwhat\s+is\s+the\s+difference\b|\bdifference\s+between\b|"
                      r"\bwhat\s+evidence\s+is\s+required\b|\bwhat.?s?\s+required\s+to\s+claim\b|"
                      r"\bhow\s+do\s+you\s+prove\b", re.I)


def _oda_source(reason: str) -> list:
    return [{"name": "Canonical ODA Component specifications", "file": "oda_ctk_assets/standard-components",
             "chunk": 0, "preview": reason, "url": "", "upload": False,
             "origin_type": "", "domain": "ODA", "content_class": "oda_component_spec"}]


def _subject_spec(entities: dict, khints: dict) -> str:
    """The TMF spec the relationship question is about — from a named id, else the router's
    linked spec hint (so 'Trouble Ticket Open API' resolves to TMF621 the way the router did)."""
    tmf = entities.get("tmf_ids") or []
    if tmf:
        return tmf[0]
    for key in ("evidence_specs", "spec_ids"):
        v = (khints or {}).get(key)
        if v:
            return v[0]
    return ""


# ── Deterministic answer bodies (worded to state the narrowest proven relationship, and to
#    avoid quoting the very false-claim phrasing they refute) ─────────────────────────────
def _global_refusal(topic_hint: str) -> str:
    ex = topic_hint or "that behaviour"
    return (
        "I can't state that as a TM-Forum-wide rule. SynaptDI has the individual Open API "
        "specifications indexed, but it does **not** have a normative TM Forum REST design "
        "guideline (the cross-API authority, e.g. TMF630) in the corpus — and a rule that holds "
        "across the entire TM Forum portfolio can only come from that normative guidance, not "
        "from generalising a handful of per-API specs.\n\n"
        f"What I can answer reliably is the **scoped** version: how {ex} works in a *specific* API "
        "and version (e.g. “in TMF622 v4”). For a named spec the canonical schema is "
        "authoritative; for a universal claim it is not, so I won't assert one — including any "
        "particular default, indexing, or uniformity that the per-API evidence doesn't actually "
        "establish for every API.")


def _sid_refusal(tmf_ids: list) -> str:
    base = (
        "I don't have a SID / Information Framework source indexed, so I can't give an "
        "authoritative SID answer. The SID — the TM Forum information model, its ABEs and entity "
        "hierarchy — is a **different authority** from the Open API specifications, which define "
        "REST resources and fields rather than the information model itself.")
    if tmf_ids:
        base += (
            f" {tmf_ids[0]} is an Open API specification; even where its resources are informed by "
            "the SID, that spec is not the SID authority and I won't present it as one. Add a SID / "
            "Information Framework source on the Documents page and I'll use it.")
    return base


def _etom_refusal() -> str:
    return (
        "I don't have an eTOM / Business Process Framework source indexed, so I can't answer that "
        "authoritatively. Business-process definitions are owned by the eTOM Business Process "
        "Framework — a different framework from both the Open API specifications and the SID — and "
        "I won't infer eTOM facts from an Open API spec.")


def _runtime_refusal() -> str:
    return (
        "No — I don't have explicit integration evidence for a runtime API-to-API interaction "
        "there. A schema reference, a *relatedEntity* or *relatedParty* association, an `href`, or "
        "a shared schema name is a **data-model** relationship; on its own it does not establish "
        "that one API invokes another at runtime. That needs explicit integration evidence (an "
        "integration guide or a declared interaction), which the canonical specifications here "
        "don't provide.")


def _dependency_direction(component_row: dict, subj: str) -> str:
    return (
        f"Direction matters here. {component_row['code']} {component_row.get('name','')} is the "
        f"**component**, and it declares a dependency on {subj}: that is *component → API* "
        f"(the component consumes {subj}). It does **not** reverse — {subj} is an Open API "
        f"specification and is not made dependent on the component, and it does not mean every "
        f"operation of the component invokes {subj} at runtime.")


def _dep_forward_refusal(subj: str, reverse_rows: list) -> str:
    msg = (
        f"No — {subj} is an Open API specification, and Open API specs do not declare outbound "
        "API-to-API dependencies. “Dependency” in the TM Forum model is an **ODA "
        "component** concept: a component declares the APIs it consumes (*component → API*).")
    if reverse_rows:
        names = ", ".join(f"{r['code']} {r.get('name','')}".strip() for r in reverse_rows[:6])
        msg += (f" In that direction, these components declare a dependency **on** {subj}: {names}. "
                f"That is *component → {subj}* and does not reverse.")
    else:
        msg += f" And no canonical ODA component declares {subj} as a dependency."
    return msg


def _concept_dependency_vs_reference() -> str:
    return (
        "They are different kinds of relationship. A **schema reference** (a `$ref`, a `…Ref`, a "
        "*relatedEntity*/*relatedParty*) is a **data-model** link inside a payload — it says two "
        "resources can reference each other. An **API dependency** is an **ODA component** contract "
        "fact: a component declares that it consumes another API (*component → API*). A schema "
        "reference never, by itself, establishes an API dependency, a runtime call, or ownership — "
        "you need the ODA contract (for a dependency) or explicit integration evidence (for a "
        "runtime call).")


def _concept_evidence_for_call() -> str:
    return (
        "To claim that API A calls API B you need **explicit integration evidence** — a documented "
        "interaction, sequence, or declared runtime call stating that invocation. What is **not** "
        "sufficient: a schema reference or `$ref`, a *relatedEntity*/*relatedParty* association, an "
        "`href`, a shared schema name, or the fact that both APIs live in the same domain. Those "
        "are data-model relationships; an ODA *dependent API* is a component-level contract "
        "(*component → API*), which is still not the same as one API invoking another at runtime.")


def _mandatory_vs_dependent() -> str:
    return (
        "No — they are different ODA relationships. A **mandatory API** is one the component must "
        "**expose** (*component → exposes → API*). A **dependent API** is one the "
        "component **consumes** (*component → depends on → API*). Different direction, "
        "different meaning: mandatory is about what the component publishes; dependent is about "
        "what it relies on from elsewhere.")


def _exposure_vs_invocation() -> str:
    return (
        "No — exposing an API and invoking one are different things. **Component exposure** means "
        "the component publishes/implements that API (*component → exposes → API*). A "
        "**runtime invocation** is one API making a request to another at run time. Exposure is a "
        "contract fact from the ODA component specification; it does not, by itself, prove any "
        "runtime call.")


def _reverse_dependency_answer(subj: str, rows: list) -> str:
    if not rows:
        return (f"No canonical ODA component declares a dependency on {subj}. (If it appears "
                f"elsewhere as an *exposed* API, that is a different relationship — exposure, not "
                f"dependency.)")
    names = "; ".join(f"**{r['code']} {r.get('name','')}**".strip() for r in rows[:8])
    return (f"These ODA components declare a dependency **on** {subj} (*component → API*: they "
            f"consume {subj}): {names}. Direction is component → {subj}; it does not mean "
            f"{subj} depends on them.\n\n_Resolved deterministically from the canonical ODA "
            f"component contracts._")


def _reverse_exposure_answer(subj: str, rows: list) -> str:
    if not rows:
        return (f"No canonical ODA component **exposes** {subj}. If you're thinking of a component "
                f"that references it, note that *depending on* an API (consuming it) is a different "
                f"relationship from *exposing* it.")
    names = "; ".join(f"**{r['code']} {r.get('name','')}**".strip() for r in rows[:8])
    return (f"{subj} is **exposed** by: {names} (*component → API*).\n\n_Resolved "
            f"deterministically from the canonical ODA component contracts._")


def _interaction_answer(subj: str, exposers: list, dependers: list) -> str:
    lines = [
        f"The honest answer separates a few **different kinds** of relationship, because {subj} "
        "“interacting with” other APIs can mean things the evidence treats very "
        "differently:", "",
        "- **Data-model associations** — within its schemas a resource may carry references to "
        "other entities (a *related entity*, a *related party*, or a `…Ref`). These are payload "
        "links: they say resources can reference one another, not that one API invokes another.",
    ]
    if exposers or dependers:
        lines.append("- **ODA component relationships** (structural, from the canonical component "
                     "contracts):")
        for r in dependers[:6]:
            lines.append(f"    - {r['code']} {r.get('name','')} declares a **dependency on** {subj} "
                         f"(component → API — it consumes {subj}).")
        for r in exposers[:6]:
            lines.append(f"    - {r['code']} {r.get('name','')} **exposes** {subj} "
                         f"(component → API).")
    else:
        lines.append(f"- **ODA component relationships**: no canonical ODA component exposes or "
                     f"depends on {subj}.")
    lines += ["",
              "- **Runtime API-to-API interaction**: I have **no explicit integration evidence** "
              f"that {subj} invokes another API at run time. None of the above proves that — a "
              "data-model reference or an ODA contract dependency is not the same as one API making "
              "a request to another.", "",
              "_ODA relationships are resolved deterministically from the canonical component "
              "contracts; the data-model and runtime distinctions come from the specification "
              "evidence, which contains no runtime-integration description._"]
    return "\n".join(lines)


def _constraint_absent_answer(cp: dict) -> str:
    present, sid, ver = cp["present"], cp["api_id"], cp["version"]
    sc, pr, ty = cp["schema"], cp["property"], cp["type"]
    if present:
        pres = ", ".join(f"`{k}: {present[k]}`" for k in present)
    else:
        pres = f"`type: {ty}`" if ty else "a bare string property with a description only"
    miss_names = {"format": "a `format`", "pattern": "a `pattern`", "enum": "an `enum`",
                  "length": "a length constraint (`minLength`/`maxLength`)",
                  "range": "a numeric range (`minimum`/`maximum`)", "nullable": "a `nullable` flag"}
    miss = [miss_names.get(m, m) for m in cp["requested"] if not cp["satisfied"].get(m)]
    miss_txt = ", ".join(miss) or "the requested constraint"
    return (
        f"The canonical {sid}{(' v' + ver) if ver else ''} schema defines {pres} for "
        f"`{sc}.{pr}`, but it does **not** define {miss_txt}. So the specification does not "
        f"constrain the value to any particular string form — I won't assert one the schema "
        f"doesn't declare. Any such convention would be an implementation choice, not something "
        f"{sid} mandates. A description is prose, not a validation constraint.")


def _constraint_present_answer(cp: dict) -> str:
    present, sid, ver = cp["present"], cp["api_id"], cp["version"]
    sc, pr = cp["schema"], cp["property"]
    pres = ", ".join(f"`{k}: {present[k]}`" for k in present)
    return (f"Yes — the canonical {sid}{(' v' + ver) if ver else ''} schema explicitly defines "
            f"{pres} on `{sc}.{pr}`, so that constraint is stated by the specification itself.")


def _constraint_generic_scoped(question: str) -> str:
    return (
        "That depends on the exact schema and version — and I won't generalise it. Whether a "
        "property carries a `format`, `pattern`, or `enum` is defined per-schema in the canonical "
        "specification, and a value being a string (or a description mentioning a convention) is "
        "**not** a validation constraint. Name the specific API, version, and property (e.g. "
        "“ProductOrder.id in TMF622 v4”) and I'll report exactly what the schema declares "
        "— and say so plainly if it declares nothing.")


# ── Generation guards (for the 'constrain' action — appended to the RAG prompt extra) ────
_GUARD_ASSOCIATION = (
    "\n\nRELATIONSHIP GUARD: The evidence here is a data-model association (relatedEntity / "
    "relatedParty / a schema reference). Explain it strictly as a data-model association. Do NOT "
    "say it is an API dependency, a runtime call, or an integration, and do NOT claim one API "
    "invokes another. State the narrowest relationship the evidence proves.")
_GUARD_CONSTRAINT = (
    "\n\nCONSTRAINT GUARD: Report only the validation constraints the canonical schema explicitly "
    "declares (type/format/pattern/enum/length). Do NOT infer a format, pattern, enum, or "
    "UUID/URI meaning from `type: string`, a property name, an example, a description, or common "
    "practice. If the requested constraint is absent, say the specification does not define it.")


def _conf(level):
    return level


def govern(question: str, kdec: dict) -> dict:
    """The deterministic authority/relationship/claim decision for `question`. `kdec` is the
    knowledge_router result (for intent + retrieval hints). Never called when the router
    already produced kind == answer/abstain."""
    q = question or ""
    entities = E.extract_entities(q)
    tmf_ids, oda_ids = entities["tmf_ids"], entities["oda_ids"]
    khints = kdec.get("hints") or {}
    router_intent = kdec.get("intent") or ""
    rel_intent = Rl.classify_relationship_intent(q)
    auth = A.resolve_required_authority(q, entities, router_intent)
    claim = Cl.classify_claim(q, entities, rel_intent)
    subj = _subject_spec(entities, khints)

    meta = {"authority": auth["required_authority"].value, "scope": auth["scope"].value,
            "authority_available": auth["authority_available"].value, "claim": claim.value,
            "relationship_intent": rel_intent.value}

    def answer(text, level, sources=None):
        return {"action": "answer", "answer": text, "sources": sources or [],
                "confidence_level": level, "meta": meta}

    def abstain(text, level="low"):
        return {"action": "abstain", "answer": text, "sources": [],
                "confidence_level": level, "meta": meta}

    def constrain(directive, level="medium", retrieval=None):
        return {"action": "constrain", "directive": directive, "confidence_level": level,
                "retrieval": retrieval or {}, "meta": meta}

    def proceed():
        return {"action": "proceed", "meta": meta}

    # ── 1. Framework authority (SID / eTOM) — abstain when the authority is absent ────────
    if claim is Cl.ClaimType.SID_FRAMEWORK_CLAIM and not A.is_present(A.Authority.SID_INFORMATION_FRAMEWORK):
        return abstain(_sid_refusal(tmf_ids))
    if claim is Cl.ClaimType.ETOM_FRAMEWORK_CLAIM and not A.is_present(A.Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK):
        return abstain(_etom_refusal())

    # ── 2. Deterministic relationship semantics — resolved BEFORE the global-rule branch, so a
    #    relationship question that happens to contain "every Open API operation" is treated as a
    #    relationship claim, not a TM-Forum-wide rule. Framework authority (SID/eTOM) still wins.
    if rel_intent is Rl.RelationshipIntent.RUNTIME_CALL_INTENT:
        if _CONCEPT.search(q):
            return answer(_concept_evidence_for_call(), "medium")
        return answer(_runtime_refusal(), "low")   # incl. "dependent API → every operation calls it"

    if rel_intent is Rl.RelationshipIntent.INTEGRATION_INTENT:
        return answer(_runtime_refusal(), "low")

    if rel_intent is Rl.RelationshipIntent.DEPENDENCY_INTENT:
        if _CONCEPT.search(q) or (re.search(r"\bschema\b", q, re.I)
                                  and re.search(r"\b(same|different|differ|versus|vs)\b", q, re.I)):
            return answer(_concept_dependency_vs_reference(), "medium")
        if re.search(r"\bmandatory\b", q, re.I) and re.search(r"\bdependent\b", q, re.I):
            return answer(_mandatory_vs_dependent(), "high", _oda_source("ODA mandatory vs dependent semantics"))
        reverse = re.search(r"\bcomponents?\b", q, re.I) and re.search(r"\bdepend", q, re.I)
        if reverse and subj:
            return answer(_reverse_dependency_answer(subj, Rl.components_depending_on(subj)),
                          "high", _oda_source(f"components depending on {subj}"))
        if oda_ids and subj:                  # direction question naming both a component and an API
            ct = Rl.oda_relationships_for_component(oda_ids[0])
            row = {"code": oda_ids[0], "name": ct.get("name", "")}
            return answer(_dependency_direction(row, subj), "high",
                          _oda_source(f"{oda_ids[0]} contract direction"))
        if subj:                              # "does <api> depend on X" — forward, unprovable
            return answer(_dep_forward_refusal(subj, Rl.components_depending_on(subj)),
                          "medium", _oda_source(f"reverse dependencies of {subj}"))
        # a bare dependency question with no resolvable entity → fall through (global/RAG)

    if rel_intent is Rl.RelationshipIntent.EXPOSURE_INTENT and subj:
        return answer(_reverse_exposure_answer(subj, Rl.components_exposing(subj)),
                      "high", _oda_source(f"components exposing {subj}"))

    if rel_intent is Rl.RelationshipIntent.AMBIGUOUS_INTERACTION_INTENT and subj:
        return answer(_interaction_answer(subj, Rl.components_exposing(subj),
                                          Rl.components_depending_on(subj)),
                      "medium", _oda_source(f"structural relationships of {subj}"))

    # ── 3. Global normative rule — refuse the universal claim when design authority is absent
    if claim is Cl.ClaimType.GLOBAL_DESIGN_RULE_CLAIM and not A.is_present(A.Authority.TMF_DESIGN_GUIDANCE):
        m = re.search(r"\b(paginat\w*|offset|limit|href|patch|error\w*|field\s*select\w*|"
                      r"sort\w*|filter\w*|id\s*format|uniqueness|status\s*code)\b", q, re.I)
        return abstain(_global_refusal(m.group(0).lower() if m else ""))

    # ── 4. Constraint precision — read the exact canonical property, invent nothing ───────
    if Cl.is_constraint_question(q):
        cp = Cl.constraint_precision(q, entities)
        if cp.get("resolved"):
            if all(cp["satisfied"].get(k) for k in cp["requested"]):
                return answer(_constraint_present_answer(cp), "medium")
            return answer(_constraint_absent_answer(cp), "low")
        if not tmf_ids:                       # no spec to pin down → scoped, honest, no guessing
            return answer(_constraint_generic_scoped(q), "low")
        return constrain(_GUARD_CONSTRAINT, "medium")   # spec named but property unresolved → guard RAG

    # ── 5. Data-model association / reference → let RAG explain under a promotion guard ────
    if rel_intent in (Rl.RelationshipIntent.ENTITY_ASSOCIATION_INTENT,
                      Rl.RelationshipIntent.REFERENCE_INTENT):
        return constrain(_GUARD_ASSOCIATION, "medium")

    return proceed()
