"""Capa 1: sanitizacion basada en reglas del contenido recuperado.

Responsable: Persona C
Limpia cada chunk antes de que llegue al prompt:
  - comentarios y tags HTML ocultos (BeautifulSoup)
  - caracteres Unicode invisibles o de ancho cero (unicodedata)
  - frases que imitan instrucciones de sistema (regex)
Debe devolver tambien un flag/log de que fue neutralizado, para
que el front pueda mostrar el aviso de bloqueo.
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def _sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200B-\u200D\uFEFF\u2060]", "", text)
    text = re.sub(r"\s+", " ", text)

    malicious_patterns = [
        r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
        r"(?i)system\s+prompt",
        r"(?i)developer\s+message",
        r"(?i)override\s+(?:all\s+)?(?:system|developer|user)\s+instructions",
        r"(?i)reveal\s+(?:the\s+)?(?:hidden|secret|system)\s+(?:prompt|instructions)",
        r"(?i)disregard\s+the\s+previous\s+instructions",
    ]
    for pattern in malicious_patterns:
        text = re.sub(pattern, "[instrucción neutralizada]", text)

    return text.strip()


def sanitize(chunk):
    if isinstance(chunk, dict):
        sanitized_text = _sanitize_text(chunk.get("text", ""))
        metadata = dict(chunk.get("metadata", {}) or {})
        return {"text": sanitized_text, "metadata": metadata}

    return _sanitize_text(chunk)
