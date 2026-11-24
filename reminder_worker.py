import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from scheduler import get_due_events, get_due_study_reminders
from storage import data_path, load_json, update_json


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


def _upsert_reminder(reminder: dict) -> dict:
    result: dict = {}

    def update(rows: list) -> list:
        existing = next(
            (row for row in rows if row.get("reminder_id") == reminder["reminder_id"]),
            None,
        )
        if existing:
            if not reminder.get("retry_key"):
                reminder["retry_key"] = existing.get("retry_key", "")
            rows = [
                {**row, **reminder} if row.get("reminder_id") == reminder["reminder_id"] else row
                for row in rows
            ]
        else:
            rows = rows + [reminder]
        result.update(reminder)
        return rows

    update_json(data_path("reminders"), update)
    return result


def _mark_unscheduled_alerted(alert_id: str) -> None:
    def update(rows: list) -> list:
        for row in rows:
            if row.get("unscheduled_alert_id") == alert_id:
                row["unscheduled_alerted"] = True
        return rows
    update_json(data_path("plan"), update)


def run_reminder_worker_once(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(TZ)
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    events = load_json(data_path("events"))
    tasks = load_json(data_path("tasks"))
    plan = load_json(data_path("plan"))
    availability = load_json(data_path("availability"))
    users = load_json(data_path("users"))
    reminders = load_json(data_path("reminders"))

    due = get_due_events(events, now, reminders)
    due.extend(get_due_study_reminders(tasks, plan, availability, users, now, reminders))
    task_map = {task["task_id"]: task for task in tasks}
    user_map = {user["user_id"]: user for user in users}
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
        saved = _upsert_reminder({**reminder, "status": "pending"})

        if reminder["kind"] == "class_feedback":
            text = (
                "課後回饋時間到囉！請在 LINE 輸入「補筆記」，"
                "回報本堂理解進度並記錄學習重點與疑問。"
            )
        elif reminder["kind"] == "study_session":
            task = task_map.get(reminder["task_id"], {})
            text = f"讀書時段開始囉！任務：{task.get('title', reminder['task_id'])}，請開始完成。"
        else:
            task = task_map.get(reminder["task_id"], {})
            text = f"提醒：任務「{task.get('title', reminder['task_id'])}」尚未排入。原因："
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

        saved["status"] = status
        saved["sent_at"] = sent_at
        _upsert_reminder(saved)
        if accepted and reminder["kind"] == "unscheduled_alert":
            _mark_unscheduled_alerted(reminder["reminder_id"])
        attempted.append(saved)
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
