"""Frontend MVP: herramienta interna del equipo de atención NovaCred.

Consulta + toggles de capas, conectado a src.pipeline.ask().
"""

from __future__ import annotations

import streamlit as st

from src.generator import LLMConfigError
from src.pipeline import ask
from src.retriever import IndexNotReadyError

st.set_page_config(page_title="NovaCred · RAG Shield", layout="centered")

st.title("NovaCred — asistente interno")
st.caption("Demo de laboratorio · RAG Shield · curso FDSI")

with st.sidebar:
    st.header("Capas de defensa")
    use_sanitizer = st.checkbox("Capa 1: sanitización", value=False)
    use_prompt_guard = st.checkbox("Capa 2: separación del prompt", value=False)
    use_privilege_guard = st.checkbox("Capa 3: mínimo privilegio", value=False)

query = st.text_area("Pregunta para el asistente", value="¿Qué pasa si un crédito supera 90 días de atraso?")

if st.button("Consultar"):
    try:
        result = ask(
            query,
            use_sanitizer=use_sanitizer,
            use_prompt_guard=use_prompt_guard,
            use_privilege_guard=use_privilege_guard,
        )
    except (IndexNotReadyError, LLMConfigError) as exc:
        st.error(str(exc))
    else:
        st.markdown("### Respuesta")
        st.write(result["respuesta"])
        st.caption(f"{result['proveedor']} · {result['modelo']} · {result['latencia_segundos']} s")
        st.markdown("### Documentos recuperados")
        for chunk in result["chunks"]:
            meta = chunk["metadata"]
            marca = "envenenado" if meta.get("is_poisoned") else "legítimo"
            st.write(f"- `{meta.get('file_name')}` ({marca})")
