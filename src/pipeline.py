"""Orquestador del pipeline RAG Shield.

`ask(query)` sin argumentos es la línea base: ninguna capa activa. Cada
flag enciende una capa, así la misma pregunta se puede correr con y sin
protección y comparar.

Devuelve siempre un dict con la misma forma, que consumen app.py y el
arnés de evaluación:
  query, config, respuesta, respuesta_modelo, chunks, documentos_recuperados,
  documento_envenenado_recuperado, sanitizacion_aplicada, sanitizacion,
  guard, proveedor, modelo, latencia_segundos, latencia_llm_segundos
"""

from __future__ import annotations

import time

from src.generator import call_llm, model_name, provider
from src.guarded_actions import BLOCK_MESSAGE, inspect_response
from src.prompt_builder import BASE_SYSTEM_PROMPT, GUARD_SYSTEM_PROMPT, build_naive_prompt, build_prompt
from src.retriever import retrieve
from src.sanitizer import sanitize


def ask(
    query: str,
    use_sanitizer: bool = False,
    use_prompt_guard: bool = False,
    use_privilege_guard: bool = False,
    k: int | None = None,
) -> dict:
    started = time.perf_counter()
    chunks = retrieve(query, k=k)

    if use_sanitizer:
        chunks = [sanitize(chunk) for chunk in chunks]

    if use_prompt_guard:
        prompt, system = build_prompt(query, chunks), GUARD_SYSTEM_PROMPT
    else:
        prompt, system = build_naive_prompt(query, chunks), BASE_SYSTEM_PROMPT

    llm_started = time.perf_counter()
    model_answer = call_llm(prompt, system=system)
    llm_seconds = time.perf_counter() - llm_started

    guard = inspect_response(model_answer)
    blocked = use_privilege_guard and guard.bloqueado
    sanitized = [
        {"source_file": c["metadata"].get("source_file"), "reglas": c["sanitizacion"]}
        for c in chunks
        if c.get("sanitizacion")
    ]

    return {
        "query": query,
        "config": {
            "use_sanitizer": use_sanitizer,
            "use_prompt_guard": use_prompt_guard,
            "use_privilege_guard": use_privilege_guard,
        },
        "respuesta": BLOCK_MESSAGE if blocked else model_answer,
        "respuesta_modelo": model_answer,
        "chunks": chunks,
        "documentos_recuperados": list(dict.fromkeys(c["metadata"].get("file_name") for c in chunks)),
        "documento_envenenado_recuperado": any(c["metadata"].get("is_poisoned") for c in chunks),
        "sanitizacion_aplicada": bool(sanitized),
        "sanitizacion": sanitized,
        "guard": {
            "activo": use_privilege_guard,
            "accion_detectada": guard.bloqueado,
            "bloqueado": blocked,
            "acciones": guard.acciones,
            "evidencia": guard.evidencia,
        },
        "proveedor": provider(),
        "modelo": model_name(),
        "latencia_segundos": round(time.perf_counter() - started, 4),
        "latencia_llm_segundos": round(llm_seconds, 4),
    }


if __name__ == "__main__":
    result = ask("¿Cuál es la política de mora para créditos de libre inversión?")
    print("Documentos usados:", ", ".join(result["documentos_recuperados"]))
    print(f"Proveedor: {result['proveedor']} / {result['modelo']} · {result['latencia_segundos']} s")
    print("\nRespuesta:\n", result["respuesta"])
