"""Conector IMAP: trae correos de un buzón y los convierte en documentos.

Es la entrada "correo" del diseño. Solo lo usa el rol laboratorio y cada
correo pasa por la misma puerta de ingesta que un documento subido: la
Capa 1 decide si queda aprobado o en cuarentena. El HTML se guarda tal
cual llega (como un cargador ingenuo), así el texto oculto con estilos o
comentarios queda visible para la Capa 1.

La conexión es de solo lectura: el buzón se abre con readonly y los
mensajes se leen con BODY.PEEK[], así que no se marcan como leídos.
Usa TLS con verificación de certificado. Las credenciales salen de .env
y nunca se muestran en la interfaz ni en la auditoría:

  IMAP_HOST=imap.gmail.com
  IMAP_PORT=993
  IMAP_USER=buzon@ejemplo.com
  IMAP_PASSWORD=contraseña de aplicación
  IMAP_FOLDER=INBOX
"""

from __future__ import annotations

import email
import html
import imaplib
import os
import re
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import parsedate_to_datetime

TIMEOUT_SECONDS = 20


class MailConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    user: str
    password: str
    folder: str

    @property
    def public(self) -> str:
        """Lo que se puede mostrar en la interfaz: servidor, buzón enmascarado y carpeta."""
        name, _, domain = self.user.partition("@")
        masked = f"{name[:2]}***@{domain}" if domain else f"{self.user[:2]}***"
        return f"{masked} · {self.host} · {self.folder}"


@dataclass(frozen=True)
class MailDocument:
    message_id: str
    subject: str
    sender: str
    date: str
    content: str
    extension: str


def settings() -> MailSettings | None:
    host = os.environ.get("IMAP_HOST", "").strip()
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASSWORD", "")
    if not (host and user and password):
        return None
    try:
        port = int(os.environ.get("IMAP_PORT", "993"))
    except ValueError as exc:
        raise MailConfigError("IMAP_PORT debe ser un número.") from exc
    return MailSettings(host, port, user, password, os.environ.get("IMAP_FOLDER", "INBOX").strip() or "INBOX")


def _header(msg: EmailMessage, name: str) -> str:
    return re.sub(r"\s+", " ", str(msg.get(name, "") or "")).strip()


def to_document(raw: bytes) -> MailDocument | None:
    msg = email.message_from_bytes(raw, policy=default_policy)
    headers = {label: _header(msg, name) for label, name in
               (("De", "From"), ("Para", "To"), ("Asunto", "Subject"), ("Fecha", "Date"))}
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    if html_part is not None:
        body = html_part.get_content()
        lines = "<br>".join(f"{k}: {html.escape(v)}" for k, v in headers.items() if v)
        content, extension = f"<p>{lines}</p>\n\n{body}", ".html"
    elif text_part is not None:
        body = text_part.get_content()
        lines = "\n".join(f"{k}: {v}" for k, v in headers.items() if v)
        content, extension = f"{lines}\n\n{body}", ".txt"
    else:
        return None
    if not body.strip():
        return None
    try:
        date = parsedate_to_datetime(headers["Fecha"]).strftime("%Y%m%d") if headers["Fecha"] else "sinfecha"
    except (TypeError, ValueError):
        date = "sinfecha"
    message_id = _header(msg, "Message-ID") or f"{headers['De']}|{headers['Fecha']}|{headers['Asunto']}"
    return MailDocument(message_id, headers["Asunto"], headers["De"], date, content, extension)


def fetch(limit: int = 20, config: MailSettings | None = None) -> list[MailDocument]:
    """Los `limit` correos más recientes de la carpeta, sin marcarlos como leídos."""
    config = config or settings()
    if config is None:
        raise MailConfigError("Falta configurar IMAP_HOST, IMAP_USER e IMAP_PASSWORD en .env.")
    limit = max(1, min(int(limit), 100))
    try:
        client = imaplib.IMAP4_SSL(config.host, config.port, ssl_context=ssl.create_default_context(),
                                   timeout=TIMEOUT_SECONDS)
    except (OSError, imaplib.IMAP4.error) as exc:
        raise MailConfigError(f"No se pudo conectar a {config.host}:{config.port}.") from exc
    try:
        try:
            client.login(config.user, config.password)
        except imaplib.IMAP4.error as exc:
            raise MailConfigError("El servidor IMAP rechazó el usuario o la contraseña.") from exc
        status, _ = client.select(f'"{config.folder}"', readonly=True)
        if status != "OK":
            raise MailConfigError(f"No existe la carpeta '{config.folder}'.")
        status, data = client.search(None, "ALL")
        ids = data[0].split()[-limit:] if status == "OK" and data and data[0] else []
        documents = []
        for message_number in reversed(ids):
            status, parts = client.fetch(message_number, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), None)
            if status == "OK" and raw:
                document = to_document(raw)
                if document:
                    documents.append(document)
        return documents
    finally:
        try:
            client.logout()
        except Exception:
            pass
