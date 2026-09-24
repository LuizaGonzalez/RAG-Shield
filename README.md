# RAG Shield

Proyecto de curso FDSI — Grupo 04
Escuela Colombiana de Ingeniería Julio Garavito

Simulación del asistente interno de **NovaCred**, empresa ficticia de
crédito digital, evaluado frente a inyección indirecta de prompts a
través de documentos recuperados (archivos, correos y páginas web
simulados como canal).

## Integrantes

- Cristian Jose Gonzalez Rodriguez
- Juana Lozano Cháves
- Luiza Mariana Gonzalez Veloza
- Rafael Santiago Moreno Velásquez

## Setup

```bash
python -m venv venv
source venv/bin/activate  # o venv\Scripts\activate en Windows
pip install -r requirements.txt
cp .env.example .env  # completar LLM_API_KEY
```

## Estructura

```
rag-shield/
├─ docs/                    # Base documental
│  ├─ legitimos/            # Documentos limpios de NovaCred
│  └─ envenenados/          # Documentos con instrucciones ocultas
├─ src/                     # Pipeline RAG
│  ├─ ingest.py             # Ingesta a ChromaDB
│  ├─ retriever.py          # Recuperación de chunks
│  ├─ sanitizer.py          # Capa 1 — sanitización basada en reglas
│  ├─ prompt_builder.py     # Capa 2 — separación datos/instrucciones
│  ├─ generator.py          # Llamada al LLM
│  ├─ guarded_actions.py    # Capa 3 (opcional) — mínimo privilegio
│  └─ pipeline.py           # Orquestador con flags por capa
├─ eval/                    # Evaluación y métricas
│  ├─ attacks/              # Prompts maliciosos y consultas de control
│  ├─ eval_harness.py       # Corre las pruebas y calcula métricas
│  └─ results/              # CSVs de resultados por configuración
└─ app.py                   # Frontend Streamlit (MVP)
```

## Fases

1. RAG  (ingesta + recuperador + generacion, sin proteccion)
2. Base documental completa + subconjunto envenenado
3. Medicion de linea base (ASR sin proteccion)
4. Implementar capa 1 y capa 2
5. Medicion con capas activas y comparacion
6. Capa 3 (opcional)
7. Frontend + despliegue
8. Informe final


