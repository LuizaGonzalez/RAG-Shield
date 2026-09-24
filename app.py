"""Frontend MVP: herramienta interna del equipo de atencion NovaCred.

Responsable: compartido (fase 7)
Chat + toggles de capas + panel de metricas, conectado a src.pipeline.
"""

import streamlit as st

st.set_page_config(page_title="NovaCred · RAG Shield", layout="centered")

st.title("NovaCred — asistente interno")
st.caption("Demo de laboratorio · RAG Shield · curso FDSI")

# TODO: toggles de capas (use_sanitizer, use_prompt_guard, use_privilege_guard)
# TODO: chat conectado a src.pipeline.ask()
# TODO: panel de metricas (ASR, falsos positivos, latencia) desde eval/results
