# SynaptDI

**Synapt Domain Intelligence — enterprise domain knowledge at your fingertips.**

Ask TM Forum questions in plain English and get accurate, **cited** answers grounded in the actual Open API spec files — with links back to the source on GitHub. Runs **entirely on local infrastructure** via Ollama: no cloud API, no per-query cost, no data leaving your environment.

```
"What mandatory fields does a Product Order have in TMF622?"
"What's the difference between TMF620 and TMF633?"
"How do I handle pagination in TM Forum Open APIs?"
"Which ODA component handles trouble tickets?"
```

---

## How it works

SynaptDI is a Retrieval-Augmented Generation (RAG) system over the TM Forum Open API corpus:

1. **Ingest** — `ingest.py` clones the full TM Forum Open API repo set (~88 `TMFxxx` API repos + ODA Canvas + design-guideline/data-model docs), parses each OpenAPI spec into natural-language text, chunks it, embeds it with `nomic-embed-text`, and stores it in ChromaDB.
2. **Retrieve** — on each question the backend detects which spec(s) you mean — **by number (`TMF641`) or by name (`Product Catalog Management API`)** — and pulls that spec's own chunks directly, so the right spec is always in context. It then fills remaining slots with general semantic matches and any relevant uploaded documents.
3. **Generate** — the retrieved chunks + your question go to a local LLM (Llama 3.1 8B via Ollama in **Deep mode**; a 3B model powers **⚡ Fast mode**), which writes a grounded answer with inline `[n]` citations. If nothing relevant is found — or the question is off-domain — it says so instead of hallucinating.

Current knowledge base: **~10,800 chunks across 74 TM Forum specs.**

---

## What's inside

- **Cited answers** — inline `[n]` citations linking to the exact spec chunk + GitHub source, plus suggested follow-up questions and a live "searching TMF…" trace while it thinks.
- **Deep / ⚡ Fast modes** — the full 8B for accuracy or a 3B for instant lookups; repeated questions are cached and return instantly.
- **TMF630 Conformance checker** — upload your own OpenAPI spec and get a scored report of where it deviates from TM Forum design rules.
- **Add knowledge from the UI** — upload files (PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, JSON, YAML), point at a Git repo, or paste a web link.
- **Admin** — live branding (logo + colour-wheel theme), users & RBAC, and an adoption dashboard (active users, daily volume, answer rate, knowledge gaps).
- **Dark mode**, a **⌘K command palette**, and a **VS Code extension** (`vscode-extension/`).
- **Self-hostable** — one-command Docker deploy (**[DEPLOY.md](DEPLOY.md)**) and an automated eval harness (`backend/eval.py`).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [Ollama](https://ollama.com) | Local LLM + embedding runtime |
| [Node.js](https://nodejs.org) (LTS) | Frontend |
| Python 3.9+ | Backend |
| ~8 GB free RAM | For the 8B model (16 GB recommended) |
| Internet (first run only) | To clone the TM Forum spec repos |

Pull the models once:
```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama pull llama3.2          # optional — powers ⚡ Fast mode (smaller, much quicker on CPU)
```

> **On the model:** the product spec references "Llama 3.3 8B", but Llama 3.3 ships only in 70B — the genuine latest-generation 8B is **Llama 3.1 8B**, which is what SynaptDI uses. To use a different model, set the `LLM_MODEL` env var (see [Configuration](#configuration)).

---

## Quick start (macOS / Linux)

```bash
# 1. Clone
git clone https://github.com/dibuAI/SynaptDI.git
cd SynaptDI

# 2. Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# 3. Frontend
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
cd ..

# 4. Launch everything
./start.sh
```

## Quick start (Windows)

Same steps, but use the Windows venv path and the `start.bat` launcher. In **Command Prompt** or **PowerShell**:

```bat
:: 1. Clone
git clone https://github.com/dibuAI/SynaptDI.git
cd SynaptDI

:: 2. Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd ..

:: 3. Frontend
cd frontend
npm install
cd ..

:: 4. Launch everything (opens backend + frontend in separate windows)
start.bat
```

**Windows prerequisites:** install [Git](https://git-scm.com/download/win), [Python 3.10+](https://www.python.org/downloads/windows/) (check **"Add python.exe to PATH"** during install), [Node.js LTS](https://nodejs.org), and [Ollama for Windows](https://ollama.com/download/windows). Then pull the models: `ollama pull llama3.1:8b` and `ollama pull nomic-embed-text`. The frontend defaults to `http://localhost:8000`, so `.env.local` is optional. *(Prefer Unix tooling? The macOS/Linux steps also work as-is inside **WSL**.)*

On the **first** launch, `start.sh` detects there is no index and runs `ingest.py` automatically — it clones the TM Forum repos and builds the vector index (**~5–10 minutes**, requires Ollama running and internet). Subsequent launches start in seconds.

When it's ready:
- **Chat UI** → http://localhost:3000
- **API docs** → http://localhost:8000/docs
- **Health** → http://localhost:8000/health

### First login

Authentication is real (hashed passwords + sessions). Seeded demo accounts:

| Email | Password | Role |
|---|---|---|
| `admin@synaptdi.com` | `admin123` | admin (can add knowledge, manage users) |
| `analyst@synaptdi.com` | `analyst123` | analyst |
| `lisa@synaptdi.com` | `viewer123` | viewer |

Change these in production (passwords are hashed in `backend/storage/users.json`, which is git-ignored).

### Adding knowledge (no scripts needed)

As an **admin/analyst**, go to **Documents** and add sources from the UI:
- **Upload a file** (PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, JSON, YAML)
- **Git repo URL** — clones & indexes any GitHub / TM Forum / MEF repo's OpenAPI specs + docs
- **Web link** — fetches a page or PDF and indexes its text

Each source indexes in the background and can be deleted (with all its chunks) in one click. In chat, the **Search scope** toggle lets you ask across *Everything*, the *Knowledge Base*, or *My Documents*.

> The vector index (`backend/chroma_db/`) and cloned specs (`backend/data/`) are **not** committed — they are generated locally by the ingest step. To rebuild the base index manually: `cd backend && source venv/bin/activate && python3 ingest.py`.

---

## Configuration

The backend reads these environment variables (all optional, with sensible defaults):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `llama3.1:8b` | Ollama model for **Deep**-mode answers |
| `FAST_MODEL` | `llama3.2:latest` | Model for **⚡ Fast** mode |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `CHROMA_PATH` | `./chroma_db` | Vector DB location |
| `LLM_CONCURRENCY` | `1` | Parallel generations (raise only with a GPU) |
| `WARM_MODELS` | `1` | Pre-load the LLM at startup so the first query isn't cold (`0` to disable) |
| `VECTOR_BACKEND` | `chroma` | Vector-store backend (interface allows future Milvus/Qdrant/pgvector) |

The frontend reads `NEXT_PUBLIC_API_URL` (set in `frontend/.env.local`, default `http://localhost:8000`).

Example — run with a smaller/faster model:
```bash
LLM_MODEL=llama3.2 uvicorn main:app --port 8000
```

---

## Knowledge base

**Included** (cloned automatically by `ingest.py`): the TM Forum Open API suite (TMF620–TMF937), ODA Canvas docs, reference example components, REST design guidelines and data-model docs — sourced from the public `tmforum-apis` and `tmforum-oda` GitHub organizations.

**Not included:** member-portal PDFs (TMF630 Design Guidelines, eTOM GB921, SID GB922) are not in the free GitHub repos. Common patterns from them (e.g. pagination via `offset`/`limit`) are still answerable because they appear across the specs, but deep framework-concept questions need those PDFs added manually. You can upload additional documents (incl. PDFs) at runtime via the Documents page.

---

## Stack

| Layer | Tool |
|---|---|
| LLM | Llama 3.1 8B via Ollama |
| Embeddings | nomic-embed-text via Ollama |
| Vector DB | ChromaDB (local, cosine) |
| Backend | FastAPI + Python |
| Frontend | Next.js + Tailwind CSS |

---

## Project structure

```
SynaptDI/
├── start.sh / start.bat    ← Ollama check, ingest (if needed), backend + frontend
├── docker-compose.yml      ← one-command deploy (see DEPLOY.md)
├── backend/
│   ├── main.py             ← FastAPI app + spec-aware RAG query engine
│   ├── ingest.py           ← clone + parse + embed + index the TM Forum corpus
│   ├── vectorstore.py      ← backend-agnostic vector store (Chroma today)
│   ├── conformance.py      ← TMF630 conformance rule engine
│   ├── eval.py + evals/    ← automated quality harness + golden set
│   ├── requirements.txt · Dockerfile
│   ├── chroma_db/          ← vector index   (generated; gitignored)
│   └── data/               ← cloned spec repos (generated; gitignored)
├── frontend/
│   └── app/                ← Next.js: Chat, Documents, Conformance, Admin, Settings
└── vscode-extension/       ← "Ask SynaptDI" VS Code extension
```

---

## API reference

**`POST /query`** — ask a question
```json
{ "question": "What mandatory fields does a Product Order have in TMF622?", "top_k": 8 }
```
Response: `{ answer, sources[], latency_ms, chunks_retrieved }`

Key endpoints: **`POST /query/stream`** (token streaming) · **`POST /conformance`** (TMF630 spec audit) · **`GET /coverage`** (indexed specs by domain) · **`POST /followups`** · **`GET /health`** · **`GET /stats`** · **`GET /analytics`** (admin). Full interactive docs at `http://localhost:8000/docs`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: uvicorn` | Activate the venv (`source backend/venv/bin/activate`) or just use `./start.sh` |
| `Address already in use` | App is already running — open http://localhost:3000 |
| `503` / "Embedding failed" | Ollama isn't running: `ollama serve &`, then retry |
| Answer says "not in the knowledge base" for everything | The index didn't build — run `cd backend && python3 ingest.py` with Ollama running |
| Answers are slow / "request timed out" | An 8B model on a CPU-only PC is slow — especially the first (cold) query. Use the **⚡ Fast** toggle in chat, warm the model once with `ollama run llama3.1:8b "hi"`, check `ollama ps` (GPU vs CPU), or run on Apple Silicon / a GPU box. The chat no longer hard-times-out — it keeps waiting as long as tokens are streaming. |
| Frontend loads but can't reach API | Ensure `frontend/.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000` |

---

*SynaptDI — a local, citation-grounded RAG assistant for TM Forum Open API standards.*

## Deploy for your team
One command on a shared server — see **[DEPLOY.md](DEPLOY.md)** (Docker Compose: backend + frontend + Ollama, one URL for everyone).
