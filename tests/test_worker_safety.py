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
