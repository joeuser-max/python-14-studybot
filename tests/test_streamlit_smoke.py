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


def test_each_dashboard_page_and_line_choice_can_render(monkeypatch, tmp_path):
    """展示使用者從側欄打開各頁並點選 08:00 的一則虛擬 LINE 訊息。"""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "normal")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    app = AppTest.from_file(str(APP)).run(timeout=25)
    app.sidebar.toggle[0].set_value(True).run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]

    for page in ("我的任務", "時間規劃", "學習回饋", "AI 助理",
                 "連接與匯出", "首次設定", "LINE 一日展示"):
        app.sidebar.radio[0].set_value(page).run(timeout=25)
        assert not app.exception, (page, [str(x) for x in app.exception])

    choice = next(button for button in app.button
                  if button.label == "查看今日安排")
    choice.click().run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]
    assert app.session_state["line_day_state"]["awaiting_next"] is True
    assert app.session_state["line_day_state"]["messages"][1]["text"] == "查看今日安排"

    next_button = next(button for button in app.button
                       if button.label == "繼續前往下一個時段")
    next_button.click().run(timeout=25)
    assert not app.exception, [str(x) for x in app.exception]
    assert app.session_state["line_day_state"]["index"] == 1
