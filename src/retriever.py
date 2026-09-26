"""Recuperacion de chunks desde ChromaDB.

Responsable: Persona B
Dada una pregunta, devuelve los k chunks mas parecidos, con su metadata
intacta (is_poisoned, canal, source_file) para que eval_harness pueda
medir tasa de recuperacion del documento malicioso.
"""

from __future__ import annotations

from pathlib import Path

import chromadb


def retrieve(query: str, k: int = 3, collection_name: str = "novacred_docs"):
    persist_dir = (Path(__file__).resolve().parents[1] / "chroma_db").resolve()
    client = chromadb.PersistentClient(path=str(persist_dir))

    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    retrieved = []

    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        retrieved.append({"text": document, "metadata": metadata})

    return retrieved
