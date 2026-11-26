"""Worker regression tests for atomic reservation and user preferences."""
import pytest
import reminder_worker as worker
import storage


def test_reminder_reservation_keeps_retry_key_and_other_records(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    first = {"reminder_id": "r1", "user_id": "u1", "retry_key": "key1", "status": "pending"}
    saved = worker._reserve_reminder(first)
    assert saved["retry_key"] == "key1"
    storage.update_json(storage.data_path("reminders"), lambda rows: rows + [
        {"reminder_id": "unrelated", "user_id": "u2", "status": "pending"}
    ])
    again = worker._reserve_reminder({**first, "retry_key": "new-key"})
    assert again["retry_key"] == "key1"
    worker._mark_reminder("r1", "sent", "2026-11-23T21:00:00+08:00")
    items = storage.load_json(storage.data_path("reminders"))
    assert len(items) == 2
    assert next(row for row in items if row["reminder_id"] == "r1")["status"] == "sent"
    assert next(row for row in items if row["reminder_id"] == "unrelated")["status"] == "pending"


def test_disabled_class_feedback_does_not_push(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    for name in ("events", "tasks", "plan", "availability", "reminders"):
        storage.save_json(storage.data_path(name), [])
    storage.save_json(storage.data_path("users"), [
        {"user_id": "u1", "line_user_id": "U123", "reminders_enabled": False}
    ])
    monkeypatch.setattr(worker, "get_due_events", lambda events, now, reminders: [
        {"reminder_id": "r1", "user_id": "u1", "kind": "class_feedback",
         "event_id": "e1", "class_date": "2026-11-23", "status": "pending",
         "retry_key": "abc"}
    ])
    monkeypatch.setattr(worker, "get_due_study_reminders", lambda *args: [])
    monkeypatch.setattr(worker, "push_line_message", lambda *args: pytest.fail("should not push"))
    class StopLoop(Exception):
        pass
    monkeypatch.setattr(worker.time, "sleep", lambda duration: (_ for _ in ()).throw(StopLoop()))
    with pytest.raises(StopLoop):
        worker.run_reminder_worker()
    assert storage.load_json(storage.data_path("reminders")) == []


def test_study_reminder_mentions_class_overlap_choice(monkeypatch, tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)
    user = {"user_id": "u1", "line_user_id": "U-example",
            "study_reminders_enabled": True, "reminders_enabled": True}
    task = {"task_id": "t1", "user_id": "u1", "status": "pending",
            "title": "複習控制系統"}
    slot = {"availability_id": "slot1", "user_id": "u1",
            "date": "2026-11-27", "start_time": "19:00", "available_minutes": 45}
    plan = {"task_id": "t1", "user_id": "u1", "availability_id": "slot1",
            "status": "scheduled", "class_override": "請假"}
    for name, rows in (("events", []), ("tasks", [task]), ("availability", [slot]),
                       ("users", [user]), ("plan", [plan]), ("reminders", [])):
        storage.save_json(storage.data_path(name), rows)
    sent = []

    def fake_push(_user, _reminder, message):
        sent.append(message)
        return True

    monkeypatch.setattr(worker, "push_line_message", fake_push)
    results = worker.run_reminder_worker_once(
        datetime(2026, 11, 27, 19, tzinfo=ZoneInfo("Asia/Taipei")))
    assert len(results) == 1
    assert results[0]["status"] == "sent"
    assert "請假" in sent[0]
    assert "與課程重疊" in sent[0]
