import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from ai_assistant import AIError, organize_class_feedback
from scheduler import get_due_events, get_due_study_checkins, get_due_study_reminders
from storage import DataError, data_path, load_json, update_feedback_analysis, update_json


TZ = ZoneInfo("Asia/Taipei")
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def push_line_message(user: dict, reminder: dict, text: str) -> bool:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        print(f"[模擬] 未設定 LINE Token，未實際推送：{text}")
        return False

    key = reminder.get("retry_key") or str(uuid.uuid4())
    reminder["retry_key"] = key
    response = requests.post(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Line-Retry-Key": key,
        },
        json={"to": user["line_user_id"], "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    response.raise_for_status()
    return True


def _reserve_reminder(reminder: dict) -> dict:
    """以檔案鎖保存重試金鑰；已存在的紀錄不可用新金鑰覆蓋。"""
    result: dict = {}

    def update(rows: list) -> list:
        existing = next((row for row in rows
                         if row.get("reminder_id") == reminder["reminder_id"]), None)
        if existing:
            key = existing.get("retry_key") or reminder.get("retry_key") or str(uuid.uuid4())
            result.update({**existing, "retry_key": key})
            return [{**row, "retry_key": key}
                    if row.get("reminder_id") == reminder["reminder_id"] else row
                    for row in rows]
        new_row = {**reminder, "retry_key": reminder.get("retry_key") or str(uuid.uuid4())}
        result.update(new_row)
        return rows + [new_row]

    update_json(data_path("reminders"), update)
    return result


def _mark_reminder(reminder_id: str, status: str, sent_at: str) -> None:
    """只更新目標提醒的送出狀態，不覆寫其他 Worker 的資料。"""
    def update(rows: list) -> list:
        return [{**row, "status": status, "sent_at": sent_at}
                if row.get("reminder_id") == reminder_id else row for row in rows]
    update_json(data_path("reminders"), update)


def _mark_unscheduled_alerted(alert_id: str) -> None:
    def update(rows: list) -> list:
        for row in rows:
            if row.get("unscheduled_alert_id") == alert_id:
                row["unscheduled_alerted"] = True
        return rows
    update_json(data_path("plan"), update)


def _study_session_message(task: dict, user: dict, feedbacks: list[dict]) -> str:
    subject = task.get("subject") or "未指定科目"
    title = task.get("title") or task.get("task_id", "")
    text = f"讀書時段開始囉！任務：科目「{subject}」，{title}，請開始完成。"
    feedback_id = task.get("source_feedback_id")
    if user.get("ai_after_class_enabled") is not True or not feedback_id:
        return text

    feedback = next(
        (
            row for row in feedbacks
            if row.get("feedback_id") == feedback_id
            and row.get("user_id") == task.get("user_id")
        ),
        None,
    )
    if not feedback:
        return text + "\n找不到這項任務關聯的課後筆記，請到 ClassPulse 筆記庫查看。"

    analysis = feedback.get("ai_analysis")
    if not isinstance(analysis, dict):
        try:
            analysis = organize_class_feedback(feedback, subject)
        except AIError as exc:
            return text + f"\nAI 筆記整理未完成：{exc}；原始筆記仍保存在筆記庫。"
        try:
            update_feedback_analysis(feedback_id, task["user_id"], analysis)
        except DataError as exc:
            return text + f"\nAI 整理結果未能保存：{exc}；原始筆記仍保存在筆記庫。"

    lines = [text, "AI 根據課後筆記整理的複習內容：", f"摘要：{analysis['summary']}"]
    if analysis.get("key_points"):
        lines.append("重點：")
        lines.extend(f"・{point}" for point in analysis["key_points"])
    if analysis.get("unresolved_questions"):
        lines.append("待釐清：")
        lines.extend(f"・{question}" for question in analysis["unresolved_questions"])
    if analysis.get("topic_tags"):
        lines.append("主題：" + "、".join(analysis["topic_tags"]))
    if analysis.get("suggested_task"):
        lines.append(
            f"AI 複習建議：{analysis['suggested_task']}（AI 參考時長 "
            f"{analysis['estimated_minutes']} 分鐘；本次排程依你設定的 "
            f"{task['estimated_minutes']} 分鐘）"
        )
    return "\n".join(lines)


def run_reminder_worker_once(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(TZ)
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    events = load_json(data_path("events"))
    tasks = load_json(data_path("tasks"))
    plan = load_json(data_path("plan"))
    availability = load_json(data_path("availability"))
    users = load_json(data_path("users"))
    reminders = load_json(data_path("reminders"))
    feedbacks = load_json(data_path("feedback"))

    due = get_due_events(events, now, reminders)
    due.extend(get_due_study_reminders(tasks, plan, availability, users, now, reminders))
    due.extend(get_due_study_checkins(tasks, plan, availability, users, now, reminders))
    task_map = {task["task_id"]: task for task in tasks}
    user_map = {user["user_id"]: user for user in users}
    event_map = {event["event_id"]: event for event in events}
    existing_ids = {row.get("reminder_id") for row in reminders}

    for row in plan:
        if row.get("status") != "unscheduled" or row.get("unscheduled_alerted"):
            continue
        task = task_map.get(row.get("task_id"))
        user = user_map.get(task.get("user_id")) if task else None
        if (
            not task
            or not user
            or not user.get("line_user_id")
            or not user.get("reminders_enabled", False)
        ):
            continue
        alert_id = row.get("unscheduled_alert_id") or f"unscheduled_{row['task_id']}"
        if alert_id in existing_ids:
            existing = next(item for item in reminders if item.get("reminder_id") == alert_id)
            if existing.get("status") == "sent":
                _mark_unscheduled_alerted(alert_id)
                continue
            due.append(dict(existing))
        else:
            due.append({
                "reminder_id": alert_id,
                "user_id": task["user_id"],
                "event_id": "",
                "task_id": task["task_id"],
                "availability_id": "",
                "class_date": "",
                "kind": "unscheduled_alert",
                "scheduled_at": now.isoformat(timespec="seconds"),
                "sent_at": "",
                "status": "pending",
                "retry_key": "",
            })

    attempted: list[dict] = []
    for reminder in due:
        reminder["retry_key"] = reminder.get("retry_key") or str(uuid.uuid4())
        user = user_map.get(reminder["user_id"])
        if (
            not user
            or not user.get("line_user_id")
            or (
                reminder["kind"] in {"class_feedback", "unscheduled_alert"}
                and not user.get("reminders_enabled", False)
            )
        ):
            continue
        saved = _reserve_reminder({**reminder, "status": "pending"})
        if saved.get("status") == "sent":
            continue

        if reminder["kind"] == "class_feedback":
            course = event_map.get(reminder["event_id"], {})
            course_title = course.get("title") or "課程"
            text = (
                f"「{course_title}」課程已結束！請在 LINE 輸入「補筆記」，"
                "回報本堂理解進度並記錄學習重點與疑問。"
            )
        elif reminder["kind"] == "study_session":
            task = task_map.get(reminder["task_id"], {})
            text = _study_session_message(task, user, feedbacks)
        elif reminder["kind"] == "study_session_checkin":
            task = task_map.get(reminder["task_id"], {})
            task_id = reminder["task_id"]
            text = (
                f"讀書時段結束囉！任務：{task.get('title', task_id)}。"
                f"請回覆「完成 {task_id}」或「未完成 {task_id}」；"
                "若未完成，接著輸入剩餘所需分鐘數。"
            )
        else:
            task = task_map.get(reminder["task_id"], {})
            subject = task.get("subject") or "未指定科目"
            title = task.get("title") or reminder["task_id"]
            text = (
                f"提醒：科目「{subject}」，任務「{title}」尚未排入。原因："
            )
            plan_row = next((p for p in plan if p.get("task_id") == reminder["task_id"]), {})
            text += plan_row.get("reason", "請在 ClassPulse 調整時段或期限。")

        accepted = False
        try:
            accepted = push_line_message(user, saved, text)
            status = "sent" if accepted else "failed"
            sent_at = now.isoformat(timespec="seconds") if accepted else ""
        except requests.RequestException as exc:
            status = "failed"
            sent_at = ""
            print(f"LINE Push 失敗，將以相同 retry key 重試：{exc}")

        _mark_reminder(saved["reminder_id"], status, sent_at)
        if accepted and reminder["kind"] == "unscheduled_alert":
            _mark_unscheduled_alerted(reminder["reminder_id"])
        attempted.append({**saved, "status": status, "sent_at": sent_at})
    return attempted


def run_reminder_worker(interval_seconds: int = 60) -> None:
    while True:
        try:
            run_reminder_worker_once()
        except Exception as exc:
            print(f"worker 檢查失敗：{exc}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_reminder_worker()
