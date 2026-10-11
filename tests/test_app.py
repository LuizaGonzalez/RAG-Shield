from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_renders_without_index_or_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "sin_indice"))
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception


def test_app_renders_with_index(indexed):
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception
