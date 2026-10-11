"""Valida los archivos reales del experimento cuando ya están en el repo."""

import pytest

from eval.dataset import load_attacks, load_manifest, validate
from src.config import ATTACKS_PATH, DOCS_DIR, MANIFEST_PATH
from src.sanitizer import sanitize_text


def test_seven_legitimate_documents_are_marked_fictional_company():
    files = sorted((DOCS_DIR / "legitimos").glob("*.txt"))
    assert len(files) == 7
    assert all("NovaCred" in f.read_text(encoding="utf-8") for f in files)


@pytest.mark.skipif(not MANIFEST_PATH.exists(), reason="todavía no está eval/manifest_envenenados.json")
def test_poisoned_documents_hide_their_instruction():
    manifest = load_manifest()
    for name, entry in manifest.items():
        raw = (DOCS_DIR / "envenenados" / name).read_text(encoding="utf-8")
        assert sanitize_text(raw).reglas, f"{name}: la Capa 1 no detecta nada; revisa el camuflaje"
        assert "NovaCred" in raw, f"{name}: debe tener contexto legítimo de NovaCred"


@pytest.mark.skipif(not (MANIFEST_PATH.exists() and ATTACKS_PATH.exists()), reason="falta el dataset de ataques")
def test_experiment_dataset_is_complete_and_consistent():
    assert validate(load_attacks(), load_manifest(), DOCS_DIR, strict=True) == []
