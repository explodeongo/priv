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
import glob
import json
import os
import re

import tmf_profile
from conformance import _schemas, _resolve_ref

_HERE = os.path.dirname(os.path.abspath(__file__))

# Intent: the question must be about which fields are *required* (not "explain X").
# Broadened to also catch the complementary framing ("which fields can be omitted",
# "what's optional") — same underlying fact, the required/optional partition.
_REQ = re.compile(r"\b(mandator(?:y|ies)|required|require[sd]?|requiring|need(?:ed|s)?|"
                  r"omit(?:s|ted|ting)?|optional)\b", re.I)
_FLD = re.compile(r"\b(field|attribute|propert|schema|(?:required|properties)\s+array)s?\b", re.I)
_TMF = re.compile(r"\bTMF\s?0*(\d{2,4})\b", re.I)
_STOP = {
    "what", "whats", "which", "whose", "does", "do", "did", "the", "a", "an", "of", "for", "in", "on",
    "is", "are", "to", "how", "require", "requires", "required", "mandatory", "optional", "fields",
    "field", "attributes", "attribute", "property", "properties", "schema", "schemas", "list", "show",
    "tell", "me", "about", "and", "or", "resource", "resources", "entity", "object", "model", "open", "api", "apis",
    "need", "needs", "needed", "have", "has", "with", "please", "give", "when", "creating", "create",
    "valid", "must", "define", "defines", "contain", "contains",
    # Procedural/"show your work" phrasing (governance/citation questions) — generic
    "raw", "exact", "path", "array", "you", "used", "use", "using", "determine", "determined",
    "creation", "return", "only", "literal", "literally", "verbatim", "explain", "infer",
    "not", "don't", "dont",
    # Predicate/intent vocabulary — never a resource OR property NAME, so it must never
    # survive as a property candidate ("does X exist", "is X present"). Completes the
    # _PROPERTY_INTENT / _GOVERNANCE_SHAPE surface so candidate extraction can accept any
    # OTHER surviving token as the target property without these leaking in.
    "requiring", "omit", "omits", "omitted", "omitting", "exist", "exists", "existing",
    "containing", "present", "absent", "invalid", "allowed", "permitted", "declared",
    # Demonstratives/pronouns — a reference to a field named elsewhere ("is THAT field
    # mandatory", "does TMF622 require IT"), not a property name; must not be mistaken
    # for a fabricated property and classified UNKNOWN.
    "that", "this", "these", "those", "it", "its", "them", "they", "there",
    # Once candidate extraction accepts arbitrary lowercase identifiers as property
    # names (so "action"/"id"/"state" work), plain FUNCTION words must be filtered too,
    # or they get misread as fabricated properties. None of these is ever a TMF resource
    # or property name. Quantifiers (so "does ANY schema…" / "ALL fields…" don't leak),
    # injection/imperative verbs (so "IGNORE the schema and tell me…" strips cleanly),
    # confirmations, modals, and common prepositions/conjunctions.
    "any", "all", "every", "each", "none", "some", "both", "other", "others", "another",
    "several", "many", "few", "no",
    "ignore", "disregard", "forget", "pretend", "override", "bypass", "assume", "suppose",
    "imagine", "insist", "claim", "claims", "confirm", "say", "says", "said",
    "correct", "right", "yes", "true", "false", "sure", "actually", "really", "obviously",
    "clearly", "simply", "just", "kind", "sort",
    "can", "could", "would", "should", "will", "shall", "may", "might", "be", "been",
    "being", "was", "were", "am",
    "at", "by", "as", "if", "but", "so", "than", "then", "because", "while", "within",
    "between", "across", "per", "into", "onto", "up",
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


_VERTOK = re.compile(r"\bv\d+(?:\.\d+){0,2}\b|\b\d+\.\d+\.\d+\b", re.I)


def _resource_words_list(q):
    """Non-stopword, non-TMF-id, non-version tokens from the question, IN ORDER — the
    raw material for resource matching. Kept as a list (not glued into one blob) so a
    resource name can be found even when it shares the sentence with words we don't
    recognize (a confirmation, a challenge, a "show your work" preamble): matching
    tries contiguous runs of this list, not the whole remainder at once."""
    cleaned = re.sub(r"\bTMF\s?\d{2,4}\b", " ", q or "", flags=re.I)
    cleaned = _VERTOK.sub(" ", cleaned)
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", cleaned)
    return [w for w in words if w.lower() not in _STOP and len(w) > 1]


def _resource_words(q):
    """Resource tokens from the question, glued into one lowercase blob — the exact
    match this product's earlier behaviour relied on ("required fields in TMF622" ->
    the whole remainder IS the resource name). Version tokens are stripped first
    ("v5.0.0", "v5"), otherwise a question that names an exact version corrupts this
    blob ("v5productorder" matches no schema)."""
    return "".join(_resource_words_list(q)).lower()


def _match_resource(spec, q):
    """(name, schema-def) for the resource this question is about. Tries the fullest
    contiguous run of resource-ish words first (identical to the old whole-blob
    behaviour) and shrinks the window until some contiguous run exactly matches a
    schema — so a resource name doesn't have to be the ENTIRE remainder of the
    question. This is the same idea `_oda_component_answer` already uses (token-set
    overlap instead of full-string equality), applied here as ordered n-grams so the
    existing exact-match `_pick_schema` contract doesn't have to change.

    Within each length, a run whose first word is Capitalized is tried before one that
    starts lowercase. `_pick_schema` matches case-insensitively, so a lowercase-leading
    token like "productOrderItem" (this corpus's PROPERTY-naming convention, TMF630
    rule R8) would otherwise be able to match the schema "ProductOrderItem" and steal
    the resource slot from the actual intended resource named elsewhere in the same
    sentence ("...productOrderItem mandatory in ProductOrder?" is asking about
    ProductOrder, using productOrderItem only as the property under discussion).
    Longest-first, capitalized-first, left-to-right means the resource named early
    ("ProductOrder requires...") is found before an incidental field name mentioned
    later ("...requires billingAccount") could ever be tried as a candidate on its own."""
    words = _resource_words_list(q)
    n = len(words)
    for length in range(n, 0, -1):
        starts = sorted(range(0, n - length + 1), key=lambda s: not words[s][:1].isupper())
        for start in starts:
            cand = "".join(words[start:start + length]).lower()
            name, sd = _pick_schema(spec, cand)
            if sd:
                return name, sd
    return None, None


_SPEC_FILES_CACHE: dict = {}


def _spec_files_for(api_id: str) -> list:
    """Every canonical file for `api_id` — {file, version, tmf, title} — found by
    scanning the corpus directly, INDEPENDENT of tmf_profile's build_index(). That index
    keeps only one file per *primary resource* key (the first-declared collection path),
    so two versions of the same API can end up filed under different, unrelated-looking
    keys (TMF622 v4's first path is /productOrder, v5's is /cancelProductOrder — v5 is
    filed under "cancelproductorder"); relying on it to answer "which versions of TMF622
    exist" is fragile. This walks data/ once per api_id (cached) and is the version-of-
    record for explicit version resolution and for `_known_versions`."""
    if not api_id:
        return []
    if api_id in _SPEC_FILES_CACHE:
        return _SPEC_FILES_CACHE[api_id]
    out = []
    for f in glob.glob(os.path.join(_HERE, "data", "**", "*"), recursive=True):
        base = os.path.basename(f)
        if api_id.upper() not in base.upper():
            continue
        mver = tmf_profile._CANON.search(base)
        if not mver:
            continue
        sp = tmf_profile._load(f)
        if not isinstance(sp, dict):
            continue
        out.append({
            "file": os.path.relpath(f, _HERE),
            "version": mver.group(1),
            "tmf": api_id,
            "title": (sp.get("info", {}) or {}).get("title", base),
        })
    _SPEC_FILES_CACHE[api_id] = out
    return out


def _requested_version(q: str):
    """The single explicit version the question asks for ('v5.0.0', '5.0.0'), or None.
    Only a full major.minor.patch is treated as an explicit request — TM Forum versions
    in this corpus are always X.Y.Z, and requiring the full form avoids a bare number
    elsewhere in the question (an id, a count) being mistaken for a version."""
    m = re.search(r"\bv?(\d+\.\d+\.\d+)\b", q or "", re.I)
    return m.group(1) if m else None


def _requested_versions(q: str) -> list:
    """Every distinct explicit version mentioned, in the order they appear — for
    comparison questions naming two versions at once."""
    seen, out = set(), []
    for m in re.finditer(r"\bv?(\d+\.\d+\.\d+)\b", q or "", re.I):
        v = m.group(1)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _resolve_spec(q):
    """(meta, spec) for the TMF API named or detected in the question, or (None, None)
    if nothing resolves at all. When an explicit TMF id is present, resolution is
    version-aware: an explicitly-stated version ("TMF622 v4.0.0") resolves THAT exact
    file via `_spec_files_for`, never a different one, and if that version isn't in the
    corpus this returns (None, None) — the caller (`required_fields_fact`) checks for
    that case up front and surfaces it as an explicit unresolved result rather than
    treating it as silent "not a fields question". Only when NO version is stated does
    "latest wins" apply, so an unqualified question's answer is predictable regardless
    of phrasing."""
    idx = tmf_profile.build_index()
    m = _TMF.search(q or "")
    if m:
        tmf = "TMF" + m.group(1).zfill(3)
        files = _spec_files_for(tmf)
        if files:
            ver = _requested_version(q)
            if ver:
                match = [f for f in files if f["version"] == ver]
                if not match:
                    return None, None                  # explicit version not in the corpus
                meta = match[0]
            else:
                meta = max(files, key=lambda f: tmf_profile._version_key(f["version"]))
            sp = tmf_profile._load(os.path.join(_HERE, meta["file"]))
            return (meta, sp) if isinstance(sp, dict) else (None, None)
        cands = [mt for mt in idx.values() if (mt.get("tmf") or "").upper() == tmf]
    else:
        cands = []
    if not cands:
        # No explicit TMF id — try contiguous n-grams of the kept words (longest first,
        # same idea as `_match_resource`) against the resource-keyed index, not just the
        # whole remainder glued into one blob: "fakeCustomerMood a valid ProductOrder
        # property" must still find "ProductOrder" even though another identifier-
        # looking word shares the sentence.
        words = _resource_words_list(q)
        n = len(words)
        for length in range(n, 0, -1):
            for start in range(0, n - length + 1):
                cand = "".join(words[start:start + length]).lower()
                for key in (cand, cand.rstrip("s")):
                    if key and key in idx:
                        cands = [idx[key]]
                        break
                if cands:
                    break
            if cands:
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


def _clean_type(t):
    return re.sub(r"_(FVO|MVO|Create|Update)\b", "", t or "")


def _cell(x):                                      # keep pipes/newlines from breaking the table
    return (x or "").replace("|", "/").replace("\n", " ").strip() or "—"


def _build_required_fields_fact(meta: dict, spec: dict, q: str):
    """Given an ALREADY-resolved (meta, spec) for one specific API+version, match the
    resource this question is about and build its VerifiedFactResult, or None if no
    resource/intent matches. Shared by single-version resolution
    (`required_fields_fact`) and independent per-version resolution inside a comparison
    (`required_fields_comparison`) — each version is resolved through this exact same
    logic, never a special-cased copy."""
    primary = (tmf_profile._collection_resources(spec) or [""])[0]
    name, sd = _match_resource(spec, q)
    if not sd:
        # No contiguous run of words matched a schema exactly. Only fall back to the
        # API's primary resource when it's a clear near-miss ("order" -> productOrder)
        # or the question used generic field/schema language with no resource named
        # at all ("required fields for TMF622"); otherwise DEFER rather than answer
        # about the wrong schema.
        words = _resource_words(q)
        pb = _base(primary)
        if words and primary and (words in pb or pb.endswith(words) or words.endswith(pb)):
            name, sd = _pick_schema(spec, primary)
        elif not words and _FLD.search(q):
            name, sd = _pick_schema(spec, primary)
    if not sd:
        return None

    req = _required(spec, sd)
    props = _properties(spec, sd)

    if not _FLD.search(q):
        # No generic "field/schema" language — only proceed if the question names one
        # of THIS resolved resource's own real properties (data-driven, never a phrase
        # list): "does X require billingAccount", "is description required", "confirm
        # billingAccount as mandatory". Otherwise the _REQ match was coincidental
        # ("is TMF622 required for certification?") and this isn't a fields question.
        q_tokens = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", q)}
        prop_tokens = {p.lstrip("@").lower() for p in props}
        if not (prop_tokens & q_tokens):
            return None

    tmf = meta.get("tmf") or ""
    title = meta.get("title") or tmf or "TM Forum API"
    ver = meta.get("version") or ""
    disp = re.sub(r"_(Create|FVO|MVO|Update)$", "", name)

    field_info = {f: dict(zip(("type", "description"), _desc(spec, props.get(f, {})))) for f in req}
    field_info = {f: {"type": _clean_type(v["type"]), "description": v["description"]} for f, v in field_info.items()}

    nested = {}                                      # array-of-subresource requirements, resolved once
    for f in req:
        sub_name, sub_def = _sub_schema(spec, props.get(f, {}))
        if sub_def:
            sub_req = _required(spec, sub_def)
            if sub_req:
                nested[f] = {"schema": _clean_type(sub_name), "required": sub_req}

    _, prefix = tmf_profile._container(spec, "schemas")  # literal JSON pointer to the ACTUAL matched
    schema_path = prefix + name                          # schema (e.g. the _FVO variant), not the display name

    citation = _citation(meta, disp)
    return {
        "status": "RESOLVED",
        "fact_type": "REQUIRED_FIELDS",
        "api_id": tmf,
        "version": ver,
        "title": title,
        "resource_or_schema": disp,
        "schema_name": name,
        "schema_path": schema_path,
        "facts": {
            "required": req,
            "optional": [f for f in props if f not in req],
            "nested_required": nested,
            "field_info": field_info,
        },
        "source_asset": citation["name"],
        "source_file": meta.get("file", ""),
        "extraction_method": "SCHEMA_DIRECT",
        "citation": citation,
    }


def _unresolved_version_fact(api_id: str, requested_version: str) -> dict:
    """An explicit VerifiedFactResult 'non-answer': the question is unambiguously a
    required-fields question naming a version we cannot deterministically resolve.
    The caller must show this to the user, NOT fall through to mixed-version RAG."""
    return {
        "status": "UNRESOLVED",
        "fact_type": "REQUIRED_FIELDS",
        "api_id": api_id,
        "requested_version": requested_version,
        "available_versions": sorted(_known_versions(api_id), key=tmf_profile._version_key),
        "reason": "VERSION_NOT_FOUND",
    }


def required_fields_fact(question: str):
    """The VerifiedFactResult for a required-fields question: everything the deterministic
    resolver established, as data (not prose) — api/version/schema identity, the literal
    schema path, and the exact required/optional field sets.

    Returns None when this isn't a required-fields question at all (the caller defers to
    the LLM/RAG, or to `oda_answer`). Returns a `status: "UNRESOLVED"` object — NOT None
    — when the question unambiguously names a TMF API and an explicit version that isn't
    in the corpus: that must surface as an explicit non-answer, never a silent fall-through
    to mixed-version RAG that then answers as if it had resolved something.

    This is the single place that resolves a single-version fact; both the rich Markdown
    template (`render_fact_markdown`) and the raw/no-explanation formatter
    (`raw_fact_answer`) render from this object rather than re-deriving it, and
    `required_fields_comparison` resolves each side of a comparison through the same
    underlying `_build_required_fields_fact`, so there is exactly one source of truth."""
    q = question or ""
    if not _REQ.search(q):
        return None

    m = _TMF.search(q)
    if m:
        api_id = "TMF" + m.group(1).zfill(3)
        ver = _requested_version(q)
        if ver and not any(f["version"] == ver for f in _spec_files_for(api_id)):
            return _unresolved_version_fact(api_id, ver)

    meta, spec = _resolve_spec(q)
    if not spec:
        return None

    fact = _build_required_fields_fact(meta, spec, q)
    if not fact:
        return None

    # Defence in depth: whatever _resolve_spec did internally, the version it landed on
    # must match an explicitly-requested version exactly — never silently substitute.
    ver = _requested_version(q)
    if ver and fact["version"] != ver:
        return _unresolved_version_fact(fact["api_id"], ver)
    return fact


def render_fact_markdown(fact: dict) -> dict:
    """The exact hand-authored rich answer previously built inline by
    `_required_fields_answer` — now rendered purely from the VerifiedFactResult. This is
    also the deterministic fallback used when a grounded LLM answer fails integrity
    validation (Phase 7), so it must never depend on anything the LLM produced."""
    tmf, ver, disp, title = fact["api_id"], fact["version"], fact["resource_or_schema"], fact["title"]
    req, optional = fact["facts"]["required"], fact["facts"]["optional"]
    all_n = len(req) + len(optional)
    # Lead the optional sample with business attributes; push @-meta fields to the end.
    optional_sample = [f for f in optional if not f.startswith("@")] + [f for f in optional if f.startswith("@")]
    head = f"**{tmf + ' — ' if tmf else ''}{title}{f' (v{ver})' if ver else ''}** · resource **{disp}**"

    if not req:
        md = [head, "",
              f"The **{disp}** resource has **no mandatory fields** — all {all_n} "
              f"attributes are optional in {tmf or 'the canonical spec'}."]
        if optional:
            md += ["", "Fields include " + ", ".join(f"`{f}`" for f in optional_sample[:16])
                   + ("…" if len(optional) > 16 else "") + "."]
        md += ["", "_Read directly from the canonical schema — deterministic, not generated._"]
        return {"answer": "\n".join(md), "sources": [fact["citation"]], "tmf": tmf, "resource": disp}

    lines = [head, "",
             f"**{len(req)} of {all_n} fields are mandatory** — these must be provided when "
             f"creating a {disp}:", "",
             "| Field | Type | Description |", "|---|---|---|"]
    for f in req:
        info = fact["facts"]["field_info"].get(f, {"type": "", "description": ""})
        lines.append(f"| `{f}` | {_cell(info['type'])} | {_cell(info['description'])} |")

    for f in req:                                  # expand array-of-subresource requirements
        nest = fact["facts"]["nested_required"].get(f)
        if nest:
            lines += ["", f"Each **`{f}`** ({nest['schema']}) in turn requires: "
                      + ", ".join(f"`{r}`" for r in nest["required"]) + "."]

    if optional:
        lines += ["", f"The remaining **{len(optional)} attributes are optional**, including "
                  + ", ".join(f"`{f}`" for f in optional_sample[:12]) + ("…" if len(optional) > 12 else "") + "."]
    lines += ["", f"_Read directly from the {tmf or 'canonical'} schema's `required` list — "
              f"deterministic, not generated._"]
    return {"answer": "\n".join(lines), "sources": [fact["citation"]], "tmf": tmf, "resource": disp}


def _required_fields_answer(question: str):
    """Deterministic answer for a required-fields question, or None to defer to the LLM."""
    fact = required_fields_fact(question)
    return render_fact_markdown(fact) if fact else None


# ── Phase 4: explicit raw-evidence requests bypass rich generation entirely ───────────
# "Show me the exact schema path and raw required array. Do not explain or infer." must
# get the literal deterministic fields back, not a generated table — no LLM involved.
_RAW_INTENT = re.compile(
    r"do\s+not\s+(?:explain|infer)|don'?t\s+(?:explain|infer)|without\s+(?:explaining|inferring)|"
    r"no\s+explanation|raw\s+(?:required\s+)?array|json\s*pointer|exact\s+schema\s+path|"
    r"schema\s+path\s+and\s+raw|literal(?:ly)?\s+(?:the\s+)?required|verbatim|"
    r"return\s+only|just\s+the\s+(?:raw|schema|required|facts?)\b",
    re.I,
)


def wants_raw(question: str) -> bool:
    """True when the question explicitly asks for raw/unexplained deterministic output
    (Phase 4) — the previously-observed failure mode was ignoring this and generating a
    Markdown table anyway."""
    return bool(_RAW_INTENT.search(question or ""))


def raw_fact_answer(fact: dict) -> dict:
    """Exact literal deterministic fields for an explicit raw/no-explanation request —
    no LLM synthesis, no Markdown table, no prose. Every value is copied verbatim from
    the VerifiedFactResult; nothing here is generated."""
    lines = [
        f"api_id: {fact['api_id']}",
        f"version: {fact['version']}",
        f"schema: {fact['schema_name']}",
        f"schema_path: {fact['schema_path']}",
        f"required: {json.dumps(fact['facts']['required'])}",
        f"source_file: {fact['source_file']}",
    ]
    return {"answer": "\n".join(lines), "sources": [fact["citation"]],
            "tmf": fact["api_id"], "resource": fact["resource_or_schema"]}


def unresolved_answer(fact: dict) -> dict:
    """Deterministic, explicit non-answer for a required-fields question whose requested
    version could not be resolved. No LLM, no sources (nothing was resolved to cite),
    and — critically — this is NEVER a fall-through to mixed-version RAG: the caller
    must show exactly this instead of silently answering from a different version."""
    avail = ", ".join(fact.get("available_versions") or []) or "none indexed"
    msg = (f"I can't resolve {fact['api_id']} v{fact['requested_version']} — the versions "
           f"of {fact['api_id']} I have indexed are: {avail}. I won't answer by substituting "
           "a different version's schema.")
    return {"answer": msg, "sources": [], "tmf": fact.get("api_id", ""), "resource": ""}


# ── Phase 3: grounded-generation bridge ───────────────────────────────────────────────
# Deterministic resolution already produced the VerifiedFactResult above. These functions
# hand it to an LLM as locked ground truth so the answer can be rich and explanatory
# without ever becoming the source of truth for the fact itself.
def grounded_instructions(fact: dict) -> str:
    """System-prompt addendum that locks the model to `fact`. Appended the same way
    `oda_grounding` pins ODA answers to the real component list."""
    f = fact["facts"]
    nested = "; ".join(
        f"{k} ({v['schema']}) requires: {', '.join(v['required'])}" for k, v in f["nested_required"].items()
    )
    return (
        "\n\nVERIFIED FACTS (locked ground truth, already extracted from the canonical schema — "
        "not retrieved text, not your own knowledge):\n"
        f"- API: {fact['api_id']} v{fact['version']} ({fact['title']})\n"
        f"- Resource/schema: {fact['resource_or_schema']} ({fact['schema_name']}, at {fact['schema_path']})\n"
        f"- Required fields, exact and complete: {json.dumps(f['required'])}\n"
        f"- Optional fields: {json.dumps(f['optional'])}\n"
        + (f"- Nested requirements: {nested}\n" if nested else "")
        + f"- Source: {fact['source_asset']} ({fact['source_file']})\n\n"
        "These facts are IMMUTABLE. You may explain them, contextualize them, organize the "
        "answer, and add useful detail so it is rich and informative — but you must NOT add, "
        "remove, rename, or alter any required field; must NOT change the api id or version "
        f"(it is {fact['api_id']} v{fact['version']} — never a different version, even one you "
        "recall from training); must NOT claim a different source; and must NOT present any "
        "field beyond the exact required list above as if it were also mandatory. If you "
        "describe nested/child structures beyond the 'Nested requirements' given, make clear "
        "that part is explanatory, not itself a verified requirement. Wrap every field name in "
        "backticks (e.g. `productOrderItem`), matching the fields listed above exactly. Do not "
        "merely restate the facts tersely — teach: explain what the fields mean, how they fit "
        "together, and why they matter, the way a knowledgeable colleague would."
    )


def _known_versions(api_id: str) -> set:
    """Every version of `api_id` actually present in the corpus. Used to catch a
    generated answer that names a version other than the one resolved (and to list
    the available versions in an unresolved-version result). Thin wrapper over
    `_spec_files_for`, which already scans the corpus directly and caches per api_id."""
    return {f["version"] for f in _spec_files_for(api_id)}


_REQUIRED_LANG = re.compile(r"\b(required|mandatory|must\s+(?:be\s+)?\w*(?:provid|includ|specif|set|submit)\w*)\b", re.I)
# A hedge/denial ("X is not required") must be recognized in however a model naturally
# phrases it — a contraction ("isn't"), an adverb ("not actually required"), or an
# article ("not a required field") all mean the same thing as the literal two-word
# "not required", but none of them matched the original strict \bnot\s+required\b. That
# under-matching was the actual live bug: a model correctly denying a field was
# required got misread as claiming it WAS required, because its hedge went unrecognized,
# and the whole rich answer was discarded for a false positive. Allow up to 3 words
# between the negator and required/mandatory to cover these natural phrasings.
_OPTIONAL_LANG = re.compile(
    r"\boptional\b|"
    r"\b(?:not|isn.t|wasn.t|aren.t|weren.t|doesn.t|didn.t|don.t|never|no\s+longer)\b"
    r"(?:\s+\S+){0,3}?\s+(?:required|mandatory)\b|"
    r"\bmay\s+(?:be\s+)?\w*(?:provid|includ)\w*\b",
    re.I,
)
_BACKTICK_FIELD = re.compile(r"`(@?[A-Za-z][A-Za-z0-9]*)`")


def _claimed_as_required(text: str, verified_required: set) -> list:
    """Backticked field names the answer text asserts are required/mandatory in the same
    breath (same sentence/table row) without also hedging with 'optional'/'not required',
    that are NOT in `verified_required` — catches both a real-but-optional field promoted
    to required AND a fully fabricated field name, uniformly. Relies on the field-in-
    backticks convention this product's answers already use (and that the grounded prompt
    asks for) — a heuristic, but a deterministic and testable one, not another LLM call."""
    hits = set()
    for seg in re.split(r"[.\n]|\s\|\s", text or ""):
        if not _REQUIRED_LANG.search(seg) or _OPTIONAL_LANG.search(seg):
            continue
        for f in _BACKTICK_FIELD.findall(seg):
            if f not in verified_required:
                hits.add(f)
    return sorted(hits)


def validate_grounded_answer(fact: dict, text: str, question: str = ""):
    """Phase 7 integrity gate: does `text` preserve the VerifiedFactResult? Programmatic
    checks only (never 'ask the LLM if the LLM is right'). Returns (ok, reasons)."""
    reasons = []
    t = text or ""
    if not t.strip():
        return False, ["empty_generation"]

    api_id, version = fact.get("api_id", ""), fact.get("version", "")
    if api_id and api_id not in t:
        reasons.append(f"api_identity_missing: {api_id} not found in answer")

    if version:
        if version not in t and f"v{version}" not in t:
            reasons.append(f"version_missing: {version} not found in answer")
        for other in sorted(_known_versions(api_id) - {version}):
            if other in t:
                reasons.append(f"version_conflict: sibling version {other} appears in answer")

    for f in fact["facts"]["required"]:
        if f not in t:
            reasons.append(f"required_field_dropped: {f}")

    # Nested requirements (Phase 3.2's "separately resolved evidence") are also verified
    # facts, just for a child schema — legitimate to mention as required, so they must
    # not trip the "added a field" check the way a real-optional or fabricated field would.
    verified = set(fact["facts"]["required"])
    for nest in fact["facts"]["nested_required"].values():
        verified |= set(nest["required"])
    for f in _claimed_as_required(t, verified):
        reasons.append(f"required_field_added: {f}")

    # Phase 6 extension: if the ORIGINAL question singled out one specific property that
    # ISN'T among this resource's own properties at all (a challenge like "is
    # `fakeCustomerMood` optional?" embedded in an otherwise-normal fields question), the
    # generated answer must not call it optional or required — an unknown property is
    # neither, no matter how the question was phrased ("ignore the schema...", "confirm
    # this...").
    if question:
        known = set(fact["facts"]["required"]) | set(fact["facts"]["optional"])
        prop, is_known = _extract_target_property(
            question, known, exclude={fact.get("resource_or_schema", ""), fact.get("schema_name", "")})
        if prop and not is_known and prop in t:
            unknown_hits = set()
            for seg in re.split(r"[.\n]|\s\|\s", t):
                if prop not in seg:
                    continue
                if _OPTIONAL_LANG.search(seg):
                    unknown_hits.add(f"unknown_property_claimed_optional: {prop}")
                if _REQUIRED_LANG.search(seg) and not _OPTIONAL_LANG.search(seg):
                    unknown_hits.add(f"unknown_property_claimed_required: {prop}")
            reasons.extend(sorted(unknown_hits))

    return (len(reasons) == 0, reasons)


def grounded_answer(question: str, fact: dict, generate) -> dict:
    """DETERMINISTIC RESOLUTION -> VERIFIED FACT OBJECT -> GROUNDED LLM GENERATION ->
    INTEGRITY VALIDATION -> RESPONSE. `generate(question, extra_instructions) -> str`
    is injected so this stays unit-testable without a live LLM (this repo's tests are
    "pure & offline (no server, no Ollama)"). On any integrity failure, falls back to
    the exact deterministic template and logs why — it never retries and never lets a
    contradicted answer through."""
    result = render_fact_markdown(fact)
    try:
        text = generate(question, grounded_instructions(fact))
    except Exception as e:
        text = ""
        print(f"[integrity] grounded generation failed for {fact.get('api_id')} "
              f"v{fact.get('version')}: {type(e).__name__}: {e}", flush=True)
    ok, reasons = validate_grounded_answer(fact, text, question)
    if ok:
        result = {**result, "answer": text}
    elif text.strip():
        print(f"[integrity] grounded answer rejected for {fact.get('api_id')} "
              f"v{fact.get('version')}: {reasons} — falling back to deterministic answer", flush=True)
    result["grounded"] = ok
    return result


# ── Comparison: two independently-resolved VerifiedFactResults ───────────────────────
# COMPARE REQUIRED FIELDS -> resolve version A -> VerifiedFactResult A
#                         -> resolve version B -> VerifiedFactResult B
#                         -> deterministic comparison object
#                         -> grounded generation -> comparison integrity validation
# Each version is resolved through the exact same `_build_required_fields_fact` used by
# a single-version question — never a special-cased copy — so "compare v4.0.0 and
# v5.0.0" cannot merge them into one answer the way plain unscoped resolution did.
_COMPARE_INTENT = re.compile(r"\b(compare|comparison|compared|differ(?:s|ent|ence|ences)?|vs\.?|versus)\b", re.I)


def required_fields_comparison(question: str):
    """The comparison VerifiedFactResult for 'compare required fields between vA and
    vB' questions, or None if this isn't a multi-version comparison at all (the caller
    falls back to `required_fields_fact` for a normal single-version question)."""
    q = question or ""
    if not (_REQ.search(q) and _COMPARE_INTENT.search(q)):
        return None
    m = _TMF.search(q)
    if not m:
        return None
    versions = _requested_versions(q)
    if len(versions) < 2:
        return None                                  # only one (or no) version named — not a comparison
    api_id = "TMF" + m.group(1).zfill(3)
    files = _spec_files_for(api_id)

    loaded = {}
    for v in versions[:2]:
        match = next((f for f in files if f["version"] == v), None)
        sp = tmf_profile._load(os.path.join(_HERE, match["file"])) if match else None
        loaded[v] = (match, sp if isinstance(sp, dict) else None)

    # A RESOURCE comparison needs the same resource identifiable in at least one of the
    # two versions — if neither spec names one at all, this isn't "compare resource X
    # between vA and vB" (e.g. it's "compare where description is required across v4
    # and v5" — a property-aggregation comparison instead); defer so that path can own
    # it, rather than reporting a misleading VERSION_NOT_FOUND when both versions
    # genuinely exist in the corpus.
    if not any(sp and _match_resource(sp, q)[1] for _match, sp in loaded.values()):
        return None

    results = []
    for v in versions[:2]:
        match, sp = loaded[v]
        fact = _build_required_fields_fact(match, sp, q) if (match and sp) else None
        results.append(fact or _unresolved_version_fact(api_id, v))

    if any(r["status"] != "RESOLVED" for r in results):
        return {
            "status": "UNRESOLVED",
            "fact_type": "REQUIRED_FIELDS_COMPARISON",
            "api_id": api_id,
            "requested_versions": versions[:2],
            "results": results,
        }

    a, b = results
    req_a, req_b = set(a["facts"]["required"]), set(b["facts"]["required"])
    return {
        "status": "RESOLVED",
        "fact_type": "REQUIRED_FIELDS_COMPARISON",
        "api_id": api_id,
        "versions": [a["version"], b["version"]],
        "results": [a, b],
        "identical": req_a == req_b,
        "only_in_a": sorted(req_a - req_b),
        "only_in_b": sorted(req_b - req_a),
        "common": sorted(req_a & req_b),
    }


def render_comparison_markdown(comparison: dict) -> dict:
    """Deterministic Markdown for a resolved comparison — also the fallback when a
    grounded comparison answer fails integrity validation."""
    api_id = comparison["api_id"]
    va, vb = comparison["versions"]
    a, b = comparison["results"]
    head = f"**{api_id}** — required-field comparison, **v{va}** vs **v{vb}**"
    lines = [head, ""]
    if comparison["identical"]:
        lines.append(f"The mandatory field sets are **identical**: "
                      + ", ".join(f"`{f}`" for f in comparison["common"]) + ".")
    else:
        lines += ["| Field | v" + va + " | v" + vb + " |", "|---|---|---|"]
        for f in comparison["common"]:
            lines.append(f"| `{f}` | required | required |")
        for f in comparison["only_in_a"]:
            lines.append(f"| `{f}` | required | not required |")
        for f in comparison["only_in_b"]:
            lines.append(f"| `{f}` | not required | required |")
    lines += ["", f"_Compared directly from each version's own `required` list "
                  f"({a['source_file']} · {b['source_file']}) — deterministic, not generated._"]
    return {"answer": "\n".join(lines),
            "sources": [a["citation"], b["citation"]],
            "tmf": api_id, "resource": comparison["results"][0]["resource_or_schema"]}


def raw_comparison_answer(comparison: dict) -> dict:
    """Literal deterministic comparison fields for an explicit raw/no-explanation
    request — no LLM synthesis, no prose."""
    api_id = comparison["api_id"]
    va, vb = comparison["versions"]
    a, b = comparison["results"]
    lines = [
        f"api_id: {api_id}",
        f"version_a: {va}", f"required_a: {json.dumps(a['facts']['required'])}", f"schema_path_a: {a['schema_path']}",
        f"version_b: {vb}", f"required_b: {json.dumps(b['facts']['required'])}", f"schema_path_b: {b['schema_path']}",
        f"identical: {json.dumps(comparison['identical'])}",
        f"only_in_v{va}: {json.dumps(comparison['only_in_a'])}",
        f"only_in_v{vb}: {json.dumps(comparison['only_in_b'])}",
    ]
    return {"answer": "\n".join(lines), "sources": [a["citation"], b["citation"]],
            "tmf": api_id, "resource": a["resource_or_schema"]}


def unresolved_comparison_answer(comparison: dict) -> dict:
    """Deterministic non-answer when one or both sides of a comparison can't be
    resolved — never silently compare against a substituted version."""
    api_id = comparison["api_id"]
    parts = []
    for r in comparison["results"]:
        if r["status"] == "UNRESOLVED":
            avail = ", ".join(r.get("available_versions") or []) or "none indexed"
            parts.append(f"v{r['requested_version']} (available: {avail})")
        else:
            parts.append(f"v{r['version']} (resolved)")
    msg = (f"I can't complete this comparison for {api_id} — " + "; ".join(parts) +
           ". I won't compare against a substituted version.")
    return {"answer": msg, "sources": [], "tmf": api_id, "resource": ""}


def comparison_instructions(comparison: dict) -> str:
    """System-prompt addendum locking the model to the comparison object. Explicitly
    scopes the model to a REQUIRED-FIELDS-ONLY comparison so it cannot generalize to
    an unsupported whole-API claim (Phase 4 live failure: 'this is the only difference
    between v4.0.0 and v5.0.0' when only required fields were ever compared)."""
    api_id = comparison["api_id"]
    va, vb = comparison["versions"]
    a, b = comparison["results"]
    verdict = (f"The required-field sets are IDENTICAL between v{va} and v{vb}: "
               + ", ".join(comparison["common"]) + "."
               if comparison["identical"] else
               f"The required-field sets DIFFER — only in v{va}: {comparison['only_in_a'] or '(none)'}; "
               f"only in v{vb}: {comparison['only_in_b'] or '(none)'}; common to both: {comparison['common']}.")
    return (
        "\n\nVERIFIED COMPARISON (locked ground truth — a comparison of REQUIRED FIELDS "
        "ONLY, not a full API comparison):\n"
        f"- {api_id} v{va} required: {json.dumps(a['facts']['required'])}\n"
        f"- {api_id} v{vb} required: {json.dumps(b['facts']['required'])}\n"
        f"- Verdict: {verdict}\n\n"
        "This comparison covers ONLY the mandatory/required field sets of these two "
        "versions — nothing else about the APIs was compared (not operations, not "
        "optional fields, not descriptions, not behavior, not the schemas overall). You "
        "may explain and contextualize the verdict above, but you must NOT claim this is "
        "'the only difference' between the versions, must NOT claim the APIs or "
        "specifications are identical or equivalent overall, and must NOT invent any "
        "other similarity or difference beyond the required-field verdict stated above. "
        "If the sets are identical, say so plainly (e.g. 'the mandatory field sets are "
        "identical') without generalizing to the whole API being unchanged."
    )


_WHOLE_API_OVERCLAIM = re.compile(
    r"\bonly\s+difference\s+between\b|\bno\s+other\s+differences?\s+(?:between|exist)\b|"
    r"\bidentical\s+api(?:s)?\b|\bexactly\s+the\s+same\s+api(?:s)?\b|"
    r"\bcompletely\s+identical\b|\bthe\s+same\s+in\s+every\s+way\b|"
    r"\bequivalent\s+overall\b|\bidentical\s+overall\b",
    re.I,
)


def validate_comparison_answer(comparison: dict, text: str):
    """Programmatic integrity gate for a comparison answer. Returns (ok, reasons)."""
    reasons = []
    t = text or ""
    if not t.strip():
        return False, ["empty_generation"]

    va, vb = comparison["versions"]
    for v in (va, vb):
        if v not in t:
            reasons.append(f"version_missing: {v} not found in answer")

    if comparison["identical"]:
        if re.search(r"\bdiffer(?:s|ent|ence|ences)?\b", t, re.I) and not re.search(
                r"\bno\s+differ|\bidentical\b|\bthe\s+same\b|\bequal\b", t, re.I):
            reasons.append("claims_difference_when_identical")
    else:
        for f in comparison["only_in_a"] + comparison["only_in_b"]:
            if f not in t:
                reasons.append(f"comparison_field_dropped: {f}")

    # However it's phrased, it must never generalize a required-fields-only comparison
    # into a whole-API claim — this is the exact live failure this validator exists for.
    if _WHOLE_API_OVERCLAIM.search(t):
        reasons.append("unscoped_whole_api_overclaim")

    return (len(reasons) == 0, reasons)


def grounded_comparison_answer(question: str, comparison: dict, generate) -> dict:
    """Same bridge as `grounded_answer`, for a two-version comparison: DETERMINISTIC
    RESOLUTION (both sides) -> COMPARISON OBJECT -> GROUNDED LLM GENERATION ->
    COMPARISON INTEGRITY VALIDATION -> RESPONSE."""
    result = render_comparison_markdown(comparison)
    try:
        text = generate(question, comparison_instructions(comparison))
    except Exception as e:
        text = ""
        print(f"[integrity] grounded comparison generation failed for {comparison.get('api_id')}: "
              f"{type(e).__name__}: {e}", flush=True)
    ok, reasons = validate_comparison_answer(comparison, text)
    if ok:
        result = {**result, "answer": text}
    elif text.strip():
        print(f"[integrity] grounded comparison answer rejected for {comparison.get('api_id')}: "
              f"{reasons} — falling back to deterministic answer", flush=True)
    result["grounded"] = ok
    return result


def route_required_fields_question(question: str):
    """Single entry point for the caller: tries the (more specific) two-version
    comparison intent first — a comparison question also satisfies the plain
    required-fields intent, so checking it first prevents a comparison from being
    mis-routed as a single-version question naming only the first version it sees.
    Falls back to single-version `required_fields_fact`. None means neither applies."""
    cmp = required_fields_comparison(question)
    if cmp is not None:
        return cmp
    return required_fields_fact(question)


# ══════════════════════════════════════════════════════════════════════════════════
# Canonical schema-fact model: property claims (existence/required/optional) and
# corpus-wide aggregation ("which schemas...", "does any schema...", "no resource...").
#
# `required_fields_fact`/`required_fields_comparison` above own ONE question shape:
# "what must I submit for resource R (at version V)?" — a single, already-identified
# schema. Live adversarial testing found a broader class they don't own at all:
# claims about a SPECIFIC PROPERTY across POSSIBLY MANY schemas — "is `x` required in
# ANY other resource", "which schemas contain `x`", "is `fakeProperty` optional in R".
# Those either fell through to free-text RAG (which then generalised from a handful of
# retrieved chunks to a corpus-wide claim it never checked) or resolved the right
# resource but never checked whether the NAMED PROPERTY was even real.
#
# The invariant this section exists to enforce: a property absent from a schema's
# `properties` is UNKNOWN, never OPTIONAL — optionality only means something for a
# property the schema actually declares — and a claim spanning "any/all/every/none" of
# a corpus is only permitted once every one of that corpus's schemas has actually been
# scanned (never Chroma, never retrieval — the same parsed OpenAPI assets
# `required_fields_fact` already reads).
# ══════════════════════════════════════════════════════════════════════════════════
def _schema_resolution_issues(spec, node, _d: int = 0) -> list:
    """Reasons this schema (or a sub-schema reached via allOf) might resolve to an
    INCOMPLETE required/properties set, given how `_required`/`_properties` actually
    walk it: they follow $ref and allOf but not oneOf/anyOf, and stop past depth 5.
    Checked along the SAME paths those functions walk, so this is an honest signal —
    not a separate, possibly-diverging notion of "complete". Empty = safe to treat as
    exhaustively resolved."""
    if _d >= 5:
        return ["allOf_depth_exceeded"]
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        if not node["$ref"].startswith("#"):
            return ["external_ref"]
        node = _resolve_ref(spec, node["$ref"])
    if not isinstance(node, dict):
        return []
    issues = ["oneOf_or_anyOf_present"] if ("oneOf" in node or "anyOf" in node) else []
    for sub in node.get("allOf", []) or []:
        issues += _schema_resolution_issues(spec, sub, _d + 1)
    return issues


def _enumerate_schemas(spec: dict) -> dict:
    """Every schema in `spec`'s components/definitions, deterministically resolved —
    straight from the parsed OpenAPI/Swagger asset, never Chroma, never retrieval, never
    the LLM. {"resolved": {name: {"required": [...], "properties": {...}}},
    "unresolved": [name, ...], "schemas_total": N}. A schema lands in "unresolved" (and
    is excluded from "resolved") whenever `_schema_resolution_issues` flags it, so a
    caller can honestly know whether its scan was exhaustive instead of assuming so."""
    schemas = _schemas(spec)
    resolved, unresolved = {}, []
    for name, sd in schemas.items():
        if _schema_resolution_issues(spec, sd):
            unresolved.append(name)
            continue
        resolved[name] = {"required": _required(spec, sd), "properties": _properties(spec, sd)}
    return {"resolved": resolved, "unresolved": sorted(unresolved), "schemas_total": len(schemas)}


def _classify_property(entry: dict, prop_name: str) -> str:
    """UNKNOWN | REQUIRED | OPTIONAL for one already-resolved schema entry (from
    `_enumerate_schemas` or an equivalent {"required", "properties"} pair). A property
    absent from `properties` is UNKNOWN — NEVER optional — regardless of whether it is
    also absent from `required`; optionality is only meaningful for a property the
    schema actually declares. This is the single invariant Phase 4 exists to enforce."""
    if prop_name not in entry["properties"]:
        return "UNKNOWN"
    return "REQUIRED" if prop_name in entry["required"] else "OPTIONAL"


# "all fields EXCEPT A and B", "besides X" — an exception/list framing means the
# question is about the whole field set (an ENUMERATION), not a predicate targeting
# ONE property, even though it names one or more real property tokens.
_EXCEPTION_FRAMING = re.compile(r"\bexcept\b|\bbesides\b|\bother\s+than\b|\baside\s+from\b", re.I)


def _named_property_candidates(q: str, known_props: set, exclude: set = frozenset()) -> list:
    """Every distinct target-property token named in the question, in order. A token is
    a candidate whether or not it is a real property of the resolved schema: property
    MEMBERSHIP is a downstream CLASSIFICATION result (REQUIRED / OPTIONAL / UNKNOWN), not
    a prerequisite for being the target — a fabricated ("fakeCustomerMood") or wrong-
    scope ("action" on ProductOrder, where it lives on the child ProductOrderItem)
    property must resolve to UNKNOWN, never disappear here (that disappearance was the
    live bug that made a perfectly specified predicate refuse). `_resource_words_list`
    has already stripped stopwords, predicate vocabulary, and demonstratives, so any
    surviving token IS a syntactic property identifier.

    Excludes a CAPITALIZED token that matches the already-identified resource/schema name
    (a resource is not one of its own properties; schema names are UpperCamelCase and
    properties lowerCamelCase, TMF630 rule R8, so a lowercase property token is never
    dropped for merely sharing a schema's spelling). Known-property matching is
    @-insensitive so the token "type" resolves the canonical property "@type"."""
    words = _resource_words_list(q)
    excl_lower = {e.lower() for e in exclude}
    lower_map = {p.lower(): p for p in known_props}
    lower_map.update({p.lstrip("@").lower(): p for p in known_props if p.startswith("@")})
    out = []
    for w in words:
        if w[:1].isupper() and w.lower() in excl_lower:
            continue
        name = lower_map.get(w.lower(), w)      # known -> canonical casing; else the token itself (UNKNOWN)
        if name not in out:
            out.append(name)
    return out


def _extract_target_property(q: str, known_props: set, exclude: set = frozenset()):
    """(name, is_known) — the ONE property this question is unambiguously about, or
    (None, False) if it isn't unambiguous: no property-shaped token is named, more than
    one is, or the question uses an exception/list framing ("all fields except A and
    B") — all three mean this is an ENUMERATION question about the whole field set,
    not a PREDICATE about a single named property ("is X required/optional?", "does X
    exist?"), even if a real property happens to be mentioned. See
    `_named_property_candidates` for how candidates are found; a fabricated property
    name is deliberately still returned (is_known=False) so it can be classified
    UNKNOWN rather than the question being silently deferred to the LLM."""
    if _EXCEPTION_FRAMING.search(q or ""):
        return None, False
    candidates = _named_property_candidates(q, known_props, exclude)
    known_lower = {p.lower() for p in known_props}
    known_hits = [c for c in candidates if c.lower() in known_lower]
    # Prefer a single REAL property when one is named — incidental non-property tokens a
    # broad function-word stoplist might still miss don't derail a well-specified
    # predicate ("does any schema require billingAccount" -> billingAccount, ignoring
    # residual noise). Only when NO real property is named does a lone remaining token
    # count as a fabricated/wrong-scope property (classified UNKNOWN downstream). A tie
    # (several real properties, or several unknown tokens) is an enumeration/ambiguous
    # question, not a single-property predicate.
    if len(known_hits) == 1:
        return known_hits[0], True
    if not known_hits and len(candidates) == 1:
        return candidates[0], False
    return None, False


# Broader than _REQ: also covers pure existence/containment phrasing ("valid property",
# "does it contain X") that names no required/optional language at all.
_PROPERTY_INTENT = re.compile(
    r"\b(mandator(?:y|ies)|required|require[sd]?|requiring|need(?:ed|s)?|"
    r"omit(?:s|ted|ting)?|optional|valid|exists?|contain(?:s|ing)?)\b", re.I,
)
# A claim needing MULTI-SCHEMA (corpus-wide) evidence to answer honestly — Phase 5's
# universal-claim words, plus "which schemas/resources" (an aggregation REQUEST even
# when it isn't phrased as a true/false universal claim).
_EXHAUSTIVE_SCOPE = re.compile(
    r"\bany\s+other\b|\bno\s+other\b|\bacross\b|\blist\s+every\b|"
    # A quantifier immediately governing "resource(s)"/"schema(s)" itself (an optional
    # TMF id/version may sit in between) — NOT just any bare "all"/"any" anywhere in the
    # sentence, which would also fire on "all TMF622 ProductOrder FIELDS..." (a single-
    # resource question about its OWN field list, not a corpus-wide claim).
    r"\b(?:any|all|every|none|no)\s+(?:other\s+)?(?:tmf\S*\s+)?(?:v?[\d.]+\s+)?(?:resource|schema)s?\b|"
    r"\bwhich\s+(?:tmf\S*\s+)?(?:v?[\d.]+\s+)?(?:schemas?|resources?)\b",
    re.I,
)


def _single_property_fact(meta: dict, spec: dict, name: str, sd, prop: str, known: bool) -> dict:
    """VerifiedFactResult for a property claim about ONE already-resolved resource —
    exhaustive by construction (the whole schema was read, not sampled)."""
    props = _properties(spec, sd)
    req = _required(spec, sd)
    status = _classify_property({"required": req, "properties": props}, prop) if known else "UNKNOWN"
    disp = re.sub(r"_(Create|FVO|MVO|Update)$", "", name)
    _, prefix = tmf_profile._container(spec, "schemas")
    citation = _citation(meta, disp)
    fact_type = {"REQUIRED": "PROPERTY_REQUIRED", "OPTIONAL": "PROPERTY_OPTIONAL",
                "UNKNOWN": "PROPERTY_EXISTENCE"}[status]
    return {
        "status": "RESOLVED", "fact_type": fact_type,
        "api_id": meta.get("tmf", ""), "requested_version": None, "resolved_version": meta.get("version", ""),
        "property_name": prop, "property_known": known, "property_status": status,
        "resource_or_schema": disp, "schema_name": name, "schema_path": prefix + name,
        "scope": "single_schema", "exhaustive": True,
        "source_asset": citation["name"], "source_file": meta.get("file", ""), "citation": citation,
        "extraction_method": "SCHEMA_DIRECT",
    }


def _build_aggregation_fact(api_id: str, files: list, explicit_versions: list, q: str):
    """VerifiedFactResult for a corpus-wide property claim: every requested (or, if none
    were named, every INDEXED) version of `api_id` is enumerated and classified
    INDEPENDENTLY — never merged — so a v4/v5 split is preserved and an unscoped
    universal claim is never silently answered from only the latest version."""
    known_versions = {f["version"] for f in files}
    target_versions = sorted(
        (set(explicit_versions) & known_versions) if explicit_versions else known_versions,
        key=tmf_profile._version_key,
    )
    if not target_versions:
        return None

    # Build the corpus-wide known-property universe across every selected version FIRST,
    # so a fabricated property name can still be named and classified UNKNOWN. Schema
    # names themselves are excluded from candidacy — "ProductOrder" is not one of its
    # own properties, and its camelCase shape would otherwise look like a fabricated one.
    enumerations, all_props, all_schema_names = {}, set(), set()
    for v in target_versions:
        meta = next(f for f in files if f["version"] == v)
        sp = tmf_profile._load(os.path.join(_HERE, meta["file"]))
        enum = _enumerate_schemas(sp) if isinstance(sp, dict) else {"resolved": {}, "unresolved": [], "schemas_total": 0}
        enumerations[v] = (meta, sp, enum)
        all_schema_names |= set(enum["resolved"]) | set(enum["unresolved"])
        for e in enum["resolved"].values():
            all_props |= set(e["properties"])

    prop, known = _extract_target_property(q, all_props, exclude=all_schema_names)
    if not prop:
        return None

    # REQUIRED_PROPERTY_AGGREGATION when the question is about mandatoriness;
    # SCHEMA_AGGREGATION when it's about mere presence ("which schemas contain X").
    fact_type = ("SCHEMA_AGGREGATION" if re.search(r"\bcontain|\bvalid\b|\bexist", q, re.I)
                and not re.search(r"\bmandator|\brequir", q, re.I) else "REQUIRED_PROPERTY_AGGREGATION")

    versions_out = []
    for v in target_versions:
        meta, sp, enum = enumerations[v]
        exist_matches, required_matches, schema_paths = [], [], {}
        if isinstance(sp, dict):
            _, prefix = tmf_profile._container(sp, "schemas")
        for sname, e in enum["resolved"].items():
            status = _classify_property(e, prop) if known else "UNKNOWN"
            if status != "UNKNOWN":
                exist_matches.append(sname)
                schema_paths[sname] = prefix + sname
                if status == "REQUIRED":
                    required_matches.append(sname)
        citation = _citation(meta, f"{api_id} schema corpus")
        versions_out.append({
            "version": v,
            "exhaustive": not enum["unresolved"],
            "schemas_total": enum["schemas_total"],
            "schemas_scanned": len(enum["resolved"]),
            "schemas_unresolved": enum["unresolved"],
            "matches_exist": sorted(exist_matches),
            "matches_required": sorted(required_matches),
            "schema_paths": schema_paths,
            "source_asset": citation["name"], "source_file": meta.get("file", ""), "citation": citation,
        })

    matches_key = "matches_required" if fact_type == "REQUIRED_PROPERTY_AGGREGATION" else "matches_exist"
    return {
        "status": "RESOLVED", "fact_type": fact_type,
        "api_id": api_id,
        "requested_version": explicit_versions[0] if len(explicit_versions) == 1 else None,
        "requested_versions": explicit_versions or [],
        "property_name": prop, "property_known": known,
        "resource_or_schema": None, "scope": "corpus",
        "exhaustive": all(v["exhaustive"] for v in versions_out),
        "schemas_total": {v["version"]: v["schemas_total"] for v in versions_out},
        "schemas_scanned": {v["version"]: v["schemas_scanned"] for v in versions_out},
        "schemas_unresolved": {v["version"]: v["schemas_unresolved"] for v in versions_out},
        "matches": {v["version"]: v[matches_key] for v in versions_out},
        "schema_paths": {v["version"]: v["schema_paths"] for v in versions_out},
        "source_assets": [v["source_asset"] for v in versions_out],
        "source_files": [v["source_file"] for v in versions_out],
        "versions": versions_out,
        "extraction_method": "CORPUS_SCAN",
    }


def property_or_aggregation_fact(question: str):
    """VerifiedFactResult for a property-existence/required/optional claim — single-
    resource or corpus-wide. Owns what `required_fields_fact` does not:
      - a specific but UNKNOWN property (classified UNKNOWN, never OPTIONAL)
      - "which schemas contain/require X" (SCHEMA_AGGREGATION / REQUIRED_PROPERTY_AGGREGATION)
      - "does ANY/ALL/no other/every ... resource/schema ..." universal claims
    Every version evaluated is independently enumerated (see `_build_aggregation_fact`).
    None means this isn't a property/governance question at all — the caller may defer."""
    q = question or ""
    if not _PROPERTY_INTENT.search(q):
        return None

    if not _EXHAUSTIVE_SCOPE.search(q):
        # Single-resource claim — same resolution path as required_fields_fact (an
        # explicit TMF id, or a bare resource name), so "ProductOrder" alone still works.
        meta, spec = _resolve_spec(q)
        if not spec:
            return None
        name, sd = _match_resource(spec, q)
        if not sd:
            return None
        prop, known = _extract_target_property(q, set(_properties(spec, sd)), exclude={name, _base(name)})
        if not prop:
            return None
        return _single_property_fact(meta, spec, name, sd, prop, known)

    # Corpus-wide aggregation: requires an explicit, unambiguous API id — the larger
    # blast radius of a corpus-wide claim earns stricter anchoring than a bare name.
    m = _TMF.search(q)
    if not m:
        return None
    api_id = "TMF" + m.group(1).zfill(3)
    files = _spec_files_for(api_id)
    if not files:
        return None

    explicit_versions = _requested_versions(q)
    known_versions = {f["version"] for f in files}
    if explicit_versions and not (set(explicit_versions) & known_versions):
        return {
            "status": "UNRESOLVED", "fact_type": "REQUIRED_PROPERTY_AGGREGATION",
            "api_id": api_id, "requested_versions": explicit_versions,
            "available_versions": sorted(known_versions, key=tmf_profile._version_key),
            "reason": "VERSION_NOT_FOUND",
        }
    return _build_aggregation_fact(api_id, files, explicit_versions, q)


# ── Rendering, raw output, and unresolved formatting for property/aggregation facts ───
def render_property_fact_markdown(fact: dict) -> dict:
    """Deterministic answer for a single-schema property claim — also the fallback when
    a grounded answer fails integrity validation."""
    prop, status = fact["property_name"], fact["property_status"]
    api_id, ver, disp = fact["api_id"], fact["resolved_version"], fact["resource_or_schema"]
    head = f"**{api_id + ' — ' if api_id else ''}{disp}{f' (v{ver})' if ver else ''}**"
    if status == "UNKNOWN":
        body = (f"`{prop}` is **not a recognized property** of {disp}"
                + (f" {api_id} v{ver}" if api_id else "") + ". It doesn't appear in the "
                "schema's `properties` at all, so it is neither required nor optional — "
                "those labels only apply to properties the schema actually declares.")
    elif status == "REQUIRED":
        body = f"Yes — `{prop}` is a **required** property of {disp}."
    else:
        body = f"`{prop}` is a real property of {disp}, and it is **optional** (not in the `required` list)."
    lines = [head, "", body, "",
             "_Read directly from the canonical schema's `properties`/`required` lists — deterministic, not generated._"]
    return {"answer": "\n".join(lines), "sources": [fact["citation"]], "tmf": api_id, "resource": disp}


def raw_property_fact_answer(fact: dict) -> dict:
    """Literal deterministic fields for an explicit raw/no-explanation request."""
    lines = [
        f"api_id: {fact['api_id']}", f"version: {fact['resolved_version']}",
        f"schema: {fact['schema_name']}", f"schema_path: {fact['schema_path']}",
        f"property: {fact['property_name']}", f"property_known: {json.dumps(fact['property_known'])}",
        f"property_status: {fact['property_status']}",
        f"source_file: {fact['source_file']}",
    ]
    return {"answer": "\n".join(lines), "sources": [fact["citation"]],
            "tmf": fact["api_id"], "resource": fact["resource_or_schema"]}


def property_fact_instructions(fact: dict) -> str:
    """Locked ground truth for a single-schema property claim. Explicit about the
    UNKNOWN invariant so the model cannot call a nonexistent property 'optional'."""
    prop, status = fact["property_name"], fact["property_status"]
    if status == "UNKNOWN":
        verdict = (f"`{prop}` is NOT a recognized property of this schema at all — it is absent from "
                  "`properties`. It is therefore UNKNOWN, not optional and not required. An unknown "
                  "property is NEVER 'optional' — optionality only applies to a property the schema "
                  "actually declares.")
    elif status == "REQUIRED":
        verdict = f"`{prop}` IS a required property of this schema."
    else:
        verdict = f"`{prop}` is a real, declared property of this schema, and it is OPTIONAL (not required)."
    return (
        "\n\nVERIFIED PROPERTY FACT (locked ground truth, already extracted from the canonical schema):\n"
        f"- API: {fact['api_id']} v{fact['resolved_version']}\n"
        f"- Resource/schema: {fact['resource_or_schema']} ({fact['schema_name']}, at {fact['schema_path']})\n"
        f"- Property asked about: `{prop}`\n"
        f"- Verdict: {verdict}\n\n"
        "This verdict is IMMUTABLE. You may explain it and add useful context, but you must NOT "
        "contradict it, must NOT claim a different status for this property, must NOT claim the "
        "property is 'optional' if the verdict says UNKNOWN, and must NOT change the api id or "
        "version. If the property is unknown, say so plainly — do not soften it into 'optional' or "
        "guess at what it might have meant."
    )


def _render_aggregation_version(fact: dict, v: dict) -> list:
    prop = fact["property_name"]
    label = "requires" if fact["fact_type"] == "REQUIRED_PROPERTY_AGGREGATION" else "contains"
    matches = v["matches_required"] if fact["fact_type"] == "REQUIRED_PROPERTY_AGGREGATION" else v["matches_exist"]
    lines = [f"**v{v['version']}** — scanned {v['schemas_scanned']}/{v['schemas_total']} schemas"
             + (f" ({len(v['schemas_unresolved'])} could not be fully resolved: "
                + ", ".join(f"`{n}`" for n in v["schemas_unresolved"][:6])
                + ("…" if len(v["schemas_unresolved"]) > 6 else "") + ")" if v["schemas_unresolved"] else "")
             + ":"]
    if matches:
        lines.append(f"{len(matches)} schema(s) {label} `{prop}`: "
                     + ", ".join(f"`{n}`" for n in matches[:12]) + ("…" if len(matches) > 12 else "") + ".")
    else:
        lines.append(f"No scanned schema {label} `{prop}`.")
    return lines


def render_aggregation_fact_markdown(fact: dict) -> dict:
    """Deterministic answer for a corpus-wide aggregation fact. When `exhaustive` is
    False, this IS the answer — no LLM is ever consulted for a claim the system can't
    fully verify (Phase 5): the universal claim is explicitly refused, not softened."""
    prop = fact["property_name"]
    head = f"**{fact['api_id']}** — {'where' if fact['fact_type']=='REQUIRED_PROPERTY_AGGREGATION' else 'which schemas contain'} `{prop}` {'is required' if fact['fact_type']=='REQUIRED_PROPERTY_AGGREGATION' else ''}"
    lines = [head.strip(), ""]
    if not fact["property_known"]:
        lines += [f"`{prop}` is not a recognized property anywhere in this corpus scan — it cannot be "
                  "required or optional in any schema, since it doesn't exist in any schema's `properties`.",
                  ""]
    for v in fact["versions"]:
        lines += _render_aggregation_version(fact, v) + [""]
    if not fact["exhaustive"]:
        lines.append("_I cannot verify this as a corpus-wide claim because canonical enumeration was "
                     "incomplete for at least one version above (some schemas could not be fully "
                     "resolved) — the results shown are only for the schemas actually scanned, not a "
                     "guarantee about the rest of the corpus._")
    else:
        lines.append("_Read directly from every schema's own `properties`/`required` lists — "
                     "deterministic, exhaustive, not generated._")
    return {"answer": "\n".join(lines), "sources": [v["citation"] for v in fact["versions"]],
            "tmf": fact["api_id"], "resource": ""}


def raw_aggregation_fact_answer(fact: dict) -> dict:
    """Literal deterministic fields for an explicit raw/no-explanation aggregation request."""
    lines = [
        f"api_id: {fact['api_id']}", f"property: {fact['property_name']}",
        f"property_known: {json.dumps(fact['property_known'])}",
        f"exhaustive: {json.dumps(fact['exhaustive'])}",
    ]
    for v in fact["versions"]:
        mk = "matches_required" if fact["fact_type"] == "REQUIRED_PROPERTY_AGGREGATION" else "matches_exist"
        lines += [
            f"version: {v['version']}",
            f"schemas_scanned: {v['schemas_scanned']}/{v['schemas_total']}",
            f"schemas_unresolved: {json.dumps(v['schemas_unresolved'])}",
            f"matches: {json.dumps(v[mk])}",
        ]
    return {"answer": "\n".join(lines), "sources": [v["citation"] for v in fact["versions"]],
            "tmf": fact["api_id"], "resource": ""}


def unresolved_aggregation_answer(fact: dict) -> dict:
    """Deterministic non-answer when an explicitly-named version isn't in the corpus at
    all — never silently substitute or fall through to mixed-version RAG."""
    avail = ", ".join(fact.get("available_versions") or []) or "none indexed"
    reqd = ", ".join(f"v{v}" for v in fact.get("requested_versions") or [])
    msg = (f"I can't resolve {fact['api_id']} {reqd} — the versions of {fact['api_id']} I have indexed "
           f"are: {avail}. I won't answer by substituting a different version's schema.")
    return {"answer": msg, "sources": [], "tmf": fact.get("api_id", ""), "resource": ""}


def non_exhaustive_refusal(question: str, api_id: str = "") -> dict:
    """Explicit refusal for a governance-shaped question that named no resolvable
    resource or property at all — the Phase 7 boundary: this must NEVER silently fall
    through to general RAG, which is how an unverified corpus-wide claim gets made."""
    msg = ("This looks like a TM Forum schema/compliance question, but I couldn't deterministically "
          "resolve a specific resource, property, or corpus-wide scope to check"
          + (f" for {api_id}" if api_id else "") + ". I won't answer a schema-fact question by "
          "guessing or generalizing from a handful of retrieved passages — please name the exact "
          "resource (e.g. ProductOrder) or property you mean.")
    return {"status": "UNRESOLVED", "fact_type": "GOVERNANCE_REFUSAL", "api_id": api_id,
            "answer": msg, "sources": [], "tmf": api_id, "resource": ""}


# ── Integrity validation for property/aggregation claims ──────────────────────────────
def validate_property_answer(fact: dict, text: str):
    """Phase 6 integrity gate for a single-schema property claim. Programmatic checks
    only. The core invariant: an UNKNOWN property must never be validated as optional
    (or required) — no matter how the model phrases its answer."""
    reasons = []
    t = text or ""
    if not t.strip():
        return False, ["empty_generation"]

    api_id, ver = fact.get("api_id", ""), fact.get("resolved_version", "")
    if api_id and api_id not in t:
        reasons.append(f"api_identity_missing: {api_id} not found in answer")
    if ver and ver not in t and f"v{ver}" not in t:
        reasons.append(f"version_missing: {ver} not found in answer")
    for other in sorted(_known_versions(api_id) - {ver}):
        if other in t:
            reasons.append(f"version_conflict: sibling version {other} appears in answer")

    prop, status = fact["property_name"], fact["property_status"]
    if prop not in t:
        reasons.append(f"property_not_mentioned: {prop}")
        return (len(reasons) == 0, reasons)

    claimed_optional = False
    claimed_required = False
    for seg in re.split(r"[.\n]|\s\|\s", t):
        if prop not in seg:
            continue
        if _OPTIONAL_LANG.search(seg) and re.search(rf"`?{re.escape(prop)}`?", seg):
            claimed_optional = True
        if _REQUIRED_LANG.search(seg) and not _OPTIONAL_LANG.search(seg):
            claimed_required = True

    if status == "UNKNOWN":
        if claimed_optional:
            reasons.append(f"unknown_property_claimed_optional: {prop}")
        if claimed_required:
            reasons.append(f"unknown_property_claimed_required: {prop}")
        if not re.search(r"\bnot\s+a\s+(?:recognized|valid|real|known)\s+propert|\bdoesn.t\s+exist|"
                        r"\bno\s+such\s+propert|\bunknown\s+propert|\bnot\s+(?:a\s+part\s+of|in)\s+the\s+schema",
                        t, re.I):
            reasons.append("unknown_property_not_flagged_as_unknown")
    elif status == "REQUIRED" and claimed_optional:
        reasons.append(f"required_property_claimed_optional: {prop}")
    elif status == "OPTIONAL" and claimed_required:
        reasons.append(f"optional_property_claimed_required: {prop}")

    return (len(reasons) == 0, reasons)


def grounded_property_answer(question: str, fact: dict, generate) -> dict:
    """Bridge for a single-schema property claim, same shape as `grounded_answer`."""
    result = render_property_fact_markdown(fact)
    try:
        text = generate(question, property_fact_instructions(fact))
    except Exception as e:
        text = ""
        print(f"[integrity] grounded property generation failed for {fact.get('api_id')}: "
              f"{type(e).__name__}: {e}", flush=True)
    ok, reasons = validate_property_answer(fact, text)
    if ok:
        result = {**result, "answer": text}
    elif text.strip():
        print(f"[integrity] grounded property answer rejected for {fact.get('api_id')} "
              f"`{fact.get('property_name')}`: {reasons} — falling back to deterministic answer", flush=True)
    result["grounded"] = ok
    return result


def validate_aggregation_answer(fact: dict, text: str):
    """Phase 6 integrity gate for a corpus-wide aggregation answer. Only ever called
    when `fact['exhaustive']` is True — a non-exhaustive fact never reaches the LLM at
    all (see `governance_answer`), so there is nothing to validate for that case: the
    deterministic refusal IS the answer."""
    reasons = []
    t = text or ""
    if not t.strip():
        return False, ["empty_generation"]
    if fact["api_id"] not in t:
        reasons.append(f"api_identity_missing: {fact['api_id']} not found in answer")
    for v in fact["versions"]:
        if v["version"] not in t:
            reasons.append(f"version_missing: {v['version']} not found in answer")
        mk = "matches_required" if fact["fact_type"] == "REQUIRED_PROPERTY_AGGREGATION" else "matches_exist"
        for name in v[mk]:
            if name not in t:
                reasons.append(f"aggregation_match_dropped: {name}")
    if _WHOLE_API_OVERCLAIM.search(t):
        reasons.append("unscoped_whole_api_overclaim")
    return (len(reasons) == 0, reasons)


def grounded_aggregation_answer(question: str, fact: dict, generate) -> dict:
    """Bridge for a corpus-wide aggregation fact. Only called when exhaustive=True."""
    result = render_aggregation_fact_markdown(fact)
    prop = fact["property_name"]
    versions_txt = "; ".join(
        f"v{v['version']} — scanned {v['schemas_scanned']}/{v['schemas_total']}, "
        f"matches: {json.dumps(v['matches_required'] if fact['fact_type']=='REQUIRED_PROPERTY_AGGREGATION' else v['matches_exist'])}"
        for v in fact["versions"]
    )
    extra = (
        "\n\nVERIFIED CORPUS SCAN (locked ground truth — every schema in scope was read directly "
        f"from the canonical asset, exhaustively):\n- API: {fact['api_id']}\n- Property: `{prop}`\n"
        f"- {versions_txt}\n\n"
        "This is a COMPLETE, exhaustive scan — you may state the result as a full corpus-wide fact. "
        "You must NOT add a schema to the match list that isn't listed above, must NOT drop one that "
        "is, must NOT mix results between versions, and must NOT claim this covers anything beyond "
        "the property/versions named above."
    )
    try:
        text = generate(question, extra)
    except Exception as e:
        text = ""
        print(f"[integrity] grounded aggregation generation failed for {fact.get('api_id')}: "
              f"{type(e).__name__}: {e}", flush=True)
    ok, reasons = validate_aggregation_answer(fact, text)
    if ok:
        result = {**result, "answer": text}
    elif text.strip():
        print(f"[integrity] grounded aggregation answer rejected for {fact.get('api_id')}: "
              f"{reasons} — falling back to deterministic answer", flush=True)
    result["grounded"] = ok
    return result


# ── Governance-intent routing boundary (Phase 7) ──────────────────────────────────────
# POSITIVE schema/conformance intent — the vocabulary that makes a question a request
# for a canonical SCHEMA FACT (not general API/domain knowledge). This is the gate for
# GOVERNANCE_REFUSAL, so it must be conservative: only unambiguous schema terms belong
# here. Deliberately EXCLUDED:
#   - comparison words (compare/difference/vs) — "what's the difference between TMF620
#     and TMF633?" is a general API-comparison question, NOT a schema-fact request; a
#     TMF id + a comparison word must never by itself imply governance intent (this was
#     the exact regression: comparison intent was wrongly OR'd in here).
#   - "valid"/"exists"/"contain" — common general-English words ("is TMF620 a valid
#     choice for catalog management?") that would cause false refusals. Their genuine
#     property-existence uses ("does ProductOrder contain X", "is X a valid property")
#     are still owned by `_PROPERTY_INTENT` on the RESOLVER side — the safe place for an
#     ambiguous word is a resolver that must POSITIVELY resolve, not a refusal gate.
_GOVERNANCE_SHAPE = re.compile(
    r"\b(required|mandatory|require[sd]?|requiring|omit(?:s|ted|ting)?|optional|"
    r"propert(?:y|ies)|field|attribute|schema|"
    r"conforman(?:ce|t)|conform(?:s|ing)?|enum|oneof|anyof|allof)\b|\$ref",
    re.I,
)


def is_governance_question(question: str) -> bool:
    """The Phase 7 boundary test, used ONLY to decide GOVERNANCE_REFUSAL vs falling
    through to general RAG when no deterministic resolver claimed the question. It
    requires POSITIVE schema/conformance intent (`_GOVERNANCE_SHAPE`) in addition to a
    TMF id — a TMF id ALONE, or a TMF id plus a mere comparison word, is NOT governance
    intent. This is what keeps general TM Forum knowledge/API questions ("what is
    TMF620?", "difference between TMF620 and TMF633?", "when to use TMF620 vs TMF633?")
    on the normal grounded-RAG path, while a genuine unresolvable schema-fact question
    ("does TMF622 have a required field called X?") is still explicitly refused rather
    than answered from arbitrary retrieved passages."""
    q = question or ""
    if not _TMF.search(q):
        return False
    return bool(_GOVERNANCE_SHAPE.search(q))


def route_governance_question(question: str):
    """Top-level entry point. Order, and why it's this order:
    1. `required_fields_comparison` — a two-version comparison is the most specific
       intent and must win even though it also satisfies the plain required-fields and
       property-predicate checks below.
    2. A single-resource, single-NAMED-PROPERTY predicate ("is X required?", "is X
       optional?", "does X exist?") — this MUST outrank whole-resource enumeration
       (step 3), because "field"/"schema"/"required"/"optional" alone say nothing about
       whether the question targets one concrete property or the whole field list; only
       `property_or_aggregation_fact` actually checks that (via
       `_extract_target_property`'s exactly-one-candidate rule), so it has to run before
       `required_fields_fact` gets a chance to claim the same question with its coarser
       "does the sentence contain a resource + intent word" test. (This was the exact
       live routing bug: "is fakeCustomerMood an optional field...?" satisfied
       `required_fields_fact`'s gate and returned the generic required-fields answer
       before this check ever ran.)
    3. Whole-resource required-fields enumeration (unchanged, existing behaviour) —
       reached only when no single property was unambiguously targeted, so "all fields
       except A and B" or "what fields are required" still enumerate correctly.
    4. Corpus-wide aggregation (`property_or_aggregation_fact`'s other branch, `scope ==
       "corpus"`) — reached only when neither a single resource nor a single-schema
       property claim applied.
    5. An explicit governance refusal — never a silent `None` for a question that is
       unmistakably a TM Forum schema/compliance fact (Phase 7); `None` only for a
       question that isn't governance-shaped at all, so the caller may defer to ODA/RAG."""
    r = required_fields_comparison(question)
    if r is not None:
        return r

    prop_fact = property_or_aggregation_fact(question)
    if prop_fact is not None and prop_fact.get("scope") == "single_schema":
        return prop_fact

    rff = required_fields_fact(question)
    if rff is not None:
        return rff

    if prop_fact is not None:
        return prop_fact

    if is_governance_question(question):
        m = _TMF.search(question or "")
        return non_exhaustive_refusal(question, ("TMF" + m.group(1).zfill(3)) if m else "")
    return None


def oda_answer(question: str):
    """Public entry for the ODA component resolver alone (required-fields facts are
    handled separately by `required_fields_fact` upstream of this in the request path)."""
    return _oda_component_answer(question)


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
