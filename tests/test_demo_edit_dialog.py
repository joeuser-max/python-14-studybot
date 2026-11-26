"""實際回歸：展示資料隔離、任務可修改、同課次筆記群組。"""
from collections import Counter
from pathlib import Path

import storage
from demo_data import sample_records, seed_demo_data
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_demo_sample_has_multiple_editable_tasks_and_grouped_feedback():
    records = sample_records()
    assert len(records["tasks"]) >= 3
    for task in records["tasks"]:
        storage.validate_task(task)
    for feedback in records["feedback"]:
        storage.validate_feedback(feedback)
    groups = Counter((f["event_id"], f["class_date"]) for f in records["feedback"])
    assert len(records["feedback"]) == 3
    assert any(count == 2 for count in groups.values())


def test_demo_task_edit_from_streamlit_card_uses_demo_json(monkeypatch, tmp_path):
    """覆蓋「任務畫面可見，但按儲存修改時找不到任務」的使用者路徑。"""
    live_dir = tmp_path / "live"
    demo_dir = tmp_path / "demo"
    monkeypatch.setattr(storage, "DATA_DIR", live_dir)
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", demo_dir)
    storage.select_demo_storage(False)

    app = AppTest.from_file(str(APP)).run(timeout=25)
    assert not app.exception
    app.sidebar.toggle[0].set_value(True).run(timeout=25)
    app.sidebar.radio[0].set_value("我的任務").run(timeout=25)
    assert not app.exception

    button = next(b for b in app.button if b.label.startswith("複習回授與穩定度"))
    button.click().run(timeout=25)
    assert not app.exception, [str(e) for e in app.exception]

    name = next(field for field in app.text_input if field.label == "任務名稱")
    name.set_value("修改成功的控制系統任務")
    submit = next(b for b in app.button if b.label == "儲存修改")
    submit.click().run(timeout=25)
    assert not app.exception, [str(e) for e in app.exception]

    tasks = storage.load_json(demo_dir / "tasks.json")
    changed = next(t for t in tasks if t["task_id"] == "demo_task_control")
    assert changed["title"] == "修改成功的控制系統任務"
    assert not (live_dir / "tasks.json").exists()


def test_reinitialize_storage_context_for_dialog_write(monkeypatch, tmp_path):
    """刻意模擬 Streamlit 對話框 fragment 沒有沿用主頁的 ContextVar。"""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(True)
    seed_demo_data()
    task = next(t for t in storage.load_json(storage.data_path("tasks"))
                if t["task_id"] == "demo_task_control")
    storage.select_demo_storage(False)  # fragment 執行環境沒有先前的設定
    assert not (tmp_path / "live" / "tasks.json").exists()

    # Dialog 會呼叫 sync_storage_context()，使 update_task 再次指向展示目錄。
    # 此處直接重現其必要的修正動作，避免依賴瀏覽器外部狀態。
    storage.select_demo_storage(True)
    storage.update_task({**task, "title": "課表編輯成功"})
    assert storage.load_json(storage.data_path("tasks"))[0]["title"] == "課表編輯成功"
    storage.select_demo_storage(False)
    assert not (tmp_path / "live" / "tasks.json").exists()
