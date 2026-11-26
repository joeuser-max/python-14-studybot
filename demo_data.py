"""ClassPulse 展示資料與 Mock AI；與正式使用者 JSON、LINE、外部 AI 完全隔離。"""
from __future__ import annotations

from datetime import datetime, timedelta

from storage import FILES, TZ, data_path, is_demo_storage, save_json


DEMO_USER_ID = "demo_user_001"


def _recent_completed_class_date(now: datetime, weekday: int, end_hour: int) -> str:
    day = now.date() - timedelta(days=(now.isoweekday() - weekday) % 7)
    if day == now.date() and now.hour < end_hour:
        day -= timedelta(days=7)
    return day.isoformat()


def sample_records(now: datetime | None = None) -> dict[str, list]:
    """一般教學用虛構課表，非任何使用者實際修課資料。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    today = now.date()
    events = [
        ("demo_class_programming", "程式設計", 1, "09:00", "11:00"),
        ("demo_class_control", "控制系統", 3, "13:00", "15:00"),
        ("demo_class_communication", "通訊原理", 5, "10:00", "12:00"),
    ]
    courses = [
        {"event_id": eid, "user_id": DEMO_USER_ID, "event_type": "class",
         "title": title, "weekday": weekday, "start_time": start,
         "end_time": end, "offset_minutes": 10,
         "prompt_template": "class_feedback", "enabled": True}
        for eid, title, weekday, start, end in events
    ]
    availability = [
        {"availability_id": f"demo_slot_{index}", "user_id": DEMO_USER_ID,
         "date": (today + timedelta(days=index)).isoformat(),
         "start_time": start, "available_minutes": minutes}
        for index, start, minutes in (
            (1, "19:00", 90), (2, "19:00", 60), (3, "20:00", 120)
        )
    ]
    tasks = [
        {"task_id": "demo_task_control", "user_id": DEMO_USER_ID,
         "subject": "控制系統", "title": "複習回授與穩定度",
         "deadline": (today + timedelta(days=5)).isoformat(),
         "estimated_minutes": 60, "status": "pending",
         "preferred_availability_id": ""},
        {"task_id": "demo_task_communication", "user_id": DEMO_USER_ID,
         "subject": "通訊原理", "title": "練習頻譜分析題目",
         "deadline": (today + timedelta(days=6)).isoformat(),
         "estimated_minutes": 45, "status": "pending",
         "preferred_availability_id": ""},
        {"task_id": "demo_task_done", "user_id": DEMO_USER_ID,
         "subject": "程式設計", "title": "完成 Python 函式練習",
         "deadline": (today + timedelta(days=4)).isoformat(),
         "estimated_minutes": 30, "status": "completed",
         "preferred_availability_id": ""},
    ]
    plan = [
        {"task_id": "demo_task_control", "user_id": DEMO_USER_ID,
         "availability_id": "demo_slot_1", "status": "scheduled",
         "source": "auto", "reason": "", "unscheduled_alerted": False},
        {"task_id": "demo_task_communication", "user_id": DEMO_USER_ID,
         "availability_id": "demo_slot_2", "status": "scheduled",
         "source": "auto", "reason": "", "unscheduled_alerted": False},
    ]
    class_date = _recent_completed_class_date(now, 1, 11)
    example_analysis = {
        "summary": "課程練習函式與參數，仍需要釐清預設值的使用方式。",
        "key_points": ["函式能重複使用程式邏輯", "參數可將資料傳入函式"],
        "unresolved_questions": ["函式參數的預設值在什麼情況下會被使用？"],
        "suggested_task": "練習撰寫包含預設參數的函式",
        "estimated_minutes": 45,
    }
    # 三則展示筆記：前兩則屬於同一天、同一課次，可測試 UI 群組顯示。
    control_date = _recent_completed_class_date(now, 3, 15)
    feedback = [
        {
            "feedback_id": "demo_feedback_programming",
            "user_id": DEMO_USER_ID,
            "event_id": "demo_class_programming", "class_date": class_date,
            "received_at": f"{class_date}T11:05:00+08:00",
            "content": "今天學到 Python 函式與參數，但不太確定預設參數什麼時候會生效。",
            "progress": 3, "source": "demo",
            "reminder_id": "demo_reminder_programming",
            "webhook_event_id": "demo_webhook_programming",
            "ai_analysis": example_analysis,
        },
        {
            "feedback_id": "demo_feedback_programming_followup",
            "user_id": DEMO_USER_ID,
            "event_id": "demo_class_programming", "class_date": class_date,
            "received_at": f"{class_date}T11:22:00+08:00",
            "content": "補充筆記：預設參數在呼叫函式時未指定該參數才會生效；還想練習幾個例子。",
            "progress": 4, "source": "demo",
            "reminder_id": "",
            "webhook_event_id": "demo_webhook_programming_followup",
        },
        {
            "feedback_id": "demo_feedback_control",
            "user_id": DEMO_USER_ID,
            "event_id": "demo_class_control", "class_date": control_date,
            "received_at": f"{control_date}T15:16:00+08:00",
            "content": "控制系統講到 Routh 判據；我還不清楚符號變化如何對應右半平面極點的數量。",
            "progress": 2, "source": "demo",
            "reminder_id": "",
            "webhook_event_id": "demo_webhook_control",
        },
    ]
    reminders = [{
        "reminder_id": "demo_reminder_programming", "user_id": DEMO_USER_ID,
        "event_id": "demo_class_programming", "task_id": "", "availability_id": "",
        "class_date": class_date, "kind": "class_feedback", "status": "sent",
        "scheduled_at": now.isoformat(timespec="seconds"),
        "sent_at": now.isoformat(timespec="seconds"), "retry_key": "",
    }]
    return {
        "events": courses, "availability": availability, "tasks": tasks,
        "plan": plan, "feedback": feedback, "reminders": reminders,
        "users": [{"user_id": DEMO_USER_ID, "line_user_id": "",
                   "reminders_enabled": True,
                   "study_reminders_enabled": True,
                   "ai_after_class_enabled": True}],
        "pending_notes": [], "processed_webhooks": [],
    }


def seed_demo_data(reset: bool = False, now: datetime | None = None) -> bool:
    """只寫展示目錄；首次載入填入虛構資料，重新載入不覆寫使用者的展示修改。"""
    if not is_demo_storage():
        raise RuntimeError("不能在正式資料模式載入展示資料")
    directory = data_path("events").parent
    marker = directory / ".demo_initialized"
    if marker.exists() and not reset:
        return False
    records = sample_records(now)
    for name in FILES:
        save_json(data_path(name), records.get(name, []))
    marker.write_text("ClassPulse isolated demo fixture\n", encoding="utf-8")
    return True


def mock_learning_suggestions(feedbacks: list, courses: list,
                              user_id: str = DEMO_USER_ID) -> dict:
    """固定規則的展示回應，明確不代表模型真的產生這份建議。"""
    own = [f for f in feedbacks if f.get("user_id") == user_id
           and isinstance(f.get("feedback_id"), str)]
    if not own:
        return {"summary": "目前沒有展示用回饋可以分析。", "suggestions": []}
    latest = max(own, key=lambda f: f.get("received_at", ""))
    titles = {c["event_id"]: c["title"] for c in courses if "event_id" in c}
    title = titles.get(latest.get("event_id"), "課程")
    return {
        "summary": f"【Mock 展示】根據「{title}」的課堂回饋，建議整理疑問並安排一段複習時間。",
        "suggestions": [{
            "topic": title,
            "unresolved_question": "回顧筆記中尚不清楚的概念",
            "suggested_task": f"整理「{title}」課堂疑問並完成一組練習",
            "source_feedback_id": latest["feedback_id"],
        }],
    }
