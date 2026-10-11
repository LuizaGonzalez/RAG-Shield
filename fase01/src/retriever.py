"""Recuperación de chunks desde ChromaDB.

Fase 1: sin ninguna lógica de seguridad — trae los k chunks más
parecidos tal cual están en la base, incluyendo metadata para que
en fases posteriores se pueda medir tasa de recuperación de
documentos envenenados.
"""

import chromadb
from src.ingest import get_embedder, COLLECTION_NAME, CHROMA_PATH


def retrieve(query: str, k: int = 3, collection_name: str = COLLECTION_NAME):
    embedder = get_embedder()
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(collection_name)

    query_embedding = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=k)

    chunks = results["documents"][0]
    metadatas = results["metadatas"][0]

    return [
        {"text": chunk, "metadata": meta}
        for chunk, meta in zip(chunks, metadatas)
    ]


if __name__ == "__main__":
    resultados = retrieve("¿cuál es la política de mora?")
    for r in resultados:
        print(f"- [{r['metadata']['source_file']}] {r['text'][:100]}...")
