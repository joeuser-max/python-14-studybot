"""ClassPulse 豐富展示情境；與正式使用者 JSON、LINE 及外部 AI 完全隔離。

本頁所有上課時段、任務進度、LINE 回覆及外部行程都是虛構範例，
用於示範操作，不代表任何人的實際課表、學習成效或真實 LINE 推播。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from storage import FILES, TZ, data_path, is_demo_storage, save_json

DEMO_USER_ID = "demo_user_001"

# 與電機系課程主題相近的虛構時間表；不聲稱與使用者實際課表相同。
COURSE_TEMPLATES = [
    ("solid_mon", "固態物理", 1, "09:00", "11:00"),
    ("python_mon", "Python 程式設計", 1, "13:00", "15:00"),
    ("electronic_mon", "電子學（三）", 1, "16:00", "18:00"),
    ("memory_tue", "進階記憶體", 2, "09:00", "11:00"),
    ("lab_tue", "電子電路實驗（三）", 2, "13:00", "16:00"),
    ("comm_wed", "通訊原理", 3, "09:00", "11:00"),
    ("control_wed", "控制系統", 3, "13:00", "15:00"),
    ("dl_wed", "深度學習系統設計", 3, "16:00", "18:00"),
    ("solid_thu", "固態物理", 4, "09:00", "11:00"),
    ("electronic_thu", "電子學（三）", 4, "13:00", "15:00"),
    ("python_thu", "Python 程式設計", 4, "16:00", "18:00"),
    ("control_fri", "控制系統", 5, "09:00", "11:00"),
    ("comm_fri", "通訊原理", 5, "13:00", "15:00"),
    ("memory_fri", "進階記憶體", 5, "16:00", "18:00"),
]

# 任務狀態穿插 pending / scheduled / completed，避免示範模式只有空白卡或全部填滿。
# 每組為 ID、科目、任務標題、相對期限（天）、預估分鐘、初始狀態。
TASK_TEMPLATES = [
    ("control", "控制系統", "練習 Routh 判別與穩定度", 5, 60, "pending"),
    ("comm", "通訊原理", "解 Fourier 頻譜與相位題", 6, 60, "pending"),
    ("electronics", "電子學（三）", "整理回授與高頻極點", 6, 120, "pending"),
    ("memory", "進階記憶體", "複習 6T SRAM Read Disturb", 5, 60, "pending"),
    ("solid", "固態物理", "整理能帶與載子統計", 6, 60, "pending"),
    ("classpulse", "Python 程式設計", "完成 ClassPulse API Mock 測試", 6, 120, "pending"),
    ("lab", "電子電路實驗（三）", "整理示波器量測與報告", 5, 60, "pending"),
    ("dl", "深度學習系統設計", "比較 Dataflow 與 GLB 存取", 6, 60, "pending"),
    ("webhook", "Python 程式設計", "撰寫 LINE Webhook 驗簽測試", 5, 60, "scheduled"),
    ("dc_dc", "控制系統", "模擬 DC-DC 轉換器的 PI 控制", 6, 120, "scheduled"),
    ("pole", "電子學（三）", "檢查 Bode Plot 與極點位置", 6, 60, "scheduled"),
    ("done_python", "Python 程式設計", "完成函式、list 與 dictionary 練習", 2, 60, "completed"),
    ("done_comm", "通訊原理", "整理 LTI 系統基本觀念", 3, 60, "completed"),
    ("done_solid", "固態物理", "練習費米分布基礎題", 3, 60, "completed"),
]

# task ID、相對日期、開始時間、時長、是系統還是手動安排。
SCHEDULE_TEMPLATES = [
    ("webhook", 1, "19:00", 60, "manual"),
    ("dc_dc", 2, "20:00", 120, "auto"),
    ("pole", 3, "19:00", 60, "auto"),
]

# 上課資訊、內容及進度皆為假資料；Mock AI 需保留來源 ID。
FEEDBACK_TEMPLATES = [
    ("python_mon", "Python 函式", "今天整理函式與參數，還不太確定預設參數何時會使用。", 3,
     ["函式", "參數"], "函式參數的預設值怎麼決定？"),
    ("control_wed", "控制穩定度", "Routh 表格會排，但碰到零列時還需要練習。", 2,
     ["Routh", "穩定度"], "Routh 全零列應如何處理？"),
    ("comm_fri", "傅立葉頻譜", "已理解 double-sided spectrum，想再練相位轉換。", 4,
     ["傅立葉", "相位"], "頻移後如何推導相位？"),
    ("memory_tue", "SRAM", "理解 bitline precharge 與 read disturb，尚需整理讀取限制。", 4,
     ["SRAM", "Read disturb"], "6T SRAM 的讀取擾動如何由尺寸比抑制？"),
    ("solid_thu", "載子統計", "能帶圖已有基本概念，還想練溫度變化對濃度的影響。", 3,
     ["能帶", "載子統計"], "溫度如何影響載子濃度？"),
]


def _recent_completed_class_date(now: datetime, weekday: int, end_hour: int) -> str:
    day = now.date() - timedelta(days=(now.isoweekday() - weekday) % 7)
    if day == now.date() and now.hour < end_hour:
        day -= timedelta(days=7)
    return day.isoformat()


def _at(day, clock: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(clock), tzinfo=TZ)


def sample_records(now: datetime | None = None) -> dict[str, list]:
    """可重複產生的七日完整虛構展示資料，所有時間以傳入的 now 相對計算。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    today = now.date()

    courses = [{
        "event_id": f"demo_class_{key}", "user_id": DEMO_USER_ID,
        "event_type": "class", "title": title, "weekday": weekday,
        "start_time": start, "end_time": end, "offset_minutes": 10,
        "prompt_template": "class_feedback", "enabled": True,
    } for key, title, weekday, start, end in COURSE_TEMPLATES]

    tasks = [{
        "task_id": f"demo_task_{key}", "user_id": DEMO_USER_ID,
        "subject": subject, "title": title,
        "deadline": (today + timedelta(days=deadline_offset)).isoformat(),
        "estimated_minutes": minutes,
        "status": "completed" if state == "completed" else "pending",
        "preferred_availability_id": "",
        **({"completed_at": (now - timedelta(days=1)).isoformat(timespec="seconds")}
           if state == "completed" else {}),
    } for key, subject, title, deadline_offset, minutes, state in TASK_TEMPLATES]

    availability = []
    plan = []
    for key, day_offset, start_time, minutes, source in SCHEDULE_TEMPLATES:
        day = today + timedelta(days=day_offset)
        slot_id = f"demo_board_{key}"
        availability.append({
            "availability_id": slot_id, "user_id": DEMO_USER_ID,
            "date": day.isoformat(), "start_time": start_time,
            "available_minutes": minutes, "board_generated": True,
        })
        plan.append({
            "task_id": f"demo_task_{key}", "user_id": DEMO_USER_ID,
            "availability_id": slot_id, "status": "scheduled",
            "source": source, "reason": "", "unscheduled_alerted": False,
            "scheduled_start": _at(day, start_time).isoformat(timespec="minutes"),
            "scheduled_minutes": minutes,
        })

    # 額外保留幾個空檔給傳統 Scheduler 及 AI 確認任務的互動流程；
    # 七日拖排不再顯示這些格子作為 All-day standby。
    for day_offset, start_time, minutes in [
        (1, "21:00", 60), (4, "19:00", 120), (5, "19:00", 90),
        (6, "20:00", 120),
    ]:
        availability.append({
            "availability_id": f"demo_spare_{day_offset}",
            "user_id": DEMO_USER_ID,
            "date": (today + timedelta(days=day_offset)).isoformat(),
            "start_time": start_time, "available_minutes": minutes,
        })

    course_by_key = {
        key: (weekday, end) for key, _, weekday, _, end in COURSE_TEMPLATES
    }
    reminders = []
    feedback = []
    for index, (course_key, label, content, progress, tags, question) in enumerate(FEEDBACK_TEMPLATES):
        weekday, end_clock = course_by_key[course_key]
        class_date = _recent_completed_class_date(now, weekday, int(end_clock[:2]))
        sent = _at(date.fromisoformat(class_date), end_clock) + timedelta(minutes=10)
        reminder_id = f"demo_reminder_{course_key}"
        reminders.append({
            "reminder_id": reminder_id, "user_id": DEMO_USER_ID,
            "event_id": f"demo_class_{course_key}",
            "task_id": "", "availability_id": "",
            "class_date": class_date, "kind": "class_feedback", "status": "sent",
            "scheduled_at": sent.isoformat(timespec="seconds"),
            "sent_at": sent.isoformat(timespec="seconds"), "retry_key": "",
        })
        feedback.append({
            "feedback_id": f"demo_feedback_{course_key}",
            "user_id": DEMO_USER_ID,
            "event_id": f"demo_class_{course_key}",
            "class_date": class_date,
            "received_at": (sent + timedelta(minutes=index + 2)).isoformat(timespec="seconds"),
            "content": content, "progress": progress, "source": "demo",
            "reminder_id": reminder_id,
            "webhook_event_id": f"demo_webhook_{course_key}",
            "topic_tags": tags,
            "ai_analysis": {
                "summary": f"【Mock 展示】{label}課程回饋整理",
                "key_points": [content],
                "unresolved_questions": [question],
                "topic_tags": tags,
                "suggested_task": f"釐清並練習：{question}",
                "estimated_minutes": 45,
            } if index < 3 else {},
        })

    # 刻意留一則已送出的提醒尚未回覆，呈現真實一點的回覆率。
    extra_key = "electronic_mon"
    extra_date = _recent_completed_class_date(now, 1, 18)
    reminders.append({
        "reminder_id": "demo_reminder_unanswered", "user_id": DEMO_USER_ID,
        "event_id": f"demo_class_{extra_key}",
        "task_id": "", "availability_id": "", "class_date": extra_date,
        "kind": "class_feedback", "status": "sent",
        "scheduled_at": now.isoformat(timespec="seconds"),
        "sent_at": now.isoformat(timespec="seconds"), "retry_key": "",
    })
    # 有三個學習時段確認，兩個已完成、一個未完成。遊戲點數不冒充客觀學習效率。
    for key, progress in [
        ("done_python", "completed"), ("done_comm", "completed"), ("control", "incomplete"),
    ]:
        reminders.append({
            "reminder_id": f"demo_checkin_{key}", "user_id": DEMO_USER_ID,
            "event_id": "", "task_id": f"demo_task_{key}",
            "availability_id": "",
            "kind": "study_session_checkin", "status": "sent",
            "progress_status": progress, "class_date": "",
            "scheduled_at": (now - timedelta(days=2)).isoformat(timespec="seconds"),
            "sent_at": (now - timedelta(days=2)).isoformat(timespec="seconds"),
            "retry_key": "",
        })

    # 在任意連續七日中至少各有週二、週六、週日；與固定課程及排定任務不衝突。
    external_templates = [
        (2, "18:00", "19:00", "專題實驗室小組討論"),
        (6, "15:00", "16:00", "社團與交流活動"),
        (7, "17:00", "18:00", "運動與休息時間"),
    ]
    external = []
    for weekday, start_time, end_time, title in external_templates:
        day = next(today + timedelta(days=offset) for offset in range(7)
                   if (today + timedelta(days=offset)).isoweekday() == weekday)
        external.append({
            "id": f"demo_external_{weekday}",
            "user_id": DEMO_USER_ID, "title": title,
            "start": _at(day, start_time).isoformat(timespec="minutes"),
            "end": _at(day, end_time).isoformat(timespec="minutes"),
            "all_day": False, "origin": "demo",
        })

    return {
        "events": courses, "availability": availability, "tasks": tasks,
        "plan": plan, "feedback": feedback, "reminders": reminders,
        "external_events": external,
        "users": [{
            "user_id": DEMO_USER_ID, "line_user_id": "",
            "reminders_enabled": True, "study_reminders_enabled": True,
            "ai_after_class_enabled": True,
        }],
        "pending_notes": [], "processed_webhooks": [],
    }


def seed_demo_data(reset: bool = False, now: datetime | None = None) -> bool:
    """只寫展示目錄；重整不覆寫手動操作，只有使用者按「重設」才重建。"""
    if not is_demo_storage():
        raise RuntimeError("不能在正式資料模式載入展示資料")
    directory = data_path("events").parent
    marker = directory / ".demo_initialized"
    if marker.exists() and not reset:
        return False
    records = sample_records(now)
    for name in FILES:
        save_json(data_path(name), records.get(name, []))
    marker.write_text("ClassPulse rich isolated demo fixture\n", encoding="utf-8")
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
