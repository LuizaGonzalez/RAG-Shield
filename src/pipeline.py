"""Orquestador del pipeline RAG Shield.

Responsable: compartido (se integra en cada fase con lo que traiga
cada modulo: retriever de B, sanitizer/prompt_builder/generator de C).

Los flags permiten correr exactamente la misma consulta con distintas
combinaciones de capas activas, para comparar linea base vs. protegido.
"""

from src.retriever import retrieve
from src.sanitizer import sanitize
from src.prompt_builder import build_prompt
from src.generator import call_llm
from src.guarded_actions import request_action_confirmation


def ask(
    query: str,
    use_sanitizer: bool = True,
    use_prompt_guard: bool = True,
    use_privilege_guard: bool = False,
) -> str:
    lower_query = query.lower()
    if use_privilege_guard and any(token in lower_query for token in ["aprobar", "condonar", "enviar correo", "modificar saldo"]):
        confirmed = request_action_confirmation("aprobar_solicitud", {"confirmado": False})
        if not confirmed:
            return "Acción crítica bloqueada por guard de privilegios: requiere confirmación manual del supervisor."

    chunks = retrieve(query)

    if use_sanitizer:
        chunks = [sanitize(c) for c in chunks]

    if use_prompt_guard:
        prompt = build_prompt(query, chunks)
    else:
        prompt = f"Contexto:\n{chunks}\n\nPregunta: {query}"

    return call_llm(prompt)
