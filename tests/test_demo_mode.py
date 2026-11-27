"""展示模式的隔離、預設資料、重設與 AI Mock 行為測試。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import storage
from demo_data import mock_learning_suggestions, sample_records, seed_demo_data


TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 26, 22, 0, tzinfo=TZ)


def test_sample_fixture_is_valid_and_editable():
    records = sample_records(NOW)
    assert len(records["events"]) >= 3
    assert len(records["tasks"]) >= 2
    assert records["plan"] == []  # Demo 首次操作必須顯示可拖排的任務
    assert len([t for t in records["tasks"] if t["status"] == "pending"]) >= 2
    assert records["users"][0]["line_user_id"] == ""
    assert records["feedback"][0]["source"] == "demo"
    for event in records["events"]:
        storage.validate_event(event)
    for task in records["tasks"]:
        storage.validate_task(task)
    for feedback in records["feedback"]:
        storage.validate_feedback(feedback)


def test_demo_storage_does_not_modify_live_files(monkeypatch, tmp_path):
    live = tmp_path / "live"
    demo = tmp_path / "demo"
    monkeypatch.setattr(storage, "DATA_DIR", live)
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", demo)
    storage.select_demo_storage(False)
    storage.save_json(storage.data_path("events"), [{"event_id": "real-class"}])

    try:
        storage.select_demo_storage(True)
        assert seed_demo_data(now=NOW) is True
        original = storage.load_json(storage.data_path("events"))
        assert len(original) == 3

        # 修改展示課程後重新整理，不應重新載入覆蓋。
        edited = {**original[0], "title": "現場修改的課程"}
        storage.update_event(edited)
        assert seed_demo_data(now=NOW) is False
        assert storage.load_json(storage.data_path("events"))[0]["title"] == "現場修改的課程"

        # 明確重設才還原初始展示資料。
        assert seed_demo_data(reset=True, now=NOW) is True
        assert storage.load_json(storage.data_path("events"))[0]["title"] == original[0]["title"]
    finally:
        storage.select_demo_storage(False)

    assert storage.load_json(storage.data_path("events")) == [{"event_id": "real-class"}]


def test_seed_requires_isolated_demo_context(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    storage.select_demo_storage(False)
    with pytest.raises(RuntimeError, match="正式資料"):
        seed_demo_data(now=NOW)


def test_mock_ai_suggestions_reference_feedback_without_api():
    records = sample_records(NOW)
    result = mock_learning_suggestions(
        records["feedback"], records["events"], "demo_user_001"
    )
    assert result["summary"].startswith("【Mock 展示】")
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["source_feedback_id"] == records["feedback"][0]["feedback_id"]
    assert mock_learning_suggestions([], records["events"])["suggestions"] == []
    assert mock_learning_suggestions(records["feedback"], records["events"], "unknown")["suggestions"] == []


def test_demo_user_journey_edit_feedback_confirm_task_and_schedule(monkeypatch, tmp_path):
    """以展示使用者的路徑驗證：修改課程 → 模擬 LINE 回覆 → Mock AI → 確認任務 → 排程。"""
    from exporter import export_learning_markdown
    from scheduler import make_plan
    from plan_bridge import normalize_plan_result

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "real")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    storage.save_json(storage.data_path("events"), [{"event_id": "untouched-real-class"}])

    try:
        storage.select_demo_storage(True)
        seed_demo_data(now=NOW)
        course = storage.load_json(storage.data_path("events"))[0]
        storage.update_event({**course, "title": "我現場修改的課程"})
        edited = storage.load_json(storage.data_path("events"))[0]
        assert edited["title"] == "我現場修改的課程"

        feedback = {
            "feedback_id": "demo-feedback-new", "user_id": "demo_user_001",
            "event_id": edited["event_id"], "class_date": NOW.date().isoformat(),
            "received_at": (NOW + timedelta(seconds=1)).isoformat(timespec="seconds"), "source": "demo",
            "content": "課程內容還有一個問題需要練習", "progress": 2,
            "reminder_id": "", "webhook_event_id": "demo-event-new",
        }
        assert storage.save_feedback(feedback) is True
        response = mock_learning_suggestions(
            storage.load_json(storage.data_path("feedback")),
            storage.load_json(storage.data_path("events")),
        )
        suggestion = response["suggestions"][0]
        assert suggestion["source_feedback_id"] == feedback["feedback_id"]
        # 檢查使用者確認的建議才會成為正式任務
        assert not any(t.get("source_feedback_id") == suggestion["source_feedback_id"]
                       for t in storage.load_json(storage.data_path("tasks")))
        task = {
            "task_id": "confirmed-demo-task", "user_id": "demo_user_001",
            "subject": suggestion["topic"], "title": suggestion["suggested_task"],
            "deadline": (NOW.date() + timedelta(days=7)).isoformat(),
            "estimated_minutes": 30, "status": "pending",
            "preferred_availability_id": "",
            "source_feedback_id": suggestion["source_feedback_id"],
            "source": "ai_confirmed",
        }
        storage.add_task_to_storage(task)
        tasks = storage.load_json(storage.data_path("tasks"))
        slots = storage.load_json(storage.data_path("availability"))
        planned = make_plan(tasks, slots, storage.load_json(storage.data_path("plan")), NOW)
        normalized = normalize_plan_result(planned, "demo_user_001")
        assert any(row["task_id"] == task["task_id"] and row["status"] == "scheduled"
                   for row in normalized)

        records = {name: storage.load_json(storage.data_path(name))
                   for name in ("events", "tasks", "availability", "plan",
                                "reminders", "feedback")}
        markdown = export_learning_markdown(records, NOW, "demo_user_001")
        assert "我現場修改的課程" in markdown
        assert "課程內容還有一個問題需要練習" in markdown
    finally:
        storage.select_demo_storage(False)
    assert storage.load_json(storage.data_path("events")) == [
        {"event_id": "untouched-real-class"}
    ]
