"""保留 main 回歸保障，調整為 btesting 的 LINE 互動介面。"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import line_bot
import storage
from scheduler import get_due_study_reminders

TZ = ZoneInfo("Asia/Taipei")


def _post_signed(client, secret, event):
    body = json.dumps({"events": [event]}, ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode("ascii")
    return client.post(
        "/webhook", data=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def _event(event_id, text, user_id="U123"):
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id,
            "source": {"type": "user", "userId": user_id},
            "message": {"type": "text", "text": text}}


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
    secret = "test-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    replies = []
    monkeypatch.setattr(
        line_bot, "reply_line_message",
        lambda token, text, choices=None: replies.append((text, choices)),
    )

    now = datetime.now(TZ)
    day = (now - timedelta(days=1)).date()
    weekday = day.isoweekday()
    storage.save_json(storage.data_path("events"), [{
        "event_id": "event_1", "user_id": "demo_user_001",
        "event_type": "class", "title": "控制系統", "weekday": weekday,
        "start_time": "00:00", "end_time": "00:01",
        "offset_minutes": 0, "prompt_template": "class_feedback", "enabled": True,
    }])
    storage.save_json(storage.data_path("users"), [{
        "user_id": "demo_user_001", "line_user_id": "U123",
        "reminders_enabled": True, "ai_after_class_enabled": False,
    }])
    storage.save_json(storage.data_path("reminders"), [{
        "reminder_id": "r1", "user_id": "demo_user_001",
        "event_id": "event_1", "class_date": day.isoformat(),
        "kind": "class_feedback", "status": "sent",
    }])

    client = line_bot.create_app().test_client()
    weekday_text = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]
    for event_id, text in [
        ("e1", "補筆記"), ("e2", weekday_text), ("e3", "1"),
        ("e4", "3"), ("e5", "今天學會根軌跡"),
    ]:
        assert _post_signed(client, secret, _event(event_id, text)).status_code == 200
    assert _post_signed(client, secret, _event("e5", "今天學會根軌跡")).status_code == 200
    notes = storage.load_json(storage.data_path("feedback"))
    assert len(notes) == 1
    assert notes[0]["reminder_id"] == "r1"
    assert notes[0]["progress"] == 3
    assert notes[0]["content"] == "今天學會根軌跡"
    assert "筆記與自評進度已儲存" in replies[-1][0]


def test_verified_webhook_can_bind_line_id(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    secret = "test-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.setenv("LINE_BINDING_CODE", "safe-example-code")
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    replies = []
    monkeypatch.setattr(
        line_bot, "reply_line_message",
        lambda token, text, choices=None: replies.append(text),
    )
    client = line_bot.create_app().test_client()
    event = _event("bind1", "綁定 safe-example-code")
    for _ in range(2):
        assert _post_signed(client, secret, event).status_code == 200
    users = storage.load_json(storage.data_path("users"))
    assert len(users) == 1
    assert users[0]["line_user_id"] == "U123"
    assert len(storage.load_json(storage.data_path("processed_webhooks"))) == 1
    assert len(replies) == 1

    # 有效綁定碼也不能把現有帳號覆綁成別人的 LINE。
    assert _post_signed(client, secret, _event(
        "bind2", "綁定 safe-example-code", "U-OTHER"
    )).status_code == 200
    users = storage.load_json(storage.data_path("users"))
    assert users[0]["line_user_id"] == "U123"
    assert "已綁定其他 LINE 使用者" in replies[-1]


def test_simulated_push_is_not_treated_as_success(monkeypatch):
    from reminder_worker import push_line_message
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    assert push_line_message(
        {"line_user_id": "U123"}, {"user_id": "demo_user_001"}, "hello"
    ) is False
