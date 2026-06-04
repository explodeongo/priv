# SynaptDI
**Synapt Domain Intelligence — Enterprise domains at your fingertips**

Ask TM Forum questions in plain English. Get accurate, cited answers grounded in the actual spec files, with direct links to GitHub. Runs entirely on your machine — no cloud API, no per-query cost.

---

## First Time? Start Here (~10 minutes, once only)

### Step 1 — Install Ollama
Download from **https://ollama.com** and install it. Then open Terminal and run:
```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```
Wait for both downloads to finish (~2 GB total).

### Step 2 — Install Node.js (if you don't have it)
Download the LTS version from **https://nodejs.org** and install it.

### Step 3 — Set up the backend
```bash
cd /Users/aryan/Downloads/axiom/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4 — Set up the frontend
```bash
cd /Users/aryan/Downloads/axiom/frontend
npm install
```

### Step 5 — Launch
```bash
cd /Users/aryan/Downloads/axiom
./start.sh
```
The first run downloads and indexes ~2,600 TM Forum spec chunks — takes about 5 minutes. After that, open **http://localhost:3000**.

---

## Returning User (app was closed)

One command:
```bash
cd /Users/aryan/Downloads/axiom && ./start.sh
```
Then open **http://localhost:3000**. Ready in ~10 seconds.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: uvicorn` | Don't run uvicorn directly — use `./start.sh` instead |
| `Address already in use` | App is already running — just open http://localhost:3000 |
| `API error 503` | Ollama got stuck. Run: `pkill ollama && ollama serve &` then retry |
| Answers are slow (30–60s) | Normal — the LLM runs locally on your CPU |
| Page loads but shows nothing | Wait 10s and refresh — Next.js is still compiling |

---

## Stack
| Layer | Tool |
|---|---|
| LLM | Llama 3.2 (3B) via Ollama |
| Embeddings | nomic-embed-text via Ollama |
| Vector DB | ChromaDB (local) |
| Backend | FastAPI + Python 3.9 |
| Frontend | Next.js + Tailwind CSS |
| Knowledge base | TM Forum Open_Api_And_Data_Model + ODA Canvas (GitHub) |

---

## Project Structure
```
axiom/
├── start.sh              ← start everything (use this)
├── backend/
│   ├── main.py           ← FastAPI RAG query engine
│   ├── ingest.py         ← download + embed + index TM Forum specs
│   ├── requirements.txt
│   ├── chroma_db/        ← vector index (auto-created on first run)
│   └── data/             ← TM Forum spec files (auto-downloaded)
└── frontend/
    └── app/page.tsx      ← chat UI
```

---

## API Reference

**POST /query**
```json
{ "question": "What mandatory fields does TMF622 Product Order require?", "top_k": 5 }
```
**GET /health** — check backend + Ollama status  
**GET /stats** — number of chunks indexed  
**Swagger UI** — http://localhost:8000/docs

---

*SynaptDI · Synapt Domain Intelligence · June 2026 · Prepared by Aryan Narang*
