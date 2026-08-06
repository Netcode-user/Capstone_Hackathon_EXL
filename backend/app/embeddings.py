"""
Embedding provider abstraction.

Priority:
  1. sentence-transformers (if installed) — real semantic embeddings.
  2. Deterministic hashing-vectorizer fallback (pure NumPy, no download, no internet).

Both providers expose the same interface: embed(texts: list[str]) -> np.ndarray [N, DIM]
so the rest of the app (vector_store, rag_pipeline) never needs to know which is active.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import List

import numpy as np

from .config import settings

_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


class HashingEmbedder:
    """
    Deterministic, dependency-free embedder.

    Each token is hashed into one of `dim` buckets (a sign is also derived from the hash
    so it behaves like a random-projection / feature-hashing trick, similar in spirit to
    scikit-learn's HashingVectorizer). Vectors are L2-normalized so cosine similarity is
    meaningful. It won't capture deep semantics like a transformer would, but it is fully
    offline, instant, and good enough to demo real RAG retrieval behavior.
    """

    name = "hashing-fallback"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        tokens = _TOKEN_RE.findall(text)
        # add bigrams for a little more context sensitivity
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        return tokens + bigrams

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in self._tokenize(text):
            h = hashlib.sha256(tok.encode("utf-8")).hexdigest()
            idx = int(h[:8], 16) % self.dim
            sign = 1.0 if int(h[8:9], 16) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed(self, texts: List[str]) -> np.ndarray:
        return np.stack([self._embed_one(t) for t in texts]).astype(np.float32)


class SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers, used only if the package
    and its model weights are available in the environment."""

    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


@lru_cache(maxsize=1)
def get_embedder():
    """Return the best available embedder, cached as a singleton."""
    try:
        embedder = SentenceTransformerEmbedder()
        print(f"[embeddings] using {embedder.name} (dim={embedder.dim})")
        return embedder
    except Exception as exc:  # noqa: BLE001 - broad on purpose, this is a graceful fallback
        print(f"[embeddings] sentence-transformers unavailable ({exc.__class__.__name__}: {exc}); "
              f"falling back to {HashingEmbedder.name}")
        return HashingEmbedder(dim=settings.EMBEDDING_DIM)


def embed_texts(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, settings.EMBEDDING_DIM), dtype=np.float32)
    return get_embedder().embed(texts)


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]
