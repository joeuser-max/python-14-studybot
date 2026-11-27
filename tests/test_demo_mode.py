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
    assert len(records["events"]) == 14
    assert len(records["tasks"]) == 14
    assert len(records["plan"]) == 3  # 豐富 Demo 保留現有安排，也保留可手動拖排的任務
    assert len([t for t in records["tasks"] if t["status"] == "pending"]) == 11
    assert len(records["tasks"]) - len(records["plan"]) >= 8
    assert len(records["feedback"]) == 5
    assert len(records["external_events"]) == 3
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
        assert len(original) == 14

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
    assert result["suggestions"][0]["source_feedback_id"] == max(records["feedback"], key=lambda f: f["received_at"])["feedback_id"]
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
            "deadline": (NOW.date() + timedelta(days=2)).isoformat(),
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


def test_rich_demo_keeps_manual_auto_pending_and_metrics_consistent(monkeypatch, tmp_path):
    from study_metrics import personal_metrics
    from tracker import calculate_response_rate
    from week_planner import board_payload, fill_remaining, place_manual

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    fixture = sample_records(NOW)
    for name, records in fixture.items():
        storage.save_json(storage.data_path(name), records)

    first_board = board_payload("demo_user_001", NOW)
    assert len(first_board["courses"]) == 14
    assert len(first_board["external"]) == 3
    assert len(first_board["scheduled"]) == 3
    assert len(first_board["tasks"]) == 8
    assert {p["source"] for p in first_board["scheduled"]} == {"manual", "auto"}

    # The demo's occupied times cannot overlap courses or external events.
    from week_planner import _busy, _datetime
    for p in first_board["scheduled"]:
        begin, end = _datetime(p["start"]), _datetime(p["end"])
        date_value = begin.date()
        busy = _busy(fixture["events"], fixture["external_events"], fixture["tasks"],
                     fixture["availability"], fixture["plan"], date_value,
                     "demo_user_001", p["task_id"])
        assert not any(begin < finish and start < end for start, finish in busy)

    completion = personal_metrics(fixture["tasks"], fixture["reminders"], "demo_user_001")
    assert completion["completed"] == 3
    assert completion["total"] == 14
    assert completion["confirmed_sessions"] == 2
    assert completion["xp"] == 80

    rate = calculate_response_rate(fixture["reminders"], fixture["feedback"], "demo_user_001")
    assert rate["sent"] == 6
    assert rate["answered"] == 5

    # Only the selected task is affected by manual placement.
    pinned = next(p for p in fixture["plan"] if p["source"] == "manual")
    new_entry = place_manual("demo_user_001", first_board["tasks"][0]["task_id"],
                             first_board["days"][1]["date"], "E", 1, NOW)
    assert new_entry["source"] == "manual"
    after = storage.load_json(storage.data_path("plan"))
    assert len(after) == 4
    assert next(p for p in after if p["task_id"] == pinned["task_id"]) == pinned


def test_rich_demo_is_date_relative():
    morning = datetime(2026, 11, 29, 8, 0, tzinfo=TZ)
    fixture = sample_records(morning)
    today = morning.date()
    assert all(today <= datetime.fromisoformat(e["start"]).date()
               <= today + timedelta(days=6) for e in fixture["external_events"])
    assert all(today < datetime.fromisoformat(p["scheduled_start"]).date()
               for p in fixture["plan"])


def test_rich_demo_line_mock_default_day_has_many_events():
    from mock_day import one_day_timeline, recommended_demo_day

    fixture = sample_records(NOW)
    today = NOW.date()
    days = [today + timedelta(days=offset) for offset in range(7)]
    tasks = {t["task_id"]: t for t in fixture["tasks"]}
    slots = {a["availability_id"]: a for a in fixture["availability"]}
    scheduled = []
    for entry in fixture["plan"]:
        slot = slots[entry["availability_id"]]
        start = datetime.fromisoformat(entry["scheduled_start"])
        scheduled.append({
            "task_id": entry["task_id"],
            "title": tasks[entry["task_id"]]["title"],
            "day": slot["date"],
            "start": start.isoformat(),
            "end": (start + timedelta(minutes=entry["scheduled_minutes"])).isoformat(),
        })
    chosen = recommended_demo_day(days, fixture["events"], scheduled)
    timeline = one_day_timeline(chosen, fixture["events"], scheduled)
    assert len(timeline) >= 8
    assert any(e["kind"] == "line_note" for e in timeline)
    assert all(e["at"].date() == chosen for e in timeline)
