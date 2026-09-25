# RAG Shield

FDSI · Grupo 04 · Escuela Colombiana de Ingeniería Julio Garavito

NovaCred es una financiera digital inventada para este curso. El
asistente interno les responde a los analistas con lo que encuentra
en políticas, procedimientos y casos. El problema que medimos es
cuando un documento recuperado trae una instrucción escondida y el
modelo la sigue como si fuera parte del sistema.

## Integrantes

- Cristian Jose Gonzalez Rodriguez
- Juana Lozano Cháves
- Luiza Mariana Gonzalez Veloza
- Rafael Santiago Moreno Velásquez

## Cómo levantarlo

```bash
python -m venv venv
source venv/bin/activate   # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # poner LLM_API_KEY
```

Con los documentos ya en `docs/legitimos/`, P2 indexa y P3 pregunta:

```bash
python -m src.ingest
python -m src.pipeline
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

En `docs/legitimos/` hay siete textos: ficha de libre inversión, mora,
refinanciación, aprobación, score y capacidad de pago, desembolso, y
el caso 00147. Cuadran entre sí (montos, tasas, quién aprueba qué).
En esta fase solo importan ingest, retriever, generator y pipeline.
Sanitizar, el harness y el frontend van después.

## Cómo lo vamos a hacer

Primero dejamos el RAG pelado y vemos qué responde con documentos
limpios. Después metemos textos con instrucciones ocultas (archivo,
correo y web simulados) y medimos cuántas veces el modelo las
obedece. Con esa línea base ponemos dos capas: una que limpia el
texto recuperado y otra que le deja claro al modelo qué es dato y
qué es instrucción. Si alcanza el tiempo, una tercera capa evita
que el chat apruebe, condone o gire plata. Al final va el chat en
Streamlit y el informe.
