"""
SynaptDI — Ingestion Pipeline
Downloads TM Forum API specs from GitHub, chunks them, embeds with
nomic-embed-text via Ollama, and stores in ChromaDB.

Run: python ingest.py
"""

import os, json, yaml, requests, shutil, subprocess, re, hashlib, urllib.request
from pathlib import Path
import chromadb

# ── Config ─────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434"
EMBED_MODEL  = "nomic-embed-text"
CHROMA_PATH  = "./chroma_db"
DATA_PATH    = "./data"
CHUNK_SIZE   = 800   # characters per chunk
CHUNK_OVERLAP= 120

# Primary org: every TMFxxx Open API repo is discovered dynamically (≈90 specs,
# the full suite) plus the Open_Api_And_Data_Model monorepo (carries the SID
# data model). CURATED_REPOS adds design-guideline / data-model / ODA-canvas
# docs that fill the gaps. Pure reference-implementation code, conformance test
# kits and the giant integration repos are intentionally excluded — ingest only
# reads OpenAPI specs + markdown, so cloning Java/Scala adds disk and time with
# no retrieval value.
API_ORG = "tmforum-apis"
CURATED_REPOS = [                       # (org, repo) — knowledge-bearing, not code
    ("tmforum-oda", "oda-canvas"),
    ("tmforum-oda", "reference-example-components"),
    ("tmforum-oda", "oda-ca-docs"),
    ("tmforum-oda", "ai-canvas-architecture"),
    ("tmforum",     "RESTGUIDELINESV2"),
    ("tmforum",     "DataModelDocumentation"),
    ("tmforum",     "RESTAPIDATAMODEL"),
]

# ── Helpers ─────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Call Ollama nomic-embed-text to get a single embedding."""
    resp = requests.post(f"{OLLAMA_URL}/api/embeddings", json={
        "model": EMBED_MODEL,
        "prompt": text
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()["embedding"]

def embed_batch(texts: list[str]) -> list:
    """Embed a list of texts in ONE Ollama call (10x fewer round-trips than
    per-chunk embedding). Returns a list of vectors aligned with `texts`;
    entries are None for any text that could not be embedded.
    Falls back to per-item embedding if the batch endpoint is unavailable."""
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/embed",
                             json={"model": EMBED_MODEL, "input": texts}, timeout=180)
        resp.raise_for_status()
        embs = resp.json().get("embeddings")
        if embs and len(embs) == len(texts):
            return embs
    except Exception as e:
        print(f"  ! batch embed failed ({e}); falling back to per-item")
    out = []
    for t in texts:
        try:    out.append(embed(t))
        except Exception: out.append(None)
    return out

def extract_spec_id(file_name: str) -> str:
    """Pull the TM Forum spec number from a filename, e.g. TMF641 — used so the
    query path can filter retrieval to the exact spec a user names."""
    m = re.search(r'TMF[\s_-]?(\d{3})', file_name.upper())
    return f"TMF{m.group(1)}" if m else ""

# Repo meta-docs that are not TM Forum knowledge — they only add noise to
# concept-query retrieval (READMEs, contributor/agent/template boilerplate).
_JUNK_MD = ("readme", "agents.md", "contributing", "code_of_conduct", "license",
            "maintainers", "changelog", "security.md", "governance", "skill.md",
            "writing-style", "style.md", "copilot", "-agent", ".agent.",
            "template", "bdd-feature-generator",
            # repo dev-tooling docs (not TM Forum knowledge)
            "plantuml", "mermaid", "-svg", "svg-", "renderer", "dashboard",
            "migration_guide", "migration-guide", "install", "setup",
            "troubleshoot", "devcontainer", "docker", "-ci", "ci-", "workflow",
            "assistant", "ai-coding", "ai_coding", "mcp")

def is_junk_markdown(file_name: str) -> bool:
    n = file_name.lower()
    return any(p in n for p in _JUNK_MD)

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c.strip() for c in chunks if c.strip()]

def doc_id(source: str, chunk_idx: int) -> str:
    h = hashlib.md5(f"{source}_{chunk_idx}".encode()).hexdigest()[:12]
    return f"{h}"

# ── Parsers ─────────────────────────────────────────────────────────────────

def _field_desc(prop: dict) -> str:
    """Short 'type — description' for one OpenAPI schema property (best-effort)."""
    if not isinstance(prop, dict):
        return ""
    t = prop.get("type", "")
    if t == "array":
        items = prop.get("items", {}) or {}
        ref   = items.get("$ref", "")
        inner = ref.split("/")[-1] if ref else items.get("type", "")
        t = f"array of {inner}" if inner else "array"
    elif not t and prop.get("$ref"):
        t = prop["$ref"].split("/")[-1]
    desc = (prop.get("description", "") or "").strip().replace("\n", " ").replace("|", "/")
    if len(desc) > 160:
        desc = desc[:160].rstrip() + "…"
    return " — ".join(p for p in (t, desc) if p)

def parse_openapi_spec(path: Path):
    """Parse an OpenAPI JSON/YAML spec into a readable text block."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix in (".yaml", ".yml"):
            spec = yaml.safe_load(raw)
        else:
            spec = json.loads(raw)
        if not isinstance(spec, dict):
            return None

        title    = spec.get("info", {}).get("title", path.stem)
        version  = spec.get("info", {}).get("version", "")
        desc     = spec.get("info", {}).get("description", "")[:500]

        lines = [f"# {title} (v{version})", desc, ""]

        api_name = title  # e.g. "Product Ordering"

        # Paths / endpoints — natural-language descriptions for better retrieval
        for path_str, methods in spec.get("paths", {}).items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method.startswith("x-") or not isinstance(op, dict):
                    continue
                op_summary = op.get("summary", op.get("operationId", ""))
                op_desc    = op.get("description", "")[:300]
                lines.append(f"## {method.upper()} {path_str}")
                if op_summary: lines.append(f"{api_name} operation: {op_summary}")
                if op_desc:    lines.append(op_desc)

                # Query parameters with descriptions (pagination, filtering, etc.)
                params = op.get("parameters", [])
                req_names, opt_parts, opt_names = [], [], set()
                for p in params:
                    if not isinstance(p, dict): continue
                    pname = p.get("name", "")
                    pdesc = p.get("description", "")
                    if not pname: continue
                    if p.get("required"):
                        req_names.append(pname)
                    else:
                        opt_names.add(pname.lower())
                        entry = pname
                        if pdesc: entry += f" ({pdesc[:100]})"
                        opt_parts.append(entry)
                if req_names:
                    lines.append(f"This operation requires: {', '.join(req_names)}")
                if opt_parts:
                    lines.append(f"Optional query parameters: {'; '.join(opt_parts)}")
                # Explicit natural-language pattern lines so conceptual questions
                # ("how do I handle pagination / filtering?") match the spec itself.
                if {"offset", "limit"} & opt_names:
                    lines.append(f"This {api_name} operation supports pagination using the "
                                 f"offset and limit query parameters — offset is the start "
                                 f"index and limit is the maximum number of results returned "
                                 f"per page, per the TM Forum REST API design guidelines.")
                if "fields" in opt_names:
                    lines.append("Responses support attribute selection (sparse fieldsets) "
                                 "via the fields query parameter.")
                if "sort" in opt_names:
                    lines.append("Results can be ordered using the sort query parameter.")

                # Request body — natural language for mandatory fields
                body = op.get("requestBody", {})
                if body and isinstance(body, dict):
                    for ct_val in body.get("content", {}).values():
                        schema = ct_val.get("schema", {})
                        props  = schema.get("properties", {})
                        req    = schema.get("required", [])
                        opt    = [k for k in props if k not in req]
                        if req:
                            lines.append(f"Mandatory fields for {api_name}: {', '.join(req)}")
                        if props:
                            ordered = [k for k in req if k in props] + [k for k in props if k not in req]
                            for k in ordered[:30]:
                                d = _field_desc(props.get(k, {}))
                                flag = "mandatory" if k in req else "optional"
                                lines.append(f"- {k} ({flag}){': ' + d if d else ''}")
                        elif opt:
                            lines.append(f"Optional fields: {', '.join(opt[:20])}")
                lines.append("")

        # Definitions / components — natural-language schema descriptions
        schemas = (
            spec.get("components", {}).get("schemas", {})
            or spec.get("definitions", {})
        )
        for schema_name, schema_def in list(schemas.items())[:80]:
            if not isinstance(schema_def, dict):
                continue
            props = schema_def.get("properties", {})
            req   = schema_def.get("required", [])
            sdesc = schema_def.get("description", "")[:200]
            opt   = [k for k in props if k not in req]

            lines.append(f"## {api_name} Schema: {schema_name}")
            if sdesc: lines.append(sdesc)
            if req:
                lines.append(f"The {schema_name} schema has these mandatory fields: {', '.join(req)}")
            if props:
                lines.append(f"Fields of {schema_name} (mandatory first):")
                ordered = [k for k in req if k in props] + [k for k in props if k not in req]
                for k in ordered[:40]:
                    d = _field_desc(props.get(k, {}))
                    flag = "mandatory" if k in req else "optional"
                    lines.append(f"- {k} ({flag}){': ' + d if d else ''}")
            elif opt:
                lines.append(f"Optional fields of {schema_name}: {', '.join(opt[:25])}")
            lines.append("")

        return {"title": title, "version": version, "text": "\n".join(lines)}

    except Exception as e:
        return None


# Dev-tooling docs (repo plumbing, not TM Forum knowledge) — these pollute
# conceptual queries with PlantUML/AI-assistant/CI noise, so drop them by content.
_JUNK_MD_CONTENT = ("plantuml", "mermaid", "svg renderer", "coding assistant",
                    "ai coding", "ai-augmented", "copilot", "windsurf", "cursor ide",
                    "dashboard import", "devcontainer", "model context protocol",
                    "gif creator", "screenshot")

def parse_markdown(path: Path):
    """Parse a markdown file into text, skipping repo dev-tooling docs."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        head = text[:1200].lower()
        if any(k in head for k in _JUNK_MD_CONTENT):
            return None                      # tooling doc, not spec knowledge
        title = path.stem.replace("-", " ").replace("_", " ").title()
        # Try to extract H1
        m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
        if m:
            title = m.group(1).strip()
        if any(k in title.lower() for k in _JUNK_MD_CONTENT):
            return None
        return {"title": title, "version": "", "text": text[:20000]}
    except:
        return None


# ── Download TM Forum data ──────────────────────────────────────────────────

def _gh_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "synaptdi-ingest"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def gather_repos():
    """Discover every TMFxxx API repo in tmforum-apis (plus the monorepo) and
    append the curated doc repos. Returns [(org, name, clone_url, blob_base)].
    Falls back to the monorepo only if the GitHub API is unreachable."""
    repos, seen = [], set()
    def add(org, name, branch="main"):
        if (org, name) in seen:
            return
        seen.add((org, name))
        repos.append((org, name,
                      f"https://github.com/{org}/{name}.git",
                      f"https://github.com/{org}/{name}/blob/{branch}"))
    try:
        api = _gh_json(f"https://api.github.com/orgs/{API_ORG}/repos?per_page=100&type=public")
        for r in api:
            n = r["name"]
            if n == "Open_Api_And_Data_Model" or re.match(r"TMF\d{3}", n):
                add(API_ORG, n, r.get("default_branch", "main"))
        print(f"  Discovered {len(repos)} {API_ORG} API repos")
    except Exception as e:
        print(f"  ! GitHub discovery failed ({e}); falling back to monorepo only")
        add(API_ORG, "Open_Api_And_Data_Model", "master")
    for org, name in CURATED_REPOS:
        branch = "main"
        try:    branch = _gh_json(f"https://api.github.com/repos/{org}/{name}").get("default_branch", "main")
        except Exception: pass
        add(org, name, branch)
    return repos

def download_data():
    """Clone all knowledge repos (shallow) into data/. Returns a
    {repo_name: github-blob-base-url} map used to build source citations."""
    data_dir = Path(DATA_PATH)
    data_dir.mkdir(exist_ok=True)

    repos = gather_repos()
    url_map = {}
    cloned = skipped = failed = 0
    for org, name, clone_url, blob_base in repos:
        url_map[name] = blob_base
        dest = data_dir / name
        if dest.exists():
            skipped += 1
            continue
        try:
            subprocess.run(["git", "clone", "--depth=1", clone_url, str(dest)],
                           check=True, capture_output=True, timeout=240)
            cloned += 1
            if cloned % 10 == 0:
                print(f"  ... cloned {cloned} repos")
        except Exception as e:
            failed += 1
            msg = e.stderr.decode()[:120] if hasattr(e, "stderr") and e.stderr else str(e)[:120]
            print(f"  ✗ {org}/{name}: {msg}")
    print(f"  repos: {cloned} cloned, {skipped} already present, {failed} failed")
    return url_map


# ── Build ChromaDB ──────────────────────────────────────────────────────────

def build_index(repo_url_map):
    print("\n[2/3] Building ChromaDB index...")

    from vectorstore import ChromaVectorStore
    store = ChromaVectorStore()              # same backend-agnostic layer the server uses

    # ── Snapshot user-uploaded chunks so we can re-add them after rebuild ──
    uploads_file = Path("./storage/uploads.json")
    upload_snapshot: dict = {}   # id → (doc, meta, emb)
    if uploads_file.exists():
        try:
            upload_files = {u["file"] for u in json.loads(uploads_file.read_text())}
            if upload_files:
                for r in store.scan(with_documents=True, with_embeddings=True):
                    if r["metadata"].get("file", "") in upload_files:
                        upload_snapshot[r["id"]] = (r["document"], r["metadata"], r["embedding"])
                print(f"  Preserved {len(upload_snapshot)} uploaded chunks for re-add")
        except Exception:
            pass   # no existing collection or no uploads — that's fine

    # Drop and recreate for a clean spec build (through the vector-store layer)
    store.recreate()
    collection = store

    data_dir = Path(DATA_PATH)
    docs_processed = 0
    chunks_added   = 0
    seen_hashes    = set()   # de-dup byte-identical specs across monorepo + individual repos

    def get_source_url(fpath: Path) -> str:
        """Build GitHub URL for a file."""
        parts = fpath.parts
        for repo_name, base_url in repo_url_map.items():
            if repo_name in parts:
                idx = parts.index(repo_name)
                rel = "/".join(parts[idx+1:])
                return f"{base_url}/{rel}"
        return ""

    # Find all relevant files
    spec_files = []
    for ext in ("*.json", "*.yaml", "*.yml"):
        spec_files.extend(data_dir.rglob(ext))
    md_files = [f for f in data_dir.rglob("*.md") if not is_junk_markdown(f.name)][:1500]

    all_files = spec_files + md_files
    print(f"  Found {len(spec_files)} spec files + {len(md_files)} markdown files")

    EMBED_BATCH = 64                       # texts embedded per Ollama call
    pend_ids, pend_docs, pend_metas = [], [], []

    def flush_batch():
        nonlocal chunks_added
        if not pend_ids:
            return
        embs = embed_batch(pend_docs)
        ids2, docs2, metas2, embs2 = [], [], [], []
        for _id, _doc, _meta, _emb in zip(pend_ids, pend_docs, pend_metas, embs):
            if _emb is None:               # skip texts that failed to embed
                continue
            ids2.append(_id);  docs2.append(_doc)
            metas2.append(_meta);  embs2.append(_emb)
        if ids2:
            collection.upsert(ids=ids2, documents=docs2,
                              metadatas=metas2, embeddings=embs2)
            chunks_added += len(ids2)
        pend_ids.clear(); pend_docs.clear(); pend_metas.clear()

    for i, fpath in enumerate(all_files):
        # Skip node_modules, .git, test files
        parts = fpath.parts
        if any(p in parts for p in (".git", "node_modules", "__pycache__")):
            continue
        if "test" in fpath.name.lower() and fpath.suffix != ".md":
            continue
        if fpath.suffix == ".md" and is_junk_markdown(fpath.name):
            continue                       # skip repo boilerplate / agent docs

        parsed = None
        if fpath.suffix in (".json", ".yaml", ".yml"):
            parsed = parse_openapi_spec(fpath)
        elif fpath.suffix == ".md":
            parsed = parse_markdown(fpath)

        if not parsed or not parsed["text"].strip():
            continue

        # Skip byte-identical specs (the monorepo and individual API repos ship
        # many of the same files) — avoids near-duplicate retrieval candidates.
        text_hash = hashlib.md5(parsed["text"].encode("utf-8", "ignore")).hexdigest()
        if text_hash in seen_hashes:
            continue
        seen_hashes.add(text_hash)

        source_name = f"{parsed['title']} {parsed['version']}".strip()
        spec_id     = extract_spec_id(fpath.name)
        chunks      = chunk_text(parsed["text"])

        for ci, chunk in enumerate(chunks):
            if len(chunk) < 60:
                continue
            pend_ids.append(doc_id(str(fpath), ci))
            pend_docs.append(chunk)
            pend_metas.append({
                "source":     source_name,
                "file":       fpath.name,
                "chunk":      ci,
                "spec_id":    spec_id,
                "source_url": get_source_url(fpath),
            })
            if len(pend_ids) >= EMBED_BATCH:
                flush_batch()

        docs_processed += 1
        if (i + 1) % 250 == 0:
            print(f"  ... {i+1}/{len(all_files)} files processed, {chunks_added} chunks so far")

    flush_batch()
    # ChromaDB's PersistentClient flushes to disk on its own; the index is
    # fully queryable on the next server start with no warmup needed.

    # ── Re-add uploaded chunks that were snapshotted before the rebuild ─────
    if upload_snapshot:
        ids, docs, metas, embs = [], [], [], []
        for iid, (doc, meta, emb) in upload_snapshot.items():
            ids.append(iid); docs.append(doc)
            metas.append(meta); embs.append(list(emb) if hasattr(emb, 'tolist') else emb)
        for i in range(0, len(ids), 50):
            collection.upsert(
                ids=ids[i:i+50], documents=docs[i:i+50],
                metadatas=metas[i:i+50], embeddings=embs[i:i+50]
            )
        chunks_added += len(ids)
        print(f"  ✓ Restored {len(ids)} uploaded document chunks")

    print(f"\n  ✓ Indexed {docs_processed} documents → {chunks_added} chunks in ChromaDB")
    return chunks_added


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  SynaptDI — Ingestion Pipeline")
    print("=" * 55)

    # Check Ollama is running
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"\n[0/3] Ollama running. Models: {models}")
        if not any("nomic-embed-text" in m for m in models):
            print("  ✗ nomic-embed-text not found. Run: ollama pull nomic-embed-text")
            exit(1)
    except Exception as e:
        print(f"  ✗ Ollama not running. Start with: ollama serve\n  Error: {e}")
        exit(1)

    print("\n[1/3] Downloading TM Forum data...")
    url_map = download_data()

    chunks = build_index(url_map)

    print("\n[3/3] Done!")
    print(f"  ChromaDB at: {CHROMA_PATH}")
    print(f"  Total chunks: {chunks}")
    print("\n  Run the API: uvicorn main:app --reload --port 8000")
