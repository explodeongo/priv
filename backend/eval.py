#!/usr/bin/env python3
"""
SynaptDI evaluation harness
═══════════════════════════
Runs a golden set of questions against a RUNNING backend and scores two things that
matter for a RAG product: answer correctness and citation correctness. It turns
"we think it's good" into a number you can track and defend.

Usage
-----
    # backend must be running (uvicorn) with Ollama + an index
    python eval.py                                  # defaults: localhost:8000, evals/golden.yaml, 0.8
    python eval.py --api http://localhost:8000 --set evals/golden.yaml --threshold 0.85
    python eval.py --json report.json               # also write a machine-readable report
    python eval.py --self-test                       # validate the scorer offline (no backend/Ollama)

Golden case schema (YAML list)
------------------------------
    - id: tmf622-required
      question: "What mandatory fields does TMF622 Product Order require?"
      scope: all                 # optional: all | kb | docs
      expect_specs: [TMF622]     # each must appear among the returned sources
      must_include: [productOrderItem]      # each (case-insensitive) must be in the answer
      must_not_include: [EventSubscription] # none of these may appear
      min_sources: 1             # optional: at least N sources returned

Exit code is non-zero if the pass rate is below --threshold (handy for CI).
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

try:
    import yaml
except Exception:
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))


# ── Scoring (pure functions — unit-testable without a backend) ──────────────────
def evaluate_case(case: dict, resp: dict):
    """Return (checks, passed) where checks is a list of {name, ok}."""
    answer = (resp.get("answer") or "")
    al = answer.lower()
    sources = resp.get("sources") or []
    src_blob = " ".join(
        f"{s.get('name','')} {s.get('file','')} {s.get('url','')}" for s in sources
    ).lower()

    checks = []
    for spec in case.get("expect_specs", []) or []:
        checks.append({"name": f"source cites {spec}", "ok": str(spec).lower() in src_blob})
    for sub in case.get("must_include", []) or []:
        checks.append({"name": f"answer includes “{sub}”", "ok": str(sub).lower() in al})
    for sub in case.get("must_not_include", []) or []:
        checks.append({"name": f"answer omits “{sub}”", "ok": str(sub).lower() not in al})
    if "min_sources" in case:
        checks.append({"name": f"≥{case['min_sources']} sources", "ok": len(sources) >= int(case["min_sources"])})

    passed = all(c["ok"] for c in checks) if checks else False
    return checks, passed


# ── Runner ──────────────────────────────────────────────────────────────────────
def run_query(api: str, question: str, scope: str, timeout: int):
    body = json.dumps({"question": question, "scope": scope or "all"}).encode()
    req = urllib.request.Request(api.rstrip("/") + "/query", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def load_cases(path: str):
    raw = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if not yaml:
            sys.exit("PyYAML not installed — `pip install pyyaml` or use a .json golden set.")
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    if not isinstance(data, list):
        sys.exit("Golden set must be a list of cases.")
    return data


def self_test():
    """Validate the scoring logic with a fabricated response — no backend needed."""
    case = {"expect_specs": ["TMF622"], "must_include": ["productOrderItem"],
            "must_not_include": ["EventSubscription"], "min_sources": 1}
    good = {"answer": "You must submit productOrderItem.",
            "sources": [{"name": "Product Ordering 4.0.0", "file": "TMF622.json"}]}
    bad = {"answer": "The EventSubscription needs id and callback.", "sources": []}
    c1, p1 = evaluate_case(case, good)
    c2, p2 = evaluate_case(case, bad)
    assert p1 is True, c1
    assert p2 is False, c2
    # bad should fail exactly the spec, include, not_include and min_sources checks
    assert sum(1 for c in c2 if not c["ok"]) == 4, c2
    print("✓ scorer self-test passed (good case passes, bad case fails the right checks)")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="SynaptDI evaluation harness")
    ap.add_argument("--api", default=os.environ.get("SYNAPTDI_API", "http://localhost:8000"))
    ap.add_argument("--set", dest="set_path", default=os.path.join(HERE, "evals", "golden.yaml"))
    ap.add_argument("--threshold", type=float, default=0.8, help="min pass rate (0–1) for exit 0")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    cases = load_cases(args.set_path)
    print(f"\nSynaptDI eval · {len(cases)} cases · {args.api}\n" + "─" * 64)

    results, passed_n, t0 = [], 0, time.time()
    for i, case in enumerate(cases, 1):
        cid = case.get("id", f"case-{i}")
        q = case.get("question", "")
        try:
            t = time.time()
            resp = run_query(args.api, q, case.get("scope", "all"), args.timeout)
            latency = time.time() - t
            checks, ok = evaluate_case(case, resp)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"✗ {cid:<22} ERROR  {e}")
            results.append({"id": cid, "ok": False, "error": str(e), "checks": []})
            continue

        passed_n += 1 if ok else 0
        mark = "✓" if ok else "✗"
        print(f"{mark} {cid:<22} {'PASS' if ok else 'FAIL'}  ({latency:4.1f}s)")
        for c in checks:
            if not c["ok"]:
                print(f"    └─ failed: {c['name']}")
        results.append({"id": cid, "ok": ok, "latency": round(latency, 2),
                        "checks": checks})

    total = len(cases)
    rate = passed_n / total if total else 0.0
    elapsed = time.time() - t0
    # per-check-type tallies
    all_checks = [c for r in results for c in r.get("checks", [])]
    chk_pass = sum(1 for c in all_checks if c["ok"])
    print("─" * 64)
    print(f"Cases passed : {passed_n}/{total}  ({rate*100:.1f}%)")
    print(f"Checks passed: {chk_pass}/{len(all_checks)}")
    print(f"Total time   : {elapsed:.1f}s · threshold {args.threshold*100:.0f}%")
    print(("✅ PASS" if rate >= args.threshold else "❌ BELOW THRESHOLD") + "\n")

    if args.json_out:
        report = {"api": args.api, "total": total, "passed": passed_n,
                  "pass_rate": rate, "threshold": args.threshold,
                  "elapsed_s": round(elapsed, 1), "results": results}
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to {args.json_out}")

    sys.exit(0 if rate >= args.threshold else 1)


if __name__ == "__main__":
    main()
