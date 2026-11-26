"""Streamlit 頁面執行測試：驗證初次引導、模式切換與 LINE 展示可渲染。"""
from pathlib import Path

import storage
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_initial_setup_and_demo_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "normal")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)

    app = AppTest.from_file(str(APP)).run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]
    assert app.sidebar.radio[0].value == "開始設定"

    app.sidebar.toggle[0].set_value(True).run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]
    assert app.sidebar.radio[0].value == "總覽"

    app.sidebar.radio[0].set_value("LINE 一日展示").run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]
    assert any("08:00" in x.value for x in app.caption)
    assert app.session_state["line_day_state"]["index"] == 0
    assert app.session_state["line_day_state"]["completed"] is False
