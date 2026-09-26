"""Orquestador del pipeline RAG.

Responsable: compartido · Fase 1 (sin protección todavía)
Conecta retriever.py con generator.py. Prompt sin separación de
datos/instrucciones a propósito: es la línea base vulnerable.
"""

from src.retriever import retrieve
from src.generator import call_llm


def build_naive_prompt(query: str, chunks: list) -> str:
    """Arma el prompt mezclando contexto y pregunta, sin delimitadores."""
    context = "\n\n".join(c["text"] for c in chunks)
    return f"Contexto:\n{context}\n\nPregunta: {query}"


def ask(query: str, k: int = 6) -> dict:
    """Recupera, arma el prompt y genera la respuesta.

    Returns:
        dict con query, chunks_recuperados y respuesta.
    """
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