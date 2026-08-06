"""
Vector store abstraction.

Priority:
  1. FAISS (if installed) — fast approximate/exact NN search.
  2. Pure NumPy brute-force cosine similarity — plenty fast at hackathon scale
     (hundreds to low-thousands of SOP chunks) and needs zero extra dependencies.

Both backends persist to disk under settings.VECTOR_STORE_DIR so the store survives
restarts, and both expose the same interface used by rag_pipeline.py:

    store.add(ids, vectors, metadatas)
    store.search(query_vector, top_k) -> list[(id, score, metadata)]
    store.delete(ids)
    store.count()
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .config import settings


class _BaseStore:
    def add(self, ids: Sequence[str], vectors: np.ndarray, metadatas: Sequence[dict]) -> None:
        raise NotImplementedError

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[str, float, dict]]:
        raise NotImplementedError

    def delete(self, ids: Sequence[str]) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


class NumpyVectorStore(_BaseStore):
    """Brute-force cosine similarity store, persisted as .npy + metadata.json."""

    backend_name = "numpy-brute-force"

    def __init__(self, collection: str, dim: int):
        self.collection = collection
        self.dim = dim
        self.dir = Path(settings.VECTOR_STORE_DIR) / collection
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.dir / "vectors.npy"
        self.meta_path = self.dir / "meta.json"
        self._lock = threading.Lock()

        self.ids: List[str] = []
        self.vectors: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self.metadatas: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.meta_path.exists() and self.vectors_path.exists():
            with open(self.meta_path, "r") as f:
                payload = json.load(f)
            self.ids = payload["ids"]
            self.metadatas = payload["metadatas"]
            self.vectors = np.load(self.vectors_path)

    def _persist(self):
        np.save(self.vectors_path, self.vectors)
        with open(self.meta_path, "w") as f:
            json.dump({"ids": self.ids, "metadatas": self.metadatas}, f)

    def add(self, ids: Sequence[str], vectors: np.ndarray, metadatas: Sequence[dict]) -> None:
        with self._lock:
            for _id, meta in zip(ids, metadatas):
                self.metadatas[_id] = meta
            self.ids.extend(ids)
            self.vectors = (
                vectors.astype(np.float32)
                if self.vectors.shape[0] == 0
                else np.vstack([self.vectors, vectors.astype(np.float32)])
            )
            self._persist()

    def delete(self, ids: Sequence[str]) -> None:
        with self._lock:
            keep_idx = [i for i, _id in enumerate(self.ids) if _id not in set(ids)]
            self.ids = [self.ids[i] for i in keep_idx]
            self.vectors = self.vectors[keep_idx] if keep_idx else np.zeros((0, self.dim), dtype=np.float32)
            for _id in ids:
                self.metadatas.pop(_id, None)
            self._persist()

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[str, float, dict]]:
        with self._lock:
            if self.vectors.shape[0] == 0:
                return []
            q = query_vector.astype(np.float32)
            q_norm = np.linalg.norm(q) or 1.0
            v_norms = np.linalg.norm(self.vectors, axis=1)
            v_norms[v_norms == 0] = 1.0
            sims = (self.vectors @ q) / (v_norms * q_norm)
            top_k = min(top_k, len(self.ids))
            top_idx = np.argsort(-sims)[:top_k]
            return [(self.ids[i], float(sims[i]), self.metadatas[self.ids[i]]) for i in top_idx]

    def count(self) -> int:
        return len(self.ids)


class FaissVectorStore(_BaseStore):
    """FAISS-backed store (flat, inner-product on normalized vectors == cosine)."""

    backend_name = "faiss"

    def __init__(self, collection: str, dim: int):
        import faiss  # type: ignore

        self.faiss = faiss
        self.collection = collection
        self.dim = dim
        self.dir = Path(settings.VECTOR_STORE_DIR) / collection
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.faiss"
        self.meta_path = self.dir / "meta.json"
        self._lock = threading.Lock()

        self.ids: List[str] = []
        self.metadatas: Dict[str, dict] = {}
        if self.index_path.exists() and self.meta_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.meta_path) as f:
                payload = json.load(f)
            self.ids = payload["ids"]
            self.metadatas = payload["metadatas"]
        else:
            self.index = faiss.IndexFlatIP(dim)

    def _persist(self):
        self.faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "w") as f:
            json.dump({"ids": self.ids, "metadatas": self.metadatas}, f)

    def add(self, ids: Sequence[str], vectors: np.ndarray, metadatas: Sequence[dict]) -> None:
        with self._lock:
            self.index.add(vectors.astype(np.float32))
            self.ids.extend(ids)
            for _id, meta in zip(ids, metadatas):
                self.metadatas[_id] = meta
            self._persist()

    def delete(self, ids: Sequence[str]) -> None:
        # Flat index has no cheap delete; rebuild (fine at hackathon scale).
        with self._lock:
            keep = [(i, _id) for i, _id in enumerate(self.ids) if _id not in set(ids)]
            if not keep:
                self.index = self.faiss.IndexFlatIP(self.dim)
                self.ids = []
            else:
                keep_idx = [i for i, _ in keep]
                vecs = self.index.reconstruct_n(0, self.index.ntotal)[keep_idx]
                self.index = self.faiss.IndexFlatIP(self.dim)
                self.index.add(vecs.astype(np.float32))
                self.ids = [_id for _, _id in keep]
            for _id in ids:
                self.metadatas.pop(_id, None)
            self._persist()

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[str, float, dict]]:
        with self._lock:
            if self.index.ntotal == 0:
                return []
            top_k = min(top_k, self.index.ntotal)
            scores, idxs = self.index.search(query_vector.reshape(1, -1).astype(np.float32), top_k)
            out = []
            for score, idx in zip(scores[0], idxs[0]):
                if idx == -1:
                    continue
                _id = self.ids[idx]
                out.append((_id, float(score), self.metadatas[_id]))
            return out

    def count(self) -> int:
        return self.index.ntotal


_stores: Dict[str, _BaseStore] = {}
_stores_lock = threading.Lock()


def get_vector_store(collection: str = "sops", dim: int = None) -> _BaseStore:
    dim = dim or settings.EMBEDDING_DIM
    with _stores_lock:
        if collection in _stores:
            return _stores[collection]
        try:
            store = FaissVectorStore(collection, dim)
            print(f"[vector_store] collection={collection} using backend={store.backend_name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[vector_store] faiss unavailable ({exc.__class__.__name__}: {exc}); "
                  f"falling back to {NumpyVectorStore.backend_name}")
            store = NumpyVectorStore(collection, dim)
        _stores[collection] = store
        return store
