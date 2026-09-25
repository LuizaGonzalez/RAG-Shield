# Fase 1 — RAG pelado

## Qué trae este zip

Código funcional (no esqueleto) para las tres piezas básicas del RAG,
más 5 documentos de prueba de NovaCred:

- `src/ingest.py` — ingesta a ChromaDB con embeddings locales (sentence-transformers)
- `src/retriever.py` — recuperación de los k chunks más parecidos
- `src/generator.py` — llamada a la API del LLM (Anthropic por defecto)
- `src/pipeline.py` — conecta las tres piezas, sin ninguna capa de seguridad
- `docs/legitimos/` — 5 documentos de prueba

## Cómo correrlo

```bash
pip install chromadb sentence-transformers anthropic python-dotenv
cp .env.example .env   # completa LLM_API_KEY
python -m src.ingest    # puebla ChromaDB una sola vez
python -m src.pipeline  # corre una pregunta de prueba
```

## División de trabajo para esta fase (rotación 1)

| Persona | Tarea |
|---|---|
| P1 | Revisar y ampliar los documentos de prueba (agregar 1-2 más si quieren más variedad) |
| P2 | Correr y validar `ingest.py` + `retriever.py`, confirmar que la recuperación trae los chunks correctos |
| P3 | Correr y validar `generator.py` + `pipeline.py`, probar con distintas preguntas |
| P4 | Documentar en una hoja aparte 5-10 preguntas de control (legítimas) que se van a usar en la fase 3 para medir falsos positivos |

Al terminar, cada quien hace commit en su rama y abren PR hacia `develop`/`main`.

## Qué NO incluye todavía

- `sanitizer.py` y `prompt_builder.py` (fase 4)
- documentos envenenados (fase 2)
- `eval_harness.py` (fase 3)

Eso llega en `fase02.zip`.
