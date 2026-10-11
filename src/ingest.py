"""Ingesta de documentos hacia ChromaDB.

Recorre docs/legitimos y docs/envenenados (.txt y .html), trocea cada
documento y guarda los embeddings con esta metadata por chunk:
  - is_poisoned: bool
  - canal: "archivo" | "correo" | "web" (prefijo del nombre del archivo)
  - tecnica: técnica de camuflaje deducida del nombre, o "ninguna"
  - source_file: ruta relativa, p. ej. docs/legitimos/politica_mora.txt
  - file_name: solo el nombre del archivo

Los .html se indexan crudos, como lo haría un cargador ingenuo: lo que
esté oculto con estilos o comentarios llega intacto al índice.

La ingesta reemplaza la colección completa. Se corre una vez por
configuración de documentos, nunca durante una evaluación.
"""

from __future__ import annotations

import re
from pathlib import Path

import chromadb

from src.config import COLLECTION_NAME, DOCS_DIR, chroma_dir
from src.embeddings import embed

SUPPORTED_EXTENSIONS = {".txt", ".html"}
CHANNEL_PREFIXES = ("archivo", "correo", "web")
TECHNIQUES = ("html_oculto", "comentario_html", "unicode_invisible")
MIN_CHUNK_CHARS = 40


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", normalized) if p.strip()]
    chunks: list[str] = []
    header = ""
    for paragraph in paragraphs:
        is_heading = all(len(line.split()) <= 8 for line in paragraph.splitlines())
        if len(paragraph) < 120 and is_heading and not paragraph.startswith("<"):
            header = f"{header}\n{paragraph}".strip()
            continue
        current, header = header, ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    if header:
        chunks.append(header)

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def channel_for(file_name: str) -> str:
    prefix = file_name.split("_", 1)[0].lower()
    return prefix if prefix in CHANNEL_PREFIXES else "archivo"


def technique_for(file_name: str) -> str:
    lowered = file_name.lower()
    return next((t for t in TECHNIQUES if t in lowered), "ninguna")


def iter_source_files(docs_path: Path) -> list[Path]:
    return sorted(
        p for p in docs_path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def build_records(docs_path: Path) -> tuple[list[str], list[dict], list[str]]:
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for file_path in iter_source_files(docs_path):
        content = file_path.read_text(encoding="utf-8")
        relative = file_path.relative_to(docs_path.parent).as_posix()
        metadata = {
            "is_poisoned": "envenenados" in file_path.parts,
            "canal": channel_for(file_path.name),
            "tecnica": technique_for(file_path.name),
            "source_file": relative,
            "file_name": file_path.name,
        }
        for index, chunk in enumerate(chunk_text(content)):
            documents.append(chunk)
            metadatas.append(dict(metadata, chunk_index=index))
            ids.append(f"{relative}::{index}")

    return documents, metadatas, ids


def ingest_documents(
    docs_path: str | Path = DOCS_DIR,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
) -> dict:
    root = Path(docs_path)
    if not root.exists():
        raise FileNotFoundError(f"No existe la ruta de documentos: {root}")

    documents, metadatas, ids = build_records(root)
    if not documents:
        raise ValueError(f"No se encontraron documentos .txt o .html en {root}")

    client = chromadb.PersistentClient(path=str(persist_dir or chroma_dir()))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )
    collection.add(documents=documents, embeddings=embed(documents), metadatas=metadatas, ids=ids)

    sources = sorted({m["source_file"] for m in metadatas})
    return {
        "collection": collection_name,
        "chunks": len(documents),
        "fuentes": len(sources),
        "envenenados": sum(1 for s in sources if "/envenenados/" in s),
    }


if __name__ == "__main__":
    result = ingest_documents()
    print(
        f"Ingesta OK: {result['chunks']} chunks de {result['fuentes']} documentos "
        f"({result['envenenados']} envenenados) en '{result['collection']}'."
    )
