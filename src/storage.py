"""Archivos que crea la app: documentos subidos, propuestas, adjuntos,
sesiones de los empleados y auditoría.

- Laboratorio sube a docs/subidos/. Ese documento entra a la base, pero
  la Capa 1 lo revisa al ingerirlo y puede dejarlo en cuarentena.
- Un empleado propone a docs/propuestas/. Siempre entra en cuarentena
  hasta que Laboratorio lo apruebe (y aun aprobado, si la Capa 1 encuentra
  algo, sigue en cuarentena).
- Laboratorio importa correos por IMAP a docs/correos/. Pasan por la
  misma Capa 1 al ingerirse; un correo ya importado no se repite.
- Los adjuntos de sesión nunca se escriben en disco ni en el índice.
- Sesiones y auditoría van a data/ (no se sube a git). La auditoría guarda
  quién preguntó, qué fuentes se usaron y qué capa actuó, no la respuesta.

Nada de esto toca docs/legitimos ni docs/envenenados: el experimento no
se puede alterar desde la app.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from src import mail
from src.config import DEPARTMENTS, DEPARTMENTS_FILE, MAX_UPLOAD_BYTES, data_dir, docs_dir
from src.ingest import SUPPORTED_EXTENSIONS, chunk_text, ingest_file, remove_source
from src.sanitizer import sanitize_text

FOLDERS = {"subido": "subidos", "propuesta": "propuestas", "correo": "correos"}
_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")


class UploadError(ValueError):
    pass


def safe_name(name: str) -> str:
    path = Path((name or "").replace("\\", "/").rsplit("/", 1)[-1])
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UploadError(f"Formato no permitido. Usa {', '.join(sorted(SUPPORTED_EXTENSIONS))}.")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem).strip("_")[:80]
    if not stem:
        raise UploadError("El nombre del archivo no es válido.")
    return f"{stem}{suffix}"


def decode(data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"El archivo supera {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("El archivo debe estar en UTF-8.") from exc
    if not text.strip():
        raise UploadError("El archivo está vacío.")
    return text


def _unique(folder: Path, name: str) -> Path:
    candidate, n = folder / name, 2
    while candidate.exists():
        candidate = folder / f"{Path(name).stem}_{n}{Path(name).suffix}"
        n += 1
    return candidate


def _update_map(folder: Path, key: str, departments: list[str] | None) -> None:
    path = folder / DEPARTMENTS_FILE
    mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if departments is None:
        mapping.pop(key, None)
    else:
        mapping[key] = departments
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def _departments_of(folder: Path, key: str) -> list[str]:
    path = folder / DEPARTMENTS_FILE
    return json.loads(path.read_text(encoding="utf-8")).get(key, []) if path.exists() else []


def save_document(name: str, data: bytes, departments: list[str], kind: str) -> dict:
    """Guarda un documento subido o propuesto y lo indexa. Devuelve su metadata."""
    if kind not in FOLDERS:
        raise ValueError(f"kind debe ser {' o '.join(FOLDERS)}")
    departments = [d for d in departments if d in DEPARTMENTS]
    text = decode(data)
    root = docs_dir()
    folder = root / FOLDERS[kind]
    folder.mkdir(parents=True, exist_ok=True)
    path = _unique(folder, safe_name(name))
    path.write_text(text, encoding="utf-8")
    _update_map(folder, f"{folder.name}/{path.name}", departments)
    try:
        return ingest_file(path, root)
    except Exception:
        path.unlink(missing_ok=True)
        _update_map(folder, f"{folder.name}/{path.name}", None)
        raise


def import_emails(departments: list[str], limit: int = 20) -> dict:
    """Trae correos por IMAP a docs/correos/ y los indexa. Un correo ya importado no se repite."""
    departments = [d for d in departments if d in DEPARTMENTS]
    root = docs_dir()
    folder = root / FOLDERS["correo"]
    folder.mkdir(parents=True, exist_ok=True)
    summary = {"leidos": 0, "importados": 0, "repetidos": 0, "cuarentena": 0, "rechazados": 0}
    for document in mail.fetch(limit):
        summary["leidos"] += 1
        digest = hashlib.sha256(document.message_id.encode("utf-8")).hexdigest()[:12]
        path = folder / f"correo_{document.date}_{digest}{document.extension}"
        if path.exists():
            summary["repetidos"] += 1
            continue
        if len(document.content.encode("utf-8")) > MAX_UPLOAD_BYTES:
            summary["rechazados"] += 1
            continue
        path.write_text(document.content, encoding="utf-8")
        _update_map(folder, f"{folder.name}/{path.name}", departments)
        try:
            meta = ingest_file(path, root)
        except ValueError:
            path.unlink(missing_ok=True)
            _update_map(folder, f"{folder.name}/{path.name}", None)
            summary["rechazados"] += 1
            continue
        summary["importados"] += 1
        summary["cuarentena"] += meta["estado"] == "cuarentena"
    return summary


def _app_file(source_file: str) -> tuple[Path, Path]:
    """Resuelve docs/subidos/x o docs/propuestas/x. Rechaza cualquier otra ruta."""
    parts = source_file.split("/")
    if len(parts) != 3 or parts[0] != "docs" or parts[1] not in FOLDERS.values() or safe_name(parts[2]) != parts[2]:
        raise PermissionError("Solo se pueden modificar documentos subidos o propuestos desde la app.")
    folder = docs_dir() / parts[1]
    return folder, folder / parts[2]


def approve_proposal(source_file: str) -> dict:
    folder, path = _app_file(source_file)
    if folder.name != "propuestas" or not path.exists():
        raise UploadError("La propuesta ya no existe.")
    departments = _departments_of(folder, f"propuestas/{path.name}")
    target_folder = docs_dir() / "subidos"
    target_folder.mkdir(parents=True, exist_ok=True)
    target = _unique(target_folder, path.name)
    path.replace(target)
    _update_map(folder, f"propuestas/{path.name}", None)
    _update_map(target_folder, f"subidos/{target.name}", departments)
    remove_source(source_file)
    return ingest_file(target, docs_dir())


def discard_document(source_file: str) -> None:
    folder, path = _app_file(source_file)
    path.unlink(missing_ok=True)
    _update_map(folder, f"{folder.name}/{path.name}", None)
    remove_source(source_file)


def attachment(name: str, data: bytes) -> dict:
    """Adjunto de sesión: se trocea en memoria, nunca entra a la base compartida."""
    name = safe_name(name)
    text = decode(data)
    pieces = chunk_text(text) or [text.strip()]
    metadata = {
        "file_name": name, "source_file": f"adjunto/{name}", "is_poisoned": False, "origen": "adjunto",
        "confianza": "baja", "canal": "archivo", "tecnica": "ninguna", "estado": "sesion",
    }
    chunks = [{"text": p, "metadata": dict(metadata, chunk_index=i), "distance": 0.0} for i, p in enumerate(pieces)]
    return {"name": name, "size": len(data), "reglas": sanitize_text(text).reglas, "chunks": chunks, "data": data}


def _sessions_path(usuario: str) -> Path:
    if not _USERNAME.match(usuario):
        raise ValueError("Usuario inválido")
    return data_dir() / "sesiones" / f"{usuario}.json"


def list_sessions(usuario: str) -> list[dict]:
    path = _sessions_path(usuario)
    if not path.exists():
        return []
    sessions = json.loads(path.read_text(encoding="utf-8")).get("sesiones", [])
    return sorted(sessions, key=lambda s: s.get("actualizada", s["creada"]), reverse=True)


def new_session() -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    return {"id": uuid.uuid4().hex[:12], "titulo": "Nueva sesión", "creada": now, "actualizada": now, "mensajes": []}


def save_session(usuario: str, session: dict) -> None:
    path = _sessions_path(usuario)
    path.parent.mkdir(parents=True, exist_ok=True)
    sessions = [s for s in list_sessions(usuario) if s["id"] != session["id"]]
    session["actualizada"] = datetime.now().isoformat(timespec="seconds")
    sessions.append(session)
    path.write_text(json.dumps({"sesiones": sessions}, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(user, accion: str, **fields) -> None:
    entry = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "usuario": user.usuario,
        "rol": user.rol,
        "departamento": user.departamento,
        "accion": accion,
        **fields,
    }
    path = data_dir() / "auditoria.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit(limit: int = 500) -> list[dict]:
    path = data_dir() / "auditoria.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]
