"""Capa 1: sanitización basada en reglas del contenido recuperado.

Limpia cada chunk antes de que llegue al prompt y registra qué regla se
activó, para que la app pueda avisar y la evaluación pueda contar
falsos positivos:
  - html_oculto: elementos con texto blanco, display:none, font-size:0...
  - comentario_html: comentarios <!-- ... -->
  - unicode_invisible: caracteres de ancho cero y tramos delimitados por ellos
  - frase_instruccion:<tipo>: oraciones que le hablan al modelo (ES y EN)

Es una lista de reglas anticipadas por el equipo, no un clasificador
general: un ataque redactado con otras palabras puede pasar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment

NEUTRALIZED = "[instrucción neutralizada]"

INVISIBLE_CLASS = "\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\U000e0000-\U000e007f"
_INVISIBLE = re.compile(f"[{INVISIBLE_CLASS}]")
_INVISIBLE_SPAN = re.compile(f"[{INVISIBLE_CLASS}]{{2,}}.*?[{INVISIBLE_CLASS}]{{2,}}", re.DOTALL)
_HTML_HINT = re.compile(r"<\s*[a-zA-Z!/]")
_HIDDEN_STYLE = re.compile(
    r"color\s*:\s*(#fff(fff)?\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))"
    r"|display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px|pt|em)?\s*(;|$)"
    r"|opacity\s*:\s*0(\.0+)?\s*(;|$)",
    re.IGNORECASE,
)

_VOWELS = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]", "n": "[nñ]"}


def _tolerant(pattern: str) -> str:
    return "".join(_VOWELS.get(ch, ch) for ch in pattern)


_PHRASES_ES = {
    "ignorar_instrucciones": r"\b(ignora|ignore|olvida|omite|descarta|desatiende)\w*\s+(todas\s+)?(las\s+|tus\s+|sus\s+)?"
    r"(instrucciones|indicaciones|reglas|politicas)\s+(anteriores|previas|del\s+sistema|originales)",
    "cambio_de_rol": r"\ba\s+partir\s+de\s+(ahora|este\s+momento)\b"
    r"|\b(actua|actuar|comportate|responde)\s+como\s+(un\s+|el\s+)?(administrador|admin|superusuario|desarrollador|sistema)"
    r"|\bmodo\s+(administrador|desarrollador|sin\s+restricciones)"
    r"|\bsin\s+(ninguna\s+)?restricciones\b",
    "dirigida_al_modelo": r"\b(instruccion|nota|mensaje|aviso)\s+(interna\s+)?(para|al|dirigida\s+al?)\s+(el\s+)?"
    r"(asistente|modelo|sistema|ia|bot|chatbot)\b"
    r"|\bcuando\s+(un|el|algun)\s+(usuario|analista|cliente)\s+pregunte\b"
    r"|\b(confirma|indica|informa|responde|dile|asegura)\w*\s+(al\s+|a\s+los\s+)?(usuario|analista|cliente)s?\s+que\b",
    "revelar_prompt": r"\b(revela|muestra|imprime|repite|comparte|transcribe)\w*\s+(tu|tus|el|las|su|sus)\s+"
    r"(system\s+prompt|prompt|instrucciones\s+(internas|del\s+sistema|ocultas)|configuracion)"
    r"|\b(prompt|mensaje|instrucciones)\s+de(l)?\s+sistema\b",
    "ocultar_al_usuario": r"\bno\s+(le\s+)?(menciones|digas|informes|reveles|comentes)\b",
}
_PHRASES_EN = {
    "ignorar_instrucciones": r"\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions",
    "cambio_de_rol": r"\byou\s+are\s+now\b|\bact\s+as\s+(an?\s+)?(admin|administrator|developer)",
    "revelar_prompt": r"\bsystem\s+prompt\b|\bdeveloper\s+message\b"
    r"|\breveal\s+(the\s+)?(hidden|secret|system)\s+(prompt|instructions)",
    "anular_instrucciones": r"\boverride\s+(all\s+)?(system|developer|user)\s+instructions",
    "ocultar_al_usuario": r"\bdo\s+not\s+tell\s+the\s+user\b",
}
PHRASE_PATTERNS = [
    (name, re.compile(_tolerant(pattern), re.IGNORECASE)) for name, pattern in _PHRASES_ES.items()
] + [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _PHRASES_EN.items()]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")


@dataclass
class SanitizeResult:
    text: str
    reglas: list[str] = field(default_factory=list)

    @property
    def neutralizado(self) -> bool:
        return bool(self.reglas)


def _add(rules: list[str], rule: str) -> None:
    if rule not in rules:
        rules.append(rule)


def _strip_html(text: str, rules: list[str]) -> str:
    if not _HTML_HINT.search(text):
        return text
    soup = BeautifulSoup(text, "html.parser")
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        _add(rules, "comentario_html")
        comment.extract()
    for element in soup.find_all(True):
        if element.decomposed:
            continue
        if element.has_attr("hidden") or _HIDDEN_STYLE.search(element.get("style", "")):
            _add(rules, "html_oculto")
            element.decompose()
    for element in soup.find_all(["script", "style", "head", "title", "meta"]):
        element.decompose()
    return soup.get_text(" ")


def _strip_invisible(text: str, rules: list[str]) -> str:
    if not _INVISIBLE.search(text):
        return text
    _add(rules, "unicode_invisible")
    text = _INVISIBLE_SPAN.sub(" ", text)
    lines = [line for line in text.split("\n") if len(_INVISIBLE.findall(line)) < 3]
    return _INVISIBLE.sub("", "\n".join(lines))


def _neutralize_phrases(text: str, rules: list[str]) -> str:
    kept = []
    for sentence in _SENTENCE_SPLIT.split(text):
        hits = [name for name, pattern in PHRASE_PATTERNS if pattern.search(sentence)]
        if hits:
            for name in hits:
                _add(rules, f"frase_instruccion:{name}")
            if not kept or kept[-1] != NEUTRALIZED:
                kept.append(NEUTRALIZED)
        elif sentence.strip():
            kept.append(sentence.strip())
    return " ".join(kept)


def sanitize_text(text: str) -> SanitizeResult:
    if not isinstance(text, str):
        return SanitizeResult("")
    rules: list[str] = []
    text = _strip_html(text, rules)
    text = _strip_invisible(text, rules)
    text = unicodedata.normalize("NFKC", text)
    text = _neutralize_phrases(text, rules)
    return SanitizeResult(re.sub(r"\s+", " ", text).strip(), rules)


def sanitize(chunk: dict) -> dict:
    result = sanitize_text(chunk.get("text", ""))
    return {**chunk, "text": result.text, "texto_original": chunk.get("text", ""), "sanitizacion": result.reglas}
