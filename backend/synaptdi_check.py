#!/usr/bin/env python3
"""
SynaptDI compliance gate
════════════════════════
Scan OpenAPI / Swagger specs against the TM Forum API Design Guidelines (TMF630) and
exit non-zero if any spec falls below a threshold — drop it into CI or a pre-commit hook
to keep a repo TMF-compliant on its own.

Pure & offline: uses the same deterministic engine as the app (no server, no LLM).

Usage:
    python synaptdi_check.py ./apis                 # scan a directory tree
    python synaptdi_check.py "specs/**/*.yaml"      # globs
    python synaptdi_check.py api.yaml --min 95      # custom threshold
    python synaptdi_check.py ./apis --json          # machine-readable report
"""
import sys, os, json, glob, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # find conformance.py next to us
import conformance


def _load(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    try:
        return json.loads(text)
    except Exception:
        try:
            import yaml
            return yaml.safe_load(text)
        except Exception:
            return None


def _is_spec(d) -> bool:
    return isinstance(d, dict) and bool(d.get("paths") or d.get("components") or d.get("definitions"))


def _collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ("yaml", "yml", "json"):
                files += glob.glob(os.path.join(p, "**", "*." + ext), recursive=True)
        else:
            files += glob.glob(p, recursive=True)
    return sorted({f for f in files if os.path.isfile(f) and "node_modules" not in f})


def main() -> int:
    ap = argparse.ArgumentParser(description="TM Forum (TMF630) compliance gate")
    ap.add_argument("paths", nargs="+", help="spec files, directories, or globs")
    ap.add_argument("--min", type=int, default=90, help="minimum passing score 0-100 (default 90)")
    ap.add_argument("--json", action="store_true", help="emit a JSON report instead of a table")
    args = ap.parse_args()

    results, worst = [], 100
    for f in _collect(args.paths):
        spec = _load(f)
        if not _is_spec(spec):
            continue
        rep = conformance.check_spec(spec)
        results.append({"file": f, "score": rep["score"], **rep["summary"]})
        worst = min(worst, rep["score"])

    if args.json:
        print(json.dumps({"min": args.min, "passed": all(r["score"] >= args.min for r in results),
                          "results": results}, indent=2))
    elif not results:
        print("No OpenAPI/Swagger specs found.")
        return 0
    else:
        print(f"\nTM Forum compliance (TMF630) — threshold {args.min}/100\n" + "-" * 60)
        for r in sorted(results, key=lambda x: x["score"]):
            tag = "PASS" if r["score"] >= args.min else "FAIL"
            print(f"  [{tag}] {r['score']:3d}/100   {r['failed']}E {r['warnings']}W   {r['file']}")
        npass = sum(1 for r in results if r["score"] >= args.min)
        print("-" * 60)
        print(f"  {npass}/{len(results)} specs pass · lowest {worst}/100")

    return 1 if any(r["score"] < args.min for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
