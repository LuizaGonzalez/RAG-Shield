"""Llamada al LLM via API comercial.

Responsable: Persona C
Aisla el proveedor detras de call_llm() para poder cambiarlo sin
tocar el resto del pipeline. Lee la API key desde variable de
entorno (LLM_API_KEY), nunca hardcodeada.
"""

import os


def call_llm(prompt: str) -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY no configurada en el entorno")
    raise NotImplementedError
