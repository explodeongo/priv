# Domain Hub

**Domain Hub — a local TM Forum knowledge assistant *and* an autonomous Open API compliance agent.**

Domain Hub does two things, both entirely on local infrastructure (Ollama + ChromaDB — no cloud API, no per-query cost, no data leaving your environment):

1. **Answers** TM Forum questions in plain English, with citations back to the actual Open API spec files.
2. **Checks, scores, and fixes** your own API specs against the TM Forum standard — and tells you exactly how far they are from the *real* TMF API they're meant to implement.

> **The proof that matters:** the compliance engine is validated against **169 of TM Forum's own official specs** — they score **99.9/100 on average** (168 at a perfect 100). It agrees with TM Forum's published catalogue, so its verdict on *your* spec is trustworthy — and it's fully deterministic (no AI in the scoring), so it's instant, free, repeatable, and auditable.

```
Ask it:                                   Point it at your spec:
"What fields does a Product Order          → "Structure 100/100, but only 26% of the
 have in TMF622?"                             real TMF641 — missing the cancel-order
"Difference between TMF620 and TMF633?"       operation and 21 fields. [Auto-fix]"
"How does pagination work in TMF?"         → an estate-wide X-ray of every API you own.
```

---

## Table of contents
- [Two halves, one engine](#two-halves-one-engine)
- [Where it runs](#where-it-runs)
- [An AI engineering platform for the TM Forum SDLC](#an-ai-engineering-platform-for-the-tm-forum-sdlc)
- [The Knowledge Layer](#the-knowledge-layer)
- [The Governance Layer](#the-governance-layer)
- [Roadmap](#roadmap)
- [The compliance agent](#the-compliance-agent)
- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start-macos--linux)
- [The VS Code extension](#the-vs-code-extension)
- [Command-line tools](#command-line-tools)
- [Integrate & automate (SDK · Action · MCP)](#integrate--automate)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Two halves, one engine

| | **Domain assistant** (RAG) | **Compliance agent** (deterministic) |
|---|---|---|
| Purpose | Understand TM Forum | Conform to TM Forum |
| Powered by | Local LLM + a deterministic knowledge router over the TMF corpus | A rules + diff engine — **no AI** |
| Gives you | Cited answers, follow-ups | A 0–100 score, the gaps, an auto-fix |
| Trust model | Grounded, cited & authority-aware | Validated against 169 official specs |

The same backend serves both — exposed through the **web app**, the **VS Code extension**, a **REST API**, a **Python SDK**, a **CLI**, a **GitHub Action**, and an **MCP server**.

---

## Where it runs

One validated engine, every surface a developer or system might use:

- **Web app** (`http://localhost:3000`) — Chat, Documents, **Conformance & X-ray**, Admin, Settings.
- **VS Code extension** (`vscode-extension/`) — live compliance score, Auto-fix, Scaffold, and the estate X-ray in your editor. See [The VS Code extension](#the-vs-code-extension).
- **REST API + Python SDK** — `backend/` (FastAPI, interactive OpenAPI docs at `/docs`) and a zero-dependency [`synaptdi` SDK](sdk/) for external systems.
- **CLI** — `validate_conformance.py`, `xray.py`, `synaptdi_check.py` for folder scans and CI gates. See [Command-line tools](#command-line-tools).
- **GitHub Action** — [`action.yml`](action.yml) gates pull requests on TMF conformance.
- **MCP server** — [`mcp-server/`](mcp-server/) lets AI agents (Cursor, Claude Desktop, Claude Code) call Domain Hub natively.

> New here? Start with the **[demo runbook](DEMO.md)**.

---

## An AI engineering platform for the TM Forum SDLC

Domain Hub started as a TM Forum chatbot. It is evolving into an **AI engineering platform that spans the full TM Forum software development lifecycle** — *understand → generate → validate → govern* — where every interface is driven by the **same Knowledge Engine and the same Governance Layer**.

The design principle is **one engine, many interfaces**. Each new surface is a thin client over the shared backend; none of them re-implement reasoning, retrieval, or governance. This is what keeps a Word plugin, a VS Code extension, and a Claude MCP tool all giving the *same* cited, version-aware, standards-compliant answer.

```text
  Interfaces      Chat  ·  VS Code  ·  MCP (Claude · Cursor · Codex)  ·  Office plugins
                                        │
  Governance      authority · version-awareness · evidence · compliance · confidence · explainability
     Layer                              │
  Knowledge       Open APIs · ODA · CTK · SID · specs · Git · org knowledge  →  one cited, version-aware engine
     Layer
```

**Interfaces — current and planned** (see the [Roadmap](#roadmap) for the full status matrix):

- **Available today** — AI Chat assistant (web app), VS Code extension, and an MCP server usable from Claude Desktop, Claude Code, and Cursor.
- **In progress** — expanding the MCP server to the ODA and CTK capabilities, with authentication.
- **Roadmap** — ChatGPT / Codex MCP, and Microsoft Word / Excel / PowerPoint plugins.

The goal is not "another chatbot." It is a single, governed reasoning engine that meets a TM Forum engineer wherever they already work.

---

## The Knowledge Layer

The Knowledge Layer is the **unified reasoning engine** underneath every interface. It answers with **citations, confidence scores, and version awareness** — never an ungrounded guess — by combining a deterministic knowledge router over the ingested TM Forum corpus with a local LLM for phrasing.

It progressively ingests and reasons across these sources:

| Source | Status |
|---|---|
| TM Forum Open APIs (Git + published specs) | ✅ Available |
| TM Forum ODA Components (catalog + manifests) | ✅ Available |
| TM Forum specifications | ✅ Available |
| Git repositories | ✅ Available |
| Organizational knowledge (uploaded documents) | ✅ Available |
| TM Forum CTK results as a first-class knowledge source | 🚧 In progress |
| TM Forum SID (Shared Information/Data Model) | 🗺️ Roadmap |

Whatever the source, the contract to the caller is the same: an answer, the **evidence it rests on**, a **confidence score**, and the **version** it applies to.

---

## The Governance Layer

The Governance Layer sits **above** the Knowledge Layer. It is what makes Domain Hub a *trusted engineering assistant* rather than a generic LLM: every answer, generated artifact, and recommendation must pass through it before it reaches a user.

Its responsibilities:

- **TM Forum governance** — enforce that outputs conform to TM Forum standards.
- **Authority resolution** — decide which source is authoritative when sources disagree.
- **Version-aware reasoning** — never blend or confuse API versions (e.g. TMF622 v4 vs v5).
- **Evidence validation** — every claim must be backed by retrievable evidence.
- **Hallucination prevention** — grounded generation; unsupported claims are withheld, not guessed.
- **Policy enforcement** — apply organizational and standards policy to responses.
- **Relationship validation** — check cross-entity relationships (API ↔ component ↔ data model).
- **Compliance verification** — confirm alignment with the applicable TM Forum specification.
- **Confidence scoring** — attach a calibrated confidence to every answer.
- **Explainability** — show *why* an answer was given and *what* it is grounded in.

A large part of this layer exists today (authority resolution, version-aware reasoning, evidence validation, grounded generation, and confidence scoring are live); the remaining responsibilities are being hardened as the platform grows. The governing rule is constant: **if it cannot be grounded and version-scoped, Domain Hub does not assert it.**

---

## Roadmap

Domain Hub is a working product with a clear forward path. This matrix separates what runs today from what is planned, so the vision is never mistaken for the current state.

**Legend:** ✅ Available today · 🚧 In progress · 🗺️ Roadmap

| Area | Capability | Status |
|---|---|---|
| **Interfaces** | AI Chat assistant (web app) | ✅ |
| | VS Code extension (`vscode-extension/`, v0.15.0) | ✅ |
| | MCP server — knowledge + schema-conformance tools (Claude Desktop · Claude Code · Cursor) | ✅ preview |
| | MCP server — ODA catalog, contract resolver & CTK tools + authentication | 🚧 |
| | ChatGPT / Codex MCP server | 🗺️ |
| | Microsoft Word plugin | 🗺️ |
| | Microsoft Excel plugin | 🗺️ |
| | Microsoft PowerPoint plugin | 🗺️ |
| **Knowledge** | Open APIs · ODA · specifications · Git · organizational docs | ✅ |
| | CTK results as a knowledge source | 🚧 |
| | TM Forum SID (Shared Information/Data Model) | 🗺️ |
| **1. Intelligent question answering** | Cited answers, confidence scoring, version-aware retrieval, related questions | ✅ |
| **2. TM Forum code generation** | Spec scaffolding — complete a partial spec from the canonical TMF spec | ✅ |
| | REST APIs · data models · functional blocks in Python / Java | 🗺️ |
| **3. Conformance validation** | TMF630 structural scoring · profile coverage · auto-fix · estate X-ray | ✅ |
| | ODA Component manifest validation · ODA contract resolution | ✅ |
| | ODA CTK execution → deterministic PASS / FAIL / INCOMPLETE verdict | ✅ validated¹ |
| **4. Workflow intelligence** | eTOM process guidance · engineering workflows · SDLC automation | 🗺️ |
| **5. AI integrations** | MCP servers · IDE integrations · enterprise productivity plugins | 🚧 |
| **Governance** | Authority resolution · version-aware reasoning · evidence validation · confidence · explainability | ✅ |

<sub>¹ CTK execution is validated end-to-end against the official TM Forum Component CTK (real PASS/FAIL verdicts from real test runs; see [DEMO.md](DEMO.md)). Running it against a production ODA deployment requires an ODA Canvas–managed cluster.</sub>

### The five capability pillars

1. **Intelligent question answering** *(available)* — grounded, cited answers with confidence and version awareness.
2. **TM Forum code generation** *(scaffolding available; full REST/data-model/Python/Java generation on the roadmap)*.
3. **Conformance validation** *(available)* — Open API validation, ODA component validation, CTK execution, standards compliance.
4. **Workflow intelligence** *(roadmap)* — eTOM process guidance, engineering workflows, and SDLC automation.
5. **AI integrations** *(in progress)* — MCP servers, IDE integrations, and enterprise productivity plugins.

> Every roadmap item extends the **same** Knowledge and Governance layers — new interfaces and capabilities, never a second, ungoverned brain.

---

## The compliance agent

Everything here is **deterministic and offline** — it never calls the LLM, so results are identical every run and safe to gate a CI pipeline on.

### 1. TMF630 structural conformance
Grades any OpenAPI / Swagger spec against the TM Forum API Design Guidelines (TMF630) — collection pagination (`offset`/`limit`), sparse fieldsets (`fields`), sorting, the standard `Error` structure, `@type` polymorphism, `201`/`204` status codes, `lowerCamelCase` naming, versioning — out of 100. **Every finding cites the TMF630 rule it enforces.** Engine: `backend/conformance.py`.

### 2. Profile-aware conformance — *the differentiator*
Detects **which** TMF API your spec is trying to be (e.g. TMF641 Service Ordering) and diffs it against the **real canonical spec** shipped in `backend/data/`, reporting the exact operations and resource attributes you're missing. This is something a generic OpenAPI linter cannot do — it requires TM Forum's whole spec catalogue as ground truth. Engine: `backend/tmf_profile.py`. A confidence gate means it never mislabels a non-TMF file.

### 3. Auto-fix
Deterministically rewrites a spec to satisfy the fixable TMF630 rules (adds the missing query params, the `Error` schema, `@type`, the right status codes, camelCases names) and re-scores it. The *same* engine that flags a violation is the one that fixes it. Endpoint: `POST /conformance/fix`.

### 4. Scaffold the gaps — *generation, not just detection*
Don't just flag what's missing — **add it**. Scaffold pulls the missing operations and resource attributes straight from the canonical TMF spec into your file (version-normalised, no dangling refs), auto-completing a partial API. Demonstrated: a stub Service Order goes **14% → 94%** coverage in one click. Engine: `backend/tmf_profile.scaffold_from_canonical`; endpoint `POST /conformance/scaffold`.

### 5. API estate X-ray
Roll the above across a whole folder/portfolio of specs into one board-ready report — every API, its structural score, its TMF coverage, and its top gaps — sorted worst-first. Engine: `backend/xray.py`; endpoint `POST /conformance/portfolio`; CLI `python xray.py <dir>`.

```
3 APIs analysed · avg structure 77/100 · avg TMF coverage 37% · 1 fully compliant

| API                | Structure | TMF profile  | Coverage | Top gaps                          |
|--------------------|-----------|--------------|----------|-----------------------------------|
| Order Management   | 50/100    | TMF641 v4.1  | 16%      | 6 ops, 22 fields (cancellationReason…) |
| Trouble Ticket     | 80/100    | TMF621 v5.0  | 22%      | 7 ops, 22 fields (attachment, channel…) |
| Customer           | 100/100   | TMF629 v5.0  | 72%      | 9 fields (agreement, creditProfile…)    |
```

### Why you can trust it
- **Validated:** `python validate_conformance.py` runs the engine over every canonical v4/v5 TMF spec — currently **169 specs, avg 99.9, 0 below the gate**. It exits non-zero if any official spec regresses, so it doubles as a CI guard for the engine itself.
- **Tested:** `python test_conformance.py` — 15 unit tests locking in the rules, the auto-fixer, profile detection, scaffolding, and the X-ray.

---

## How it works

**The assistant (Knowledge Engine V2):** every question runs through a deterministic pipeline *before* any text is generated, so the model narrates evidence instead of inventing it.
1. **Ingest** — `ingest.py` clones the TM Forum Open API repo set (TMF620–TMF937 + ODA Canvas + design-guideline/data-model docs), parses each spec into text, embeds it with `nomic-embed-text`, and stores it in ChromaDB.
2. **Route deterministically** — exact entities (`TMF641`, `TMFC050`, versions) are extracted and a rules-based router answers what it can *without the LLM*: ODA component-contract facts (exposed / mandatory / dependent APIs, events) come straight from the canonical component specs; a named spec with no indexed evidence — or a requested version that doesn't exist — triggers an **honest abstention** instead of a guess.
3. **Retrieve** — version- and content-scoped retrieval pulls the named spec's chunks (isolating the requested major version so v4 answers never leak v5), then fills the rest with semantic matches and your uploaded documents.
4. **Govern authority & relationships** — a deterministic gate decides *which source has the right to answer* and *what the evidence is allowed to prove*: it won't pass off an Open API spec as the SID/eTOM authority, won't generalise one API's behaviour into a TM-Forum-wide rule, preserves the exact relationship type (a schema reference is not an API dependency; an ODA dependency is not a runtime call, and its direction is never reversed), and never invents a `format`/`pattern`/`enum` the schema doesn't declare. When the authoritative source is absent, it abstains rather than substituting a weaker one.
5. **Generate** — the scoped evidence + your question go to a local LLM (Llama 3.1 8B in **Deep** mode; a 3B model in **⚡ Fast** mode), which writes a grounded answer with inline `[n]` citations and an **authority-aware confidence** level — or says it doesn't know rather than hallucinating.

**The compliance agent:** parses your spec and runs the deterministic engines above — *no model involved*. The canonical TMF specs in `backend/data/` (cloned at ingest time) are the ground truth for profile detection and the X-ray.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [Ollama](https://ollama.com) | Local LLM + embedding runtime (only needed for **chat**; conformance works without it) |
| [Node.js](https://nodejs.org) (LTS) | Frontend |
| Python 3.9+ | Backend |
| ~8 GB free RAM | For the 8B model (16 GB recommended) |
| Internet (first run only) | To clone the TM Forum spec repos |

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama pull llama3.2          # optional — powers ⚡ Fast mode
```

---

## Quick start (macOS / Linux)

```bash
git clone https://github.com/dibuAI/SynaptDI.git
cd SynaptDI

# Backend
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && cd ..

# Frontend
cd frontend && npm install && echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local && cd ..

# Launch everything (first run auto-ingests the corpus — ~5–10 min, needs Ollama + internet)
./start.sh
```

On Windows use `start.bat` and the `venv\Scripts\activate` path (full notes below in the repo). Prefer Unix tooling on Windows? The steps work as-is inside **WSL**.

When it's ready: **Chat** → http://localhost:3000 · **Conformance & X-ray** → http://localhost:3000/conformance · **API docs** → http://localhost:8000/docs · **Health** → http://localhost:8000/health

### First login
Real auth (hashed passwords + sessions). Seeded accounts: `admin@synaptdi.com / admin123` (admin), `analyst@synaptdi.com / analyst123`, `lisa@synaptdi.com / viewer123`. Change these in production (`backend/storage/users.json`, git-ignored).

> The vector index (`backend/chroma_db/`) and cloned specs (`backend/data/`) are generated locally and **not** committed. Rebuild manually: `cd backend && source venv/bin/activate && python3 ingest.py`.

---

## The VS Code extension

The compliance agent, in your editor. Build/install it:

```bash
cd vscode-extension && npm install && npm run compile
npx @vscode/vsce package --no-dependencies         # produces synaptdi-<version>.vsix
code --install-extension synaptdi-0.14.1.vsix      # or: Extensions panel → ⋯ → Install from VSIX
```

It talks to the backend at `http://localhost:8000` (configurable via the `synaptdi.apiUrl` setting). What you get:

- **Chat that reads your open file** — ask a question and it automatically includes the spec you're editing (a "Reading `orders.yaml`" chip; toggle off anytime), plus a **+ Add file** picker for multi-file context.
- **Live compliance** — spec files are checked **as you type**; a status-bar badge and a chat pill show **`TMF N/100`**, and squiggles in the editor cite the exact TMF630 rule.
- **The coverage pill** — a second **`vs TMF641 · 26%`** pill shows how much of the real TMF API you implement; click it for the full gap report.
- **One-click Auto-fix** and **Apply-as-diff** — fix mechanical issues, or apply a chat's code suggestion as a reviewable diff.
- **API Estate X-ray** — a dashboard button in the panel header scans your workspace (or open spec tabs) into the portfolio report.
- **Local chat history + search**, Fast/Deep toggle, per-answer copy/regenerate.

Try it immediately with the repo's use-case samples in [`examples/`](examples/) — `1-single-api-check/product-ordering.broken.yaml` for a single spec, `2-portfolio-xray/` for the X-ray, `3-oda-component/` for ODA components. See [`examples/README.md`](examples/README.md).

---

## Command-line tools

All pure-Python, offline, and CI-friendly (`cd backend && source venv/bin/activate`):

| Command | Purpose |
|---|---|
| `python validate_conformance.py [--min 90] [--json]` | Run the engine over every official TMF spec; exit 1 if any drops below the gate. Engine self-test / regression guard. |
| `python xray.py <folder>` | API estate X-ray of a folder — prints the report and writes `synaptdi-xray.md`. |
| `python synaptdi_check.py <files…> [--min 90]` | Gate your *own* specs in CI — exits non-zero if any scores below `--min`. See `backend/COMPLIANCE.md` for a pre-commit hook + GitHub Actions snippet. |
| `python test_conformance.py` | The 15-test unit suite (also pytest-compatible). |

---

## Integrate & automate

**Python SDK** ([`sdk/`](sdk/)) — zero-dependency client for the REST API:
```python
from synaptdi import SynaptDI
sd = SynaptDI("http://localhost:8000")
sd.check("orders.yaml")["score"]       # TMF630 score
sd.profile("orders.yaml")["coverage"]  # % of the real canonical TMF API
sd.xray(["a.yaml", "b.yaml"])          # portfolio report
```

**GitHub Action** ([`action.yml`](action.yml)) — gate pull requests on TMF conformance:
```yaml
- uses: dibuAI/SynaptDI@v1
  with:
    path: ./specs
    min: "90"
```

**MCP server** ([`mcp-server/`](mcp-server/)) — let Cursor / Claude Desktop / Claude Code call Domain Hub natively (`tmf_ask`, `tmf_check`, `tmf_profile`, `tmf_scaffold`). Config in [`mcp-server/README.md`](mcp-server/README.md).

---

## Configuration

The backend reads these (all optional). Conformance needs none of them — only chat uses the models.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `llama3.1:8b` | Ollama model for **Deep** answers |
| `FAST_MODEL` | `llama3.2:latest` | Model for **⚡ Fast** mode |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `CHROMA_PATH` | `./chroma_db` | Vector DB location |
| `WARM_MODELS` | `1` | Pre-load the LLM at startup (`0` to disable) |
| `NUM_CTX` | `4096` | Context window |
| `VECTOR_BACKEND` | `chroma` | Vector store (interface allows future Milvus/Qdrant/pgvector) |

Frontend reads `NEXT_PUBLIC_API_URL` (`frontend/.env.local`, default `http://localhost:8000`).

---

## Project structure

```
SynaptDI/
├── start.sh / start.bat        ← Ollama check, ingest (if needed), backend + frontend
├── docker-compose.yml          ← one-command deploy (see DEPLOY.md)
├── backend/
│   ├── main.py                 ← FastAPI app: RAG query engine + all /conformance/* endpoints
│   ├── ingest.py               ← clone + parse + embed + index the TM Forum corpus
│   ├── knowledge_*.py          ← Knowledge Engine V2: deterministic router + authority/relationship governance (pre-RAG)
│   ├── oda_component_contract.py ← canonical ODA component-contract resolver (exposed/dependent APIs, events)
│   ├── conformance.py          ← TMF630 structural rule engine (deterministic)
│   ├── tmf_profile.py          ← profile-aware conformance + scaffold (diff/complete vs canonical)
│   ├── xray.py                 ← API estate X-ray (portfolio roll-up) + CLI
│   ├── validate_conformance.py ← validate the engine vs 169 official specs / CI gate
│   ├── synaptdi_check.py       ← CI gate for your own specs
│   ├── test_conformance.py     ← 15 unit tests (conformance · fixer · profile · scaffold · X-ray)
│   ├── COMPLIANCE.md           ← CLI usage, pre-commit hook, GitHub Actions
│   ├── vectorstore.py · eval.py · evals/
│   ├── chroma_db/  data/       ← generated, gitignored
├── frontend/app/               ← Next.js: Chat · Documents · Conformance & X-ray · Admin · Settings
├── vscode-extension/           ← Domain Hub VS Code extension + examples/ (demo specs)
├── sdk/                        ← zero-dependency Python SDK (synaptdi)
├── mcp-server/                 ← MCP server for Cursor / Claude / Claude Code
├── action.yml + .github/       ← reusable GitHub Action + the TMF-conformance workflow
└── DEMO.md                     ← demo runbook
```

---

## API reference

**Assistant** — `POST /query` · `POST /query/stream` (token streaming) · `POST /followups` · `GET /coverage` · `GET /health` · `GET /stats` · `GET /analytics` (admin). `GET /health` and `GET /stats` also report the active vector collection and the **authority-availability inventory** — which authoritative source classes (Open API schema, ODA contract, SID, eTOM, design guidance) are actually present in the index.

**Compliance** (all deterministic, no LLM):

| Endpoint | Does |
|---|---|
| `POST /conformance` | TMF630 audit of an uploaded spec file (multipart) |
| `POST /conformance/text` | TMF630 score **+ profile coverage**, from a JSON body — used by the editor |
| `POST /conformance/profile` | Detect the TMF API and diff vs the canonical spec |
| `POST /conformance/fix` | Auto-fix fixable TMF630 violations, return the corrected spec |
| `POST /conformance/scaffold` | Complete a partial spec from the canonical TMF spec |
| `POST /conformance/portfolio` | API estate X-ray across many specs (+ rendered markdown) |
| `POST /conformance/component` | **ODA Component conformance** — score the APIs a `.component.yaml` exposes/depends on |

Full interactive docs at `http://localhost:8000/docs`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: uvicorn` | Activate the venv (`source backend/venv/bin/activate`) or use `./start.sh` |
| `503` / "Embedding failed" | Ollama isn't running: `ollama serve &`, then retry (chat only — conformance is unaffected) |
| Chat says "not in the knowledge base" for everything | The index didn't build — `cd backend && python3 ingest.py` with Ollama running |
| Answers slow on a CPU laptop | Use the **⚡ Fast** toggle; see **[PERFORMANCE.md](PERFORMANCE.md)** |
| VS Code X-ray says "no files to X-ray" | Open the folder (or the spec files) you want to scan, then run it again |
| Extension shows no score | Ensure the backend is on `:8000` (the `synaptdi.apiUrl` setting) and the file is an OpenAPI/Swagger spec |

---

## Deploy & performance
- **[DEPLOY.md](DEPLOY.md)** — one-command Docker Compose (backend + frontend + Ollama, one URL for the team).
- **[PERFORMANCE.md](PERFORMANCE.md)** — speeding up the *same* full-quality answer (flash-attention, Intel IPEX-LLM, a GPU host).

---

## Stack

| Layer | Tool |
|---|---|
| LLM / Embeddings | Llama 3.1 8B · nomic-embed-text (via Ollama) |
| Vector DB | ChromaDB (local, cosine) |
| Conformance | Pure-Python rules + diff engine (no AI) |
| Backend | FastAPI + Python |
| Frontend | Next.js + Tailwind CSS |
| Editor | VS Code extension (TypeScript) |
| Integrations | REST API · Python SDK · MCP server · GitHub Action (all stdlib / no extra deps) |

---

*Domain Hub — a local, citation-grounded RAG assistant **and** a validated TM Forum compliance agent. Ask it anything about TM Forum; point it at your APIs and it tells you the truth.*
