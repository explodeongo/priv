"""
Phase 7E — FROZEN Phase 7D authority/relationship eval (Task 1).
════════════════════════════════════════════════════════════════════════════════
Preserves EVERY Phase 7D question and its original red-flag classifier UNCHANGED (imported
verbatim from authority_eval.Q), so the headline number stays directly comparable to the 7D
baseline. On top of that it adds the explicit expected dimensions the 7D artifact lacked and
scores them SEPARATELY:

    FACT ACCURACY · AUTHORITY ACCURACY · RELATIONSHIP-SEMANTICS ACCURACY · CONSTRAINT
    PRECISION · OVERALL SUCCESS

expected_outcome ∈ {FACTUAL_ANSWER, NEGATIVE_FACT, HONEST_ABSTENTION}. The original
substring classifier is NOT weakened (reported as `raw_red`, the 7D-comparable lower bound);
the dimensional scorer is negation-aware so a correct refusal is not mis-scored as a defect.

Phase 7D baseline (measured, final audit):  75/80 completed · 27 RED = 36.0% defect floor.

Run:  venv/bin/python eval/authority_eval_frozen.py   (backend on :8000, axiom_v2)
"""
import json, os, sys, urllib.request
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authority_eval import Q, classify as classify_raw, _ABSTAIN   # UNCHANGED 7D questions + classifier

API = "http://localhost:8000/query"
BASELINE_7D = {"completed": 75, "raw_red": 27, "pct": 36.0}

# ── Expected dimensions per question (added in 7E; ground truth = repository evidence) ────
# dimension: which accuracy bucket the question measures.
# outcome: the semantically-correct SHAPE of the answer.
DIM = {   # category prefix → (dimension, default expected_outcome, expected_authority, expected_scope)
    "A_global": ("AUTHORITY", "HONEST_ABSTENTION", "TMF_DESIGN_GUIDANCE", "GLOBAL"),
    "D_cross":  ("AUTHORITY", "HONEST_ABSTENTION", "TMF_DESIGN_GUIDANCE", "GLOBAL"),
    "E_guide":  ("AUTHORITY", "HONEST_ABSTENTION", "TMF_DESIGN_GUIDANCE", "GLOBAL"),
    "G_follow": ("AUTHORITY", "HONEST_ABSTENTION", "OPENAPI_SCHEMA", "PROPERTY"),
    "H_auth":   ("AUTHORITY", "HONEST_ABSTENTION", "SID_INFORMATION_FRAMEWORK", "FRAMEWORK"),
    "B_api":    ("FACT", "FACTUAL_ANSWER", "OPENAPI_SPEC", "SPEC"),
    "C_prop":   ("CONSTRAINT", "NEGATIVE_FACT", "OPENAPI_SCHEMA", "PROPERTY"),
    "F_absent": ("CONSTRAINT", "NEGATIVE_FACT", "OPENAPI_SCHEMA", "PROPERTY"),
    "I_rel":    ("RELATIONSHIP", "NEGATIVE_FACT", "ODA_COMPONENT_CONTRACT", "RELATIONSHIP"),
    "J_bait":   ("RELATIONSHIP", "NEGATIVE_FACT", "ODA_COMPONENT_CONTRACT", "RELATIONSHIP"),
}
# Per-question outcome overrides (concept/explanation questions that SHOULD answer factually,
# and the reverse-lookup relationship questions that have a real deterministic answer).
FACTUAL_OVERRIDES = {
    "What is the difference between a schema reference and an API dependency?",
    "What evidence is required to claim that API A calls API B?",
    "What does TroubleTicket.relatedEntity represent?",
    "Which ODA components expose TMF621?",       # deterministic (none) — a factual structural answer
    "Which ODA components depend on TMF621?",     # deterministic (TMFC050) — factual structural answer
    "Is ProductOrder.id required in TMF622 v4?",  # requiredness fact
    "Does TMF642 v4 define a limit query parameter?",
    "Does TMF621 define a relatedEntity field?",
    "What operations exist in TMF669 v4?",
    "How does pagination work in TMF622 v4?",
    "What query parameters does TMF622 v4 support for listing product orders?",
}

_AFFIRM = ("yes,", "yes.", "yes —", "yes -", "correct", "that's right", "thats right",
           "absolutely", "indeed it", "sure,")
_REFUSAL = _ABSTAIN + (
    "no —", "no -", "no,", "does not", "doesn't", "do not", "don't", "won't", "cannot",
    "can't", "not the sid", "different authority", "different framework", "not an api dependency",
    "not a runtime", "data-model", "component → api", "component → api", "narrowest",
    "no canonical", "no explicit integration", "not derivable", "not sufficient", "not define",
    "does not define", "different relationship", "not reverse", "not the same")


def _affirms(a): return any(a.lstrip("* ").startswith(x) or (" " + x) in a for x in _AFFIRM)
def _refuses(a): return any(m in a for m in _REFUSAL)


def expected_outcome(cat, q):
    if q in FACTUAL_OVERRIDES:
        return "FACTUAL_ANSWER"
    return DIM.get(cat, ("FACT", "FACTUAL_ANSWER", "", ""))[1]


def score(cat, q, red, ans):
    """Return (dimension, passed) under the negation-aware dimensional scorer."""
    a = (ans or "").lower()
    dim = DIM.get(cat, ("FACT",))[0]
    out = expected_outcome(cat, q)
    positive_defect = any(r.lower() in a for r in red) and not _refuses(a)
    if out == "HONEST_ABSTENTION":
        passed = _refuses(a) and not _affirms(a) and not positive_defect
    elif out == "NEGATIVE_FACT":
        passed = (_refuses(a) or not any(r.lower() in a for r in red)) and not _affirms(a)
    else:  # FACTUAL_ANSWER — must answer without positively asserting a flagged promotion
        passed = not positive_defect
    return dim, passed


def run():
    out, dims = [], defaultdict(lambda: [0, 0])   # dim → [passed, total]
    raw_red = 0
    for i, (cat, q, red, note) in enumerate(Q):
        body = json.dumps({"question": q, "mode": "deep", "no_cache": True, "top_k": 8}).encode()
        try:
            r = json.loads(urllib.request.urlopen(
                urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"}),
                timeout=180).read())
            ans, conf = r.get("answer", ""), (r.get("confidence") or {}).get("level")
        except Exception as e:
            out.append({"i": i, "cat": cat, "q": q, "cls": "ERROR", "err": str(e)[:120]});
            print(f"[{i+1}/{len(Q)}] ERROR {q[:40]}"); continue
        raw = classify_raw(ans, red)
        if raw.startswith("RED"):
            raw_red += 1
        dim, passed = score(cat, q, red, ans)
        dims[dim][1] += 1; dims[dim][0] += 1 if passed else 0
        out.append({"i": i, "cat": cat, "q": q, "raw": raw, "dim": dim,
                    "outcome": expected_outcome(cat, q), "pass": passed, "conf": conf,
                    "answer": (ans or "")[:200]})
        json.dump(out, open("/tmp/authority_eval_frozen.json", "w"), indent=1)
        print(f"[{i+1}/{len(Q)}] {'PASS' if passed else 'FAIL'} {dim:12s} {raw[:16]:16s} {q[:40]}")

    scored = [o for o in out if o.get("cls") != "ERROR"]
    npass = sum(1 for o in scored if o["pass"])
    print("\n════════ FROZEN 7D EVAL — Phase 7E result ════════")
    print(f"  Completed              {len(scored)}/{len(Q)}")
    print(f"  raw_red (7D classifier, UNCHANGED)   {raw_red}/{len(scored)}  "
          f"[7D baseline: {BASELINE_7D['raw_red']}/{BASELINE_7D['completed']} = {BASELINE_7D['pct']}%]")
    for d in ("FACT", "AUTHORITY", "RELATIONSHIP", "CONSTRAINT"):
        p, t = dims[d]
        print(f"  {d+' ACCURACY':24s} {p}/{t} = {100*p/t:.1f}%" if t else f"  {d}: n/a")
    print(f"  OVERALL SUCCESS          {npass}/{len(scored)} = {100*npass/len(scored):.1f}%")
    print("\n  Remaining dimensional failures:")
    for o in scored:
        if not o["pass"]:
            print(f"    [{o['i']}] {o['dim']:12s} {o['cat']:9s} {o['q'][:52]}")


if __name__ == "__main__":
    run()
