from datetime import datetime
from zoneinfo import ZoneInfo
import storage
import line_bot
import reminder_worker
from scheduler import get_due_events

TZ = ZoneInfo("Asia/Taipei")

def test_class_end_reminder_is_sent_when_end_time_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    event = {
        "event_id": "class-1",
        "user_id": "user-1",
        "event_type": "class",
        "title": "控制系統",
        "weekday": 5,
        "start_time": "12:00",
        "end_time": "13:17",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    user = {
        "user_id": "user-1",
        "line_user_id": "LINE-USER",
        "reminders_enabled": True,
    }
    previous_reminder = {
        "reminder_id": "class_class-1_2026-11-27",
        "user_id": "user-1",
        "event_id": "class-1",
        "class_date": "2026-11-27",
        "kind": "class_feedback",
        "scheduled_at": "2026-11-27T12:54+08:00",
        "status": "sent",
        "sent_at": "2026-11-27T12:54+08:00",
    }
    for name in ("tasks", "plan", "availability"):
        storage.save_json(storage.data_path(name), [])
    storage.save_json(storage.data_path("events"), [event])
    storage.save_json(storage.data_path("users"), [user])
    storage.save_json(storage.data_path("reminders"), [previous_reminder])

    pushed = []
    monkeypatch.setattr(
        reminder_worker,
        "push_line_message",
        lambda target, reminder, text: pushed.append((reminder, text)) or True,
    )
    now = datetime(2026, 11, 27, 13, 18, tzinfo=TZ)
    attempted = reminder_worker.run_reminder_worker_once(now)

    assert len(attempted) == 1
    assert attempted[0]["scheduled_at"] == "2026-11-27T13:17+08:00"
    assert attempted[0]["reminder_id"] != previous_reminder["reminder_id"]
    assert "控制系統" in pushed[0][1]
    assert "補筆記" in pushed[0][1]
    assert line_bot._find_class_reminder("user-1", "class-1", "2026-11-27") == attempted[0]["reminder_id"]
    assert reminder_worker.run_reminder_worker_once(now) == []

def test_class_end_reminder_catches_up_for_one_hour():
    event = {
        "event_id": "class-1",
        "user_id": "user-1",
        "event_type": "class",
        "title": "控制系統",
        "weekday": 5,
        "start_time": "12:00",
        "end_time": "13:17",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }

    due = get_due_events(
        [event],
        datetime(2026, 11, 27, 14, 16, tzinfo=TZ),
        [],
    )
    expired = get_due_events(
        [event],
        datetime(2026, 11, 27, 14, 18, tzinfo=TZ),
        [],
    )

    assert len(due) == 1
    assert due[0]["scheduled_at"] == "2026-11-27T13:17+08:00"
    assert expired == []
