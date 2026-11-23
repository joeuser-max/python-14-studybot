"""Regression tests for LINE binding, guided notes, and study reminder retries."""
import base64
import hashlib
import hmac
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import line_bot
import storage
from scheduler import get_due_study_reminders

TZ = ZoneInfo("Asia/Taipei")


def _sample_event():
    return {
        "event_id": "event_1", "user_id": "demo_user_001",
        "event_type": "class", "title": "控制系統",
        "weekday": 1, "start_time": "13:00", "end_time": "15:00",
        "offset_minutes": 10, "prompt_template": "class_feedback", "enabled": True,
    }


def test_failed_study_reminder_retry_does_not_crash():
    when = datetime(2026, 11, 23, 19, tzinfo=TZ)
    tasks = [{"task_id": "t1", "user_id": "demo_user_001", "status": "pending"}]
    slots = [{"availability_id": "a1", "user_id": "demo_user_001", "date": "2026-11-23",
              "start_time": "19:00", "available_minutes": 60}]
    plan = [{"task_id": "t1", "availability_id": "a1", "status": "scheduled"}]
    users = [{"user_id": "demo_user_001", "line_user_id": "U123",
              "study_reminders_enabled": True}]
    failed = [{"reminder_id": "r1", "user_id": "demo_user_001", "task_id": "t1",
               "availability_id": "a1", "kind": "study_session", "status": "failed"}]
    due = get_due_study_reminders(tasks, plan, slots, users, when, failed)
    assert len(due) == 1
    assert due[0]["reminder_id"] == "r1"


def test_guided_note_flow_and_deduplication(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.save_json(storage.data_path("events"), [_sample_event()])
    storage.save_json(storage.data_path("reminders"), [{
        "reminder_id": "r1", "user_id": "demo_user_001",
        "event_id": "event_1", "class_date": "2026-11-23",
        "kind": "class_feedback", "status": "sent",
    }])
    now = datetime(2026, 11, 23, 16, tzinfo=TZ)
    user = {"user_id": "demo_user_001"}
    assert "星期" in line_bot.handle_line_text(user, "補筆記", "e1", now)
    assert "時段" in line_bot.handle_line_text(user, "1", "e2", now)
    assert "請直接輸入筆記" in line_bot.handle_line_text(user, "1", "e3", now)
    assert "已儲存" in line_bot.handle_line_text(user, "今天學會根軌跡", "e4", now)
    notes = storage.load_json(storage.data_path("feedback"))
    assert len(notes) == 1
    assert notes[0]["reminder_id"] == "r1"
    assert notes[0]["event_id"] == "event_1"
    assert not line_bot.save_feedback(notes[0])["saved"]
    assert len(storage.load_json(storage.data_path("feedback"))) == 1


def test_verified_webhook_can_bind_line_id(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-secret")
    monkeypatch.setenv("LINE_BIND_CODE", "safe-example-code")
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    replies = []
    monkeypatch.setattr(line_bot, "_reply_line", lambda token, text: replies.append(text))
    payload = {"events": [{"webhookEventId": "e1", "type": "message",
                           "source": {"type": "user", "userId": "U123"},
                           "message": {"type": "text", "text": "綁定 safe-example-code"},
                           "replyToken": "test-token"}]}
    body = json.dumps(payload).encode("utf-8")
    signature = base64.b64encode(hmac.new(b"test-secret", body, hashlib.sha256).digest()).decode()
    client = line_bot.create_app().test_client()
    for _ in range(2):
        response = client.post("/webhook", data=body,
                               headers={"X-Line-Signature": signature, "Content-Type": "application/json"})
        assert response.status_code == 200
    users = storage.load_json(storage.data_path("users"))
    assert len(users) == 1
    assert users[0]["line_user_id"] == "U123"
    assert len(storage.load_json(storage.data_path("processed_webhooks"))) == 1
    assert len(replies) == 1


def test_simulated_push_is_not_treated_as_success(monkeypatch):
    from reminder_worker import push_line_message
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    assert push_line_message({"line_user_id": "U123"}, {"user_id": "demo_user_001"}, "hello") is False
