# SynaptDI — 30-second demo

A deterministic TM Forum (TMF630) compliance agent, live in VS Code. No AI is
needed for the checking and fixing — those are a pure, offline rules engine, so
they're instant and reproducible. (Only the *chat* step needs the model running.)

## Prerequisites
1. SynaptDI backend running on `http://localhost:8000` (`./start.sh` from the repo root).
2. The **SynaptDI** extension installed (`synaptdi-0.9.0.vsix` or later) and reloaded.
3. *(Chat step only)* Ollama running (`ollama serve`).

## Walkthrough

**1 — Open the broken spec.**
Open [`product-ordering.broken.yaml`](product-ordering.broken.yaml). Within a moment you'll see:
- **Red squiggles** on the offending lines (Problems panel lists each rule + the fix).
- A status-bar badge: **`TMF 0/100`**.

**2 — Watch it check as you type.**
Add a space and delete it. The score re-computes live (~0.7s after you stop typing) —
no save, no command. This is the "it checks automatically" part.

**3 — See the score in the chat.**
Open the **SynaptDI** panel (activity bar). Above the message box, next to
**Reading `product-ordering.broken.yaml`**, a shield pill shows:

> 🛡 **`0/100` · 3 errors · 4 warnings**   🪄 **Auto-fix 8**

**4 — Auto-fix.**
Click **`Auto-fix 8`**. The deterministic engine rewrites the spec in place
(camelCase fields, `offset`/`limit`/`fields`/`sort` params, `201`/`204` status
codes, a TMF `Error` schema, `@type` discriminators) and re-checks:

> 🛡 **`100/100` · all checks pass**

**5 — Ask about it (needs Ollama).**
Type **"Is this spec TMF-compliant, and what was wrong with it?"** — because the
chat auto-reads the open file, you get a cited answer grounded in the TM Forum
knowledge base, no copy-paste.

## What just happened
| Step | Powered by | AI? |
|------|------------|-----|
| Squiggles + score | TMF630 rules engine (`conformance.py`) | No |
| Live re-check on type | same engine, debounced | No |
| Auto-fix | same engine (`fix_spec`) | No |
| Cited chat answer | RAG over the TM Forum corpus | Yes (Ollama) |

The checking and fixing are deterministic by design — that's the moat: the same
engine that *flags* a violation is the one that *fixes* it, so results are
auditable and identical every run.
