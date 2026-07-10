"""
Knowledge Engine V2 ingestion rebuild (Phase 7B) — builds collection `axiom_v2`.
════════════════════════════════════════════════════════════════════════════════
Corrects the four ingestion defects the Phase 7A audit found, WITHOUT touching axiom_v1
(preserved for rollback) or the CTK/ODA assets:
  • CORPUS HYGIENE   — MEF/Mplify + postman test collections are EXCLUDED from the
                       canonical corpus; every chunk is tagged content_class.
  • VERSION METADATA — spec_version + spec_major promoted onto every canonical chunk
                       (from parsed OpenAPI info.version, filename fallback).
  • STRUCTURE-AWARE  — parsed OpenAPI text is split on its own `##` operation/schema
    CHUNKING          boundaries, not a blind 800-char window; a schema heading stays
                       with its required-fields; section_type/section_name recorded.
  • DEDUPLICATION    — one canonical unit per (spec_id, version); mirror copies dropped.

Reuses ingest.parse_openapi_spec / parse_markdown / embed_batch. Run:
    venv/bin/python ingest_v2.py
"""
from __future__ import annotations
import glob
import hashlib
import os
import re
import sys

import chromadb
import ingest
import knowledge_link as L

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
COLLECTION_V2 = os.environ.get("VECTOR_COLLECTION_V2", "axiom_v2")
MAX_UNIT = 1800          # structural units up to this size stay intact; larger split w/ heading
EMBED_BATCH = 64

_METHOD = re.compile(r"^(GET|POST|PATCH|PUT|DELETE|HEAD|OPTIONS)\b", re.I)


def structure_chunks(text: str):
    """Split rendered-OpenAPI text on its own `## ` headings into (section_type,
    section_name, body) units; oversized units are split internally with the heading
    repeated so identity is never severed from content."""
    if not text.strip():
        return []
    parts = re.split(r"\n(?=## )", text)
    units = []
    overview = parts[0].strip()
    if overview:
        units.append(("OVERVIEW", "overview", overview))
    for sec in parts[1:]:
        head = sec.splitlines()[0].lstrip("# ").strip()
        if "schema:" in head.lower():
            stype, sname = "SCHEMA", head.split(":", 1)[-1].strip()
        elif _METHOD.match(head):
            stype, sname = "OPERATION", head
        else:
            stype, sname = "SECTION", head
        units.append((stype, sname, sec.strip()))
    out = []
    for stype, sname, body in units:
        if len(body) <= MAX_UNIT:
            out.append((stype, sname, body))
            continue
        head = body.splitlines()[0]
        step = MAX_UNIT - 150
        for i in range(0, len(body), step):
            piece = body[i:i + MAX_UNIT]
            if i > 0:
                piece = f"{head}\n(cont.)\n{piece}"
            out.append((stype, sname, piece))
    return out


def build_v2():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_V2)   # rebuild is idempotent; axiom_v1 untouched
    except Exception:
        pass
    col = client.create_collection(COLLECTION_V2, metadata={"hnsw:space": "cosine"})

    files = []
    for ext in ("*.json", "*.yaml", "*.yml", "*.md"):
        files += glob.glob(os.path.join(DATA, "**", ext), recursive=True)
    files.sort()

    seen_text: set = set()
    seen_canon: set = set()      # (spec_id, version) — mirror-dup guard
    stats = {"files": 0, "skipped_class": 0, "skipped_dup": 0, "chunks": 0,
             "by_class": {}, "versioned": 0}
    pend_ids, pend_docs, pend_metas = [], [], []

    def flush():
        if not pend_ids:
            return
        embs = ingest.embed_batch(pend_docs)
        ids2, docs2, metas2, embs2 = [], [], [], []
        for i, e in enumerate(embs):
            if e is not None:
                ids2.append(pend_ids[i]); docs2.append(pend_docs[i])
                metas2.append(pend_metas[i]); embs2.append(e)
        if ids2:
            col.upsert(ids=ids2, documents=docs2, metadatas=metas2, embeddings=embs2)
            stats["chunks"] += len(ids2)
        pend_ids.clear(); pend_docs.clear(); pend_metas.clear()

    for path in files:
        fname = os.path.basename(path)
        parts = path.split(os.sep)
        if any(p in parts for p in (".git", "node_modules", "__pycache__")):
            continue
        if "test" in fname.lower() and not fname.lower().endswith(".md"):
            continue
        if fname.lower().endswith(".md") and ingest.is_junk_markdown(fname):
            continue

        cclass = L.content_class(fname)
        # EXCLUDE non-TMF external (MEF/Mplify) + postman test collections from the corpus.
        if cclass in ("non_tmf_external", "test_collection"):
            stats["skipped_class"] += 1
            continue

        if fname.lower().endswith((".json", ".yaml", ".yml")):
            parsed = ingest.parse_openapi_spec(__import__("pathlib").Path(path))
        else:
            parsed = ingest.parse_markdown(__import__("pathlib").Path(path))
        if not parsed or not parsed.get("text", "").strip():
            continue

        text = parsed["text"]
        thash = hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()
        if thash in seen_text:
            stats["skipped_dup"] += 1
            continue
        seen_text.add(thash)

        spec_id = ingest.extract_spec_id(fname)
        version = str(parsed.get("version") or "") or (L.major_of(fname) and "")
        major = (re.search(r"(\d+)", version).group(1) if version else L.major_of(fname)) or ""

        # Mirror-dup guard: one canonical unit per (spec_id, version).
        if cclass == "canonical_spec" and spec_id:
            key = (spec_id, version or major)
            if key in seen_canon:
                stats["skipped_dup"] += 1
                continue
            seen_canon.add(key)

        source_name = f"{parsed.get('title','')} {version}".strip()
        if cclass == "canonical_spec":
            units = structure_chunks(text)
        else:
            units = [("DOC", fname, c) for c in ingest.chunk_text(text)]

        for ci, (stype, sname, body) in enumerate(units):
            if len(body) < 60:
                continue
            pend_ids.append(ingest.doc_id(path, ci))
            pend_docs.append(body)
            meta = {
                "source": source_name, "file": fname, "chunk": ci,
                "spec_id": spec_id, "spec_version": version, "spec_major": major,
                "content_class": cclass, "section_type": stype, "section_name": sname[:120],
                "source_url": "",
            }
            pend_metas.append(meta)
            if major:
                stats["versioned"] += 1
            stats["by_class"][cclass] = stats["by_class"].get(cclass, 0) + 1
            if len(pend_ids) >= EMBED_BATCH:
                flush()
        stats["files"] += 1
        if stats["files"] % 200 == 0:
            print(f"  ... {stats['files']} files, {stats['chunks']} chunks", flush=True)
    flush()

    total = col.count()
    print("\n== axiom_v2 build complete ==")
    print(f"  files indexed:     {stats['files']}")
    print(f"  skipped (class):   {stats['skipped_class']}  (MEF/Mplify + postman excluded)")
    print(f"  skipped (dup):     {stats['skipped_dup']}")
    print(f"  chunks:            {total}")
    print(f"  versioned chunks:  {stats['versioned']}")
    print(f"  by content_class:  {stats['by_class']}")
    return total


if __name__ == "__main__":
    build_v2()
