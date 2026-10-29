"""Capa 3: mínimo privilegio sobre la respuesta del modelo.

La inyección indirecta vive en los documentos, no en la pregunta. Por
eso esta capa revisa lo que el modelo responde: si afirma haber
aprobado, condonado, desembolsado, enviado datos o cambiado condiciones,
la respuesta se bloquea hasta que un humano confirme por el canal formal.
Explicar un procedimiento ("para aprobar un crédito se requiere...") no
se bloquea.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

BLOCK_MESSAGE = (
    "Respuesta retenida por la capa de mínimo privilegio: afirmaba ejecutar una acción crítica "
    "(aprobar, condonar, desembolsar, enviar datos o cambiar condiciones). El asistente solo informa; "
    "esa acción requiere registro formal y confirmación de un supervisor."
)

_PARTICIPLE_PREFIX = r"\b(he|hemos|ha|han|se\s+ha|se\s+han|queda|quedan|qued[oó]|fue|fueron|ya\s+est[aá])\s+(sido\s+)?"

ACTION_PATTERNS: dict[str, list[str]] = {
    "aprobar_credito": [
        _PARTICIPLE_PREFIX + r"aprobad[oa]s?\b",
        r"\b(apruebo|aprobamos)\b",
        r"\baprobaci[oó]n\s+(autom[aá]tica\s+)?(confirmada|otorgada|realizada|concedida)",
    ],
    "condonar_mora": [
        _PARTICIPLE_PREFIX + r"condonad[oa]s?\b",
        r"\b(condono|condonamos)\b",
        r"\bcondonaci[oó]n\s+(aplicada|aprobada|realizada|confirmada)",
    ],
    "ordenar_desembolso": [
        _PARTICIPLE_PREFIX + r"(desembolsad[oa]s?|girad[oa]s?)\b",
        r"\b(desembolso|giro)\s+(confirmado|realizado|ejecutado|ordenado)",
        r"\b(ordeno|autorizo|confirmo)\s+(el\s+)?(desembolso|giro)",
    ],
    "enviar_datos": [
        r"\b(he|hemos)\s+(enviado|reenviado|compartido|remitido)\b",
        r"\b(datos|informaci[oó]n|expediente|documentos|historial)\b[^.]{0,60}\b(enviad[oa]s?|reenviad[oa]s?|compartid[oa]s?)\s+(a|al|con|por)\b",
        r"\b(env[ií]o|reenv[ií]o|remito|comparto)\s+(los\s+datos|la\s+informaci[oó]n|el\s+expediente|los\s+documentos)",
    ],
    "modificar_condiciones": [
        _PARTICIPLE_PREFIX + r"(modificad[oa]|cambiad[oa]|ajustad[oa]|actualizad[oa])\s+(el\s+saldo|la\s+tasa|el\s+plazo|las\s+condiciones)",
    ],
}
_COMPILED = {action: [re.compile(p, re.IGNORECASE) for p in patterns] for action, patterns in ACTION_PATTERNS.items()}
_NEGATION = re.compile(r"\b(no|nunca|ningun[oa]?|ningún|jam[aá]s|ni)\s+(\S+\s+){0,2}$", re.IGNORECASE)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class GuardResult:
    bloqueado: bool
    acciones: list[str] = field(default_factory=list)
    evidencia: list[str] = field(default_factory=list)


def inspect_response(text: str) -> GuardResult:
    actions: list[str] = []
    evidence: list[str] = []
    for sentence in _SENTENCES.split(text or ""):
        for action, patterns in _COMPILED.items():
            for pattern in patterns:
                match = pattern.search(sentence)
                if match and not _NEGATION.search(sentence[: match.start()]):
                    if action not in actions:
                        actions.append(action)
                    evidence.append(sentence.strip())
                    break
    return GuardResult(bool(actions), actions, list(dict.fromkeys(evidence)))


REQUEST_MESSAGE = (
    "No puedo ejecutar esa acción. El asistente solo informa: esa solicitud requiere registro formal "
    "y confirmación de un supervisor."
)

_IMPERATIVES = {
    "aprobar_credito": "aprueba|apruebe|apruebalo|apruebala",
    "condonar_mora": "condona|condone|condonalo|condonala|condonale",
    "ordenar_desembolso": "desembolsa|desembolse|desembolsalo|gira|gire|transfiere|transfiera",
    "enviar_datos": "envia|envie|envialo|enviale|reenvia|reenvie|manda|mande|remite|remita",
    "modificar_condiciones": "modifica|modifique|cambia|cambie|ajusta|ajuste",
}
_INFINITIVES = {
    "aprobar_credito": "aprobar|aprobarme",
    "condonar_mora": "condonar|condonarle",
    "ordenar_desembolso": "desembolsar|girar|transferir",
    "enviar_datos": "enviar|reenviar|mandar|remitir",
    "modificar_condiciones": "modificar|cambiar|ajustar",
}
_SUBJUNCTIVES = {
    "aprobar_credito": "apruebes",
    "condonar_mora": "condones",
    "ordenar_desembolso": "desembolses|gires|transfieras",
    "enviar_datos": "envies|reenvies|mandes|remitas",
    "modificar_condiciones": "modifiques|cambies|ajustes",
}
_REQUEST_PATTERNS = {
    action: [
        re.compile(rf"^(?:por favor,?\s+|ahora\s+|ya\s+)*(?:{_IMPERATIVES[action]})\b"),
        re.compile(rf"\b(?:puedes|podrias)\s+(?:me\s+|le\s+)?(?:{_INFINITIVES[action]})\b"),
        re.compile(rf"\bque\s+(?:me\s+|le\s+)?(?:{_SUBJUNCTIVES[action]})\b"),
    ]
    for action in _IMPERATIVES
}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def detect_action_request(query: str) -> list[str]:
    """Acciones críticas que la pregunta le pide ejecutar al asistente.

    Solo cuenta órdenes en segunda persona ("condona la mora", "¿puedes
    aprobar...?", "necesito que envíes..."). Una pregunta informativa en
    tercera persona ("¿se puede condonar...?", "¿cambia la tasa...?") pasa.
    Es una heurística de la vista de Empleado; la evaluación no la usa.
    """
    actions: list[str] = []
    for sentence in re.split(r"(?<=[.!?])|\n", _plain(query or "")):
        sentence = sentence.strip(" ,;:.!")
        is_question = sentence.startswith("¿") or sentence.endswith("?")
        for action, (imperative, infinitive, subjunctive) in _REQUEST_PATTERNS.items():
            hit = (not is_question and imperative.search(sentence)) or infinitive.search(sentence) \
                or subjunctive.search(sentence)
            if hit and action not in actions:
                actions.append(action)
    return actions


def request_action_confirmation(action: str, params: dict) -> bool:
    """Solo deja pasar acciones críticas con confirmación explícita."""
    if not isinstance(action, str) or not action.strip():
        return False
    if action.strip().lower() not in {*ACTION_PATTERNS, "aprobar_solicitud", "enviar_correo", "enviar_mensaje", "modificar_saldo"}:
        return True
    return isinstance(params, dict) and bool(params.get("confirmado"))
