from __future__ import annotations
"""
SynaptDI — FastAPI Backend  v2.0
Endpoints:
  POST /query                      → RAG answer
  GET  /documents                  → list uploaded documents
  POST /documents/upload           → upload + background-ingest a file
  GET  /documents/{file}/status    → ingestion progress
  DELETE /documents/{file}         → remove from ChromaDB + disk
  GET  /branding                   → branding config
  POST /branding                   → save branding config
  GET  /users                      → user list
  POST /users                      → add user
  PUT  /users/{id}                 → update user
  DELETE /users/{id}               → remove user
  GET  /stats/queries              → per-doc query hit counts
  GET  /health  GET /stats         → health / index stats
"""

import os, json, time, hashlib, uuid, re, requests, threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb

_chroma_lock = threading.Lock()   # protects singleton + upsert/query overlap

# ── Config ─────────────────────────────────────────────────────────────────────
OLLAMA_URL  = os.getenv("OLLAMA_URL",  "http://localhost:11434")
LLM_MODEL   = os.getenv("LLM_MODEL",  "llama3.1:8b")   # PRD wants an 8B; 3.3 is 70B-only, so 3.1:8b is the real 8B
EMBED_MODEL = os.getenv("EMBED_MODEL","nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH","./chroma_db")

# ── Retrieval tuning ─────────────────────────────────────────────────────────
TOP_K            = 8      # chunks handed to the LLM
KB_DIST_MAX      = 0.85   # cosine-distance ceiling for a KB chunk to count as relevant
UPLOAD_THRESHOLD = 0.48   # uploads sit farther out in nomic space; gate them tighter
UPLOAD_SLOTS     = 2      # max uploaded chunks that may pre-empt KB chunks
CONFIDENT_DIST   = 0.35   # if the best chunk is this close, treat as high-confidence in-domain
                          # and use the no-refusal prompt even when no spec ID was named
                          # (stops the 3B over-refusing on strong but un-named matches,
                          #  e.g. "which ODA component handles trouble tickets?" → ~0.25)

NO_INFO_MSG    = ("I don't have enough information in the current knowledge base to "
                  "answer this. The relevant document may not be indexed yet.")
NO_INFO_PREFIX = "i don't have enough information in the current knowledge base"

STORAGE_DIR = Path("./storage"); STORAGE_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = Path("./uploads");  UPLOADS_DIR.mkdir(exist_ok=True)

UPLOADS_FILE  = STORAGE_DIR / "uploads.json"
BRANDING_FILE = STORAGE_DIR / "branding.json"
USERS_FILE    = STORAGE_DIR / "users.json"

# ── In-memory state ────────────────────────────────────────────────────────────
PROCESSING_STATUS: dict[str, dict] = {}   # file → {status, chunks, error?}
QUERY_HITS:        dict[str, int]  = {}   # source → hit count (resets on restart)

# ── Default seed data ──────────────────────────────────────────────────────────
DEFAULT_BRANDING = {
    "companyName":  "SynaptDI",
    "tagline":      "Enterprise domains at your fingertips",
    "primaryColor": "#dc2626",
}

DEFAULT_USERS = [
    {"id":"1","name":"Admin User",    "email":"admin@synaptdi.com",   "role":"admin",  "status":"active",  "lastActive":"Now"},
    {"id":"2","name":"Sarah Chen",    "email":"analyst@synaptdi.com", "role":"analyst","status":"active",  "lastActive":"2h ago"},
    {"id":"3","name":"Marcus Johnson","email":"marcus@synaptdi.com",  "role":"analyst","status":"active",  "lastActive":"1d ago"},
    {"id":"4","name":"Lisa Park",     "email":"lisa@synaptdi.com",    "role":"viewer", "status":"away",    "lastActive":"3d ago"},
    {"id":"5","name":"Tom Wilson",    "email":"tom@synaptdi.com",     "role":"viewer", "status":"inactive","lastActive":"2w ago"},
]

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SynaptDI API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup_init():
    # The collection is opened lazily on the first request and cached as a
    # singleton. ChromaDB's PersistentClient loads the persisted HNSW index on
    # open, so the very first query already sees the full corpus (verified).
    print("[startup] SynaptDI ready — ChromaDB opens on first request", flush=True)

# ── ChromaDB singleton ─────────────────────────────────────────────────────────
_chroma_client     = None
_chroma_collection = None

# Pre-built mapping of "TMF622" → "TMF622-ProductOrdering-v4.0.0.swagger.json"
# populated at startup so the query path never needs to scan all metadatas.

def get_collection():
    """Return the ChromaDB collection singleton (thread-safe, lazily opened)."""
    global _chroma_client, _chroma_collection
    with _chroma_lock:
        if _chroma_collection is None:
            _chroma_client     = chromadb.PersistentClient(path=CHROMA_PATH)
            _chroma_collection = _chroma_client.get_collection("axiom_v1")
        return _chroma_collection

# ── Spec-ID awareness ────────────────────────────────────────────────────────
# Engineers name a spec directly ("mandatory fields in TMF641?"). nomic-embed-text
# clusters every telco spec into one tight region, so pure vector search often
# ranks sibling specs above the one the user actually named. We detect the spec
# ID and retrieve that spec's own chunks explicitly so they're always in context.
_SPEC_RE  = re.compile(r"TMF[\s_-]?(\d{3})")
_VER_RE   = re.compile(r"\bv?\d+(?:\.\d+){1,3}\b")   # strip "4.0.0", "v4.1.0", "2.0"
_spec_map:   Optional[dict] = None   # spec_id -> set(filenames), built once from metadata
_spec_names: list           = []     # (name_lower, spec_id), longest-first — by-name lookup

def _clean_spec_name(source: str) -> str:
    s = _VER_RE.sub(" ", source or "")
    s = re.sub(r"\bapi\b", " ", s, flags=re.I)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()

def detect_spec_ids(text: str) -> list[str]:
    """Resolve specs the user named — by number (TMF641) OR by name
    ("Product Catalog Management API" → TMF620). Name matching uses the
    by-name index built in get_spec_map()."""
    t   = text.lower()
    ids = {f"TMF{n}" for n in _SPEC_RE.findall(text.upper())}
    for name, sid in _spec_names:           # specific multi-word titles only
        if name in t:
            ids.add(sid)
    return sorted(ids)

def get_spec_map(col) -> dict:
    """Map every indexed spec ID to its filename(s) AND build a by-name index
    (spec title -> ID). Built once and cached; falls back to deriving the ID
    from the filename for older indexes that predate the spec_id metadata."""
    global _spec_map, _spec_names
    if _spec_map is None:
        with _chroma_lock:
            if _spec_map is None:
                sm:    dict[str, set] = {}
                names: dict[str, str] = {}
                try:    metas = col.get(include=["metadatas"])["metadatas"]
                except Exception: metas = []
                for m in metas:
                    sid = m.get("spec_id") or ""
                    if not sid:
                        mm  = _SPEC_RE.search((m.get("file") or "").upper())
                        sid = f"TMF{mm.group(1)}" if mm else ""
                    if not sid:
                        continue
                    sm.setdefault(sid, set()).add(m.get("file", ""))
                    nm = _clean_spec_name(m.get("source", ""))
                    # keep only specific titles (>=2 words, >=12 chars) so common
                    # words ("event", "party") can't false-match a question
                    if nm and len(nm) >= 12 and " " in nm:
                        names.setdefault(nm, sid)
                _spec_map   = sm
                _spec_names = sorted(names.items(), key=lambda kv: -len(kv[0]))
    return _spec_map

# ── Text helpers ───────────────────────────────────────────────────────────────
CHUNK_SIZE, CHUNK_OVERLAP = 800, 120           # used by the original ingest.py

# Uploads use SMALLER chunks so each chunk covers one coherent topic.
# Larger chunks produce "blurry" embeddings (average of many topics) that
# don't match specific sub-topic queries well.
UPLOAD_CHUNK_SIZE, UPLOAD_CHUNK_OVERLAP = 350, 50

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    result, start = [], 0
    while start < len(text):
        result.append(text[start : start + size])
        start += size - overlap
    return [c.strip() for c in result if len(c.strip()) >= 40]

def embed(text: str) -> list[float]:
    r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                      json={"model": EMBED_MODEL, "prompt": text}, timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]

def make_chunk_id(file_name: str, idx: int) -> str:
    return "up_" + hashlib.md5(f"{file_name}_{idx}".encode()).hexdigest()[:14]

# ── File text extraction ───────────────────────────────────────────────────────
def extract_text(content: bytes, file_name: str) -> str:
    name = file_name.lower()
    if name.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    return content.decode("utf-8", errors="ignore")

# ── Uploads JSON helpers ───────────────────────────────────────────────────────
def load_uploads() -> list[dict]:
    if UPLOADS_FILE.exists():
        try:    return json.loads(UPLOADS_FILE.read_text())
        except: pass
    return []

def save_uploads(docs: list[dict]):
    UPLOADS_FILE.write_text(json.dumps(docs, indent=2))

def upsert_upload(entry: dict):
    docs = [d for d in load_uploads() if d.get("file") != entry["file"]]
    docs.insert(0, entry)
    save_uploads(docs)

def remove_upload_record(file_name: str):
    save_uploads([d for d in load_uploads() if d.get("file") != file_name])

# ── Background ingestion ───────────────────────────────────────────────────────
def ingest_file_bg(content: bytes, file_name: str, source_name: str, size_mb: float):
    PROCESSING_STATUS[file_name] = {"status": "processing", "chunks": 0}
    try:
        text        = extract_text(content, file_name)
        # Use smaller chunks for uploads (focused embeddings → better recall)
        text_chunks = chunk_text(text, size=UPLOAD_CHUNK_SIZE, overlap=UPLOAD_CHUNK_OVERLAP)
        if not text_chunks:
            raise ValueError("No extractable text found in this file.")

        # Grab the singleton ONCE at the start of ingestion.
        # All batch upserts go into the same object, so the query endpoint
        # (which also holds a reference to the same singleton) sees the
        # new chunks immediately after each upsert — no cache flush needed.
        col    = get_collection()
        stored = 0
        batch_ids, batch_docs, batch_metas, batch_embs = [], [], [], []

        for i, chunk in enumerate(text_chunks):
            try:
                e = embed(chunk)   # Ollama network call — outside the lock
            except Exception:
                continue           # skip un-embeddable chunks silently

            batch_ids.append(make_chunk_id(file_name, i))
            batch_docs.append(chunk)
            batch_metas.append({"source": source_name, "file": file_name,
                                 "chunk": i, "source_url": ""})
            batch_embs.append(e)

            if len(batch_ids) >= 50:
                col.upsert(ids=batch_ids, documents=batch_docs,
                            metadatas=batch_metas, embeddings=batch_embs)
                stored += len(batch_ids)
                batch_ids.clear(); batch_docs.clear()
                batch_metas.clear(); batch_embs.clear()

        if batch_ids:
            col.upsert(ids=batch_ids, documents=batch_docs,
                        metadatas=batch_metas, embeddings=batch_embs)
            stored += len(batch_ids)

        # Do NOT reset the collection singleton — the same in-memory object
        # that just received the upserts IS what future queries will use.
        # Resetting would create a new client from SQLite which may not
        # have the writes flushed yet, making the new doc invisible to queries.

        if stored == 0:
            raise ValueError("Embedding failed for all chunks — is Ollama running?")

        PROCESSING_STATUS[file_name] = {"status": "indexed", "chunks": stored}
        upsert_upload({"file": file_name, "name": source_name,
                       "size": f"{size_mb} MB", "status": "indexed",
                       "chunks": stored, "uploaded": time.strftime("%b %d, %Y")})

    except Exception as exc:
        err = str(exc)
        PROCESSING_STATUS[file_name] = {"status": "failed", "chunks": 0, "error": err}
        upsert_upload({"file": file_name, "name": source_name,
                       "size": f"{size_mb} MB", "status": "failed",
                       "chunks": 0, "uploaded": time.strftime("%b %d, %Y"),
                       "error": err})

# ── RAG ────────────────────────────────────────────────────────────────────────
# Two prompts, chosen by retrieval confidence.
#
# When the user names a spec we actually have indexed, the answer IS in the
# context — so we DON'T offer a refusal option. Small models (llama3.2 3B)
# over-refuse: a refusal sentence makes them bail even on clearly-relevant
# context (verified directly). For these high-confidence queries we force a
# grounded answer instead.
#
# For open-ended / non-spec queries we keep an out-of-domain escape hatch,
# because nomic-embed-text distances can't reliably separate in-domain from
# out-of-domain (an off-topic question can still land at a low distance).
_BASE_PROMPT = """You are SynaptDI (Synapt Domain Intelligence), a precise assistant for TM Forum telecom standards — Open APIs TMF620–TMF915, ODA (Open Digital Architecture), eTOM, and SID.

Answer the QUESTION using only the CONTEXT below. Each source is labelled with its TM Forum spec number and title. Be specific, and name the spec you actually used (its number and title) when you state a fact. Use bullet points for lists of fields, events, or steps. The context may include several related specs — synthesize across the chunks and focus on exactly what the question asks.

When asked for the mandatory/required fields of an entity, read them from that entity's MAIN resource schema or its _Create schema (e.g. the ProductOrder or ProductOrder_Create schema) — NOT from a reference (*Ref) or *_Update schema. Give a direct, confident answer; do not say information is missing if a relevant source is present.

Start immediately with the substance of the answer. Do NOT open with filler like "Based on the provided context", "According to the sources", or "To answer the question" — just answer, citing spec numbers inline where relevant."""

ANSWER_PROMPT  = _BASE_PROMPT
GUARDED_PROMPT = _BASE_PROMPT + """

If the CONTEXT does not address the question at all, reply with exactly:
"I don't have enough information in the current knowledge base to answer this. The relevant document may not be indexed yet." """

def _source_label(meta: dict) -> str:
    """Prefix the spec number so the model connects e.g. 'TMF622' (in the
    question) with 'Product Ordering' (the spec's title) — without it the model
    says the named spec 'is not in the context' and refuses."""
    sid, src = meta.get("spec_id"), meta.get("source", "Unknown")
    return f"{sid} — {src}" if sid else src

def build_prompt(question: str, chunks: list[dict], guarded: bool) -> str:
    sysp = GUARDED_PROMPT if guarded else ANSWER_PROMPT
    ctx  = "\n\n".join(
        f"[Source {i+1}: {_source_label(c['metadata'])}]\n{c['document']}"
        for i, c in enumerate(chunks)
    )
    return f"{sysp}\n\nCONTEXT:\n{ctx}\n\nQUESTION: {question}\n\nANSWER:"

def generate_answer(prompt: str) -> str:
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": LLM_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.0, "num_predict": 700,
                                        "stop": ["QUESTION:", "CONTEXT:"]}},
                      timeout=300)
    r.raise_for_status()
    return r.json()["response"].strip()

# ── Schemas ────────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    top_k:    int           = TOP_K
    standards_filter: Optional[list] = None

class Source(BaseModel):
    name: str; file: str; chunk: int; preview: str; url: str = ""

class QueryResponse(BaseModel):
    answer: str; sources: list; latency_ms: int; chunks_retrieved: int

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Health / Stats ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        col    = get_collection()
        r      = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        return {"status":"ok","chunks_indexed":col.count(),"ollama_models":models,
                "llm_model":LLM_MODEL,"embed_model":EMBED_MODEL}
    except Exception as e:
        raise HTTPException(503, str(e))

@app.get("/stats")
def stats():
    col = get_collection()
    return {"chunks_indexed": col.count(), "collection": "axiom_v1"}

# ── Query ──────────────────────────────────────────────────────────────────────
@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    start = time.time()
    top_k = max(1, min(req.top_k, 20))

    try:    q_emb = embed(req.question)
    except Exception as e: raise HTTPException(503, f"Embedding failed: {e}")

    col = get_collection()
    try:    total = col.count()
    except Exception as e: raise HTTPException(503, f"Retrieval failed: {e}")
    if total == 0:
        return QueryResponse(answer=NO_INFO_MSG, sources=[],
                             latency_ms=int((time.time()-start)*1000), chunks_retrieved=0)

    seen:    set[tuple] = set()
    chunks:  list[dict] = []
    matched: list[str]  = []   # spec IDs the user named that we actually have indexed

    def take(res, limit: int, dist_max: float):
        """Append de-duplicated, in-range chunks from a chroma result (distance order)."""
        if not res.get("documents") or not res["documents"][0]:
            return
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            if limit <= 0:
                break
            if dist >= dist_max:
                continue
            key = (m.get("file", ""), m.get("chunk", 0))
            if key in seen:
                continue
            seen.add(key)
            chunks.append({"document": d, "metadata": m, "distance": dist})
            limit -= 1

    try:
        # ── 1. Spec-targeted retrieval — guarantee named specs are in context ──
        # If the user names TMF641 (or compares TMF620 vs TMF633), retrieve each
        # named spec's own chunks directly and in balance. This keeps them from
        # being outranked — or diluted by "hub" chunks that sit near the centre
        # of nomic's space and rank close to nearly every query.
        spec_map = get_spec_map(col)            # builds the by-name index first
        spec_ids = detect_spec_ids(req.question)  # number- and name-aware
        matched  = [s for s in spec_ids if spec_map.get(s)]
        if matched:
            per_spec = max(top_k // len(matched), 2)   # balanced share per named spec
            for sid in matched:
                sfiles = sorted(spec_map[sid])
                res = col.query(query_embeddings=[q_emb], n_results=min(per_spec * 3, total),
                                where={"file": {"$in": sfiles}},
                                include=["documents", "metadatas", "distances"])
                take(res, per_spec, KB_DIST_MAX)

        # ── 2. Uploaded-document slots (relevance-gated) ──────────────────────
        # Uploads cluster slightly farther out in nomic space, so reserve a few
        # slots for them when genuinely relevant — otherwise the KB crowds them out.
        upload_files = [d["file"] for d in load_uploads() if d.get("status") == "indexed"]
        if upload_files and len(chunks) < top_k:
            res = col.query(query_embeddings=[q_emb], n_results=min(top_k, total),
                            where={"file": {"$in": upload_files}},
                            include=["documents", "metadatas", "distances"])
            take(res, min(UPLOAD_SLOTS, top_k - len(chunks)), UPLOAD_THRESHOLD)

        # ── 3. General semantic fill over the whole corpus ────────────────────
        if len(chunks) < top_k:
            res = col.query(query_embeddings=[q_emb], n_results=min(top_k * 3, total),
                            include=["documents", "metadatas", "distances"])
            take(res, top_k - len(chunks), KB_DIST_MAX)
    except Exception as e:
        raise HTTPException(503, f"Retrieval failed: {e}")

    if not chunks:
        return QueryResponse(answer=NO_INFO_MSG, sources=[],
                             latency_ms=int((time.time()-start)*1000), chunks_retrieved=0)

    # Most-relevant first for the LLM
    chunks.sort(key=lambda c: c["distance"])

    # Use the no-refusal prompt when the user named a spec we have, OR retrieval
    # is high-confidence (top chunk clearly on-topic). Only fall back to the
    # guarded/refusable prompt for weak retrieval that might be out-of-domain.
    confident = bool(matched) or chunks[0]["distance"] < CONFIDENT_DIST
    try:    answer = generate_answer(build_prompt(req.question, chunks, guarded=not confident))
    except Exception as e: raise HTTPException(503, f"Generation failed: {e}")

    # If the LLM used its exact "no info" escape hatch, return no sources so the
    # UI doesn't imply the answer was supported by documents.
    if answer.lower().strip().startswith(NO_INFO_PREFIX):
        return QueryResponse(answer=answer, sources=[],
                             latency_ms=int((time.time()-start)*1000), chunks_retrieved=0)

    # ── Build de-duplicated source list ──────────────────────────────────────
    src_seen, sources = set(), []
    for c in chunks:
        src = c["metadata"].get("source", "Unknown")
        if src in src_seen:
            continue
        src_seen.add(src)
        QUERY_HITS[src] = QUERY_HITS.get(src, 0) + 1
        sources.append(Source(
            name=src, file=c["metadata"].get("file", ""),
            chunk=c["metadata"].get("chunk", 0),
            preview=c["document"][:400] + ("..." if len(c["document"]) > 400 else ""),
            url=c["metadata"].get("source_url", ""),
        ))

    return QueryResponse(answer=answer, sources=sources,
                         latency_ms=int((time.time()-start)*1000),
                         chunks_retrieved=len(chunks))

# ── Documents ──────────────────────────────────────────────────────────────────
@app.get("/documents/library")
def documents_library():
    """
    Return the pre-indexed knowledge base documents grouped by source folder.
    These are the docs ingested from the data/ directory — read-only.
    """
    data_dir = Path("./data")
    upload_files = {d["file"] for d in load_uploads()}

    # Build filename → top-level folder mapping by scanning data/
    file_to_folder: dict[str, str] = {}
    if data_dir.exists():
        for folder in data_dir.iterdir():
            if folder.is_dir() and not folder.name.startswith("."):
                for f in folder.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        file_to_folder[f.name] = folder.name

    # Get chunk counts per file from ChromaDB (metadata segment, always accurate)
    col   = get_collection()
    items = col.get(include=["metadatas"])

    file_stats: dict[str, dict] = {}
    for meta in items["metadatas"]:
        fname = meta.get("file", "")
        if not fname or fname in upload_files:
            continue                            # skip user uploads
        if fname not in file_stats:
            folder = file_to_folder.get(fname, "other")
            # Human-readable name: strip extension + normalise
            display = fname
            for ext in (".swagger.json", ".oas.yaml", ".oas.json", ".yaml",
                        ".yml", ".json", ".md", ".txt"):
                if display.endswith(ext):
                    display = display[: -len(ext)]
                    break
            display = display.replace("-", " ").replace("_", " ")
            file_stats[fname] = {"file": fname, "name": display,
                                 "folder": folder, "chunks": 0, "status": "indexed"}
        file_stats[fname]["chunks"] += 1

    # Group by folder
    groups: dict[str, dict] = {}
    for stat in file_stats.values():
        g = stat["folder"]
        if g not in groups:
            # Friendly folder display name
            friendly = g.replace("_", " ").replace("-", " ").title()
            groups[g] = {"id": g, "name": friendly, "files": 0,
                         "chunks": 0, "documents": []}
        groups[g]["files"]  += 1
        groups[g]["chunks"] += stat["chunks"]
        groups[g]["documents"].append(stat)

    # Sort groups by chunk count; within each group sort docs by chunks desc
    sorted_groups = sorted(groups.values(), key=lambda x: -x["chunks"])
    for grp in sorted_groups:
        grp["documents"] = sorted(grp["documents"],
                                  key=lambda x: -x["chunks"])[:30]  # top 30 per group

    return {
        "total_files":  len(file_stats),
        "total_chunks": sum(s["chunks"] for s in file_stats.values()),
        "groups": sorted_groups,
    }

@app.get("/documents")
def list_documents():
    docs = load_uploads()
    # Overlay live in-memory status (more up-to-date than persisted JSON)
    for d in docs:
        fn = d.get("file","")
        if fn in PROCESSING_STATUS:
            live = PROCESSING_STATUS[fn]
            d["status"] = live["status"]
            d["chunks"] = live.get("chunks", d.get("chunks", 0))
    return {"documents": docs}

@app.post("/documents/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    content     = await file.read()
    file_name   = file.filename or "unnamed_file"
    source_name = file_name.rsplit(".", 1)[0].replace("_"," ").replace("-"," ")
    size_mb     = round(len(content) / 1_048_576, 1)

    # Persist raw bytes
    (UPLOADS_DIR / file_name).write_bytes(content)

    # Optimistically register as processing
    entry = {"file": file_name, "name": source_name,
             "size": f"{size_mb} MB", "status": "processing",
             "chunks": 0, "uploaded": time.strftime("%b %d, %Y")}
    upsert_upload(entry)
    PROCESSING_STATUS[file_name] = {"status": "processing", "chunks": 0}

    background_tasks.add_task(ingest_file_bg, content, file_name, source_name, size_mb)
    return {"file": file_name, "status": "processing"}

@app.get("/documents/{file_name}/status")
def document_status(file_name: str):
    if file_name in PROCESSING_STATUS:
        return PROCESSING_STATUS[file_name]
    for d in load_uploads():
        if d.get("file") == file_name:
            return {"status": d.get("status","unknown"), "chunks": d.get("chunks",0)}
    raise HTTPException(404, "Document not found")

@app.delete("/documents/{file_name}")
def delete_document(file_name: str):
    col       = get_collection()
    all_items = col.get(include=["metadatas"])
    to_delete = [
        iid for iid, meta in zip(all_items["ids"], all_items["metadatas"])
        if meta.get("file") == file_name
    ]
    if to_delete:
        col.delete(ids=to_delete)
        # Keep the singleton — it already reflects the deletion in memory.

    remove_upload_record(file_name)
    PROCESSING_STATUS.pop(file_name, None)
    raw = UPLOADS_DIR / file_name
    if raw.exists(): raw.unlink()

    return {"deleted_chunks": len(to_delete), "file": file_name}

# ── Branding ───────────────────────────────────────────────────────────────────
@app.get("/branding")
def get_branding():
    if BRANDING_FILE.exists():
        try: return json.loads(BRANDING_FILE.read_text())
        except: pass
    return DEFAULT_BRANDING

@app.post("/branding")
def save_branding_endpoint(body: dict):
    cleaned = {k: v for k, v in body.items()
               if k in {"companyName","tagline","primaryColor"} and isinstance(v, str)}
    merged  = {**DEFAULT_BRANDING, **cleaned}
    BRANDING_FILE.write_text(json.dumps(merged, indent=2))
    return merged

# ── Users ──────────────────────────────────────────────────────────────────────
def _load_users() -> list[dict]:
    if USERS_FILE.exists():
        try: return json.loads(USERS_FILE.read_text())
        except: pass
    _save_users(DEFAULT_USERS[:])
    return DEFAULT_USERS[:]

def _save_users(users: list[dict]):
    USERS_FILE.write_text(json.dumps(users, indent=2))

@app.get("/users")
def get_users():
    return {"users": _load_users()}

@app.post("/users")
def add_user(body: dict):
    users   = _load_users()
    new_u   = {"id": str(uuid.uuid4()), "name": body.get("name",""),
               "email": body.get("email",""), "role": body.get("role","viewer"),
               "status": "inactive", "lastActive": "Never"}
    users.append(new_u)
    _save_users(users)
    return new_u

@app.put("/users/{user_id}")
def update_user(user_id: str, body: dict):
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            for k in ("name","role","status"):
                if k in body: u[k] = body[k]
            _save_users(users)
            return u
    raise HTTPException(404, "User not found")

@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    users     = _load_users()
    remaining = [u for u in users if u["id"] != user_id]
    if len(remaining) == len(users):
        raise HTTPException(404, "User not found")
    _save_users(remaining)
    return {"ok": True}

# ── Query analytics ────────────────────────────────────────────────────────────
@app.get("/stats/queries")
def query_stats():
    return {"hits": QUERY_HITS}
