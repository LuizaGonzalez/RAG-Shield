"""Ingesta de documentos hacia ChromaDB (puerta 1 del diseño).

Recorre docs/ (.txt, .html y .md), trocea cada documento y guarda los
embeddings con esta metadata por chunk:
  - is_poisoned: bool (verdad de laboratorio, solo para medir)
  - canal: "archivo" | "correo" | "web" (prefijo del nombre del archivo)
  - tecnica: técnica de camuflaje deducida del nombre, o "ninguna"
  - source_file: ruta relativa, p. ej. docs/legitimos/politica_mora.txt
  - file_name: solo el nombre del archivo
  - origen: "base" (legitimos/envenenados), "subido", "propuesta" o "correo" (IMAP)
  - confianza: "alta" | "media" | "baja", según el origen
  - estado: "aprobado" o "cuarentena". La Capa 1 revisa el documento
    completo al ingerirlo; si encuentra algo, queda en cuarentena. Una
    propuesta de un empleado siempre entra en cuarentena.
  - motivo_cuarentena: reglas de la Capa 1 que se activaron
  - dep_<departamento>: bool por cada departamento (docs/departamentos.json)

Los .html se indexan crudos, como lo haría un cargador ingenuo: lo que
esté oculto con estilos o comentarios llega intacto al índice. La
cuarentena no borra nada: el Laboratorio sigue recuperando todo para
medir, y la vista de Empleado filtra por estado y departamento.

La ingesta completa reemplaza la colección. Se corre una vez por
configuración de documentos, nunca durante una evaluación.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import chromadb

from src.config import COLLECTION_NAME, DEPARTMENTS, DEPARTMENTS_FILE, chroma_dir, docs_dir
from src.embeddings import embed
from src.sanitizer import sanitize_text

SUPPORTED_EXTENSIONS = {".txt", ".html", ".md"}
CHANNEL_PREFIXES = ("archivo", "correo", "web")
TECHNIQUES = ("html_oculto", "comentario_html", "unicode_invisible")
ORIGINS = {"subidos": ("subido", "media"), "propuestas": ("propuesta", "baja"), "correos": ("correo", "baja")}
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


def load_department_map(docs_path: Path) -> dict[str, list[str]]:
    """Une todos los departamentos.json bajo docs/. Las claves son rutas relativas a docs/."""
    mapping: dict[str, list[str]] = {}
    for path in sorted(docs_path.rglob(DEPARTMENTS_FILE)):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key.startswith("_"):
                continue
            values = [value] if isinstance(value, str) else list(value)
            mapping[key] = sorted(DEPARTMENTS) if "todos" in values else [d for d in values if d in DEPARTMENTS]
    return mapping


def _metadata(file_path: Path, docs_path: Path, content: str, departments: list[str]) -> dict:
    folder = file_path.relative_to(docs_path).parts[0]
    origen, confianza = ORIGINS.get(folder, ("base", "alta"))
    rules = sanitize_text(content).reglas
    if rules:
        motivo = ";".join(rules)
    else:
        motivo = "propuesta pendiente" if origen == "propuesta" else ""
    metadata = {
        "is_poisoned": "envenenados" in file_path.parts,
        "canal": channel_for(file_path.name),
        "tecnica": technique_for(file_path.name),
        "source_file": file_path.relative_to(docs_path.parent).as_posix(),
        "file_name": file_path.name,
        "origen": origen,
        "confianza": confianza,
        "estado": "cuarentena" if motivo else "aprobado",
        "motivo_cuarentena": motivo,
    }
    metadata.update({f"dep_{d}": d in departments for d in DEPARTMENTS})
    return metadata


def _file_records(file_path: Path, docs_path: Path, departments: dict[str, list[str]]):
    content = file_path.read_text(encoding="utf-8")
    key = file_path.relative_to(docs_path).as_posix()
    metadata = _metadata(file_path, docs_path, content, departments.get(key, []))
    for index, chunk in enumerate(chunk_text(content)):
        yield chunk, dict(metadata, chunk_index=index), f"{metadata['source_file']}::{index}"


def build_records(docs_path: Path) -> tuple[list[str], list[dict], list[str]]:
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    departments = load_department_map(docs_path)

    for file_path in iter_source_files(docs_path):
        for chunk, metadata, chunk_id in _file_records(file_path, docs_path, departments):
            documents.append(chunk)
            metadatas.append(metadata)
            ids.append(chunk_id)

    return documents, metadatas, ids


def _client(persist_dir: str | Path | None):
    return chromadb.PersistentClient(path=str(persist_dir or chroma_dir()))


def ingest_documents(
    docs_path: str | Path | None = None,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
) -> dict:
    root = Path(docs_path or docs_dir())
    if not root.exists():
        raise FileNotFoundError(f"No existe la ruta de documentos: {root}")

    documents, metadatas, ids = build_records(root)
    if not documents:
        raise ValueError(f"No se encontraron documentos .txt, .html o .md en {root}")

    client = _client(persist_dir)
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

    sources = {m["source_file"]: m for m in metadatas}
    return {
        "collection": collection_name,
        "chunks": len(documents),
        "fuentes": len(sources),
        "envenenados": sum(1 for s in sources if "/envenenados/" in s),
        "cuarentena": sum(1 for m in sources.values() if m["estado"] == "cuarentena"),
    }


def remove_source(source_file: str, collection_name: str = COLLECTION_NAME,
                  persist_dir: str | Path | None = None) -> None:
    collection = _client(persist_dir).get_collection(collection_name, embedding_function=None)
    collection.delete(where={"source_file": source_file})


def ingest_file(
    file_path: str | Path,
    docs_path: str | Path | None = None,
    collection_name: str = COLLECTION_NAME,
    persist_dir: str | Path | None = None,
) -> dict:
    """Indexa (o reindexa) un solo archivo sin tocar el resto de la colección."""
    root = Path(docs_path or docs_dir())
    records = list(_file_records(Path(file_path), root, load_department_map(root)))
    if not records:
        raise ValueError(f"{Path(file_path).name} no tiene texto suficiente para indexar.")
    documents, metadatas, ids = (list(x) for x in zip(*records))
    collection = _client(persist_dir).get_collection(collection_name, embedding_function=None)
    collection.delete(where={"source_file": metadatas[0]["source_file"]})
    collection.add(documents=documents, embeddings=embed(documents), metadatas=metadatas, ids=ids)
    return metadatas[0]


if __name__ == "__main__":
    result = ingest_documents()
    print(
        f"Ingesta OK: {result['chunks']} chunks de {result['fuentes']} documentos "
        f"({result['envenenados']} envenenados, {result['cuarentena']} en cuarentena) en '{result['collection']}'."
    )
