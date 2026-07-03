# SynaptDI — TM Forum compliance, in your editor

SynaptDI brings a **local TM Forum knowledge assistant** and an **autonomous Open API compliance agent** into VS Code. Ask questions about the spec you're writing, and get a live, deterministic score of how well it conforms to the TM Forum standard — with one-click fixes. It talks to your running [SynaptDI backend](https://github.com/dibuAI/SynaptDI) and keeps everything local.

> The compliance engine is validated against **169 of TM Forum's own official specs** (avg 99.9/100) and is fully deterministic — no AI in the scoring, so its verdict on your spec is trustworthy, instant, and repeatable.

---

## Chat that reads your code

Open the **SynaptDI** panel in the activity bar and ask anything:

- **Reads your open file automatically** — a *"Reading `orders.yaml`"* chip appears above the box, so you can ask *"is this compliant?"* without pasting anything. Toggle it off for a general question, or use **+ Add file** to include several specs at once.
- **Cited, streaming answers** with full Markdown (headings, tables, syntax-highlighted code), clickable source chips, and suggested follow-ups.
- **Fast / Deep** toggle, per-answer **Copy** / **Regenerate**, and a live backend-status dot.
- **Local history + search** — every chat is saved on your machine (no login), grouped by date, full-text searchable. Header **History** button.
- **Apply-as-diff** — every code block the assistant returns has **Copy** and **Apply**; *Apply* opens a reviewable diff against your file before anything changes.

## Live compliance, as you type

Open any OpenAPI / Swagger spec and SynaptDI checks it against the TM Forum Design Guidelines (TMF630) **in real time** — no command, no save:

- A status-bar badge and a chat pill show **`TMF N/100`**; editor squiggles mark each issue and **cite the exact TMF630 rule** behind it.
- **Auto-fix** — when there are mechanical issues, an **`Auto-fix N`** button (and editor-title wand) deterministically adds the missing pagination params, `Error` schema, `@type`, status codes, and camelCases names, then re-scores.

## Coverage against the *real* TMF API

SynaptDI detects **which** TMF API your spec is meant to be and compares it to the canonical spec:

- A second pill, **`vs TMF641 · 26%`**, shows how much of the real API you actually implement.
- Click it (or run **TMF Profile Report**) for the full gap list — the exact operations and resource attributes you're missing.

## API Estate X-ray

The **dashboard button** in the panel header (or *API Estate X-ray* in the palette) scans your whole workspace — or just the spec tabs you have open — into a **board-ready portfolio report**: every API, its structural score, its TMF coverage, and its top gaps, opened as a Markdown preview you can hand to a client.

## Right-click any code → SynaptDI
**Explain Selected Code** · **Check TM Forum Compliance** · **Auto-fix TM Forum Issues** · **Validate Against TM Forum Spec** (AI review) · **Generate API Client**. (No selection? It uses the whole file.)

---

## Commands

| Command | What it does |
|---|---|
| `SynaptDI: Ask a question` | Free-form question in the panel |
| `SynaptDI: Check TM Forum Compliance` | TMF630 score for the active spec |
| `SynaptDI: Auto-fix TM Forum Issues` | Deterministically fix fixable issues |
| `SynaptDI: TMF Profile Report` | Detect the API + diff vs the canonical spec |
| `SynaptDI: API Estate X-ray` | Portfolio report across the workspace / open specs |
| `SynaptDI: Scan Workspace for TM Forum Compliance` | Score every spec into the output channel |
| `SynaptDI: Explain Selected Code` · `Validate…` · `Generate API Client` · `New Chat` | Editor actions + chat reset |

## Settings

| Setting | Default | Description |
|---|---|---|
| `synaptdi.apiUrl` | `http://localhost:8000` | Base URL of the SynaptDI backend |
| `synaptdi.scope` | `all` | Default chat scope: `all` · `kb` (knowledge base) · `docs` (your uploads) |

> The panel needs to reach the backend — make sure SynaptDI is running (`./start.sh` / `start.bat`). The chat needs Ollama; the **compliance, profile, and X-ray features work without it**.

---

## Install

**From VS Code (no terminal):** ⇧⌘P → **"Extensions: Install from VSIX…"** → pick `synaptdi-0.15.0.vsix` → reload. A **SynaptDI** icon appears in the activity bar.

**From the terminal:**
```bash
code --install-extension synaptdi-0.15.0.vsix
```

## Try it in 30 seconds
Open the repo's samples (`examples/` at the repo root):
- `examples/1-single-api-check/product-ordering.broken.yaml` → watch the score, the `vs TMF622` pill, and **Auto-fix**.
- Open the `examples/2-portfolio-xray/` folder → hit the **dashboard** button for the X-ray report.

See `examples/README.md` for the full use-case guide.

## Develop / package
```bash
cd vscode-extension
npm install
npm run compile                              # builds out/extension.js
# open this folder in VS Code → press F5 → Extension Development Host
npx @vscode/vsce package --no-dependencies   # produces synaptdi-<version>.vsix
```
