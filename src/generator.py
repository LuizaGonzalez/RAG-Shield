"""Llamada al LLM.

Un solo proveedor por corrida, elegido con LLM_PROVIDER:
  - groq (por defecto): GroqCloud, modelo qwen/qwen3.8-27b (llama-3.3-70b-versatile ya no está disponible)
  - anthropic: Claude, modelo claude-3-5-haiku-latest
  - mock: respuesta determinista para pruebas; nunca se reporta como resultado

La API key se lee de LLM_API_KEY, nunca del código.
"""

from __future__ import annotations

import os
import time

DEFAULT_MODELS = {
    "groq": "qwen/qwen3.8-27b",
    "anthropic": "claude-3-5-haiku-latest",
    "mock": "mock",
}
MAX_RETRIES = 4


class LLMConfigError(RuntimeError):
    pass


def provider() -> str:
    name = os.environ.get("LLM_PROVIDER", "groq").strip().lower()
    if name not in DEFAULT_MODELS:
        raise LLMConfigError(f"LLM_PROVIDER='{name}' no es válido. Usa: {', '.join(DEFAULT_MODELS)}")
    return name


def model_name() -> str:
    return os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider()]


def _settings() -> tuple[float, int]:
    return float(os.environ.get("LLM_TEMPERATURE", "0.7")), int(os.environ.get("LLM_MAX_TOKENS", "600"))


def _api_key() -> str:
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key or key.startswith("tu_api_key"):
        raise LLMConfigError("LLM_API_KEY no está configurada. Copia .env.example a .env y pon tu key.")
    return key


def _mock(prompt: str) -> str:
    context = prompt.split("Pregunta", 1)[0]
    return f"[MODO MOCK] Respuesta simulada a partir del contexto: {' '.join(context.split())[:400]}"


def _groq(prompt: str, system: str | None) -> str:
    from groq import Groq

    temperature, max_tokens = _settings()
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    response = Groq(api_key=_api_key()).chat.completions.create(
        model=model_name(), messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    return response.choices[0].message.content or ""


def _anthropic(prompt: str, system: str | None) -> str:
    from anthropic import Anthropic

    temperature, max_tokens = _settings()
    kwargs = {"system": system} if system else {}
    response = Anthropic(api_key=_api_key()).messages.create(
        model=model_name(),
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def _is_rate_limit(exc: Exception) -> bool:
    """Límite por minuto: vale la pena esperar y reintentar. La cuota diaria no se libera en segundos."""
    message = str(exc).lower()
    if "per day" in message:
        return False
    return getattr(exc, "status_code", None) == 429 or "rate limit" in message


def call_llm(prompt: str, system: str | None = None) -> str:
    name = provider()
    if name == "mock":
        return _mock(prompt)

    backend = _groq if name == "groq" else _anthropic
    for attempt in range(MAX_RETRIES):
        try:
            return backend(prompt, system)
        except Exception as exc:
            if not _is_rate_limit(exc) or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt * 5)
    raise AssertionError("unreachable")
