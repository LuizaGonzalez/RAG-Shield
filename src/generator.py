"""Llamada al LLM via API comercial.

Responsable: Persona C
Aisla el proveedor detras de call_llm() para poder cambiarlo sin
tocar el resto del pipeline. Lee la API key desde variable de
entorno (LLM_API_KEY), nunca hardcodeada.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def call_llm(prompt: str) -> str:
    api_key = os.environ.get("LLM_API_KEY")
    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").lower()

    if not api_key:
        snippet = prompt.split("Contexto:", 1)[-1].split("Pregunta del usuario:", 1)[0].strip()
        return (
            "Modo local: no hay LLM_API_KEY configurada. "
            f"Se responde con base en el contexto disponible: {snippet[:350]}"
        )

    if provider == "anthropic":
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as exc:
            return f"No se pudo consultar Anthropic: {exc}. Respuesta local basada en contexto disponible."

    return f"Proveedor no soportado: {provider}. Configura LLM_PROVIDER o usa la respuesta local."
