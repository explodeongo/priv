"""Screenshot-ready Scaffold demo (deck slide 11).

Shows the coverage jump + the operations/fields SynaptDI merges in from the canonical
TM Forum spec — the deterministic "complete a partial spec" capability.

Usage:
    python scaffold_demo.py                       # uses the bundled broken example
    python scaffold_demo.py path/to/your-spec.yaml

Needs the backend running on :8000 (WARM_MODELS=0 is fine — no Ollama required).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))
from synaptdi import SynaptDI  # noqa: E402

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "examples",
                        "1-single-api-check", "product-ordering.broken.yaml")


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT
    r = SynaptDI().scaffold(spec)
    d = r["detected"]
    ops, fields = r["added"]["operations"], r["added"]["fields"]
    print()
    print("  SynaptDI · Scaffold from canonical spec")
    print("  file:     %s" % os.path.basename(spec))
    print("  detected: %s %s" % (d["tmf"], d.get("title", "")))
    print("  " + "-" * 54)
    print("  Coverage vs canonical %s:   %s%%  →  %s%%"
          % (d["tmf"], r["coverage_before"], r["coverage_after"]))
    print("  Merged in: %d operations, %d resource fields" % (len(ops), len(fields)))
    print()
    for o in ops:
        print("    +  " + o)
    print("    +  fields: " + ", ".join(fields[:8]) + (" …" if len(fields) > 8 else ""))
    print()


if __name__ == "__main__":
    main()
