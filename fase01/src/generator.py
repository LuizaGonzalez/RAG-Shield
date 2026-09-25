"""Llamada al LLM vía API comercial.

Aislado detrás de call_llm() para poder cambiar de proveedor sin
tocar el resto del pipeline. La API key se lee desde variable de
entorno, nunca hardcodeada (buena práctica de seguridad).
"""

import os
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        import anthropic
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY no configurada. Copia .env.example a .env "
                "y completa tu API key."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


DEFAULT_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")  # ajusten al modelo que tengan disponible en su API key


def call_llm(prompt: str, model: str = None, max_tokens: int = 1000) -> str:
    model = model or DEFAULT_MODEL
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
