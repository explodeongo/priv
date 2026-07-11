"""
Knowledge Engine V2 — relationship type model + intent + structural evidence (Phase 7E)
════════════════════════════════════════════════════════════════════════════════════════
Phase 7D proved SynaptDI collapsed every kind of relationship into one word ("interacts"):
a schema `$ref`, a `relatedEntity` association, an ODA component dependency, and a (never-
evidenced) runtime call were all presented identically — and the ODA dependency direction
was even inverted (TMFC050→TMF621 reported as "TMF621 relies on Product Recommendation").

This module introduces the missing concept: a CLOSED set of relationship types, each with an
explicit DIRECTION, the authority that proves it, and what it does / does NOT prove; a
deterministic relationship-intent classifier; and structural evidence built ONLY from the
canonical ODA contract resolver (never RAG prose). The invariant is absolute:

    component → (ODA_DEPENDENT_API) → API        # a component CONSUMES an API
    this never means  API → depends on → component,
    and never means  every operation of the component calls that API.

Pure & offline: ODA contracts (oda_component_contract) + the component inventory. No RAG,
no Ollama, no network.
"""
from __future__ import annotations
import enum
import json
import os
import re
from functools import lru_cache

import oda_component_contract as C

_HERE = os.path.dirname(os.path.abspath(__file__))
_ODA_COMPONENTS = os.path.join(_HERE, "oda_components.json")


# ── Closed relationship-type set ────────────────────────────────────────────────────────
class RelationshipType(enum.Enum):
    SCHEMA_REFERENCE = "SCHEMA_REFERENCE"                   # schema A $ref schema B (data model)
    RELATED_ENTITY_ASSOCIATION = "RELATED_ENTITY_ASSOCIATION"  # a relatedEntity payload link
    RELATED_PARTY_ASSOCIATION = "RELATED_PARTY_ASSOCIATION"    # a relatedParty payload link
    ODA_EXPOSED_API = "ODA_EXPOSED_API"                    # component publishes an API
    ODA_MANDATORY_API = "ODA_MANDATORY_API"                # component must expose an API
    ODA_DEPENDENT_API = "ODA_DEPENDENT_API"                # component consumes an API
    COMPONENT_EXPOSURE = "COMPONENT_EXPOSURE"              # component→API exposure (generic)
    EVENT_PUBLICATION = "EVENT_PUBLICATION"                # component publishes an event
    EVENT_SUBSCRIPTION = "EVENT_SUBSCRIPTION"              # component subscribes to an event
    RUNTIME_API_CALL = "RUNTIME_API_CALL"                  # A invokes B at runtime (needs explicit evidence)
    DOCUMENTED_INTEGRATION_PATTERN = "DOCUMENTED_INTEGRATION_PATTERN"  # a documented A↔B pattern
    DOMAIN_RELATIONSHIP = "DOMAIN_RELATIONSHIP"            # same domain / conceptual relation
    OWNERSHIP = "OWNERSHIP"                                # a spec/component owns a resource
    UNKNOWN_RELATIONSHIP = "UNKNOWN_RELATIONSHIP"


class RelationshipIntent(enum.Enum):
    REFERENCE_INTENT = "REFERENCE_INTENT"
    ENTITY_ASSOCIATION_INTENT = "ENTITY_ASSOCIATION_INTENT"
    DEPENDENCY_INTENT = "DEPENDENCY_INTENT"
    EXPOSURE_INTENT = "EXPOSURE_INTENT"
    RUNTIME_CALL_INTENT = "RUNTIME_CALL_INTENT"
    INTEGRATION_INTENT = "INTEGRATION_INTENT"
    OWNERSHIP_INTENT = "OWNERSHIP_INTENT"
    EVENT_RELATIONSHIP_INTENT = "EVENT_RELATIONSHIP_INTENT"
    AMBIGUOUS_INTERACTION_INTENT = "AMBIGUOUS_INTERACTION_INTENT"
    NONE = "NONE"


# What each relationship type proves / does not prove (documented + used in answers).
PROVES = {
    RelationshipType.SCHEMA_REFERENCE: "a data-model reference between schemas",
    RelationshipType.RELATED_ENTITY_ASSOCIATION: "an entity association carried in the payload",
    RelationshipType.RELATED_PARTY_ASSOCIATION: "a party association carried in the payload",
    RelationshipType.ODA_EXPOSED_API: "the component publishes this API",
    RelationshipType.ODA_MANDATORY_API: "the component must expose this API",
    RelationshipType.ODA_DEPENDENT_API: "the component consumes this API",
    RelationshipType.EVENT_PUBLICATION: "the component publishes this event",
    RelationshipType.EVENT_SUBSCRIPTION: "the component subscribes to this event",
    RelationshipType.RUNTIME_API_CALL: "a runtime API-to-API invocation",
    RelationshipType.OWNERSHIP: "the spec/component owns this resource",
}
DOES_NOT_PROVE = {
    RelationshipType.SCHEMA_REFERENCE: ("an API dependency", "a runtime call", "ownership of the other API"),
    RelationshipType.RELATED_ENTITY_ASSOCIATION: ("that this API calls the related entity's API", "a dependency"),
    RelationshipType.RELATED_PARTY_ASSOCIATION: ("that Party Management is invoked", "a dependency"),
    RelationshipType.ODA_DEPENDENT_API: ("that the API depends on the component (inverse)",
                                         "that every operation calls this API"),
    RelationshipType.ODA_EXPOSED_API: ("runtime invocation", "ownership of referenced entities"),
    RelationshipType.RUNTIME_API_CALL: (),
}


# ── Relationship-intent classifier (deterministic, precedence-ordered) ──────────────────
_RUNTIME = re.compile(r"\b(call[s]?|called|calling|invoke\w*|invoc\w+|runtime|at\s+run\s*time|"
                      r"makes?\s+a?\s*request|http\s+call)\b", re.I)
_INTEGRATE = re.compile(r"\b(integrat\w+|orchestrat\w+)\b", re.I)
_DEPEND = re.compile(r"\b(depend\w*|rely|relies|reliance|consume[sd]?|requires?\s+another|"
                     r"dependent\s+api)\b", re.I)
_EXPOSE = re.compile(r"\b(expose[sd]?|exposure|publish(?:es|ed)?\s+the\s+api|which\s+components?)\b", re.I)
_OWN = re.compile(r"\b(own[sd]?|ownership|belongs?\s+to|part\s+of)\b", re.I)
_EVENT = re.compile(r"\b(publish(?:es|ed)?\s+event|subscribe[sd]?\s+(to\s+)?event|event\s+notification)\b", re.I)
_REFERENCE = re.compile(r"\b(reference[sd]?|refers?\s+to|\$?ref\b|contains?\s+a\s+\w*ref)\b", re.I)
_ASSOC = re.compile(r"\brelated(entity|party)\b|\brelated\s+(entity|party)\b", re.I)
_INTERACT = re.compile(r"\b(interact[s]?|interaction|work[s]?\s+with|relate[s]?\s+to\s+other|"
                       r"with\s+other\s+apis?|talk[s]?\s+to)\b", re.I)


def classify_relationship_intent(question: str) -> RelationshipIntent:
    """Which KIND of relationship the question asks about. Precedence matters: a runtime/
    call claim is the strongest (and the most dangerous to affirm), then integration, then
    dependency/exposure/ownership/events, then reference/association, and finally the vague
    'interact with other APIs' shape — which must NOT fall through to generic RAG."""
    q = question or ""
    # 'related entity/party ... call/dependency' → still a runtime/dependency claim about it,
    # but the association vocabulary is the subject; handle the promotion intents first.
    if _RUNTIME.search(q):
        return RelationshipIntent.RUNTIME_CALL_INTENT
    if _INTEGRATE.search(q):
        return RelationshipIntent.INTEGRATION_INTENT
    if _DEPEND.search(q):
        return RelationshipIntent.DEPENDENCY_INTENT
    if _EVENT.search(q):
        return RelationshipIntent.EVENT_RELATIONSHIP_INTENT
    if _EXPOSE.search(q) and re.search(r"\bcomponents?\b", q, re.I):
        return RelationshipIntent.EXPOSURE_INTENT
    if _ASSOC.search(q):
        return RelationshipIntent.ENTITY_ASSOCIATION_INTENT
    if _OWN.search(q):
        return RelationshipIntent.OWNERSHIP_INTENT
    if _REFERENCE.search(q):
        return RelationshipIntent.REFERENCE_INTENT
    if _INTERACT.search(q):
        return RelationshipIntent.AMBIGUOUS_INTERACTION_INTENT
    return RelationshipIntent.NONE


# ── Structural relationship evidence — ONLY from the canonical ODA contract resolver ────
def _component_codes() -> list:
    try:
        return [c["code"] for c in json.load(open(_ODA_COMPONENTS))["components"]]
    except Exception:
        return []


@lru_cache(maxsize=1)
def _oda_edges() -> dict:
    """Every ODA component→API relationship, direction preserved, built once from the 35
    canonical contracts. { 'exposed': {TMF: [comp...]}, 'dependent': {TMF: [comp...]} }.
    'comp' rows are {code, name, version, status}."""
    exposed, dependent = {}, {}
    for code in _component_codes():
        ct = C.resolve_contract(code)
        if ct.get("status") != "RESOLVED":
            continue
        name = ct["component"]["name"]
        for r in ct["requirements"]["exposed"]:
            if r.get("is_placeholder") or (r.get("api_type") or "").lower() != "openapi":
                continue
            exposed.setdefault((r["id"] or "").upper(), []).append(
                {"code": code, "name": name, "version": r.get("declared_version"),
                 "status": r.get("requirement_status")})
        for d in ct["requirements"]["dependent"]:
            if d.get("is_placeholder"):
                continue
            dependent.setdefault((d["id"] or "").upper(), []).append(
                {"code": code, "name": name, "version": d.get("declared_version"),
                 "status": d.get("requirement_status")})
    return {"exposed": exposed, "dependent": dependent}


def components_exposing(tmf_id: str) -> list:
    """ODA components that EXPOSE `tmf_id` (component → ODA_EXPOSED_API → API). May be []."""
    return list(_oda_edges()["exposed"].get((tmf_id or "").upper(), []))


def components_depending_on(tmf_id: str) -> list:
    """ODA components that DEPEND ON `tmf_id` (component → ODA_DEPENDENT_API → API). Direction
    is component→API: these components CONSUME the API; the API does not depend on them."""
    return list(_oda_edges()["dependent"].get((tmf_id or "").upper(), []))


def oda_relationships_for_component(component_id: str) -> dict:
    """All structural relationships a named component declares, direction preserved:
    exposed / mandatory / dependent APIs + published / subscribed events."""
    ct = C.resolve_contract(component_id)
    if ct.get("status") != "RESOLVED":
        return {"status": ct.get("status", "UNRESOLVED")}
    req = ct["requirements"]
    real = lambda rows: [{"id": r["id"], "version": r.get("declared_version"),
                          "status": r.get("requirement_status")}
                         for r in rows if not r.get("is_placeholder")
                         and (r.get("api_type") or "openapi").lower() == "openapi"]
    return {
        "status": "RESOLVED",
        "component": ct["component"]["id"], "name": ct["component"]["name"],
        "exposed": real(req["exposed"]),
        "mandatory": [{"id": r["id"], "version": r["declared_version"]}
                      for r in req["mandatory_exposed"]],
        "dependent": [{"id": d["id"], "version": d.get("declared_version")}
                      for d in req["dependent"] if not d.get("is_placeholder")],
        "events": req["events"],
    }


def evidence_required_to_claim(rel_type: RelationshipType) -> str:
    """The evidence that would justify a given relationship claim — used to answer 'what
    evidence is required to claim API A calls API B?' honestly and generically."""
    if rel_type in (RelationshipType.RUNTIME_API_CALL, RelationshipType.DOCUMENTED_INTEGRATION_PATTERN):
        return ("explicit integration evidence that states the runtime invocation (an "
                "integration guide, a sequence/interaction description, or a declared API call) "
                "— a schema reference, a relatedEntity/relatedParty association, or a shared "
                "schema name is NOT sufficient")
    if rel_type == RelationshipType.ODA_DEPENDENT_API:
        return "a canonical ODA component contract listing the API as a dependentAPI (component→API)"
    if rel_type in (RelationshipType.ODA_EXPOSED_API, RelationshipType.ODA_MANDATORY_API):
        return "a canonical ODA component contract listing the API as an exposedAPI"
    return "explicit canonical evidence of that exact relationship type"
