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

import os, json, time, hashlib, uuid, re, requests, threading, base64, hmac, secrets, shutil, subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Header, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb
import ingest   # reuse the ingestion parsers: parse_openapi_spec, parse_markdown, chunk_text, embed_batch, …
import conformance   # TMF630 conformance rule engine

_chroma_lock = threading.Lock()   # protects singleton + upsert/query overlap

# ── Config ─────────────────────────────────────────────────────────────────────
OLLAMA_URL  = os.getenv("OLLAMA_URL",  "http://localhost:11434")
LLM_MODEL   = os.getenv("LLM_MODEL",  "llama3.1:8b")   # PRD wants an 8B; 3.3 is 70B-only, so 3.1:8b is the real 8B
EMBED_MODEL = os.getenv("EMBED_MODEL","nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH","./chroma_db")

# ── Retrieval tuning ─────────────────────────────────────────────────────────
TOP_K            = 8      # chunks handed to the LLM
KB_DIST_MAX      = 0.85   # cosine-distance ceiling for a KB chunk to count as relevant
CONFIDENT_DIST   = 0.35   # if the best chunk is this close, treat as high-confidence in-domain
                          # and use the no-refusal prompt even when no spec ID was named
                          # (stops the model over-refusing on strong but un-named matches)
# Uploaded docs are intentional context — treat them as first-class, not a gated afterthought.
UPLOAD_MAX_DIST  = 0.70   # include an uploaded chunk if it's at least loosely on-topic
UPLOAD_BOOST     = 0.06   # let a relevant upload edge out an equidistant KB chunk in ranking
UPLOAD_CONFIDENT = 0.55   # an uploaded chunk this close → answer confidently from the user's doc
DOC_SCOPE_MAX    = 0.90   # in "My Documents" scope, accept almost anything from the docs

NO_INFO_MSG    = ("I don't have enough information in the current knowledge base to "
                  "answer this. The relevant document may not be indexed yet.")
NO_INFO_PREFIX = "i don't have enough information in the current knowledge base"

STORAGE_DIR = Path("./storage"); STORAGE_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = Path("./uploads");  UPLOADS_DIR.mkdir(exist_ok=True)

UPLOADS_FILE  = STORAGE_DIR / "uploads.json"
BRANDING_FILE = STORAGE_DIR / "branding.json"
USERS_FILE    = STORAGE_DIR / "users.json"
CHATCFG_FILE  = STORAGE_DIR / "chat_config.json"
CONVOS_DIR    = STORAGE_DIR / "conversations"; CONVOS_DIR.mkdir(exist_ok=True)
ANALYTICS_FILE = STORAGE_DIR / "analytics.json"
FEEDBACK_FILE  = STORAGE_DIR / "feedback.json"
_analytics_lock = threading.Lock()

def _log_query(question: str, answered: bool):
    """Track query volume + 'knowledge gaps' (questions we couldn't answer)."""
    try:
        with _analytics_lock:
            a = json.loads(ANALYTICS_FILE.read_text()) if ANALYTICS_FILE.exists() else {}
            a["total"] = a.get("total", 0) + 1
            if answered:
                a["answered"] = a.get("answered", 0) + 1
            else:
                gaps = a.get("gaps", [])
                gaps.insert(0, {"q": question[:200], "ts": int(time.time())})
                a["gaps"] = gaps[:50]
            ANALYTICS_FILE.write_text(json.dumps(a))
    except Exception:
        pass

# ── In-memory state ────────────────────────────────────────────────────────────
PROCESSING_STATUS: dict[str, dict] = {}   # file → {status, chunks, error?}
QUERY_HITS:        dict[str, int]  = {}   # source → hit count (resets on restart)

# ── Default seed data ──────────────────────────────────────────────────────────
DEFAULT_BRANDING = {
    "companyName":  "SynaptDI",
    "tagline":      "Enterprise domains at your fingertips",
    "primaryColor": "#dc2626",
}

# Admin-configurable chat surface (persona feeds the system prompt; placeholder +
# suggestions drive the chat UI). Lets the same app be retargeted to any domain.
DEFAULT_CHAT_CONFIG = {
    "placeholder": "Ask about TM Forum APIs, ODA, eTOM, SID...",
    "persona":     "TM Forum telecom standards — Open APIs TMF620–TMF915, ODA (Open Digital Architecture), eTOM, and SID",
    "suggestions": [
        "What mandatory fields does TMF622 Product Order require?",
        "What is the difference between TMF620 and TMF633?",
        "How do I handle pagination in TM Forum Open APIs?",
        "Which ODA component handles trouble tickets?",
        "Explain the eTOM Level 1 processes",
        "What is the SID ABE for customer data?",
    ],
}

def load_chat_config() -> dict:
    if CHATCFG_FILE.exists():
        try:    return {**DEFAULT_CHAT_CONFIG, **json.loads(CHATCFG_FILE.read_text())}
        except: pass
    return dict(DEFAULT_CHAT_CONFIG)

DEFAULT_USERS = [
    {"id":"1","name":"Admin User",    "email":"admin@synaptdi.com",   "role":"admin",  "status":"active",  "lastActive":"Now",    "title":"System Administrator",      "department":"IT Operations"},
    {"id":"2","name":"Sarah Chen",    "email":"analyst@synaptdi.com", "role":"analyst","status":"active",  "lastActive":"2h ago", "title":"Telecom Standards Analyst", "department":"Architecture"},
    {"id":"3","name":"Marcus Johnson","email":"marcus@synaptdi.com",  "role":"analyst","status":"active",  "lastActive":"1d ago", "title":"Network Standards Engineer","department":"Architecture"},
    {"id":"4","name":"Lisa Park",     "email":"lisa@synaptdi.com",    "role":"viewer", "status":"away",    "lastActive":"3d ago", "title":"Product Manager",           "department":"Product"},
    {"id":"5","name":"Tom Wilson",    "email":"tom@synaptdi.com",     "role":"viewer", "status":"inactive","lastActive":"2w ago", "title":"Business Analyst",          "department":"Strategy"},
]

# Seed passwords for the default accounts — hashed on first load. Change in production.
SEED_PASSWORDS = {
    "admin@synaptdi.com":   "admin123",
    "analyst@synaptdi.com": "analyst123",
    "marcus@synaptdi.com":  "analyst123",
    "lisa@synaptdi.com":    "viewer123",
    "tom@synaptdi.com":     "viewer123",
}

# ── Auth: hashed passwords + HMAC-signed session tokens (no external deps) ────
AUTH_SECRET_FILE = STORAGE_DIR / "auth_secret"
def _auth_secret() -> bytes:
    if AUTH_SECRET_FILE.exists():
        return AUTH_SECRET_FILE.read_bytes()
    s = secrets.token_bytes(32)
    AUTH_SECRET_FILE.write_bytes(s)
    return s
AUTH_SECRET = _auth_secret()

def hash_password(password: str, salt: str = "") -> tuple:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return h, salt

def verify_password(password: str, h: str, salt: str) -> bool:
    if not h or not salt:
        return False
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, h)

def make_token(user: dict, days: int = 7) -> str:
    payload = {"uid": user["id"], "email": user.get("email"), "role": user.get("role"),
               "exp": int(time.time()) + days * 86400}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig  = hmac.new(AUTH_SECRET, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def verify_token(token: str):
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(AUTH_SECRET, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def _public_user(u: dict) -> dict:
    """User fields safe to return to clients (never the password hash/salt)."""
    return {k: u.get(k) for k in
            ("id", "name", "email", "role", "title", "department", "status", "lastActive")}

class LoginReq(BaseModel):
    email: str
    password: str

def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not authenticated")
    payload = verify_token(authorization.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(401, "Invalid or expired session")
    u = next((x for x in _load_users() if x.get("id") == payload.get("uid")), None)
    if not u:
        raise HTTPException(401, "User no longer exists")
    return u

def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user

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
    from io import BytesIO
    if name.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(BytesIO(content))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for tbl in d.tables:
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f"# Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    if name.endswith(".pptx"):
        import pptx
        prs = pptx.Presentation(BytesIO(content))
        parts = []
        for i, slide in enumerate(prs.slides, 1):
            parts.append(f"# Slide {i}")
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    parts.append(shape.text_frame.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            parts.append(" | ".join(cells))
        return "\n".join(parts)
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
                                 "chunk": i, "source_url": "",
                                 "origin": file_name, "origin_type": "file"})
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
        upsert_upload({"file": file_name, "name": source_name, "type": "file", "origin": file_name,
                       "size": f"{size_mb} MB", "status": "indexed",
                       "chunks": stored, "uploaded": time.strftime("%b %d, %Y")})

    except Exception as exc:
        err = str(exc)
        PROCESSING_STATUS[file_name] = {"status": "failed", "chunks": 0, "error": err}
        upsert_upload({"file": file_name, "name": source_name, "type": "file", "origin": file_name,
                       "size": f"{size_mb} MB", "status": "failed",
                       "chunks": 0, "uploaded": time.strftime("%b %d, %Y"),
                       "error": err})

# ── Knowledge from a Git repo or a web link (reuses ingest.py parsers) ───────
def _store_chunks(items: list, origin: str, origin_type: str) -> int:
    """Embed items [{source,file,chunk,document,source_url,spec_id?}] in batches and
    add them to the collection tagged with a shared `origin` so the whole source
    can be listed/deleted as a unit. Returns the number of chunks stored."""
    col, stored = get_collection(), 0
    for i in range(0, len(items), 64):
        batch = items[i:i + 64]
        embs  = ingest.embed_batch([it["document"] for it in batch])
        ids, docs, metas, es = [], [], [], []
        for it, e in zip(batch, embs):
            if e is None:
                continue
            ids.append("src_" + hashlib.md5(f"{origin}|{it['file']}|{it['chunk']}".encode()).hexdigest()[:16])
            docs.append(it["document"])
            metas.append({"source": it["source"], "file": it["file"], "chunk": it["chunk"],
                          "spec_id": it.get("spec_id", ""), "source_url": it.get("source_url", ""),
                          "origin": origin, "origin_type": origin_type})
            es.append(e)
        if ids:
            col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=es)
            stored += len(ids)
            PROCESSING_STATUS[origin] = {"status": "processing", "chunks": stored}
    return stored

def _html_to_text(html: str) -> str:
    import html as _h
    html = re.sub(r"(?is)<(script|style|noscript|head|nav|footer).*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article)>", "\n", html)
    text = _h.unescape(re.sub(r"(?s)<[^>]+>", " ", html))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()

def _fail(origin, label, typ, url, err):
    PROCESSING_STATUS[origin] = {"status": "failed", "chunks": 0, "error": err[:300]}
    upsert_upload({"file": origin, "name": label, "type": typ, "url": url, "origin": origin,
                   "size": typ, "status": "failed", "chunks": 0,
                   "uploaded": time.strftime("%b %d, %Y"), "error": err[:300]})

def _done(origin, label, typ, url, stored):
    PROCESSING_STATUS[origin] = {"status": "indexed", "chunks": stored}
    upsert_upload({"file": origin, "name": label, "type": typ, "url": url, "origin": origin,
                   "size": typ, "status": "indexed", "chunks": stored,
                   "uploaded": time.strftime("%b %d, %Y")})

def ingest_web_bg(url: str, origin: str, label: str):
    PROCESSING_STATUS[origin] = {"status": "processing", "chunks": 0}
    try:
        r = requests.get(url, timeout=40, headers={"User-Agent": "SynaptDI/1.0"})
        r.raise_for_status()
        if "pdf" in r.headers.get("content-type", "").lower() or url.lower().endswith(".pdf"):
            import fitz
            text = "\n".join(p.get_text() for p in fitz.open(stream=r.content, filetype="pdf"))
        else:
            text = _html_to_text(r.text)
        items = [{"source": label, "file": origin, "chunk": i, "document": p, "source_url": url}
                 for i, p in enumerate(chunk_text(text, size=900, overlap=150)) if len(p) >= 60]
        stored = _store_chunks(items, origin, "web")
        if stored == 0:
            raise ValueError("No readable text found at that URL.")
        _done(origin, label, "web", url, stored)
    except Exception as exc:
        _fail(origin, label, "web", url, str(exc))

def ingest_repo_bg(clone_url: str, origin: str, label: str):
    PROCESSING_STATUS[origin] = {"status": "processing", "chunks": 0}
    dest = UPLOADS_DIR / "_repos" / re.sub(r"[^A-Za-z0-9_.-]", "_", origin)
    try:
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth=1", clone_url, str(dest)],
                       check=True, capture_output=True, timeout=600)
        base   = re.sub(r"\.git$", "", clone_url.rstrip("/"))
        branch = "main"
        try:
            hb = subprocess.run(["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, timeout=15)
            branch = hb.stdout.decode().strip() or "main"
        except Exception:
            pass
        blob = f"{base}/blob/{branch}" if base.startswith("http") else ""
        spec_files = []
        for ext in ("*.json", "*.yaml", "*.yml"):
            spec_files.extend(dest.rglob(ext))
        md_files = [f for f in dest.rglob("*.md") if not ingest.is_junk_markdown(f.name)]
        seen_hash, items = set(), []
        for f in spec_files + md_files:
            if any(p in f.parts for p in (".git", "node_modules", "__pycache__")):
                continue
            if "test" in f.name.lower() and f.suffix != ".md":
                continue
            parsed = ingest.parse_openapi_spec(f) if f.suffix != ".md" else ingest.parse_markdown(f)
            if not parsed or not parsed["text"].strip():
                continue
            h = hashlib.md5(parsed["text"].encode("utf-8", "ignore")).hexdigest()
            if h in seen_hash:
                continue
            seen_hash.add(h)
            src, sid = f"{parsed['title']} {parsed['version']}".strip(), ingest.extract_spec_id(f.name)
            surl = f"{blob}/{'/'.join(f.relative_to(dest).parts)}" if blob else ""
            for ci, ch in enumerate(ingest.chunk_text(parsed["text"])):
                if len(ch) >= 60:
                    items.append({"source": src, "file": f.name, "chunk": ci,
                                  "document": ch, "source_url": surl, "spec_id": sid})
        stored = _store_chunks(items, origin, "repo")
        if stored == 0:
            raise ValueError("No OpenAPI specs or docs found in that repository.")
        _done(origin, label, "repo", clone_url, stored)
    except subprocess.CalledProcessError as exc:
        _fail(origin, label, "repo", clone_url, exc.stderr.decode()[:200] if exc.stderr else "git clone failed")
    except Exception as exc:
        _fail(origin, label, "repo", clone_url, str(exc))
    finally:
        shutil.rmtree(dest, ignore_errors=True)   # discard the clone; embeddings are already stored

class RepoReq(BaseModel):
    url: str
    label: Optional[str] = None

class WebReq(BaseModel):
    url: str
    label: Optional[str] = None

@app.post("/sources/repo")
def add_repo_source(req: RepoReq, background_tasks: BackgroundTasks, _admin: dict = Depends(require_admin)):
    url = (req.url or "").strip()
    if not (url.lower().startswith(("http://", "https://")) or url.startswith("git@")):
        raise HTTPException(400, "Provide an https git URL, e.g. https://github.com/org/repo.")
    name   = re.sub(r"\.git$", "", url.rstrip("/")).split("/")[-1] or "repo"
    origin = "repo:" + name
    label  = (req.label or name).strip()
    upsert_upload({"file": origin, "name": label, "type": "repo", "url": url, "origin": origin,
                   "size": "repo", "status": "processing", "chunks": 0,
                   "uploaded": time.strftime("%b %d, %Y")})
    PROCESSING_STATUS[origin] = {"status": "processing", "chunks": 0}
    background_tasks.add_task(ingest_repo_bg, url, origin, label)
    return {"origin": origin, "status": "processing"}

@app.post("/sources/weblink")
def add_web_source(req: WebReq, background_tasks: BackgroundTasks, _admin: dict = Depends(require_admin)):
    url = (req.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Provide a valid http(s) URL.")
    label  = (req.label or url.split("//", 1)[-1][:60]).strip()
    origin = "web:" + hashlib.md5(url.encode()).hexdigest()[:12]
    upsert_upload({"file": origin, "name": label, "type": "web", "url": url, "origin": origin,
                   "size": "web", "status": "processing", "chunks": 0,
                   "uploaded": time.strftime("%b %d, %Y")})
    PROCESSING_STATUS[origin] = {"status": "processing", "chunks": 0}
    background_tasks.add_task(ingest_web_bg, url, origin, label)
    return {"origin": origin, "status": "processing"}

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
_PROMPT_INSTRUCTIONS = """You answer the QUESTION using the CONTEXT below. Each source is labelled with its number and title, e.g. "[Source 2: TMF620 — Product Catalog]".

Write like a sharp, friendly expert explaining something to a teammate — clear, warm, and genuinely insightful, never robotic or one-word terse. Open with the direct answer in the very first sentence (no preamble, no label, no "Answer:"/"Summary:" heading). Then teach: explain what the key fields or concepts are for, how the pieces fit together, and any gotcha worth knowing — the context an expert would add so the reader actually understands, not just a bare list. A good answer usually has a one-line direct opener, a short plain-English explanation, and a structured detail block. Make every sentence count (no filler, no restating the question, no "In summary"/"I hope this helps" endings), but never be so brief that the answer carries no insight. Let the depth match the question.

Shape the answer to the question:
- Fields, attributes, query parameters, events, or status codes → a Markdown table such as `| Field | Required | Description |`, marking each mandatory or optional, and give every row a real plain-English description of what it is for (not just its name).
- Comparing two or more things (e.g. specs) → a Markdown table with one column each, then a one-line bottom line on which to use when.
- "How do I…" or how to call an operation → numbered steps plus a fenced code block with a concrete, runnable example (curl by default, or the language asked for) built from the real path and fields in the context.
- Anything else → short, scannable bullets or brief paragraphs.

Every specific field name, path, status code, and value must come from the CONTEXT — never invent them — but do explain and connect them in your own words so the answer teaches rather than just lists. Cite inline with the bracketed source number: put [n] right after the fact it backs (combine like [2][3]); cite only sources you used. Synthesize across related chunks. Be confident and decisive: if a relevant source is present, answer it directly and do not claim information is missing. Never open with filler like "Based on the provided context" or "According to the sources".

When asked what fields a resource requires, this almost always means what you must SUBMIT to create one: read the required list from the resource's _Create schema (e.g. ProductOrder_Create → productOrderItem), not the response resource's server-assigned id, not a *Ref or *_Update schema, and not an unrelated EventSubscription/Hub/Event/Error schema. Name the parent object a required field sits on (e.g. each productOrderItem needs an action and a productOffering) when the context shows it, and never answer with a single bare field name when you can explain what it is and where it lives. If two spec versions appear (e.g. 4.0.0 and 5.0.0), answer for the latest and note any notable difference."""

_GUARD_LINE = """

If the CONTEXT does not address the question at all, reply with exactly:
"I don't have enough information in the current knowledge base to answer this. The relevant document may not be indexed yet." """

def _system_prompt(guarded: bool) -> str:
    """Build the system prompt, injecting the admin-configured domain persona."""
    persona = (load_chat_config().get("persona") or DEFAULT_CHAT_CONFIG["persona"]).strip()
    head = (f"You are SynaptDI (Synapt Domain Intelligence), an expert and friendly assistant for {persona}. "
            "You explain things clearly and helpfully, like a knowledgeable colleague who wants the reader to truly get it.")
    return f"{head}\n\n{_PROMPT_INSTRUCTIONS}" + (_GUARD_LINE if guarded else "")

def _source_label(meta: dict) -> str:
    """Prefix the spec number so the model connects e.g. 'TMF622' (in the
    question) with 'Product Ordering' (the spec's title) — without it the model
    says the named spec 'is not in the context' and refuses."""
    sid, src = meta.get("spec_id"), meta.get("source", "Unknown")
    return f"{sid} — {src}" if sid else src

def _format_history(history) -> str:
    if not history:
        return ""
    turns = []
    for m in history[-6:]:
        c = (m.get("content") or "").strip()
        if not c:
            continue
        who = "User" if m.get("role") == "user" else "Assistant"
        turns.append(f"{who}: {c[:600]}")
    if not turns:
        return ""
    return ('RECENT CONVERSATION (use only to resolve references like "it"/"that"; '
            "the answer itself must still come from CONTEXT):\n" + "\n".join(turns) + "\n\n")

def _retrieval_query(question: str, history) -> str:
    """Fold the previous user turn into the retrieval query so follow-ups like
    'what about its events?' still retrieve the right spec."""
    if history:
        for m in reversed(history):
            if m.get("role") == "user" and (m.get("content") or "").strip():
                return f"{m['content'].strip()}\n{question}".strip()
    return question

def _ordered_sources(chunks: list) -> tuple:
    """Unique source names in first-seen order, a {name: 1-based number} map, and a
    per-chunk number list. Shared by build_prompt and build_sources so the inline
    [n] citations the model writes line up with the sources list sent to the client."""
    order, index, nums = [], {}, []
    for c in chunks:
        src = c["metadata"].get("source", "Unknown")
        if src not in index:
            order.append(src)
            index[src] = len(order)
        nums.append(index[src])
    return order, index, nums

def _unique_specs(chunks: list) -> list:
    """Ordered unique spec ids present in the retrieved chunks (for the retrieval trace)."""
    seen = []
    for c in chunks:
        sid = c["metadata"].get("spec_id")
        if sid and sid not in seen:
            seen.append(sid)
    return seen

def build_prompt(question: str, chunks: list[dict], guarded: bool, history=None) -> str:
    sysp = _system_prompt(guarded)
    _, index, _ = _ordered_sources(chunks)
    # Number by SOURCE (not by chunk) so multiple chunks of the same spec share one
    # citation number, and so [n] resolves to sources[n-1] on the client.
    ctx  = "\n\n".join(
        f"[Source {index[c['metadata'].get('source', 'Unknown')]}: {_source_label(c['metadata'])}]\n{c['document']}"
        for c in chunks
    )
    return f"{sysp}\n\n{_format_history(history)}CONTEXT:\n{ctx}\n\nQUESTION: {question}\n\nANSWER:"

def generate_answer(prompt: str) -> str:
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": LLM_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.0, "num_predict": 900,
                                        "stop": ["QUESTION:", "CONTEXT:"]}},
                      timeout=300)
    r.raise_for_status()
    return r.json()["response"].strip()

# ── Schemas ────────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    top_k:    int           = TOP_K
    scope:    str           = "all"   # "all" = KB + your docs · "kb" = TM Forum only · "docs" = your uploads only
    history:  Optional[list] = None   # [{role, content}] recent turns, for follow-up questions
    standards_filter: Optional[list] = None

class Source(BaseModel):
    name: str; file: str; chunk: int; preview: str; url: str = ""; upload: bool = False

class QueryResponse(BaseModel):
    answer: str; sources: list; latency_ms: int; chunks_retrieved: int

class FollowupReq(BaseModel):
    question: str = ""
    answer:   str = ""

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

@app.get("/coverage")
def coverage():
    """What the knowledge base actually covers — specs grouped by domain (for onboarding)."""
    col = get_collection()
    try:
        smap = get_spec_map(col)
    except Exception:
        smap = {}
    groups: dict = {}
    for sid, files in smap.items():
        f0 = sorted(files)[0] if files else ""
        dom = _kb_category(sid, f0, "")
        groups.setdefault(dom, set()).add(sid)
    domains = [{"domain": d, "specs": sorted(groups[d])} for d in sorted(groups)]
    return {"chunks": col.count(), "spec_count": len(smap), "domains": domains}

# ── Query ──────────────────────────────────────────────────────────────────────
# Schema-aware re-ranking. nomic-embed distances alone can rank an unrelated schema
# that literally says "required: [id, callback]" (e.g. EventSubscription) above the
# resource the user actually named (e.g. ProductOrder). We nudge the ranking by
# matching the schema name embedded in each chunk to the resource in the question.
_SCHEMA_RE    = re.compile(r"Schema:\s*([A-Za-z0-9_]+)")
_FIELD_INTENT = re.compile(r"\b(mandatory|required|require[sd]?|fields?|attributes?|propert(?:y|ies)|schema)\b", re.I)
_FOCUS_STOP   = {"what","whats","which","whose","does","do","did","the","a","an","of","for","in","on","is",
                 "are","to","how","require","requires","required","mandatory","optional","fields","field",
                 "attributes","attribute","property","properties","schema","schemas","list","show","tell",
                 "me","about","and","or","resource","entity","object","model","open","api","apis","need",
                 "needs","needed","have","has","with","please","give","when","creating","create"}
_GENERIC_SCHEMAS = ("eventsubscription","hub","event","notification","error","extensibleerror","meta",
                    "entityref","timeperiod","money","quantity","note","characteristic","attachmentref")
LEX_WEIGHT = 0.12   # hybrid re-rank: how much a full keyword match can pull a chunk up

def _schema_name(doc: str) -> str:
    m = _SCHEMA_RE.search(doc or "")
    return m.group(1) if m else ""

def _resource_focus(question: str) -> dict:
    """Pull the resource the user is asking about out of the question, e.g.
    'mandatory fields of TMF622 Product Order' -> target 'productorder', plus the
    set of content keywords used for the lexical half of the hybrid re-rank."""
    cleaned = re.sub(r"\bTMF\s?\d{3,4}\b", " ", question or "", flags=re.I)
    words   = re.findall(r"[A-Za-z][A-Za-z0-9]*", cleaned)
    keep    = [w for w in words if w.lower() not in _FOCUS_STOP and len(w) > 1]
    terms   = sorted({w.lower() for w in words if len(w) > 2 and w.lower() not in _FOCUS_STOP})
    return {"target": "".join(keep).lower(),
            "is_field": bool(_FIELD_INTENT.search(question or "")),
            "terms": terms}

def _rank_adjust(focus: dict, doc: str, dist: float) -> float:
    """Hybrid re-rank → effective distance (lower = better). Blends the dense embedding
    distance with two sparse signals: (a) a schema-name match to the named resource
    (preferring its _Create variant for 'fields' questions, demoting *Ref/*_Update and
    unrelated generic schemas), and (b) lexical overlap with the question's keywords."""
    eff = dist
    target = focus.get("target") or ""
    sn = _schema_name(doc).lower().replace("_", "") if target else ""
    if target and sn:
        is_field = focus.get("is_field")
        if is_field and any(sn == g or sn.startswith(g) for g in _GENERIC_SCHEMAS):
            eff += 0.25                           # unrelated notification/error schema on a fields question
        elif is_field and target in sn and (sn.endswith("ref") or sn.endswith("update")):
            eff += 0.15                           # *Ref / *_Update aren't where required-to-create lives
        elif sn == target + "create":
            eff -= 0.22                           # the _Create / FVO variant — exactly what you must submit
        elif sn == target:
            eff -= 0.16                           # the main resource schema
        elif target in sn or sn in target:
            eff -= 0.10                           # related schema (e.g. ProductOrderItem)
    # Lexical (sparse) signal: reward chunks that literally contain the query's keywords.
    terms = focus.get("terms") or []
    if terms:
        dl = doc.lower()
        hits = sum(1 for t in terms if t in dl)
        if hits:
            eff -= LEX_WEIGHT * (hits / len(terms))
    return eff

def retrieve(question: str, q_emb: list, top_k: int, scope: str):
    """Shared retrieval for /query and /query/stream.
    Returns (chunks, confident, empty_msg). chunks == [] means nothing relevant;
    empty_msg holds the user-facing fallback text in that case."""
    col = get_collection()
    total = col.count()
    if total == 0:
        return [], False, NO_INFO_MSG

    added     = [d.get("origin") or d.get("file") for d in load_uploads() if d.get("status") == "indexed"]
    added_set = set(added)
    focus     = _resource_focus(question)
    seen:    set  = set()
    chunks:  list = []
    matched: list = []

    def add(d, m, dist, upload=False, eff=None) -> bool:
        key = (m.get("file", ""), m.get("chunk", 0))
        if key in seen:
            return False
        seen.add(key)
        chunks.append({"document": d, "metadata": m, "distance": dist, "upload": upload,
                       "eff": dist if eff is None else eff})
        return True

    if scope == "docs":
        # Answer ONLY from the user's uploaded documents.
        if added:
            res = col.query(query_embeddings=[q_emb], n_results=min(top_k * 2, total),
                            where={"origin": {"$in": added}},
                            include=["documents", "metadatas", "distances"])
            for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                if len(chunks) >= top_k:
                    break
                if dist < DOC_SCOPE_MAX:
                    add(d, m, dist, upload=True)
    else:
        # 1. Spec-targeted retrieval — guarantee named specs are present.
        spec_map = get_spec_map(col)
        spec_ids = detect_spec_ids(question)
        matched  = [s for s in spec_ids if spec_map.get(s)]
        if matched:
            per_spec = max(top_k // len(matched), 2)
            for sid in matched:
                sfiles = sorted(spec_map[sid])
                res = col.query(query_embeddings=[q_emb], n_results=min(per_spec * 4, total),
                                where={"file": {"$in": sfiles}},
                                include=["documents", "metadatas", "distances"])
                cands = [(_rank_adjust(focus, d, dist), d, m, dist)
                         for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
                         if dist < KB_DIST_MAX]
                cands.sort(key=lambda x: x[0])           # schema-aware re-rank within the named spec
                n = per_spec
                for eff, d, m, dist in cands:
                    if n <= 0:
                        break
                    if add(d, m, dist, eff=eff):
                        n -= 1

        # 2. Merge uploaded docs (boosted) + general KB by effective distance.
        pool: list = []
        if scope == "all" and added:
            res = col.query(query_embeddings=[q_emb], n_results=min(top_k * 2, total),
                            where={"origin": {"$in": added}},
                            include=["documents", "metadatas", "distances"])
            for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                if dist < UPLOAD_MAX_DIST:
                    pool.append({"d": d, "m": m, "dist": dist, "upload": True,
                                 "eff": max(0.0, _rank_adjust(focus, d, dist) - UPLOAD_BOOST)})
        res = col.query(query_embeddings=[q_emb], n_results=min(top_k * 3, total),
                        include=["documents", "metadatas", "distances"])
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            if m.get("origin", "") in added_set:        # user-added sources handled separately above
                continue
            if dist < KB_DIST_MAX:
                pool.append({"d": d, "m": m, "dist": dist, "upload": False, "eff": _rank_adjust(focus, d, dist)})
        pool.sort(key=lambda c: c["eff"])
        for c in pool:
            if len(chunks) >= top_k:
                break
            add(c["d"], c["m"], c["dist"], upload=c["upload"], eff=c["eff"])

    if not chunks:
        if scope == "docs":
            msg = ("You haven't uploaded any documents yet — add one on the Documents page."
                   if not upload_files else
                   "I couldn't find anything relevant in your uploaded documents for that question.")
        else:
            msg = NO_INFO_MSG
        return [], False, msg

    chunks.sort(key=lambda c: c.get("eff", c["distance"]))   # schema-aware order → best match becomes [Source 1]
    best = min(c["distance"] for c in chunks)
    if scope == "docs":
        confident = best < UPLOAD_MAX_DIST
    else:
        confident = bool(matched) \
            or any(c["upload"] and c["distance"] < UPLOAD_CONFIDENT for c in chunks) \
            or best < CONFIDENT_DIST
    return chunks, confident, ""

def build_sources(chunks: list) -> list:
    """De-duplicated source list (JSON-serialisable), ordered to match the [Source n]
    numbering used in the prompt so inline [n] citations resolve to the right entry."""
    order, _, _ = _ordered_sources(chunks)
    first = {}
    for c in chunks:
        src = c["metadata"].get("source", "Unknown")
        if src not in first:
            first[src] = c
    sources = []
    for src in order:
        c = first[src]
        QUERY_HITS[src] = QUERY_HITS.get(src, 0) + 1
        sources.append({
            "name":    src,
            "file":    c["metadata"].get("file", ""),
            "chunk":   c["metadata"].get("chunk", 0),
            "preview": c["document"][:400] + ("..." if len(c["document"]) > 400 else ""),
            "url":     c["metadata"].get("source_url", ""),
            "upload":  bool(c.get("upload")),
        })
    return sources

def stream_ollama(prompt: str):
    """Yield answer text fragments from Ollama as they are generated."""
    with requests.post(f"{OLLAMA_URL}/api/generate",
                       json={"model": LLM_MODEL, "prompt": prompt, "stream": True,
                             "options": {"temperature": 0.0, "num_predict": 900,
                                         "stop": ["QUESTION:", "CONTEXT:"]}},
                       stream=True, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:    obj = json.loads(line)
            except Exception: continue
            frag = obj.get("response", "")
            if frag:
                yield frag
            if obj.get("done"):
                break

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    start = time.time()
    top_k = max(1, min(req.top_k, 20))
    scope = (req.scope or "all").lower()
    if scope not in ("all", "kb", "docs"):
        scope = "all"

    rq = _retrieval_query(req.question, req.history)
    try:    q_emb = embed(rq)
    except Exception as e: raise HTTPException(503, f"Embedding failed: {e}")

    try:    chunks, confident, empty = retrieve(rq, q_emb, top_k, scope)
    except Exception as e: raise HTTPException(503, f"Retrieval failed: {e}")

    if not chunks:
        _log_query(req.question, False)
        return QueryResponse(answer=empty, sources=[],
                             latency_ms=int((time.time()-start)*1000), chunks_retrieved=0)

    try:    answer = generate_answer(build_prompt(req.question, chunks, guarded=not confident, history=req.history))
    except Exception as e: raise HTTPException(503, f"Generation failed: {e}")

    # If the LLM used its exact "no info" escape hatch, return no sources.
    if answer.lower().strip().startswith(NO_INFO_PREFIX):
        _log_query(req.question, False)
        return QueryResponse(answer=answer, sources=[],
                             latency_ms=int((time.time()-start)*1000), chunks_retrieved=0)

    _log_query(req.question, True)
    return QueryResponse(answer=answer, sources=build_sources(chunks),
                         latency_ms=int((time.time()-start)*1000), chunks_retrieved=len(chunks))


# ── Query (streaming, token-by-token) ────────────────────────────────────────
@app.post("/query/stream")
def query_stream(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    start = time.time()
    top_k = max(1, min(req.top_k, 20))
    scope = (req.scope or "all").lower()
    if scope not in ("all", "kb", "docs"):
        scope = "all"
    rq = _retrieval_query(req.question, req.history)
    try:    q_emb = embed(rq)
    except Exception as e: raise HTTPException(503, f"Embedding failed: {e}")
    chunks, confident, empty = retrieve(rq, q_emb, top_k, scope)

    def gen():
        if not chunks:
            _log_query(req.question, False)
            yield json.dumps({"type": "token", "text": empty}) + "\n"
            yield json.dumps({"type": "done", "sources": [],
                              "latency_ms": int((time.time() - start) * 1000),
                              "chunks_retrieved": 0}) + "\n"
            return
        # Tell the client what we're reading before the slow generation starts.
        yield json.dumps({"type": "context",
                          "sources": _ordered_sources(chunks)[0][:6],
                          "specs":   _unique_specs(chunks)[:6]}) + "\n"
        acc = ""
        try:
            for frag in stream_ollama(build_prompt(req.question, chunks, guarded=not confident, history=req.history)):
                acc += frag
                yield json.dumps({"type": "token", "text": frag}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "text": f"Generation failed: {e}"}) + "\n"
            return
        srcs = [] if acc.lower().strip().startswith(NO_INFO_PREFIX) else build_sources(chunks)
        _log_query(req.question, bool(srcs))
        yield json.dumps({"type": "done", "sources": srcs,
                          "latency_ms": int((time.time() - start) * 1000),
                          "chunks_retrieved": len(chunks)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")

# ── Follow-up suggestions ────────────────────────────────────────────────────────
def generate_followups(question: str, answer: str) -> list:
    """Suggest 3 natural next questions from a Q&A pair. Best-effort; [] on any failure."""
    ans = (answer or "").strip()
    if not ans or ans.lower().startswith(NO_INFO_PREFIX):
        return []
    prompt = (
        "You help a user explore TM Forum / telecom standards. Given the question and answer "
        "below, suggest exactly 3 short, specific follow-up questions the user would naturally "
        "ask next. Each must be self-contained and under 12 words. Return ONLY the questions, "
        "one per line, with no numbering or bullets.\n\n"
        f"QUESTION: {question}\n\nANSWER: {ans[:1500]}\n\nFOLLOW-UPS:"
    )
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate",
                          json={"model": LLM_MODEL, "prompt": prompt, "stream": False,
                                "options": {"temperature": 0.4, "num_predict": 120,
                                            "stop": ["QUESTION:", "ANSWER:"]}},
                          timeout=60)
        r.raise_for_status()
        raw = r.json().get("response", "")
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        q = line.strip().lstrip("0123456789.-)*• ").strip().strip('"').strip()
        if len(q) >= 8:
            out.append(q if q.endswith("?") else q + "?")
        if len(out) == 3:
            break
    return out

@app.post("/followups")
def followups(req: FollowupReq):
    return {"questions": generate_followups(req.question, req.answer)}

# ── TMF630 conformance checker ───────────────────────────────────────────────────
@app.post("/conformance")
async def conformance_check(file: UploadFile = File(...)):
    """Upload an OpenAPI/Swagger spec → get a TMF630 conformance report (score + findings)."""
    raw  = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    spec = None
    try:
        spec = json.loads(text)
    except Exception:
        try:
            import yaml
            spec = yaml.safe_load(text)
        except Exception:
            spec = None
    if not isinstance(spec, dict):
        raise HTTPException(400, "Could not parse that file as an OpenAPI/Swagger spec (JSON or YAML).")
    if not spec.get("paths") and not (spec.get("components") or spec.get("definitions")):
        raise HTTPException(400, "That doesn't look like an OpenAPI spec — no paths or schemas found.")
    report = conformance.check_spec(spec)
    report["filename"] = file.filename
    return report

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
        if not fname or fname in upload_files or meta.get("origin"):
            continue                            # skip user-added sources (files/repos/web)
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
            file_stats[fname] = {"file": fname, "name": display, "folder": folder,
                                 "category": _kb_category(meta.get("spec_id", ""), fname, folder),
                                 "chunks": 0, "status": "indexed"}
        file_stats[fname]["chunks"] += 1

    # Group by domain category (TM Forum / ODA / MEF / …) — same folders as user sources
    groups: dict[str, dict] = {}
    for stat in file_stats.values():
        g = stat["category"]
        if g not in groups:
            groups[g] = {"id": g, "name": g, "files": 0, "chunks": 0, "documents": []}
        groups[g]["files"]  += 1
        groups[g]["chunks"] += stat["chunks"]
        groups[g]["documents"].append(stat)

    CAT_ORDER = ["TM Forum", "ODA", "MEF", "ETSI", "3GPP", "IETF", "Other"]
    sorted_groups = sorted(groups.values(),
                           key=lambda x: CAT_ORDER.index(x["name"]) if x["name"] in CAT_ORDER else 99)
    for grp in sorted_groups:
        grp["documents"] = sorted(grp["documents"], key=lambda x: -x["chunks"])[:200]

    return {
        "total_files":  len(file_stats),
        "total_chunks": sum(s["chunks"] for s in file_stats.values()),
        "groups": sorted_groups,
    }

def _categorize(*hints) -> str:
    """Best-effort domain bucket for a USER-ADDED source (defaults to 'Other')."""
    blob = " ".join(h for h in hints if h).lower()
    if "tmforum" in blob or "tm forum" in blob or "tmf" in blob: return "TM Forum"
    if "oda" in blob:                    return "ODA"
    if "mef" in blob:                    return "MEF"
    if "etsi" in blob or "nfv" in blob:  return "ETSI"
    if "3gpp" in blob:                   return "3GPP"
    if "ietf" in blob or "rfc" in blob:  return "IETF"
    return "Other"

def _kb_category(spec_id: str, file: str, folder: str) -> str:
    """Domain bucket for a base Knowledge Base doc. Defaults to 'TM Forum' since
    the bundled KB is TM Forum-sourced; splits out ODA/MEF/etc. when detectable."""
    blob = f"{spec_id} {file} {folder}".lower()
    if "oda" in blob:                    return "ODA"
    if "mef" in blob:                    return "MEF"
    if "etsi" in blob or "nfv" in blob:  return "ETSI"
    if "3gpp" in blob:                   return "3GPP"
    if "ietf" in blob or "rfc" in blob:  return "IETF"
    return "TM Forum"

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
        # Auto-organize: tag each source with a domain bucket (TM Forum / ODA / MEF / …)
        d["category"] = d.get("category") or _categorize(d.get("name"), d.get("url"), d.get("file"))
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
        if meta.get("origin") == file_name or meta.get("file") == file_name
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
def save_branding_endpoint(body: dict, _admin: dict = Depends(require_admin)):
    cleaned = {k: v for k, v in body.items()
               if k in {"companyName","tagline","primaryColor"} and isinstance(v, str)}
    merged  = {**DEFAULT_BRANDING, **cleaned}
    BRANDING_FILE.write_text(json.dumps(merged, indent=2))
    return merged

# ── Chat config (placeholder / suggestions / domain persona) ─────────────────
@app.get("/chat-config")
def get_chat_config():
    return load_chat_config()

@app.post("/chat-config")
def save_chat_config(body: dict, _admin: dict = Depends(require_admin)):
    cfg = load_chat_config()
    if isinstance(body.get("placeholder"), str): cfg["placeholder"] = body["placeholder"][:200]
    if isinstance(body.get("persona"), str):     cfg["persona"]     = body["persona"][:600]
    if isinstance(body.get("suggestions"), list):
        cfg["suggestions"] = [str(s).strip()[:200] for s in body["suggestions"] if str(s).strip()][:8]
    CHATCFG_FILE.write_text(json.dumps(cfg, indent=2))
    return cfg

# ── Conversations (per-user chat history) ────────────────────────────────────
def _convos_path(uid: str):
    return CONVOS_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '_', uid)}.json"

def _load_convos(uid: str) -> list:
    p = _convos_path(uid)
    if p.exists():
        try:    return json.loads(p.read_text())
        except: pass
    return []

def _save_convos(uid: str, convos: list):
    _convos_path(uid).write_text(json.dumps(convos, indent=2))

@app.get("/conversations")
def list_conversations(user: dict = Depends(current_user)):
    convos = _load_convos(user["id"])
    return {"conversations": sorted(
        [{"id": c["id"], "title": c.get("title", "New chat"),
          "updated": c.get("updated", 0), "count": len(c.get("messages", []))}
         for c in convos],
        key=lambda x: -x["updated"])}

@app.get("/conversations/{cid}")
def get_conversation(cid: str, user: dict = Depends(current_user)):
    for c in _load_convos(user["id"]):
        if c["id"] == cid:
            return c
    raise HTTPException(404, "Conversation not found")

@app.post("/conversations")
def create_conversation(body: dict, user: dict = Depends(current_user)):
    convos = _load_convos(user["id"])
    c = {"id": uuid.uuid4().hex[:12],
         "title": (body.get("title") or "New chat")[:80],
         "messages": body.get("messages") or [],
         "updated": int(time.time())}
    convos.append(c)
    _save_convos(user["id"], convos)
    return c

@app.put("/conversations/{cid}")
def update_conversation(cid: str, body: dict, user: dict = Depends(current_user)):
    convos = _load_convos(user["id"])
    for c in convos:
        if c["id"] == cid:
            if isinstance(body.get("messages"), list):
                c["messages"] = body["messages"][:200]
            if body.get("title"):
                c["title"] = str(body["title"])[:80]
            c["updated"] = int(time.time())
            _save_convos(user["id"], convos)
            return c
    raise HTTPException(404, "Conversation not found")

@app.delete("/conversations/{cid}")
def delete_conversation(cid: str, user: dict = Depends(current_user)):
    convos = _load_convos(user["id"])
    remaining = [c for c in convos if c["id"] != cid]
    if len(remaining) == len(convos):
        raise HTTPException(404, "Conversation not found")
    _save_convos(user["id"], remaining)
    return {"ok": True}

# ── Users ──────────────────────────────────────────────────────────────────────
_DEFAULTS_BY_EMAIL = {u["email"]: u for u in DEFAULT_USERS}

def _ensure_passwords(users: list[dict]) -> bool:
    """Migrate stored users: give everyone a password hash (seed accounts use
    their known demo password) and backfill title/department from defaults."""
    changed = False
    for u in users:
        em = (u.get("email") or "").lower()
        if not u.get("password_hash"):
            pw = SEED_PASSWORDS.get(em, secrets.token_hex(8))
            u["password_hash"], u["salt"] = hash_password(pw)
            changed = True
        d = _DEFAULTS_BY_EMAIL.get(em)
        if d:
            for k in ("title", "department"):
                if not u.get(k) and d.get(k):
                    u[k] = d[k]; changed = True
    return changed

def _load_users() -> list[dict]:
    if USERS_FILE.exists():
        try:
            users = json.loads(USERS_FILE.read_text())
            if _ensure_passwords(users):
                _save_users(users)
            return users
        except: pass
    users = [dict(u) for u in DEFAULT_USERS]
    _ensure_passwords(users)
    _save_users(users)
    return users

def _save_users(users: list[dict]):
    USERS_FILE.write_text(json.dumps(users, indent=2))

# ── Auth endpoints ───────────────────────────────────────────────────────────
@app.post("/auth/login")
def auth_login(body: LoginReq):
    email = (body.email or "").lower().strip()
    users = _load_users()
    u = next((x for x in users if (x.get("email") or "").lower() == email), None)
    if not u or not verify_password(body.password, u.get("password_hash", ""), u.get("salt", "")):
        raise HTTPException(401, "Invalid email or password.")
    u["lastActive"] = "Now"
    _save_users(users)
    return {"token": make_token(u), "user": _public_user(u)}

@app.get("/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return {"user": _public_user(user)}

@app.put("/auth/profile")
def auth_update_profile(body: dict, user: dict = Depends(current_user)):
    """Let a signed-in user edit their own name / title / department."""
    users = _load_users()
    for u in users:
        if u["id"] == user["id"]:
            for k in ("name", "title", "department"):
                if k in body and isinstance(body[k], str):
                    u[k] = body[k]
            _save_users(users)
            return {"user": _public_user(u)}
    raise HTTPException(404, "User not found")

@app.post("/auth/password")
def auth_change_password(body: dict, user: dict = Depends(current_user)):
    """Change the signed-in user's own password (verifies the current one)."""
    new = body.get("new_password", "")
    if len(new) < 6:
        raise HTTPException(400, "New password must be at least 6 characters.")
    users = _load_users()
    for u in users:
        if u["id"] == user["id"]:
            if not verify_password(body.get("current_password", ""), u.get("password_hash", ""), u.get("salt", "")):
                raise HTTPException(401, "Current password is incorrect.")
            u["password_hash"], u["salt"] = hash_password(new)
            _save_users(users)
            return {"ok": True}
    raise HTTPException(404, "User not found")

@app.get("/users")
def get_users():
    return {"users": [_public_user(u) for u in _load_users()]}

@app.post("/users")
def add_user(body: dict, _admin: dict = Depends(require_admin)):
    users = _load_users()
    ph, salt = hash_password(body.get("password") or secrets.token_hex(8))
    new_u = {"id": str(uuid.uuid4()), "name": body.get("name", ""),
             "email": body.get("email", ""), "role": body.get("role", "viewer"),
             "status": "inactive", "lastActive": "Never",
             "title": body.get("title", ""), "department": body.get("department", ""),
             "password_hash": ph, "salt": salt}
    users.append(new_u)
    _save_users(users)
    return _public_user(new_u)

@app.put("/users/{user_id}")
def update_user(user_id: str, body: dict, _admin: dict = Depends(require_admin)):
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            for k in ("name", "role", "status", "title", "department"):
                if k in body: u[k] = body[k]
            if body.get("password"):
                u["password_hash"], u["salt"] = hash_password(body["password"])
            _save_users(users)
            return _public_user(u)
    raise HTTPException(404, "User not found")

@app.delete("/users/{user_id}")
def delete_user(user_id: str, _admin: dict = Depends(require_admin)):
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

# ── Feedback + analytics + KB refresh ────────────────────────────────────────
@app.post("/feedback")
def submit_feedback(body: dict, user: dict = Depends(current_user)):
    rating = body.get("rating")
    if rating not in ("up", "down"):
        raise HTTPException(400, "rating must be 'up' or 'down'")
    try:    fb = json.loads(FEEDBACK_FILE.read_text()) if FEEDBACK_FILE.exists() else []
    except Exception: fb = []
    fb.insert(0, {"ts": int(time.time()), "user": user.get("email"), "rating": rating,
                  "question": str(body.get("question", ""))[:200],
                  "sources": (body.get("sources") or [])[:5]})
    FEEDBACK_FILE.write_text(json.dumps(fb[:500], indent=2))
    return {"ok": True}

@app.get("/analytics")
def get_analytics(_admin: dict = Depends(require_admin)):
    try:    a = json.loads(ANALYTICS_FILE.read_text()) if ANALYTICS_FILE.exists() else {}
    except Exception: a = {}
    try:    fb = json.loads(FEEDBACK_FILE.read_text()) if FEEDBACK_FILE.exists() else []
    except Exception: fb = []
    top = sorted(QUERY_HITS.items(), key=lambda x: -x[1])[:10]
    return {
        "total_queries": a.get("total", 0),
        "answered":      a.get("answered", 0),
        "gaps":          a.get("gaps", [])[:20],
        "top_sources":   [{"name": k, "hits": v} for k, v in top],
        "feedback": {
            "up":   sum(1 for f in fb if f.get("rating") == "up"),
            "down": sum(1 for f in fb if f.get("rating") == "down"),
            "recent": fb[:10],
        },
    }

@app.post("/admin/refresh-kb")
def refresh_kb(_admin: dict = Depends(require_admin)):
    """Re-pull the source repos and rebuild the index. Heavy — best off-peak.
    Schedule it by cron'ing a call to this endpoint."""
    if PROCESSING_STATUS.get("__kb_refresh__", {}).get("status") == "processing":
        return {"status": "processing"}
    def _run():
        global _chroma_client, _chroma_collection, _spec_map, _spec_names
        PROCESSING_STATUS["__kb_refresh__"] = {"status": "processing", "chunks": 0}
        try:
            url_map = ingest.download_data()
            n = ingest.build_index(url_map)
            with _chroma_lock:                 # force re-open of the rebuilt collection
                _chroma_client = None; _chroma_collection = None
                _spec_map = None; _spec_names = []
            PROCESSING_STATUS["__kb_refresh__"] = {"status": "indexed", "chunks": n}
        except Exception as e:
            PROCESSING_STATUS["__kb_refresh__"] = {"status": "failed", "chunks": 0, "error": str(e)[:200]}
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "processing"}

@app.get("/admin/refresh-kb/status")
def refresh_kb_status(_admin: dict = Depends(require_admin)):
    return PROCESSING_STATUS.get("__kb_refresh__", {"status": "idle", "chunks": 0})
