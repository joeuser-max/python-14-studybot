"""展示模式任務的回歸：卡片對話框可見、實際儲存動作明確隔離。"""
from collections import Counter
from pathlib import Path

import storage
from demo_data import sample_records, seed_demo_data
from task_actions import save_task_changes, delete_task_and_plan
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


def test_task_card_opens_edit_dialog(monkeypatch, tmp_path):
    """Streamlit AppTest 能檢查 dialog 元件，但不能可靠驅動 fragment 內提交。"""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    app = AppTest.from_file(str(APP)).run(timeout=25)
    assert not app.exception
    app.sidebar.toggle[0].set_value(True).run(timeout=25)
    app.sidebar.radio[0].set_value("我的任務").run(timeout=25)
    assert not app.exception
    button = next(b for b in app.button if b.label.startswith("複習回授與穩定度"))
    button.click().run(timeout=25)
    assert not app.exception, [str(e) for e in app.exception]
    assert any(x.label == "任務名稱" for x in app.text_input)
    assert any(x.label == "儲存修改" for x in app.button)


def test_edit_existing_and_new_demo_tasks_without_live_mutation(monkeypatch, tmp_path):
    """實際執行 UI 所呼叫的服務：展示任務及新建立任務皆可更新 JSON。"""
    demo = tmp_path / "demo"
    live = tmp_path / "live"
    monkeypatch.setattr(storage, "DATA_DIR", live)
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", demo)
    storage.select_demo_storage(True)
    seed_demo_data()
    initial = storage.load_json(storage.data_path("tasks"))
    task = next(t for t in initial if t["task_id"] == "demo_task_control")
    newly_created = {
        "task_id": "user-added-task", "user_id": "demo_user_001",
        "subject": "程式設計", "title": "現場新增的任務",
        "deadline": task["deadline"], "estimated_minutes": 45,
        "status": "pending", "progress_percent": 0,
        "preferred_availability_id": "",
    }
    storage.add_task_to_storage(newly_created)
    storage.select_demo_storage(False)  # 模擬對話框的 ContextVar 遺失

    save_task_changes({**task, "title": "修改成功的控制系統任務",
                       "progress_percent": 60}, demo_mode=True)
    storage.select_demo_storage(False)
    save_task_changes({**newly_created, "title": "新增後也可修改",
                       "progress_percent": 30}, demo_mode=True)
    assert not (live / "tasks.json").exists()
    tasks = storage.load_json(demo / "tasks.json")
    edited = {item["task_id"]: item for item in tasks}
    assert edited["demo_task_control"]["title"] == "修改成功的控制系統任務"
    assert edited["demo_task_control"]["progress_percent"] == 60
    assert edited["user-added-task"]["title"] == "新增後也可修改"
    assert edited["user-added-task"]["progress_percent"] == 30
    # 新版行為：修改任務會重新計算排程，而不是清空整份計畫。
    plan = storage.load_json(demo / "plan.json")
    assert any(row.get("task_id") == "demo_task_control" for row in plan)
    assert len(storage.load_json(demo / "progress_events.json")) >= 2


def test_delete_demo_task_does_not_touch_live(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(True)
    seed_demo_data()
    storage.select_demo_storage(False)
    delete_task_and_plan("demo_task_control", "demo_user_001", demo_mode=True)
    assert not (tmp_path / "live" / "tasks.json").exists()
    assert not any(x["task_id"] == "demo_task_control"
                   for x in storage.load_json(tmp_path / "demo" / "tasks.json"))
    assert not any(x.get("task_id") == "demo_task_control"
                   for x in storage.load_json(tmp_path / "demo" / "plan.json"))


def test_edit_real_task_uses_real_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    task = {
        "task_id": "real-task", "user_id": "demo_user_001",
        "subject": "測試", "title": "原始任務", "deadline": "2026-12-01",
        "estimated_minutes": 30, "status": "pending",
        "preferred_availability_id": "",
    }
    storage.add_task_to_storage(task)
    save_task_changes({**task, "title": "真實模式修改成功"}, demo_mode=False)
    assert storage.load_json(tmp_path / "live" / "tasks.json")[0]["title"] == "真實模式修改成功"
    assert not (tmp_path / "demo" / "tasks.json").exists()
