"""Recuperación de chunks desde ChromaDB.

Devuelve los k chunks más parecidos con su metadata intacta
(is_poisoned, canal, tecnica, source_file), para que la evaluación
pueda medir si el documento envenenado llegó al prompt.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from src.config import COLLECTION_NAME, DEPARTMENTS, chroma_dir, default_k
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


def employee_filter(department: str) -> dict:
    """Lo único que puede recuperar un empleado: documentos aprobados de su departamento."""
    if department not in DEPARTMENTS:
        raise ValueError(f"Departamento desconocido: {department}")
    return {"$and": [{"estado": "aprobado"}, {f"dep_{department}": True}]}


def indexed_documents(
    where: dict | None = None,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
) -> list[dict]:
    """Un registro por documento indexado (no por chunk), con su número de chunks."""
    metadatas = get_collection(collection_name, persist_dir).get(where=where, include=["metadatas"])["metadatas"]
    documents: dict[str, dict] = {}
    for meta in metadatas:
        entry = documents.setdefault(meta["source_file"], {**meta, "chunks": 0})
        entry["chunks"] += 1
    for entry in documents.values():
        entry.pop("chunk_index", None)
        entry["departamentos"] = [d for d in DEPARTMENTS if entry.get(f"dep_{d}")]
    return sorted(documents.values(), key=lambda d: d["source_file"])


def rank_chunks(query: str, chunks: list[dict], k: int) -> list[dict]:
    """Ordena chunks que no están en el índice (adjuntos de sesión) por similitud con la pregunta."""
    if len(chunks) <= k:
        return list(chunks)
    vectors = embed([query] + [c["text"] for c in chunks])
    scores = [sum(a * b for a, b in zip(vectors[0], v)) for v in vectors[1:]]
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:k]
    return [chunks[i] for i in sorted(order)]


def retrieve(
    query: str,
    k: int | None = None,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
    where: dict | None = None,
) -> list[dict]:
    collection = get_collection(collection_name, persist_dir)
    available = collection.count() if where is None else len(collection.get(where=where, include=[])["ids"])
    if available == 0:
        return []
    results = collection.query(
        query_embeddings=embed([query]),
        n_results=min(k or default_k(), available),
        where=where,
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
