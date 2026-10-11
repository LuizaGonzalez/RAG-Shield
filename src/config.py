"""Rutas y parámetros compartidos por ingesta, recuperación y evaluación."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DOCS_DIR = ROOT_DIR / "docs"
EVAL_DIR = ROOT_DIR / "eval"
RESULTS_DIR = EVAL_DIR / "results"
MANIFEST_PATH = EVAL_DIR / "manifest_envenenados.json"
ATTACKS_PATH = EVAL_DIR / "attacks" / "attacks.json"

COLLECTION_NAME = "novacred_docs"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def chroma_dir() -> Path:
    return Path(os.environ.get("CHROMA_PATH", ROOT_DIR / "chroma_db"))


def default_k() -> int:
    return int(os.environ.get("RETRIEVAL_K", "6"))
