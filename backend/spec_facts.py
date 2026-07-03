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


def answer(question: str):
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


if __name__ == "__main__":
    import sys
    tmf_profile.build_index()
    r = answer(" ".join(sys.argv[1:]) or "What mandatory fields does TMF622 Product Order require?")
    print(r["answer"] if r else "(no deterministic answer — would defer to the LLM)")
