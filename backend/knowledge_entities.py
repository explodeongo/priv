"""
Knowledge Engine V2 — deterministic entity extraction (Phase 7B)
════════════════════════════════════════════════════════════════
Pure, side-effect-free extraction of the exact identifiers a TM Forum question names,
so routing/retrieval can be driven by EXACT entities instead of fuzzy semantics. No
Ollama, no ChromaDB — this module never touches the network or the corpus.

Extracts:
  • TMF API ids        — TMF + exactly 3 digits (TMF642), rejecting TMFC/embedded/4-digit.
  • ODA component ids  — TMFC + exactly 3 digits (TMFC043).
  • Requested version  — v4 / v4.0.0 / "version 4" attached to (or near) a TMF id.
Schema→spec linking (Alarm→TMF642) is corpus-derived and lives in knowledge_link.py so
this module stays pure and unit-testable in isolation.
"""
from __future__ import annotations
import re
from typing import Optional

# TMF id = "TMF" + exactly 3 digits, NOT the "TMFC" component prefix, not embedded in a
# longer alphanumeric run, not TMF####. Word-ish boundaries on both sides.
_TMF_RE  = re.compile(r"(?<![A-Za-z0-9])TMF(?!C)(\d{3})(?![0-9A-Za-z])", re.I)
# ODA component id = "TMFC" + exactly 3 digits.
_TMFC_RE = re.compile(r"(?<![A-Za-z0-9])TMFC(\d{3})(?![0-9A-Za-z])", re.I)
# Version token: "v4", "v4.0", "v4.0.0" (optionally the bare "4.0.0" right after a TMF id
# or "version N"). Capture major + the full dotted string when present.
_VER_TOKEN = re.compile(r"\bv(\d+)(?:\.(\d+))?(?:\.(\d+))?\b", re.I)
_VER_WORD  = re.compile(r"\bversion\s+(\d+)(?:\.(\d+))?(?:\.(\d+))?\b", re.I)


def extract_tmf_ids(text: str) -> list[str]:
    """All TMF-API ids named in `text`, upper-cased, de-duplicated, order-preserving.
    Rejects TMFC (component) ids and TMF#### / embedded runs (e.g. XTMF642, TMF6420)."""
    out, seen = [], set()
    for m in _TMF_RE.finditer(text or ""):
        sid = "TMF" + m.group(1)
        if sid not in seen:
            seen.add(sid); out.append(sid)
    return out


def extract_oda_ids(text: str) -> list[str]:
    """All ODA component ids (TMFCxxx) named in `text`, upper-cased, de-duplicated."""
    out, seen = [], set()
    for m in _TMFC_RE.finditer(text or ""):
        cid = "TMFC" + m.group(1)
        if cid not in seen:
            seen.add(cid); out.append(cid)
    return out


def _ver_from_match(m) -> dict:
    major = int(m.group(1))
    parts = [g for g in m.groups() if g is not None]
    exact = ".".join(parts) if len(parts) > 1 else None
    return {"major": major, "version": exact}


def extract_versions(text: str) -> list[dict]:
    """Every explicit version reference: [{major:int, version:str|None}]. 'v4' → major 4,
    no exact; 'v4.0.0' → major 4, version '4.0.0'. De-duplicated by (major, version)."""
    out, seen = [], set()
    for rx in (_VER_TOKEN, _VER_WORD):
        for m in rx.finditer(text or ""):
            v = _ver_from_match(m)
            key = (v["major"], v["version"])
            if key not in seen:
                seen.add(key); out.append(v)
    return out


def requested_major(text: str) -> Optional[int]:
    """The single requested major version, or None. If the query names conflicting majors
    (a comparison like 'v4 vs v5') this returns None — the caller must treat that as a
    comparison, not a single-version filter."""
    vs = extract_versions(text)
    majors = {v["major"] for v in vs}
    return next(iter(majors)) if len(majors) == 1 else None


def extract_entities(text: str) -> dict:
    """One-shot deterministic extraction for the router.
    { tmf_ids, oda_ids, versions, requested_major, has_conflicting_versions }."""
    tmf = extract_tmf_ids(text)
    oda = extract_oda_ids(text)
    vers = extract_versions(text)
    majors = {v["major"] for v in vers}
    return {
        "tmf_ids": tmf,
        "oda_ids": oda,
        "versions": vers,
        "requested_major": next(iter(majors)) if len(majors) == 1 else None,
        "has_conflicting_versions": len(majors) > 1,
    }
