"""Recuperación de chunks desde ChromaDB.

Devuelve los k chunks más parecidos con su metadata intacta
(is_poisoned, canal, tecnica, source_file), para que la evaluación
pueda medir si el documento envenenado llegó al prompt.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from src.config import COLLECTION_NAME, chroma_dir, default_k
from src.embeddings import embed


class IndexNotReadyError(RuntimeError):
    pass


def get_collection(collection_name: str = COLLECTION_NAME, persist_dir: str | Path | None = None):
    client = chromadb.PersistentClient(path=str(persist_dir or chroma_dir()))
    try:
        collection = client.get_collection(name=collection_name, embedding_function=None)
    except Exception as exc:
        raise IndexNotReadyError(
            f"No existe la colección '{collection_name}'. Corre primero: python -m src.ingest"
        ) from exc
    if collection.count() == 0:
        raise IndexNotReadyError(f"La colección '{collection_name}' está vacía. Corre: python -m src.ingest")
    return collection


def indexed_sources(collection_name: str = COLLECTION_NAME, persist_dir: str | Path | None = None) -> set[str]:
    metadatas = get_collection(collection_name, persist_dir).get(include=["metadatas"])["metadatas"]
    return {m["file_name"] for m in metadatas}


def retrieve(
    query: str,
    k: int | None = None,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
) -> list[dict]:
    collection = get_collection(collection_name, persist_dir)
    results = collection.query(
        query_embeddings=embed([query]),
        n_results=min(k or default_k(), collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"text": text, "metadata": dict(meta or {}), "distance": float(distance)}
        for text, meta, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]


if __name__ == "__main__":
    for chunk in retrieve("¿Cuál es la política de mora?"):
        meta = chunk["metadata"]
        flag = "ENVENENADO" if meta.get("is_poisoned") else "legítimo"
        print(f"- [{meta['source_file']} · {flag} · d={chunk['distance']:.3f}] {chunk['text'][:90]}...")
