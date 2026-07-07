"""Deterministic answers for structured spec-fact questions.

The RAG chat *interprets* retrieved text, and an LLM can misread even correct
context — inventing a required field, or missing one. For questions whose answer is
a hard fact in a canonical TM Forum spec ("what mandatory fields does TMF622 Product
Order require?"), we read the answer straight from the schema's `required` list, so
it is correct by construction rather than a model's guess.

`answer(question)` returns a dict with the ready-made answer + citation, or None for
anything it should not own — in which case the caller falls back to the LLM. This is
the same deterministic-over-generative principle as the conformance engine, applied
to Q&A: never let the model be the source of truth for a fact the spec states.
"""
import json
import os
import re

import tmf_profile
from conformance import _schemas, _resolve_ref

_HERE = os.path.dirname(os.path.abspath(__file__))

# Intent: the question must be about which fields are *required* (not "explain X").
_REQ = re.compile(r"\b(mandatory|required|require[sd]?|need(?:ed|s)?)\b", re.I)
_FLD = re.compile(r"\b(field|attribute|propert|schema)s?\b", re.I)
_TMF = re.compile(r"\bTMF\s?0*(\d{2,4})\b", re.I)
_STOP = {
    "what", "whats", "which", "whose", "does", "do", "did", "the", "a", "an", "of", "for", "in", "on",
    "is", "are", "to", "how", "require", "requires", "required", "mandatory", "optional", "fields",
    "field", "attributes", "attribute", "property", "properties", "schema", "schemas", "list", "show",
    "tell", "me", "about", "and", "or", "resource", "entity", "object", "model", "open", "api", "apis",
    "need", "needs", "needed", "have", "has", "with", "please", "give", "when", "creating", "create",
    "valid", "must", "define", "defines", "contain", "contains",
}


def _resolve(spec, node):
    return _resolve_ref(spec, node["$ref"]) if isinstance(node, dict) and "$ref" in node else (node or {})


def _required(spec, schema, _d=0):
    """Order-preserving required-field list, honouring allOf composition."""
    schema = _resolve(spec, schema)
    req = list(schema.get("required", []) or [])
    if _d < 5:
        for sub in schema.get("allOf", []) or []:
            for r in _required(spec, sub, _d + 1):
                if r not in req:
                    req.append(r)
    return req


def _properties(spec, schema, _d=0):
    schema = _resolve(spec, schema)
    props = dict(schema.get("properties", {}) or {})
    if _d < 5:
        for sub in schema.get("allOf", []) or []:
            props.update(_properties(spec, sub, _d + 1))
    return props


def _sub_schema(spec, prop):
    """If a property is (an array of) a named schema $ref, return (name, def)."""
    p = _resolve(spec, prop)
    node = p.get("items", {}) if p.get("type") == "array" else p
    node = _resolve(spec, node)
    ref = (prop.get("$ref") if isinstance(prop, dict) else None)
    if p.get("type") == "array":
        items = p.get("items", {}) or {}
        ref = items.get("$ref")
        if not ref:
            for s in items.get("allOf", []) or []:
                if isinstance(s, dict) and s.get("$ref"):
                    ref = s["$ref"]
                    break
    if ref:
        return ref.split("/")[-1], _resolve_ref(spec, ref)
    return None, None


def _desc(spec, prop):
    """Terse 'type — description' for a property, best-effort. When the property has no
    description of its own, fall back to the referenced schema's description (still
    spec-sourced, never invented)."""
    p = _resolve(spec, prop) if isinstance(prop, dict) and "$ref" in prop else (prop or {})
    t = p.get("type", "")
    if t == "array":
        it = p.get("items", {}) or {}
        inner = it.get("$ref", "").split("/")[-1] or it.get("type", "")
        t = f"array of {inner}" if inner else "array"
    elif not t and isinstance(prop, dict) and prop.get("$ref"):
        t = prop["$ref"].split("/")[-1]
    d = (p.get("description") or "").strip().split("\n")[0]
    if not d:
        _sn, sub = _sub_schema(spec, prop)
        if sub:
            d = (sub.get("description") or "").strip().split("\n")[0]
    return t, (d[:90] + ("…" if len(d) > 90 else ""))


def _base(name):
    return re.sub(r"_(create|update|fvo|mvo|ref)$", "", name.lower()).replace("_", "").rstrip("s")


def _pick_schema(spec, resource):
    """(name, def) of the schema to report for `resource`. Among name-matching
    variants, prefer the one declaring the most required fields (that is where
    'what you must submit' lives), tie-broken by the plainest (shortest) name."""
    schemas = _schemas(spec)
    rl = resource.lower().replace("_", "").rstrip("s")
    matches = [n for n in schemas if _base(n) == rl]
    if not matches:
        return None, None
    matches.sort(key=lambda n: (-len(_required(spec, schemas[n])), len(n)))
    return matches[0], schemas[matches[0]]


def _resource_words(q):
    cleaned = re.sub(r"\bTMF\s?\d{2,4}\b", " ", q or "", flags=re.I)
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", cleaned)
    keep = [w for w in words if w.lower() not in _STOP and len(w) > 1]
    return "".join(keep).lower()


def _resolve_spec(q):
    """(meta, spec) for the TMF API named or detected in the question, or (None, None).
    When several versions match, the latest wins — so the answer is predictable and
    reflects the current standard regardless of how the question was phrased."""
    idx = tmf_profile.build_index()
    cands = []
    m = _TMF.search(q or "")
    if m:
        tmf = "TMF" + m.group(1).zfill(3)
        cands = [mt for mt in idx.values() if (mt.get("tmf") or "").upper() == tmf]
    if not cands:
        words = _resource_words(q)
        for key in (words, words.rstrip("s")):
            if key and key in idx:
                cands = [idx[key]]
                break
    if not cands:
        return None, None
    meta = max(cands, key=lambda mt: tmf_profile._version_key(mt.get("version", "0")))
    sp = tmf_profile._load(os.path.join(_HERE, meta["file"]))
    return (meta, sp) if isinstance(sp, dict) else (None, None)


def _citation(meta, resource):
    label = " ".join(x for x in [meta.get("tmf", ""), meta.get("title", "")] if x).strip()
    if meta.get("version"):
        label += f" v{meta['version']}"
    return {
        "name": label or "TM Forum canonical spec",
        "file": meta.get("file", ""),
        "chunk": 0,
        "preview": f"Canonical {meta.get('tmf', 'TM Forum')} specification — {resource} schema. "
                   f"Required fields read directly from the schema's `required` list (deterministic).",
        "url": "",
    }


def _required_fields_answer(question: str):
    """Deterministic answer for a required-fields question, or None to defer to the LLM."""
    q = question or ""
    if not (_REQ.search(q) and _FLD.search(q)):
        return None
    meta, spec = _resolve_spec(q)
    if not spec:
        return None

    words = _resource_words(q)
    primary = (tmf_profile._collection_resources(spec) or [""])[0]
    if words:
        name, sd = _pick_schema(spec, words)
        if not sd:
            # Named a resource we can't match exactly. Only accept it if it's clearly
            # the spec's primary resource ("order" → productOrder); otherwise DEFER to
            # the LLM rather than answer about the wrong schema.
            pb = _base(primary)
            if primary and (words in pb or pb.endswith(words) or words.endswith(pb)):
                name, sd = _pick_schema(spec, primary)
        if not sd:
            return None
    else:
        name, sd = _pick_schema(spec, primary)   # "required fields in TMF622" → primary resource
    if not sd:
        return None

    req = _required(spec, sd)
    props = _properties(spec, sd)
    tmf = meta.get("tmf") or ""
    title = meta.get("title") or tmf or "TM Forum API"
    ver = meta.get("version") or ""
    disp = re.sub(r"_(Create|FVO|MVO|Update)$", "", name)

    def _clean_type(t):
        return re.sub(r"_(FVO|MVO|Create|Update)\b", "", t or "")

    def _cell(x):                                  # keep pipes/newlines from breaking the table
        return (x or "").replace("|", "/").replace("\n", " ").strip() or "—"

    all_fields = list(props.keys())
    optional = [f for f in all_fields if f not in req]
    # Lead the optional sample with business attributes; push @-meta fields to the end.
    optional_sample = [f for f in optional if not f.startswith("@")] + [f for f in optional if f.startswith("@")]
    head = f"**{tmf + ' — ' if tmf else ''}{title}{f' (v{ver})' if ver else ''}** · resource **{disp}**"

    if not req:
        md = [head, "",
              f"The **{disp}** resource has **no mandatory fields** — all {len(all_fields)} "
              f"attributes are optional in {tmf or 'the canonical spec'}."]
        if optional:
            md += ["", "Fields include " + ", ".join(f"`{f}`" for f in optional_sample[:16])
                   + ("…" if len(optional) > 16 else "") + "."]
        md += ["", "_Read directly from the canonical schema — deterministic, not generated._"]
        return {"answer": "\n".join(md), "sources": [_citation(meta, disp)], "tmf": tmf, "resource": disp}

    lines = [head, "",
             f"**{len(req)} of {len(all_fields)} fields are mandatory** — these must be provided when "
             f"creating a {disp}:", "",
             "| Field | Type | Description |", "|---|---|---|"]
    for f in req:
        t, d = _desc(spec, props.get(f, {}))
        lines.append(f"| `{f}` | {_cell(_clean_type(t))} | {_cell(d)} |")

    for f in req:                                  # expand array-of-subresource requirements
        sub_name, sub_def = _sub_schema(spec, props.get(f, {}))
        if sub_def:
            sub_req = _required(spec, sub_def)
            if sub_req:
                lines += ["", f"Each **`{f}`** ({_clean_type(sub_name)}) in turn requires: "
                          + ", ".join(f"`{r}`" for r in sub_req) + "."]

    if optional:
        lines += ["", f"The remaining **{len(optional)} attributes are optional**, including "
                  + ", ".join(f"`{f}`" for f in optional_sample[:12]) + ("…" if len(optional) > 12 else "") + "."]
    lines += ["", f"_Read directly from the {tmf or 'canonical'} schema's `required` list — "
              f"deterministic, not generated._"]
    return {"answer": "\n".join(lines), "sources": [_citation(meta, disp)], "tmf": tmf, "resource": disp}


# ── ODA component resolver ────────────────────────────────────────────────────
# "Which ODA component handles X?" is a mapping question the LLM invents answers to
# (fake components, fake domains). We answer it straight from the official 35-component
# catalog — every name and block is real by construction, so it cannot hallucinate.
_ODA_STOP = _STOP | {
    "oda", "component", "components", "handle", "handles", "handling", "manage", "manages",
    "managing", "responsible", "used", "uses", "implements", "exposes", "expose", "cover",
    "covers", "deal", "deals", "part", "domain", "block", "function", "area", "tmf",
}

# All ODA answers are derived from data, never from a lookup table we invented:
#   1. component names/blocks    — oda_components.json (official v1.0.0 component list)
#   2. component ↔ TMF API links — oda_component_apis.json (fetched from TM Forum's own
#      component Specification YAMLs in TMForum-ODA-Ready-for-publication)
#   3. TMF API titles/resources  — the local canonical spec corpus (tmf_profile index)
#   4. tie-break, optional       — the product's own embedding model (semantic, flagged)
_ODA_DATA = None


def _oda_data():
    global _ODA_DATA
    if _ODA_DATA is not None:
        return _ODA_DATA
    import oda
    cat = oda.catalog()
    try:
        comp_apis = json.load(open(os.path.join(_HERE, "oda_component_apis.json")))["components"]
    except Exception:
        comp_apis = {}
    inv = {}                                    # TMF id → (title, primary resource)
    for res, m in tmf_profile.build_index().items():
        t = (m.get("tmf") or "").upper()
        if t and t not in inv:
            inv[t] = ((m.get("title") or ""), res)
    api_idx = {}                                # TMF id → who exposes / depends on it
    for c in cat["components"]:
        for kind in ("exposed", "dependent"):
            for a in (comp_apis.get(c["code"], {}) or {}).get(kind, []):
                t = (a.get("tmf") or "").upper()
                if not re.fullmatch(r"TMF\d{3,4}", t):
                    continue
                e = api_idx.setdefault(t, {"title": inv.get(t, ("", ""))[0],
                                           "resource": inv.get(t, ("", ""))[1],
                                           "names": set(), "exposed_by": [], "dependent_of": []})
                if a.get("name"):
                    e["names"].add(a["name"])
                e["exposed_by" if kind == "exposed" else "dependent_of"].append(c["code"])
    _ODA_DATA = {"cat": cat, "comp_apis": comp_apis, "api_idx": api_idx,
                 "by_code": {c["code"]: c for c in cat["components"]}, "vecs": None}
    return _ODA_DATA


def _fold(w):
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


def _toks(s):
    return {_fold(w) for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())}


def _comp_api_titles(d, code, kind="exposed"):
    out = []
    for a in (d["comp_apis"].get(code, {}) or {}).get(kind, []):
        t = (a.get("tmf") or "").upper()
        if re.fullmatch(r"TMF\d{3,4}", t):
            title = d["api_idx"].get(t, {}).get("title") or a.get("name") or ""
            out.append(f"{t} {title}".strip())
    return out


def _oda_citation(d, extra=""):
    cat = d["cat"]
    return {
        "name": f"TM Forum ODA component map ({cat.get('release', 'v1.0.0')})",
        "file": "oda_component_apis.json", "chunk": 0,
        "preview": ("Official ODA data: the v1.0.0 component list and each component's "
                    "exposed/dependent TMF Open APIs, taken from TM Forum's published "
                    "component specifications. " + extra).strip(),
        "url": "",
    }


def _embed(texts):
    """Vectors via the product's own embedding model; None if Ollama is unavailable."""
    try:
        import requests
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("EMBED_MODEL", "nomic-embed-text")
        out = []
        for t in texts:
            r = requests.post(f"{url}/api/embeddings",
                              json={"model": model, "prompt": t}, timeout=6)
            r.raise_for_status()
            out.append(r.json()["embedding"])
        return out
    except Exception:
        return None


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def _semantic_pick(d, question):
    """Optional tier: closest component by the product's own embeddings. Returns
    (component, runner_up, margin) or None. Never invents — only ranks the real 35."""
    comps = d["cat"]["components"]
    if d["vecs"] is None:
        docs = []
        for c in comps:
            apis = _comp_api_titles(d, c["code"], "exposed") + _comp_api_titles(d, c["code"], "dependent")
            docs.append(f"{c['name']}. {d['cat']['blocks'].get(c['block'], c['block'])}. "
                        + " ".join(apis))
        d["vecs"] = _embed(docs) or False        # False = tried and unavailable
    if not d["vecs"]:
        return None
    qv = _embed([question])
    if not qv:
        return None
    scored = sorted(((_cos(qv[0], v), c) for v, c in zip(d["vecs"], comps)), key=lambda x: -x[0])
    (s1, c1), (s2, c2) = scored[0], scored[1]
    if s1 >= 0.55 and (s1 - s2) >= 0.03:
        return c1, c2, s1 - s2
    return None


def _oda_component_answer(question: str):
    """'Which ODA component …' — resolved against official TM Forum data only."""
    q = question or ""
    if not (re.search(r"\bcomponent", q, re.I)
            and re.search(r"\b(which|what|handles?|manages?|responsible|does|for|expose)", q, re.I)):
        return None
    try:
        d = _oda_data()
    except Exception:
        return None
    comps, blocks = d["cat"]["components"], d["cat"]["blocks"]
    if not comps:
        return None
    terms = {w for w in _toks(q) if w not in {_fold(x) for x in _ODA_STOP}}
    if not terms:
        return None

    def comp_answer(c, note=""):
        lines = [f"That maps to the **{c['name']}** ODA component ({c['code']}), in the "
                 f"**{blocks.get(c['block'], c['block'])}** functional block." + (f" {note}" if note else "")]
        apis = _comp_api_titles(d, c["code"], "exposed")
        if apis:
            lines.append("Per its official component specification it exposes: "
                         + " · ".join(apis) + ".")
        lines += ["", "_From TM Forum's official ODA v1.0.0 component specifications — "
                      "deterministic, not generated._"]
        return {"answer": "\n".join(lines), "sources": [_oda_citation(d)], "tmf": "", "resource": "ODA"}

    # Tier 1a — match against component NAMES (theirs, not ours).
    def cscore(c):
        nt = _toks(c["name"])
        return len(nt & terms)
    ranked = sorted(comps, key=cscore, reverse=True)
    cbest = cscore(ranked[0])
    ctops = [c for c in ranked if cscore(c) == cbest] if cbest else []

    # Tier 1b — match against the TMF APIs themselves (titles from the canonical corpus,
    # api names from the official component specs). "trouble ticket" → TMF621 lives here.
    def ascore(t, e):
        blob = _toks(e.get("title", "")) | _toks(e.get("resource", ""))
        for n in e.get("names", ()):
            blob |= _toks(n.replace("-", " "))
        return len(blob & terms)
    api_ranked = sorted(d["api_idx"].items(), key=lambda kv: ascore(*kv), reverse=True)
    abest = ascore(*api_ranked[0]) if api_ranked else 0

    if cbest >= 2 and len(ctops) == 1 and cbest >= abest:
        return comp_answer(ctops[0])

    if abest >= 2 or (abest == 1 and cbest == 0):
        tmf, e = api_ranked[0]
        title = (e.get("title") or "").strip()
        label = f"**{tmf}{' ' + title if title else ''}**"
        lines = [f"That capability is the {label} Open API."]
        if e["exposed_by"]:
            names = [f"**{d['by_code'][x]['name']}** ({x})" for x in sorted(set(e["exposed_by"]))]
            lines.append(f"In the official ODA v1.0.0 map it is exposed by { ' and '.join(names) }.")
        else:
            lines.append("In the official ODA v1.0.0 component map, **no component exposes "
                         f"{tmf} directly**.")
            if e["dependent_of"]:
                names = [f"**{d['by_code'][x]['name']}** ({x})" for x in sorted(set(e["dependent_of"]))]
                lines.append(f"It appears as a *dependent* API of { ', '.join(names) }.")
        if not e["exposed_by"] and not e["dependent_of"]:
            sem = _semantic_pick(d, q)
            if sem:
                c1, _c2, _m = sem
                lines.append(f"Functionally closest component (semantic match, for orientation): "
                             f"**{c1['name']}** ({c1['code']}).")
        lines += ["", "_From TM Forum's official ODA v1.0.0 component specifications — "
                      "deterministic, not generated._"]
        return {"answer": "\n".join(lines), "sources": [_oda_citation(d)], "tmf": tmf, "resource": "ODA"}

    if cbest >= 1 and len(ctops) == 1:
        return comp_answer(ctops[0])
    if cbest >= 1:
        lines = ["Several official ODA components match:"]
        for c in ctops[:4]:
            lines.append(f"- **{c['name']}** ({c['code']}) — {blocks.get(c['block'], c['block'])} block")
        lines += ["", "_From the official TM Forum ODA component map — deterministic, not generated._"]
        return {"answer": "\n".join(lines), "sources": [_oda_citation(d)], "tmf": "", "resource": "ODA"}

    # Tier 2 — semantic (the product's own embeddings), clearly flagged, real components only.
    sem = _semantic_pick(d, q)
    if sem:
        c1, c2, _m = sem
        return comp_answer(c1, note=f"(Closest match by semantic similarity; runner-up: "
                                    f"{c2['name']}, {c2['code']}.)")

    # Nothing defensible → honest non-answer grounded in the real map.
    sample = ", ".join(f"**{c['name']}** ({c['code']})" for c in comps[:6])
    md = ("I couldn't map that to a specific ODA component with confidence — so I won't guess. "
          f"The official TM Forum ODA map has **{len(comps)} components** across "
          f"**{len(blocks)} functional blocks**, including {sample}… "
          "Browse them all on the **ODA Map**.")
    return {"answer": md, "sources": [_oda_citation(d)], "tmf": "", "resource": "ODA"}


def oda_grounding(question: str) -> str:
    """Prompt-grounding for ODA questions that still reach the LLM: pin it to the real
    component list so it cannot invent names or blocks."""
    if not re.search(r"\boda\b|\bcomponent", question or "", re.I):
        return ""
    try:
        d = _oda_data()
    except Exception:
        return ""
    names = "; ".join(f"{c['code']} {c['name']}" for c in d["cat"]["components"])
    blocks = ", ".join(d["cat"]["blocks"].values())
    return ("\n\nODA GROUND TRUTH (authoritative, overrides retrieved text): the official "
            f"TM Forum ODA v1.0.0 map has exactly these components: {names}. "
            f"The only functional blocks are: {blocks}. When discussing ODA components, use "
            "ONLY these names and codes; if none fits the question, say the official map has "
            "no such component. Never invent a component or block name.")


def answer(question: str):
    """Deterministic answer for a structured question, or None to defer to the LLM.
    Tries required-fields first, then the ODA component map."""
    return _required_fields_answer(question) or _oda_component_answer(question)


if __name__ == "__main__":
    import sys
    tmf_profile.build_index()
    r = answer(" ".join(sys.argv[1:]) or "What mandatory fields does TMF622 Product Order require?")
    print(r["answer"] if r else "(no deterministic answer — would defer to the LLM)")
