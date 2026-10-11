"""Embeddings compartidos entre ingesta y consulta.

Ingesta y recuperación deben usar exactamente el mismo modelo; si no,
las distancias de Chroma no significan nada. `RAG_EMBEDDINGS=hash`
activa un embedding léxico determinista, solo para pruebas sin red.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from functools import lru_cache

from src.config import EMBEDDING_MODEL

HASH_DIM = 384


def _hash_embed(text: str) -> list[float]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    vector = [0.0] * HASH_DIM
    for token in re.findall(r"[a-z0-9]{3,}", normalized):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "little") % HASH_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def backend() -> str:
    return os.environ.get("RAG_EMBEDDINGS", "minilm").lower()


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if backend() == "hash":
        return [_hash_embed(t) for t in texts]
    vectors = _model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.tolist()
