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
    """根據使用者提供的課表圖片整理展示課次；完成數據為明確標示的範例。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    today = now.date()
    # 根據使用者提供的 1151 學期課表截圖，僅擷取課名、星期、時間及教室，
    # 不儲存截圖上的姓名、學號或其他個人身分資訊。每週不同上課日視為獨立課次。
    events = [
        ("demo_class_programming", "程式設計-Python", 1, "18:00", "20:50", "I-002"),
        ("demo_class_control", "控制系統", 3, "13:00", "13:50", "E1-124"),
        ("demo_class_communication", "通訊原理", 5, "10:00", "11:50", "E1-102"),
        ("demo_class_electronics", "電子學 III", 1, "09:00", "11:50", "E1-124"),
        ("demo_class_geophysics", "運動地球物理", 1, "13:00", "14:50", "O-122"),
        ("demo_class_communication_mon", "通訊原理", 1, "15:00", "15:50", "E1-102"),
        ("demo_class_deep_learning", "深度學習系統設計與應用", 2, "09:00", "11:50", "E1-102"),
        ("demo_class_control_tue", "控制系統", 2, "13:00", "14:50", "E1-124"),
        ("demo_class_electronics_lab", "電子電路實驗 III", 2, "15:00", "17:50", "E1-223"),
        ("demo_class_solid_state", "固態電子元件", 3, "09:00", "11:50", "E1-019"),
        ("demo_class_astronomy", "現代天文學簡介", 3, "15:00", "16:50", "TR-A203"),
        ("demo_class_memory", "先進記憶體元件物理與製造技術", 4, "14:00", "16:50", "E1-120"),
        ("demo_class_swimming", "游泳概論", 5, "15:00", "16:50", "YH-室內"),
        ("demo_class_research", "專題實作", 6, "13:00", "15:50", "E1-120"),
    ]
    courses = [
        {"event_id": eid, "user_id": DEMO_USER_ID, "event_type": "class",
         "title": title, "weekday": weekday, "start_time": start,
         "end_time": end, "room": room, "offset_minutes": 10,
         "prompt_template": "class_feedback", "enabled": True}
        for eid, title, weekday, start, end, room in events
    ]
    availability = [
        {"availability_id": f"demo_slot_{index}", "user_id": DEMO_USER_ID,
         "date": (today + timedelta(days=index)).isoformat(),
         "start_time": start, "available_minutes": minutes}
        for index, start, minutes in (
            (1, "19:00", 90), (2, "19:00", 60), (3, "20:00", 120),
            (4, "21:00", 90), (5, "19:00", 90),
            (6, "19:00", 60), (7, "19:00", 90),
        )
    ]
    tasks = [
        {"task_id": "demo_task_control", "user_id": DEMO_USER_ID,
         "subject": "控制系統", "title": "複習回授與穩定度",
         "deadline": (today + timedelta(days=5)).isoformat(),
         "estimated_minutes": 60, "status": "pending", "progress_percent": 20,
         "preferred_availability_id": "", "source": "manual_user"},
        {"task_id": "demo_task_communication", "user_id": DEMO_USER_ID,
         "subject": "通訊原理", "title": "練習頻譜分析題目",
         "deadline": (today + timedelta(days=6)).isoformat(),
         "estimated_minutes": 45, "status": "pending", "progress_percent": 0,
         "preferred_availability_id": "", "source": "manual_user"},
        {"task_id": "demo_task_electronics", "user_id": DEMO_USER_ID,
         "subject": "電子學 III", "title": "整理 Miller Effect 與回授小訊號模型",
         "deadline": (today + timedelta(days=7)).isoformat(),
         "estimated_minutes": 60, "status": "pending", "progress_percent": 30,
         "preferred_availability_id": "", "source": "manual_user"},
        {"task_id": "demo_task_memory", "user_id": DEMO_USER_ID,
         "subject": "先進記憶體", "title": "閱讀 SRAM Read Disturb 筆記",
         "deadline": (today + timedelta(days=7)).isoformat(),
         "estimated_minutes": 45, "status": "pending", "progress_percent": 0,
         "preferred_availability_id": "", "source": "manual_user"},
        {"task_id": "demo_task_ai_feedback", "user_id": DEMO_USER_ID,
         "subject": "控制系統", "title": "練習 Routh 判據的右半平面極點計數",
         "deadline": (today + timedelta(days=4)).isoformat(),
         "estimated_minutes": 45, "status": "pending", "progress_percent": 0,
         "preferred_availability_id": "", "source": "ai_confirmed",
         "source_feedback_id": "demo_feedback_control"},
        {"task_id": "demo_task_done", "user_id": DEMO_USER_ID,
         "subject": "程式設計", "title": "完成 Python 函式練習",
         "deadline": (today + timedelta(days=4)).isoformat(),
         "estimated_minutes": 30, "status": "completed", "progress_percent": 100,
         "preferred_availability_id": "", "source": "manual_user"},
    ]
    # 實際寫入 demo tasks.json 的已完成範例；展示成績並非正式模式資料。
    done_examples = [
        ("demo_done_frequencies", "通訊原理", "整理傅立葉轉換與頻譜", 45, 0),
        ("demo_done_pid", "控制系統", "完成 PID 控制器練習", 60, 1),
        ("demo_done_sram", "先進記憶體", "整理 6T SRAM 讀取流程", 75, 3),
        ("demo_done_poles", "電子學 III", "複習極點與補償電容", 50, 5),
        ("demo_done_device", "固態電子元件", "完成半導體載子濃度題目", 60, 9),
        ("demo_done_python", "程式設計", "完成 dictionary 與函式測驗", 30, 16),
        ("demo_done_lab", "電子電路實驗 III", "整理量測結果及實驗報告", 90, 24),
    ]
    for task_id, subject, title, minutes, days_ago in done_examples:
        tasks.append({
            "task_id": task_id, "user_id": DEMO_USER_ID,
            "subject": subject, "title": title,
            "deadline": (today - timedelta(days=max(0, days_ago - 1))).isoformat(),
            "estimated_minutes": minutes, "status": "completed",
            "progress_percent": 100, "preferred_availability_id": "",
            "source": "manual_user",
        })
    plan = [
        {"task_id": "demo_task_control", "user_id": DEMO_USER_ID,
         "availability_id": "demo_slot_1", "status": "scheduled",
         "source": "auto", "reason": "", "unscheduled_alerted": False},
        {"task_id": "demo_task_communication", "user_id": DEMO_USER_ID,
         "availability_id": "demo_slot_2", "status": "scheduled",
         "source": "auto", "reason": "", "unscheduled_alerted": False},
    ]
    class_date = _recent_completed_class_date(now, 1, 21)
    example_analysis = {
        "summary": "課程練習函式與參數，仍需要釐清預設值的使用方式。",
        "key_points": ["函式能重複使用程式邏輯", "參數可將資料傳入函式"],
        "unresolved_questions": ["函式參數的預設值在什麼情況下會被使用？"],
        "suggested_task": "練習撰寫包含預設參數的函式",
        "estimated_minutes": 45,
    }
    # 三則展示筆記：前兩則屬於同一天、同一課次，可測試 UI 群組顯示。
    control_date = _recent_completed_class_date(now, 3, 14)
    feedback = [
        {
            "feedback_id": "demo_feedback_programming",
            "user_id": DEMO_USER_ID,
            "event_id": "demo_class_programming", "class_date": class_date,
            "received_at": f"{class_date}T21:05:00+08:00",
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
            "received_at": f"{class_date}T21:22:00+08:00",
            "content": "補充筆記：預設參數在呼叫函式時未指定該參數才會生效；還想練習幾個例子。",
            "progress": 4, "source": "demo",
            "reminder_id": "",
            "webhook_event_id": "demo_webhook_programming_followup",
        },
        {
            "feedback_id": "demo_feedback_control",
            "user_id": DEMO_USER_ID,
            "event_id": "demo_class_control", "class_date": control_date,
            "received_at": f"{control_date}T14:05:00+08:00",
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
    sample_completed_at = (now - timedelta(days=2)).replace(
        hour=20, minute=15, second=0, microsecond=0
    )
    sample_progress_events = [{
        "task_id": "demo_task_done", "user_id": DEMO_USER_ID,
        "timestamp": sample_completed_at.isoformat(timespec="seconds"),
        "old_percent": 0, "progress_percent": 100,
        "status": "completed", "estimated_minutes": 30,
        "source": "demo_seed",
    }]
    for task_id, _subject, _title, minutes, days_ago in done_examples:
        completed_at = (now - timedelta(days=days_ago)).replace(
            second=0, microsecond=0
        )
        sample_progress_events.append({
            "task_id": task_id, "user_id": DEMO_USER_ID,
            "timestamp": completed_at.isoformat(timespec="seconds"),
            "old_percent": 0, "progress_percent": 100,
            "status": "completed", "estimated_minutes": minutes,
            "source": "demo_seed",
        })
    return {
        "events": courses, "availability": availability, "tasks": tasks,
        "plan": plan, "feedback": feedback, "reminders": reminders,
        "progress_events": sample_progress_events,
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
