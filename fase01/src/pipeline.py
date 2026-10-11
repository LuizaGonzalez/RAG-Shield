"""Orquestador del pipeline RAG.

Fase 1: sin ninguna capa de seguridad activa. El sistema es
intencionalmente ingenuo — confía en todo lo que el recuperador trae.
Las capas de sanitización y separación de prompt se agregan en la
fase 4 (ver sanitizer.py y prompt_builder.py).
"""

from src.retriever import retrieve
from src.generator import call_llm


def build_naive_prompt(query: str, chunks: list) -> str:
    """Prompt sin ninguna separación entre datos e instrucciones (fase 1)."""
    context = "\n\n".join(c["text"] for c in chunks)
    return f"Contexto:\n{context}\n\nPregunta: {query}"


def ask(query: str, k: int = 3) -> dict:
    chunks = retrieve(query, k=k)
    prompt = build_naive_prompt(query, chunks)
    respuesta = call_llm(prompt)

    return {
        "query": query,
        "chunks_recuperados": [c["metadata"]["source_file"] for c in chunks],
        "respuesta": respuesta,
    }


if __name__ == "__main__":
    resultado = ask("¿Cuál es la política de mora para créditos de libre inversión?")
    print("Documentos usados:", resultado["chunks_recuperados"])
    print("\nRespuesta:\n", resultado["respuesta"])
