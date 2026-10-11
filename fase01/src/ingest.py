"""Ingesta de documentos hacia ChromaDB.

Fase 1: RAG pelado, sin capas de seguridad.
Trocea cada archivo .txt de docs/legitimos/, calcula embeddings con
un modelo local (no depende de API paga) y los guarda en ChromaDB.
"""

import os
import chromadb
from sentence_transformers import SentenceTransformer

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
COLLECTION_NAME = "novacred_docs"
CHROMA_PATH = "./chroma_db"

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def ingest_documents(docs_path: str = "docs/legitimos", collection_name: str = COLLECTION_NAME):
    embedder = get_embedder()
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name)

    total_chunks = 0
    for filename in sorted(os.listdir(docs_path)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(docs_path, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)
        if not chunks:
            continue

        embeddings = embedder.encode(chunks).tolist()
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_file": filename,
                "is_poisoned": False,
                "canal": "archivo",
            }
            for _ in chunks
        ]

        collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas,
        )
        total_chunks += len(chunks)
        print(f"  {filename}: {len(chunks)} chunks")

    print(f"\nListo. {total_chunks} chunks indexados en '{collection_name}'.")
    return collection


if __name__ == "__main__":
    print("Ingestando documentos...")
    ingest_documents()
