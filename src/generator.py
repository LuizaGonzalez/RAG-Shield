"""Llamada al LLM vía GroqCloud.

Responsable: Persona C (rol P3 en esta rotación)
Fase: 1 (RAG pelado, sin protección)

Aísla el proveedor del LLM detrás de call_llm() para poder cambiar
de servicio (Groq, Anthropic, OpenAI) sin tocar el resto del
pipeline. La API key se lee siempre desde variable de entorno,
nunca escrita directamente en el código — esto sigue la misma buena
práctica de seguridad que auditamos en el Lab04 (CWE-798, uso de
credenciales embebidas).
"""

import os
from dotenv import load_dotenv

load_dotenv()
_client = None


def get_client():
    """Devuelve el cliente de Groq, creándolo la primera vez que se necesita.

    Levanta RuntimeError si la variable de entorno LLM_API_KEY no
    está configurada, en vez de fallar más adelante con un error
    críptico del SDK.

    Returns:
        groq.Groq: cliente ya autenticado, listo para hacer llamadas.
    """
    global _client
    if _client is None:
        import groq
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY no configurada. Copia .env.example a .env "
                "y completa tu API key de GroqCloud."
            )
        _client = groq.Groq(api_key=api_key)
    return _client


# Modelo por defecto: se puede sobreescribir con la variable de
# entorno LLM_MODEL sin tocar este archivo.
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")


def call_llm(prompt: str, model: str = None, max_tokens: int = 1000) -> str:
    """Envía un prompt al LLM y devuelve el texto de la respuesta.

    Args:
        prompt: el texto completo que recibe el modelo (contexto +
            pregunta, ya armado por quien llama a esta función).
        model: nombre del modelo de Groq a usar; si se omite, usa
            DEFAULT_MODEL (configurable vía LLM_MODEL en .env).
        max_tokens: límite de tokens de la respuesta generada.

    Returns:
        str: el texto de la respuesta del modelo, sin metadata extra.
    """
    model = model or DEFAULT_MODEL
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content