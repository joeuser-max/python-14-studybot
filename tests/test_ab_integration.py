import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import line_bot
import reminder_worker
import storage
from exporter import export_learning_markdown
from plan_bridge import normalize_plan_result
from scheduler import make_plan
from storage import data_path, load_json, save_json
from tracker import calculate_response_rate


TZ = ZoneInfo("Asia/Taipei")


def init_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    for name in storage.FILES:
        save_json(data_path(name), [])


def send_webhook(client, secret, event):
    body = json.dumps({"events": [event]}, ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    return client.post(
        "/webhook",
        data=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def test_streamlit_plan_bridge_and_worker_share_data(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    user = {
        "user_id": "demo_user_001",
        "line_user_id": "U-test",
        "reminders_enabled": True,
        "study_reminders_enabled": True,
    }
    task = {
        "task_id": "task-1",
        "user_id": user["user_id"],
        "subject": "Python",
        "title": "完成期末作業",
        "deadline": "2026-11-28",
        "estimated_minutes": 30,
        "status": "pending",
        "preferred_availability_id": "",
    }
    slot = {
        "availability_id": "slot-1",
        "user_id": user["user_id"],
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 45,
    }
    raw_plan = make_plan([task], [slot], [], datetime(2026, 11, 23, 16, tzinfo=TZ))
    plan = normalize_plan_result(raw_plan, user["user_id"])
    assert plan[0]["status"] == "scheduled"
    assert plan[0]["user_id"] == user["user_id"]
    save_json(data_path("tasks"), [task])
    save_json(data_path("availability"), [slot])
    save_json(data_path("plan"), plan)
    save_json(data_path("users"), [user])

    calls = []

    def accepted_push(target_user, reminder, text):
        calls.append((target_user["user_id"], reminder["retry_key"], text))
        return True

    monkeypatch.setattr(reminder_worker, "push_line_message", accepted_push)
    now = datetime(2026, 11, 24, 19, tzinfo=TZ)
    first = reminder_worker.run_reminder_worker_once(now)
    second = reminder_worker.run_reminder_worker_once(now)

    assert len(first) == 1
    assert first[0]["kind"] == "study_session"
    assert first[0]["status"] == "sent"
    assert second == []
    assert len(calls) == 1
    assert load_json(data_path("reminders"))[0]["status"] == "sent"


def test_failed_study_push_reuses_retry_key(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    user = {
        "user_id": "demo_user_001", "line_user_id": "U-test",
        "study_reminders_enabled": True,
    }
    task = {"task_id": "task-1", "user_id": user["user_id"], "title": "讀書",
            "status": "pending"}
    slot = {"availability_id": "slot-1", "user_id": user["user_id"],
            "date": "2026-11-24", "start_time": "19:00", "available_minutes": 30}
    plan = [{"user_id": user["user_id"], "task_id": task["task_id"],
             "availability_id": slot["availability_id"], "status": "scheduled"}]
    save_json(data_path("tasks"), [task])
    save_json(data_path("availability"), [slot])
    save_json(data_path("plan"), plan)
    save_json(data_path("users"), [user])
    keys = []

    def failed_then_accepted(target_user, reminder, text):
        keys.append(reminder["retry_key"])
        if len(keys) == 1:
            raise requests.ConnectionError("temporary network failure")
        return True

    monkeypatch.setattr(reminder_worker, "push_line_message", failed_then_accepted)
    due = datetime(2026, 11, 24, 19, tzinfo=TZ)
    first = reminder_worker.run_reminder_worker_once(due)
    retry = reminder_worker.run_reminder_worker_once(due + timedelta(minutes=6))

    assert first[0]["status"] == "failed"
    assert retry[0]["status"] == "sent"
    assert keys[0] == keys[1]


def test_unscheduled_alert_state_is_saved_and_not_resent(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    user_id = "demo_user_001"
    task = {
        "task_id": "task-no-slot",
        "user_id": user_id,
        "subject": "Python",
        "title": "沒有可用時段的任務",
        "deadline": "2026-11-30",
        "estimated_minutes": 60,
        "status": "pending",
        "preferred_availability_id": "",
    }
    user = {
        "user_id": user_id,
        "line_user_id": "U-test",
        "reminders_enabled": True,
        "study_reminders_enabled": False,
    }
    result = make_plan([task], [], [], datetime(2026, 11, 23, 16, tzinfo=TZ))
    plan = normalize_plan_result(result, user_id)
    assert result["new_alerts"] == [task["task_id"]]
    assert plan[0]["unscheduled_alerted"] is False
    save_json(data_path("tasks"), [task])
    save_json(data_path("plan"), plan)
    save_json(data_path("users"), [user])
    calls = []
    monkeypatch.setattr(
        reminder_worker,
        "push_line_message",
        lambda target_user, reminder, text: calls.append(reminder["reminder_id"]) or True,
    )

    delivered = reminder_worker.run_reminder_worker_once(
        datetime(2026, 11, 23, 16, tzinfo=TZ)
    )
    saved_plan = load_json(data_path("plan"))
    assert delivered[0]["kind"] == "unscheduled_alert"
    assert saved_plan[0]["unscheduled_alerted"] is True
    next_result = make_plan(
        [task], [], saved_plan, datetime(2026, 11, 23, 16, 1, tzinfo=TZ)
    )
    assert next_result["new_alerts"] == []

    repeated = reminder_worker.run_reminder_worker_once(
        datetime(2026, 11, 23, 16, 1, tzinfo=TZ)
    )
    assert repeated == []
    assert len(calls) == 1


def test_signed_line_webhook_binds_and_saves_course_note(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    secret = "test-channel-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.setenv("LINE_BINDING_CODE", "pair-code")
    replies = []
    monkeypatch.setattr(
        line_bot,
        "reply_line_message",
        lambda reply_token, text, choices=None: replies.append((text, choices)),
    )
    client = line_bot.create_app().test_client()

    bind = {
        "type": "message",
        "webhookEventId": "webhook-bind",
        "replyToken": "reply-bind",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "綁定 pair-code"},
    }
    response = send_webhook(client, secret, bind)
    assert response.status_code == 200
    assert load_json(data_path("users"))[0]["user_id"] == "demo_user_001"

    yesterday = datetime.now(TZ).date() - timedelta(days=1)
    weekday = yesterday.isoweekday()
    event = {
        "event_id": "class-1",
        "user_id": "demo_user_001",
        "event_type": "class",
        "title": "程式設計",
        "weekday": weekday,
        "start_time": "00:00",
        "end_time": "00:01",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    save_json(data_path("events"), [event])
    save_json(data_path("reminders"), [{
        "reminder_id": "reminder-1",
        "user_id": "demo_user_001",
        "event_id": "class-1",
        "class_date": yesterday.isoformat(),
        "kind": "class_feedback",
        "status": "sent",
    }])

    messages = [
        ("webhook-start", "補筆記"),
        ("webhook-weekday", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]),
        ("webhook-slot", "1"),
        ("webhook-note", "今天複習了函式與清單"),
    ]
    for webhook_id, text in messages:
        response = send_webhook(client, secret, {
            "type": "message",
            "webhookEventId": webhook_id,
            "replyToken": f"reply-{webhook_id}",
            "source": {"userId": "U-test"},
            "message": {"type": "text", "text": text},
        })
        assert response.status_code == 200

    feedback = load_json(data_path("feedback"))
    assert len(feedback) == 1
    assert feedback[0]["user_id"] == "demo_user_001"
    assert feedback[0]["event_id"] == "class-1"
    assert feedback[0]["class_date"] == yesterday.isoformat()
    assert feedback[0]["reminder_id"] == "reminder-1"
    assert feedback[0]["webhook_event_id"] == "webhook-note"
    assert load_json(data_path("pending_notes")) == []
    stats = calculate_response_rate(
        load_json(data_path("reminders")),
        feedback,
        "demo_user_001",
    )
    assert stats == {"sent": 1, "answered": 1, "rate": 100.0}
    records = {
        name: load_json(data_path(name))
        for name in ("events", "tasks", "availability", "plan", "reminders", "feedback")
    }
    markdown = export_learning_markdown(records, datetime.now(TZ), "demo_user_001")
    assert "今天複習了函式與清單" in markdown
    assert "U-test" not in markdown


def test_webhook_rejects_bad_signature(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test-secret")
    client = line_bot.create_app().test_client()
    response = client.post(
        "/webhook",
        data=b'{"events":[]}',
        headers={"X-Line-Signature": "invalid"},
    )
    assert response.status_code == 401
