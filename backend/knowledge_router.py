"""
Knowledge Engine V2 — deterministic knowledge router (Phase 7B)
═══════════════════════════════════════════════════════════════
Runs BEFORE general RAG. Uses EXACT extracted entities (knowledge_entities) + the
canonical corpus inventory (knowledge_link) + the ODA contract resolver
(oda_component_contract) to answer, abstain, or hand RAG precise version-/content-scoped
retrieval hints. Structured facts before RAG; RAG before generation; generation last.

Contract:  route(question) -> dict
  kind == "answer"   : {"answer","sources",...}  — a deterministic fact; return as-is.
  kind == "abstain"  : {"answer","sources"}      — named entity has no evidence; return.
  kind == "rag"      : {"hints": {...}}           — proceed to version-aware RAG.
  kind == "defer"    : {}                          — not our concern; normal pipeline.

No Ollama fact discovery. No ChromaDB writes. Read-only inventory only.
"""
from __future__ import annotations
import json
import os
import re

import knowledge_entities as E
import knowledge_link as L
import oda_component_contract as C

# ── ODA reverse index (TMF API → components that expose it), built once from the 35
#    canonical contracts. Deterministic; enables "which component exposes TMF642?" and
#    "what version of TMF642 does TMFC043 use?" without RAG. ────────────────────────────
_REVERSE = None
def _reverse_map() -> dict:
    global _REVERSE
    if _REVERSE is None:
        rev = {}
        try:
            codes = [c["code"] for c in json.load(
                open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oda_components.json")))["components"]]
        except Exception:
            codes = []
        for code in codes:
            ct = C.resolve_contract(code)
            if ct.get("status") != "RESOLVED":
                continue
            for r in ct["requirements"]["exposed"]:
                if r.get("is_placeholder") or (r.get("api_type") or "").lower() != "openapi":
                    continue
                rev.setdefault(r["id"], []).append(
                    {"code": code, "name": ct["component"]["name"],
                     "status": r["requirement_status"], "version": r["declared_version"]})
        _REVERSE = rev
    return _REVERSE

# ── Intent shapes (keyword-anchored; the LLM never decides whether a deterministic
#    source exists) ─────────────────────────────────────────────────────────────────────
_EXPOSE   = re.compile(r"\b(expose[sd]?|mandatory|require[sd]?|offer[sd]?|provide[sd]?|"
                       r"exposed|which apis?|what apis?|core apis?|security apis?)\b", re.I)
_DEPEND   = re.compile(r"\b(depend(s|ency|encies|ent)?|rely|relies|consume[sd]?)\b", re.I)
_EVENTS   = re.compile(r"\b(event|events|publish(es|ed)?|subscribe[sd]?|notification)\b", re.I)
_VERSIONQ = re.compile(r"\b(version|v\d)\b", re.I)
_BLOCK    = re.compile(r"\b(functional block|block|domain)\b", re.I)
_COMPARE  = re.compile(r"\b(difference|differ|compare|comparison|changed?|versus|vs\.?|"
                       r"between)\b", re.I)
_OPS      = re.compile(r"\b(operation|operations|endpoint|endpoints|method|methods|"
                       r"post|get|patch|delete|create|update|acknowledge|how do i)\b", re.I)
_REQFIELD = re.compile(r"\b(required|mandatory|attribute|attributes|field|fields|property|"
                       r"properties|identif(y|ies|ier))\b", re.I)
_IDENTITY = re.compile(r"\b(what is|what'?s|about|describe|overview|domain|cover[s]?|manage[s]?)\b", re.I)


def _contract_sources(contract: dict) -> list:
    comp = contract.get("component", {}) or {}
    return [{
        "name": f"{comp.get('id','')} {comp.get('name','')} (v{comp.get('version','')})".strip(),
        "file": contract.get("source", ""),
        "chunk": 0, "preview": "Canonical ODA Component specification (deterministic resolver).",
        "url": "", "upload": False, "origin_type": "", "domain": "ODA",
        "content_class": "oda_component_spec",
    }]


def _fmt_apis(rows) -> str:
    return " · ".join(f"**{r['id']}** {r['declared_version']}" for r in rows) or "none"


def _oda_contract_answer(cid: str, q: str) -> dict | None:
    """Deterministic answer for a contract-fact question about a named ODA component.
    Everything comes from oda_component_contract.resolve_contract — never RAG/LLM."""
    ct = C.resolve_contract(cid)
    if ct.get("status") != "RESOLVED":
        return {"answer": (f"**{cid}** is not a resolvable ODA component in the canonical "
                           f"v1.0.0 catalogue ({ct.get('status')}). I won't guess its contract."),
                "sources": [], "tmf": "", "resource": "ODA"}
    comp = ct["component"]; req = ct["requirements"]
    mand = C.mandatory_api_coverage(ct)
    optional = [r for r in req["optional_exposed"] if (r.get("api_type") or "").lower() == "openapi"]
    dep = [d for d in req["dependent"] if not d.get("is_placeholder")]
    ev = req["events"]
    disp = f"**{comp['id']} {comp['name']}** (v{comp['version']}, {comp.get('functionalBlock','')} block)"
    lines = []

    if _EVENTS.search(q):
        lines.append(f"{disp} — event contract (canonical specification):")
        lines.append(f"- Publishes **{len(ev['published'])}** event(s)"
                     + (": " + ", ".join(e['name'] for e in ev['published'] if e.get('name')) if ev['published'] else "."))
        lines.append(f"- Subscribes to **{len(ev['subscribed'])}** event(s)"
                     + (": " + ", ".join(e['name'] for e in ev['subscribed'] if e.get('name')) if ev['subscribed'] else "."))
    elif _DEPEND.search(q):
        if dep:
            lines.append(f"{disp} declares **{len(dep)}** dependent API(s): "
                         + " · ".join(f"**{d['id']}** {d.get('declared_version','')}".strip() for d in dep) + ".")
        else:
            lines.append(f"{disp} declares **no dependent APIs** in its canonical specification.")
    elif _BLOCK.search(q) and not _EXPOSE.search(q):
        lines.append(f"{disp.split(' (v')[0]} is in the **{comp.get('functionalBlock','')}** functional block "
                     f"(component version {comp['version']}).")
    elif _VERSIONQ.search(q) and not _EXPOSE.search(q):
        lines.append(f"The canonical version of **{comp['id']} {comp['name']}** is **{comp['version']}**.")
    else:  # expose / mandatory / required / general contract
        lines.append(f"{disp} exposes these APIs (canonical component contract):")
        lines.append(f"- **Mandatory (required)**: {_fmt_apis(mand)}")
        lines.append(f"- **Optional**: {_fmt_apis([{'id':r['id'],'declared_version':r['declared_version']} for r in optional])}")
        if dep:
            lines.append(f"- **Dependent**: " + " · ".join(f"{d['id']} {d.get('declared_version','')}".strip() for d in dep))
        else:
            lines.append("- **Dependent**: none")
    lines += ["", "_Resolved deterministically from the canonical TM Forum ODA v1.0.0 "
                  "component specification — not generated, not retrieved._"]
    return {"answer": "\n".join(lines), "sources": _contract_sources(ct), "tmf": "", "resource": "ODA"}


def _abstain(entity: str, kind: str = "TMF") -> dict:
    return {"answer": (
        f"I don't have authoritative **{entity}** specification evidence in the current "
        f"indexed TM Forum corpus, so I can't give a reliable answer for it. I won't infer "
        f"{entity} from neighbouring or unrelated APIs. If you have the {entity} spec, add it "
        f"on the Documents page and I'll index it."),
        "sources": [], "tmf": "", "resource": ""}


def route(question: str) -> dict:
    """See module docstring. Deterministic; safe to call on every /query."""
    q = question or ""
    ent = E.extract_entities(q)
    tmf_ids, oda_ids = ent["tmf_ids"], ent["oda_ids"]

    # ── A(-1). Malformed identifier ("TMF6420", "TMF64") that yields no valid TMF/TMFC id
    #    must NOT be semantic-matched to a similar real spec. Decline explicitly. ─────────
    if not tmf_ids and not oda_ids and re.search(r"(?<![A-Za-z0-9])TMFC?\d{4,}\b", q, re.I):
        bad = re.search(r"(?<![A-Za-z0-9])TMFC?\d{4,}\b", q, re.I).group(0)
        return {"kind": "abstain", "intent": "MALFORMED_ENTITY",
                "answer": (f"**{bad}** is not a valid TM Forum identifier — TMF APIs are `TMF` + three "
                           f"digits (e.g. TMF642) and ODA components are `TMFC` + three digits. I won't "
                           f"guess which spec you meant."),
                "sources": [], "tmf": "", "resource": ""}

    # ── A0. "security API for every/all ODA component" → deterministic (always TMF669) ──
    if re.search(r"\b(every|all|each|any)\b.{0,30}\bcomponent", q, re.I) and re.search(r"\bsecurity\b", q, re.I):
        return {"kind": "answer", "intent": "ODA_API_RELATIONSHIP",
                "answer": ("Every ODA component's mandatory **security** API is **TMF669 Party Role "
                           "Management** (v4.0.0) — it is required in the securityFunction of all 35 "
                           "canonical v1.0.0 components.\n\n_Deterministic from the canonical ODA "
                           "component specifications._"),
                "sources": [], "tmf": "TMF669", "resource": "ODA"}

    # ── A1. TMF API version WITHIN a named component ("is TMF760 v4 or v5 in TMFC027?",
    #    "what version of TMF642 does TMFC043 require?") → the API's declared_version. ────
    if oda_ids and tmf_ids and (_VERSIONQ.search(q) or _COMPARE.search(q) or _EXPOSE.search(q)):
        ct = C.resolve_contract(oda_ids[0])
        if ct.get("status") == "RESOLVED":
            for r in ct["requirements"]["exposed"]:
                if (r.get("id") or "").upper() == tmf_ids[0] and not r.get("is_placeholder"):
                    return {"kind": "answer", "intent": "ODA_API_RELATIONSHIP",
                            "answer": (f"In **{ct['component']['id']} {ct['component']['name']}**, "
                                       f"**{r['id']}** is used at version **{r['declared_version']}** "
                                       f"({(r['requirement_status'] or '').lower()}).\n\n_Deterministic "
                                       f"from the canonical ODA component specification._"),
                            "sources": _contract_sources(ct), "tmf": r["id"], "resource": "ODA"}

    # ── A2. "which component exposes/owns TMFxxx" → reverse lookup (TMF id → components) ─
    if tmf_ids and not oda_ids and re.search(r"\b(which|what)\b", q, re.I) \
       and re.search(r"\b(component|components|expose[sd]?|own[sd]?|use[sd]?|using)\b", q, re.I):
        hits = _reverse_map().get(tmf_ids[0], [])
        if hits:
            use = [h for h in hits if h["status"] == "MANDATORY"] or hits
            names = ", ".join(f"**{h['name']}** ({h['code']}, {h['version']}, {h['status'].lower()})"
                              for h in use[:6])
            return {"kind": "answer", "intent": "ODA_API_RELATIONSHIP",
                    "answer": (f"**{tmf_ids[0]}** is exposed by: {names}.\n\n_Deterministic from the "
                               f"canonical ODA component specifications._"),
                    "sources": [], "tmf": tmf_ids[0], "resource": "ODA"}

    # ── A. ODA component CONTRACT / identity fact (TMFCxxx) → resolver ──────────────────
    #    A named ODA component almost always wants deterministic contract facts, never RAG
    #    (the ODA YAMLs aren't even in the vector corpus). Cover contract intents and bare
    #    identity ("what is TMFC043").
    if oda_ids and (_EXPOSE.search(q) or _DEPEND.search(q) or _EVENTS.search(q)
                    or _BLOCK.search(q) or _VERSIONQ.search(q) or _IDENTITY.search(q)
                    or re.search(r"\b(contract|component)\b", q, re.I)):
        ans = _oda_contract_answer(oda_ids[0], q)
        if ans:
            return {"kind": "answer", "intent": "ODA_COMPONENT_CONTRACT", **ans}

    # ── B. Named TMF id with NO canonical evidence → honest abstention ─────────────────
    #    (never semantic-search unrelated specs). Only fire when the question is *about*
    #    that spec, not an incidental mention inside a broader question.
    if tmf_ids:
        absent = [s for s in tmf_ids if not L.spec_present(s)]
        if absent and not oda_ids:
            return {"kind": "abstain", "intent": "UNKNOWN_NAMED_ENTITY", **_abstain(absent[0])}

    # ── C. Version comparison ("difference between v4 and v5") → existing version-diff ──
    if tmf_ids and (ent["has_conflicting_versions"] or _COMPARE.search(q)):
        return {"kind": "rag", "intent": "VERSION_COMPARISON",
                "hints": {"spec_ids": tmf_ids, "major": None, "compare": True,
                          "canonical_only": True, "evidence_specs": tmf_ids}}

    # ── D. Build version-/content-scoped retrieval hints for RAG ───────────────────────
    #    Seed retrieval from named TMF ids; else from a uniquely-linked bare entity.
    spec_ids = [s for s in tmf_ids if L.spec_present(s)]
    schema_hint = None
    if not spec_ids and not oda_ids:
        # Try to link a bare entity to its owning spec. Test each token and each adjacent
        # bigram (CamelCase-joined) — "Alarm" → TMF642, "Party Role" → PartyRole → TMF669.
        toks = re.findall(r"[A-Za-z]+", q)
        cands_ordered = [t for t in toks] + ["".join(p) for p in zip(toks, toks[1:])]
        for cand_name in cands_ordered:
            if len(cand_name) < 4:
                continue
            cand = [c for c in L.link_schema(cand_name) if L.spec_present(c)]
            if cand:
                spec_ids = cand[:3]; schema_hint = cand_name
                break
    major = ent["requested_major"]
    # Required-fields / schema-fact questions are owned by the deterministic spec_facts
    # engine, which resolves the exact version and returns an explicit UNRESOLVED result
    # (with the full requested version + available versions) when a version is absent. Defer
    # those entirely — the router must NOT preempt them with a major-only abstention.
    is_reqfield = bool(_REQFIELD.search(q))
    # For NON-required-fields questions: if a requested major isn't available for a named
    # spec, abstain rather than answer another major (never a wrong-major answer).
    if spec_ids and major is not None and not is_reqfield:
        for s in list(spec_ids):
            if str(major) not in L.majors_for(s):
                return {"kind": "abstain", "intent": "WRONG_VERSION_REQUESTED",
                        **_abstain(f"{s} v{major}")}
    if spec_ids or oda_ids:
        intent = "SPEC_OPERATIONS" if _OPS.search(q) else (
                 "SPEC_IDENTITY" if _IDENTITY.search(q) else "SPEC_EXPLANATION")
        return {"kind": "rag", "intent": intent,
                "hints": {"spec_ids": spec_ids, "major": major, "schema": schema_hint,
                          "canonical_only": bool(spec_ids), "evidence_specs": spec_ids}}

    # ── E. No entity → normal generic fallback (still content-class aware downstream) ───
    return {"kind": "defer", "intent": "GENERAL_EXPLANATION", "hints": {"canonical_only": False}}
