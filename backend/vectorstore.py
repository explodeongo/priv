"""
Vector store abstraction
════════════════════════
A thin, backend-agnostic layer over the only vector operations SynaptDI actually
needs: count, query, upsert, delete, scan, and (re)create.

ChromaDB is the sole implementation today — it's rock-solid, zero-ops, and the right
call at our scale (~10k vectors on one box; the LLM is the bottleneck, not the DB).
This interface exists so we can swap to Milvus / Qdrant / pgvector in ~a day *if* we
ever hit millions of vectors or need horizontal scale: implement `VectorStore` for the
new backend, add a branch in `_build()`, set `VECTOR_BACKEND`. No call sites change.

Deliberately small. The query filter is limited to "field IN list" (`where_in`) — the
only filter the app uses — so every backend can express it without a query-language
shim.
"""
from __future__ import annotations
import os
import threading
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, TypedDict

# Phase 7C: axiom_v2 (Knowledge Engine V2 — version-tagged, structure-aware, MEF/postman
# excluded) is the DEFAULT product knowledge collection. An explicit VECTOR_COLLECTION
# override is still honoured (e.g. VECTOR_COLLECTION=axiom_v1 for rollback). axiom_v1 is
# preserved on disk and never rebuilt/deleted by this default change.
DEFAULT_COLLECTION = "axiom_v2"
COLLECTION  = os.environ.get("VECTOR_COLLECTION", DEFAULT_COLLECTION)
COLLECTION_IS_EXPLICIT = "VECTOR_COLLECTION" in os.environ
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
BACKEND     = os.environ.get("VECTOR_BACKEND", "chroma").lower()
SPACE       = "cosine"


class Hit(TypedDict):
    id: str
    document: str
    metadata: dict
    distance: float


class Record(TypedDict, total=False):
    id: str
    metadata: dict
    document: str
    embedding: list


class VectorStore(ABC):
    """The contract every backend must satisfy."""

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def query(self, embedding: List[float], n_results: int,
              where_in: Optional[Tuple[str, list]] = None) -> List[Hit]:
        """Nearest neighbours, optionally filtered to metadata[field] ∈ values.
        Returns hits sorted nearest-first (lower distance = closer)."""

    @abstractmethod
    def upsert(self, ids: list, documents: list, metadatas: list, embeddings: list) -> None: ...

    @abstractmethod
    def delete(self, ids: list) -> None: ...

    @abstractmethod
    def scan(self, with_documents: bool = False, with_embeddings: bool = False) -> List[Record]:
        """Every record's id + metadata (and optionally document/embedding). Used for
        spec-map building, the document library, deletes, and rebuild snapshots."""

    @abstractmethod
    def recreate(self) -> None:
        """Drop and recreate an empty collection (used by a full rebuild)."""


# ── ChromaDB implementation ─────────────────────────────────────────────────────
class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        import chromadb
        self._client = chromadb.PersistentClient(path=CHROMA_PATH)
        self._col = None

    def _collection(self):
        if self._col is None:
            # get_or_create so serving never crashes on a missing collection
            # (an empty KB simply returns count()==0 → graceful "no info").
            self._col = self._client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": SPACE})
        return self._col

    def count(self) -> int:
        return self._collection().count()

    def query(self, embedding, n_results, where_in=None):
        where = {where_in[0]: {"$in": list(where_in[1])}} if where_in else None
        res = self._collection().query(
            query_embeddings=[embedding], n_results=max(1, n_results),
            where=where, include=["documents", "metadatas", "distances"],
        )
        docs  = (res.get("documents")  or [[]])[0]
        metas = (res.get("metadatas")  or [[]])[0]
        dists = (res.get("distances")  or [[]])[0]
        ids   = (res.get("ids")        or [[]])[0]
        hits: List[Hit] = []
        for i in range(len(docs)):
            hits.append({
                "id":       ids[i]   if i < len(ids)   else "",
                "document": docs[i],
                "metadata": metas[i] if i < len(metas) else {},
                "distance": float(dists[i]) if i < len(dists) else 0.0,
            })
        return hits

    def upsert(self, ids, documents, metadatas, embeddings):
        if ids:
            self._collection().upsert(ids=ids, documents=documents,
                                      metadatas=metadatas, embeddings=embeddings)

    def delete(self, ids):
        if ids:
            self._collection().delete(ids=ids)

    def scan(self, with_documents=False, with_embeddings=False):
        include = ["metadatas"]
        if with_documents:  include.append("documents")
        if with_embeddings: include.append("embeddings")
        res   = self._collection().get(include=include)
        # NB: Chroma returns embeddings as a numpy array — `x or []` would raise
        # "ambiguous truth value", so check for None explicitly.
        ids   = res.get("ids")
        metas = res.get("metadatas")
        docs  = res.get("documents")
        embs  = res.get("embeddings")
        ids   = list(ids)   if ids   is not None else []
        metas = list(metas) if metas is not None else []
        docs  = list(docs)  if docs  is not None else []
        embs  = list(embs)  if embs  is not None else []
        out: List[Record] = []
        for i in range(len(ids)):
            r: Record = {"id": ids[i], "metadata": metas[i] if i < len(metas) else {}}
            if with_documents:  r["document"]  = docs[i] if i < len(docs) else ""
            if with_embeddings: r["embedding"] = embs[i] if i < len(embs) else None
            out.append(r)
        return out

    def recreate(self):
        try:
            self._client.delete_collection(COLLECTION)
        except Exception:
            pass
        self._col = self._client.create_collection(COLLECTION, metadata={"hnsw:space": SPACE})


# ── Factory / singleton ─────────────────────────────────────────────────────────
_store: Optional[VectorStore] = None
_lock = threading.Lock()


def _build() -> VectorStore:
    if BACKEND in ("chroma", "chromadb"):
        return ChromaVectorStore()
    # Future backends slot in here — same interface, no call-site changes:
    #   if BACKEND == "milvus":   return MilvusVectorStore()
    #   if BACKEND == "qdrant":   return QdrantVectorStore()
    #   if BACKEND == "pgvector": return PgVectorStore()
    raise ValueError(f"Unknown VECTOR_BACKEND '{BACKEND}' (expected: chroma)")


def get_store() -> VectorStore:
    """Process-wide vector store singleton (lazily opened, thread-safe)."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = _build()
    return _store


def reset_store() -> None:
    """Drop the cached store so the next get_store() re-opens it (after a rebuild)."""
    global _store
    with _lock:
        _store = None
