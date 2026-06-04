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
3. **Generate** — the retrieved chunks + your question go to a local LLM (Llama 3.1 8B via Ollama), which writes a grounded, cited answer. If nothing relevant is found, it says so instead of hallucinating.

Current knowledge base: **~9,300 chunks across 74 TM Forum specs.**

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
```

> **On the model:** the product spec references "Llama 3.3 8B", but Llama 3.3 ships only in 70B — the genuine latest-generation 8B is **Llama 3.1 8B**, which is what SynaptDI uses. To use a different model, set the `LLM_MODEL` env var (see [Configuration](#configuration)).

---

## Quick start

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

On the **first** launch, `start.sh` detects there is no index and runs `ingest.py` automatically — it clones the TM Forum repos and builds the vector index (**~5–10 minutes**, requires Ollama running and internet). Subsequent launches start in seconds.

When it's ready:
- **Chat UI** → http://localhost:3000
- **API docs** → http://localhost:8000/docs
- **Health** → http://localhost:8000/health

> The vector index (`backend/chroma_db/`) and cloned specs (`backend/data/`) are **not** committed to the repo — they are generated locally by the ingest step. To rebuild the index manually at any time: `cd backend && source venv/bin/activate && python3 ingest.py`.

---

## Configuration

The backend reads these environment variables (all optional, with sensible defaults):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `llama3.1:8b` | Ollama model used for answers |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `CHROMA_PATH` | `./chroma_db` | Vector DB location |

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
├── start.sh                ← starts Ollama check, ingest (if needed), backend + frontend
├── backend/
│   ├── main.py             ← FastAPI app + spec-aware RAG query engine
│   ├── ingest.py           ← clone + parse + embed + index the TM Forum corpus
│   ├── requirements.txt
│   ├── chroma_db/          ← vector index   (generated; gitignored)
│   └── data/               ← cloned spec repos (generated; gitignored)
└── frontend/
    └── app/                ← Next.js chat UI, Documents, Admin, Settings
```

---

## API reference

**`POST /query`** — ask a question
```json
{ "question": "What mandatory fields does a Product Order have in TMF622?", "top_k": 8 }
```
Response: `{ answer, sources[], latency_ms, chunks_retrieved }`

Other endpoints: **`GET /health`** (backend + Ollama status), **`GET /stats`** (chunks indexed), **`POST /documents/upload`** (add your own docs). Full interactive docs at `http://localhost:8000/docs`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: uvicorn` | Activate the venv (`source backend/venv/bin/activate`) or just use `./start.sh` |
| `Address already in use` | App is already running — open http://localhost:3000 |
| `503` / "Embedding failed" | Ollama isn't running: `ollama serve &`, then retry |
| Answer says "not in the knowledge base" for everything | The index didn't build — run `cd backend && python3 ingest.py` with Ollama running |
| Answers take ~10–25s | Normal for an 8B model on CPU; set `LLM_MODEL=llama3.2` for faster (less precise) responses, or run on Apple Silicon/GPU |
| Frontend loads but can't reach API | Ensure `frontend/.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000` |

---

*SynaptDI — a local, citation-grounded RAG assistant for TM Forum Open API standards.*
