#!/usr/bin/env python3
"""
Validate the TMF630 conformance engine against TM Forum's OWN reference specs.

The official, TMF-published Open API specs are the ground truth: a trustworthy
checker must score them at (or very near) 100. This script runs the engine over
every canonical spec under backend/data/ and fails (exit 1) if any official spec
drops below --min. It's pure/offline (no LLM, no network) — safe to run anywhere
and a good CI regression gate after changing any rule.

    python validate_conformance.py            # table + summary
    python validate_conformance.py --min 95   # stricter gate
    python validate_conformance.py --json
"""
import argparse
import glob
import json
import os
import re
import sys

import conformance

try:
    import yaml
except Exception:
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# Canonical, modern TMF release files (v4/v5 — the versions the current TMF630
# guidelines actually govern): "...-v4.0.0.swagger.json" / "...-v5.0.0.oas.yaml".
# Pre-v4 drafts predate these conventions and are intentionally out of scope.
CANONICAL = re.compile(r"-v[45]\.\d+\.\d+.*\.(swagger\.json|oas\.ya?ml)$", re.I)


def _load(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    try:
        return json.loads(text)
    except Exception:
        if yaml:
            try:
                return yaml.safe_load(text)
            except Exception:
                return None
    return None


def collect():
    out = []
    for path in glob.glob(os.path.join(DATA, "**", "*"), recursive=True):
        if os.path.isfile(path) and CANONICAL.search(os.path.basename(path)):
            out.append(path)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Validate the TMF630 engine against official TMF specs.")
    ap.add_argument("--min", type=int, default=90, help="Fail if any official spec scores below this (default 90).")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = ap.parse_args()

    specs = collect()
    rows, failures = [], []
    for path in specs:
        spec = _load(path)
        if not isinstance(spec, dict):
            continue
        try:
            r = conformance.check_spec(spec)
        except Exception as e:  # a crash on a real spec is itself a failure
            rows.append({"file": os.path.basename(path), "score": -1, "error": str(e)})
            failures.append(path)
            continue
        fails = [f["id"] for f in r["findings"] if f["status"] == "fail" and f["severity"] in ("error", "warning")]
        rows.append({"file": os.path.basename(path), "api": r["api"], "score": r["score"], "fails": fails})
        if r["score"] < args.min:
            failures.append(path)

    scored = [x["score"] for x in rows if x["score"] >= 0]
    summary = {
        "checked": len(rows),
        "min_required": args.min,
        "avg": round(sum(scored) / len(scored), 1) if scored else 0,
        "min": min(scored) if scored else 0,
        "at_100": sum(1 for s in scored if s == 100),
        "below_min": len(failures),
    }

    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, indent=2))
    else:
        print("%-60s %7s  %s" % ("OFFICIAL TMF SPEC", "SCORE", "remaining issues"))
        print("-" * 100)
        for x in rows:
            mark = "" if x["score"] >= args.min else "  ◀ BELOW MIN"
            print("%-60s %5s/100  %s%s" % (x["file"][:60], x["score"], ",".join(x.get("fails") or []) or "clean", mark))
        print("-" * 100)
        print("checked %(checked)d · avg %(avg)s · min %(min)s · %(at_100)d at 100/100 · %(below_min)d below %(min_required)d"
              % summary)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
