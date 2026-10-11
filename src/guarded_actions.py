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


def request_action_confirmation(action: str, params: dict) -> bool:
    """Solo deja pasar acciones críticas con confirmación explícita."""
    if not isinstance(action, str) or not action.strip():
        return False
    if action.strip().lower() not in {*ACTION_PATTERNS, "aprobar_solicitud", "enviar_correo", "enviar_mensaje", "modificar_saldo"}:
        return True
    return isinstance(params, dict) and bool(params.get("confirmado"))
