"""Ingesta de documentos hacia ChromaDB.

Responsable: Persona B
Recorre docs/legitimos y docs/envenenados, trocea cada documento,
calcula embeddings y los guarda en la coleccion de ChromaDB.
Cada chunk debe conservar en metadata:
  - is_poisoned: bool
  - canal: "archivo" | "correo" | "web"
  - source_file: str
"""

from __future__ import annotations

import re
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()


def _chunk_text(text: str, max_chars: int = 800) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", normalized) if p.strip()]
    chunks: list[str] = []

    for paragraph in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = sentence
        if current.strip():
            chunks.append(current.strip())

    if not chunks:
        return [normalized[:max_chars]]

    return [c for c in chunks if len(c.strip()) >= 40]


def ingest_documents(docs_path: str, collection_name: str = "novacred_docs"):
    root = Path(docs_path)
    if not root.exists():
        raise FileNotFoundError(f"No existe la ruta de documentos: {docs_path}")

    persist_dir = (Path(__file__).resolve().parents[1] / "chroma_db").resolve()
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection(name=collection_name)

    existing_ids = collection.get(include=[])['ids']
    if existing_ids:
        collection.delete(ids=existing_ids)

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for file_path in sorted(root.rglob("*.txt")):
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        is_poisoned = "envenenados" in file_path.parts
        channel = "archivo"
        relative_path = file_path.relative_to(root.parent)

        for chunk_index, chunk in enumerate(_chunk_text(content)):
            chunk_id = f"{relative_path.as_posix()}::{chunk_index}"
            documents.append(chunk)
            metadatas.append(
                {
                    "is_poisoned": is_poisoned,
                    "canal": channel,
                    "source_file": relative_path.as_posix(),
                }
            )
            ids.append(chunk_id)

    if not documents:
        raise ValueError(f"No se encontraron documentos .txt en {docs_path}")

    embeddings = model.encode(documents, convert_to_numpy=True, normalize_embeddings=True).tolist()
    collection.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
    return {"collection": collection_name, "count": len(documents)}


if __name__ == "__main__":
    result = ingest_documents("docs/")
    print(f"ingesta OK, {result['count']} chunks indexados")
