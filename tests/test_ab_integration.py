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
    assert calls[0][2] == (
        "讀書時段開始囉！任務：科目「Python」，完成期末作業，請開始完成。"
    )
    assert load_json(data_path("reminders"))[0]["status"] == "sent"


def test_failed_study_push_reuses_retry_key(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    user = {
        "user_id": "demo_user_001", "line_user_id": "U-test",
        "study_reminders_enabled": True,
    }
    task = {"task_id": "task-1", "user_id": user["user_id"], "title": "讀書",
            "estimated_minutes": 30, "status": "pending"}
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
        lambda target_user, reminder, text: calls.append(
            (reminder["reminder_id"], text)
        ) or True,
    )

    delivered = reminder_worker.run_reminder_worker_once(
        datetime(2026, 11, 23, 16, tzinfo=TZ)
    )
    saved_plan = load_json(data_path("plan"))
    assert delivered[0]["kind"] == "unscheduled_alert"
    assert calls[0][1] == (
        "提醒：科目「Python」，任務「沒有可用時段的任務」尚未排入。"
        "原因：找不到足夠且不衝突的可用時段"
    )
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

    def unexpected_ai_call(*args, **kwargs):
        raise AssertionError("AI must not run without user consent")

    monkeypatch.setattr(reminder_worker, "organize_class_feedback", unexpected_ai_call)
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
        ("webhook-progress", "4"),
        ("webhook-course-progress", "Ch.4 p.22"),
        ("webhook-note", "今天複習了函式與清單"),
        ("webhook-skip-task", "先不用"),
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
    assert feedback[0]["course_progress"] == "Ch.4 p.22"
    assert feedback[0]["event_id"] == "class-1"
    assert feedback[0]["class_date"] == yesterday.isoformat()
    assert feedback[0]["reminder_id"] == "reminder-1"
    assert feedback[0]["webhook_event_id"] == "webhook-note"
    assert feedback[0]["progress"] == 4
    assert "ai_analysis" not in feedback[0]
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
    assert "自評理解進度：4/5" in markdown
    assert "上課進度：Ch.4 p.22" in markdown
    assert "U-test" not in markdown


def test_ai_feedback_is_delivered_after_user_schedules_study(monkeypatch, tmp_path):
    init_data_dir(monkeypatch, tmp_path)
    secret = "test-channel-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    now = datetime.now(TZ)
    class_date = (now.date() - timedelta(days=1)).isoformat()
    weekday = (now.date() - timedelta(days=1)).isoweekday()
    user = {
        "user_id": "demo_user_001",
        "line_user_id": "U-test",
        "reminders_enabled": True,
        "study_reminders_enabled": True,
        "ai_after_class_enabled": True,
    }
    course = {
        "event_id": "class-1",
        "user_id": user["user_id"],
        "event_type": "class",
        "title": "程式設計",
        "weekday": weekday,
        "start_time": "00:00",
        "end_time": "00:01",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    slot = {
        "availability_id": "slot-1",
        "user_id": user["user_id"],
        "date": (now.date() + timedelta(days=1)).isoformat(),
        "start_time": "20:00",
        "available_minutes": 60,
    }
    save_json(data_path("users"), [user])
    save_json(data_path("events"), [course])
    save_json(data_path("availability"), [slot])
    replies = []
    analysis = {
        "summary": "本堂介紹函式與清單。",
        "key_points": ["函式可重複使用", "清單可存放多筆資料"],
        "unresolved_questions": ["尚不清楚函式參數的預設值"],
        "topic_tags": ["函式", "清單"],
        "suggested_task": "練習撰寫含參數的函式",
        "estimated_minutes": 45,
    }
    monkeypatch.setattr(
        line_bot,
        "reply_line_message",
        lambda reply_token, text, choices=None: replies.append((text, choices)),
    )
    client = line_bot.create_app().test_client()

    messages = [
        ("ai-start", "補筆記"),
        ("ai-weekday", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]),
        ("ai-slot", "1"),
        ("ai-progress", "2"),
        ("ai-course-progress", "Ch.2 第 3 節"),
        ("ai-note", "今天學習函式和清單，還不清楚預設參數。"),
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

    feedback = load_json(data_path("feedback"))[0]
    assert feedback["progress"] == 2
    assert feedback["course_progress"] == "Ch.2 第 3 節"
    assert "ai_analysis" not in feedback
    assert load_json(data_path("tasks")) == []
    assert load_json(data_path("pending_notes"))[0]["stage"] == "study_minutes"
    assert "讀書時段開始時" in replies[-1][0]

    response = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "ai-minutes",
        "replyToken": "reply-ai-minutes",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "30"},
    })
    assert response.status_code == 200
    assert load_json(data_path("tasks")) == []
    assert load_json(data_path("pending_notes"))[0]["stage"] == "study_deadline"

    response = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "ai-deadline-invalid",
        "replyToken": "reply-ai-deadline-invalid",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "2026-02-31"},
    })
    assert response.status_code == 200
    assert load_json(data_path("tasks")) == []
    assert load_json(data_path("pending_notes"))[0]["stage"] == "study_deadline"

    response = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "ai-deadline",
        "replyToken": "reply-ai-deadline",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": slot["date"]},
    })
    assert response.status_code == 200
    assert load_json(data_path("pending_notes"))[0]["stage"] == "study_slot"
    response = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "ai-slot-choice",
        "replyToken": "reply-ai-slot-choice",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "1"},
    })
    assert response.status_code == 200
    tasks = load_json(data_path("tasks"))
    plan = load_json(data_path("plan"))
    assert len(tasks) == len(plan) == 1
    assert tasks[0]["source_feedback_id"] == feedback["feedback_id"]
    assert tasks[0]["source_event_id"] == "class-1"
    assert tasks[0]["source_class_date"] == class_date
    assert tasks[0]["reading_progress"] == "Ch.2 第 3 節"
    assert tasks[0]["deadline"] == slot["date"]
    assert tasks[0]["estimated_minutes"] == 30
    assert plan[0]["status"] == "scheduled"
    assert plan[0]["availability_id"] == "slot-1"
    assert load_json(data_path("pending_notes")) == []

    pushes = []
    monkeypatch.setattr(
        reminder_worker,
        "organize_class_feedback",
        lambda saved_feedback, course_title: analysis,
    )
    monkeypatch.setattr(
        reminder_worker,
        "push_line_message",
        lambda target_user, reminder, text: pushes.append(text) or True,
    )
    study_at = datetime.fromisoformat(f"{slot['date']}T{slot['start_time']}:00+08:00")
    delivered = reminder_worker.run_reminder_worker_once(study_at)
    assert len(delivered) == 1
    assert delivered[0]["kind"] == "study_session"
    assert "本堂介紹函式與清單" in pushes[0]
    assert "函式可重複使用" in pushes[0]
    assert "尚不清楚函式參數的預設值" in pushes[0]
    assert "練習撰寫含參數的函式" in pushes[0]
    assert "本次排程依你設定的 30 分鐘" in pushes[0]
    assert load_json(data_path("feedback"))[0]["ai_analysis"] == analysis

    duplicate = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "ai-slot-choice",
        "replyToken": "reply-ai-slot-choice-duplicate",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "1"},
    })
    assert duplicate.status_code == 200
    assert len(load_json(data_path("tasks"))) == 1
    records = {
        name: load_json(data_path(name))
        for name in ("events", "tasks", "availability", "plan", "reminders", "feedback")
    }
    markdown = export_learning_markdown(records, now, user["user_id"])
    assert "本堂介紹函式與清單" in markdown
    assert "練習撰寫含參數的函式" in markdown
    assert "## 可搜尋筆記庫" in markdown
    assert "主題：函式、清單" in markdown
    assert "來源課程：程式設計" in markdown


def test_ai_enabled_note_is_saved_without_calling_ai_before_scheduling(
    monkeypatch, tmp_path
):
    init_data_dir(monkeypatch, tmp_path)
    secret = "test-channel-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    today = datetime.now(TZ).date()
    class_date = today - timedelta(days=1)
    weekday = class_date.isoweekday()
    user = {
        "user_id": "demo_user_001",
        "line_user_id": "U-test",
        "ai_after_class_enabled": True,
    }
    course = {
        "event_id": "class-1",
        "user_id": user["user_id"],
        "event_type": "class",
        "title": "程式設計",
        "weekday": weekday,
        "start_time": "00:00",
        "end_time": "00:01",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    save_json(data_path("users"), [user])
    save_json(data_path("events"), [course])

    replies = []
    monkeypatch.setattr(
        line_bot,
        "reply_line_message",
        lambda reply_token, text, choices=None: replies.append(text),
    )
    client = line_bot.create_app().test_client()
    messages = [
        ("failure-start", "補筆記"),
        ("failure-weekday", ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]),
        ("failure-slot", "1"),
        ("failure-progress", "3"),
        ("failure-course-progress", "第一章"),
        ("failure-note", "今天複習了函式參數"),
        ("failure-skip-task", "先不用"),
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
    assert feedback[0]["content"] == "今天複習了函式參數"
    assert feedback[0]["progress"] == 3
    assert feedback[0]["course_progress"] == "第一章"
    assert "ai_analysis" not in feedback[0]
    assert load_json(data_path("pending_notes")) == []
    assert "筆記已保存，未新增讀書任務" in replies[-1]


def test_study_checkin_records_completion_and_replans_only_remaining_minutes(
    monkeypatch, tmp_path
):
    init_data_dir(monkeypatch, tmp_path)
    secret = "test-channel-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    now = datetime.now(TZ).replace(second=0, microsecond=0)
    old_start = now - timedelta(minutes=35)
    next_date = (now.date() + timedelta(days=1)).isoformat()
    user = {
        "user_id": "demo_user_001",
        "line_user_id": "U-test",
        "study_reminders_enabled": True,
    }
    task = {
        "task_id": "task-progress",
        "user_id": user["user_id"],
        "subject": "Python",
        "title": "複習函式",
        "deadline": (now.date() + timedelta(days=7)).isoformat(),
        "estimated_minutes": 30,
        "status": "pending",
        "preferred_availability_id": "old-slot",
    }
    slots = [
        {
            "availability_id": "old-slot",
            "user_id": user["user_id"],
            "date": old_start.date().isoformat(),
            "start_time": old_start.strftime("%H:%M"),
            "available_minutes": 60,
        },
        {
            "availability_id": "future-slot",
            "user_id": user["user_id"],
            "date": next_date,
            "start_time": "20:00",
            "available_minutes": 60,
        },
    ]
    plan = [{
        "task_id": task["task_id"],
        "user_id": user["user_id"],
        "availability_id": "old-slot",
        "status": "scheduled",
        "source": "manual",
    }]
    save_json(data_path("users"), [user])
    save_json(data_path("tasks"), [task])
    save_json(data_path("availability"), slots)
    save_json(data_path("plan"), plan)

    pushed = []
    monkeypatch.setattr(
        reminder_worker,
        "push_line_message",
        lambda target_user, reminder, text: pushed.append((reminder, text)) or True,
    )
    checkins = reminder_worker.run_reminder_worker_once(now)
    assert len(checkins) == 1
    assert checkins[0]["kind"] == "study_session_checkin"
    assert load_json(data_path("tasks"))[0]["status"] == "pending"
    assert "未完成 task-progress" in pushed[0][1]
    assert reminder_worker.run_reminder_worker_once(now) == []

    replies = []
    monkeypatch.setattr(
        line_bot,
        "reply_line_message",
        lambda reply_token, text, choices=None: replies.append(text),
    )
    client = line_bot.create_app().test_client()

    for webhook_id, text in [
        ("checkin-incomplete", "未完成 task-progress"),
        ("checkin-remaining", "45"),
    ]:
        response = send_webhook(client, secret, {
            "type": "message",
            "webhookEventId": webhook_id,
            "replyToken": f"reply-{webhook_id}",
            "source": {"userId": "U-test"},
            "message": {"type": "text", "text": text},
        })
        assert response.status_code == 200

    updated_task = load_json(data_path("tasks"))[0]
    updated_plan = load_json(data_path("plan"))[0]
    checkin = load_json(data_path("reminders"))[0]
    assert updated_task["status"] == "pending"
    assert updated_task["estimated_minutes"] == 30
    assert updated_task["remaining_minutes"] == 45
    assert updated_task["preferred_availability_id"] == ""
    assert updated_plan["availability_id"] == "future-slot"
    assert updated_plan["status"] == "scheduled"
    assert checkin["progress_status"] == "replanned"
    assert checkin["remaining_minutes"] == 45
    assert "已重新安排" in replies[-1]
    duplicate = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "checkin-remaining",
        "replyToken": "reply-checkin-remaining-duplicate",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "45"},
    })
    assert duplicate.status_code == 200
    assert load_json(data_path("tasks"))[0]["remaining_minutes"] == 45

    completed_task = {
        **task,
        "task_id": "task-complete",
        "preferred_availability_id": "",
    }
    save_json(data_path("tasks"), [updated_task, completed_task])
    save_json(data_path("reminders"), load_json(data_path("reminders")) + [{
        "reminder_id": "checkin-complete",
        "user_id": user["user_id"],
        "task_id": "task-complete",
        "availability_id": "old-slot",
        "kind": "study_session_checkin",
        "status": "sent",
        "progress_status": "awaiting_response",
    }])
    response = send_webhook(client, secret, {
        "type": "message",
        "webhookEventId": "checkin-complete-response",
        "replyToken": "reply-checkin-complete",
        "source": {"userId": "U-test"},
        "message": {"type": "text", "text": "完成 task-complete"},
    })
    assert response.status_code == 200
    tasks = load_json(data_path("tasks"))
    assert next(row for row in tasks if row["task_id"] == "task-complete")["status"] == "completed"


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
