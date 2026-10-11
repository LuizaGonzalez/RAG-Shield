import pytest

from src.ingest import build_records, channel_for, chunk_text, technique_for
from src.retriever import IndexNotReadyError, indexed_sources, retrieve


def test_chunk_text_respects_max_size():
    text = "Una oración larga sobre la política de crédito de NovaCred. " * 30
    chunks = chunk_text(text, max_chars=200)
    assert len(chunks) > 1
    assert all(40 <= len(c) <= 200 for c in chunks)


def test_titles_are_merged_into_the_next_paragraph():
    text = "POLÍTICA DE MORA\nNovaCred S.A.S.\n\nEl crédito entra en mora a partir del día 31 sin pago."
    assert chunk_text(text) == ["POLÍTICA DE MORA\nNovaCred S.A.S. El crédito entra en mora a partir del día 31 sin pago."]


def test_channel_and_technique_come_from_file_name():
    assert channel_for("correo_comentario_html_x.txt") == "correo"
    assert channel_for("web_unicode_invisible_x.txt") == "web"
    assert channel_for("politica_mora.txt") == "archivo"
    assert technique_for("archivo_html_oculto_x.html") == "html_oculto"
    assert technique_for("politica_mora.txt") == "ninguna"


def test_records_mark_poisoned_documents_and_keep_raw_html(docs_dir):
    documents, metadatas, ids = build_records(docs_dir)
    assert len(ids) == len(set(ids))
    poisoned = [m for m in metadatas if m["is_poisoned"]]
    assert {m["file_name"] for m in poisoned} == {
        "archivo_html_oculto_limite_prueba.html",
        "correo_comentario_html_mora_prueba.txt",
        "web_unicode_invisible_score_prueba.txt",
    }
    html_chunk = next(d for d, m in zip(documents, metadatas) if m["file_name"].endswith(".html"))
    assert 'style="color:#FFFFFF"' in html_chunk
    assert all(m["source_file"].startswith("docs/") for m in metadatas)


def test_ingest_then_retrieve_uses_same_embeddings(indexed):
    assert indexed["result"]["fuentes"] == 10
    assert indexed["result"]["envenenados"] == 3
    chunks = retrieve("¿Cuál es el límite de aprobación del analista de nivel 1?", k=4)
    assert len(chunks) == 4
    assert {"text", "metadata", "distance"} <= set(chunks[0])
    assert chunks == sorted(chunks, key=lambda c: c["distance"])
    assert "archivo_html_oculto_limite_prueba.html" in indexed_sources()


def test_ingest_replaces_previous_collection(indexed):
    from src.ingest import ingest_documents

    again = ingest_documents(indexed["docs"], persist_dir=indexed["chroma"])
    assert again["chunks"] == indexed["result"]["chunks"]


def test_retrieve_without_index_explains_how_to_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "vacio"))
    with pytest.raises(IndexNotReadyError, match="src.ingest"):
        retrieve("hola")
