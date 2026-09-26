"""Frontend MVP: herramienta interna del equipo de atencion NovaCred.

Responsable: compartido (fase 7)
Chat + toggles de capas + panel de metricas, conectado a src.pipeline.
"""

from __future__ import annotations

import streamlit as st

from src.pipeline import ask

st.set_page_config(page_title="NovaCred · RAG Shield", layout="centered")

st.title("NovaCred — asistente interno")
st.caption("Demo de laboratorio · RAG Shield · curso FDSI")

with st.sidebar:
    st.header("Controles de capa")
    use_sanitizer = st.checkbox("Usar sanitizador", value=True)
    use_prompt_guard = st.checkbox("Usar guard de prompt", value=True)
    use_privilege_guard = st.checkbox("Usar guard de privilegios", value=False)

    st.header("Métricas")
    st.caption("Se leen los resultados de eval/results/eval_results.csv si existen.")

query = st.text_area("Pregunta para el asistente", value="¿Qué requisitos debe cumplir un cliente para entrar en mora?")

if st.button("Consultar"):
    answer = ask(
        query,
        use_sanitizer=use_sanitizer,
        use_prompt_guard=use_prompt_guard,
        use_privilege_guard=use_privilege_guard,
    )
    st.markdown("### Respuesta")
    st.write(answer)
