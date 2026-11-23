import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from scheduler import (
    get_due_events,
    get_due_study_reminders,
)
from storage import load_json, save_json


TZ = ZoneInfo("Asia/Taipei")
DATA_DIR = Path(__file__).resolve().parent / "data"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def push_line_message(user: dict, reminder: dict, text: str) -> bool:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        print(f"[模擬] 推送給 {user.get('line_user_id', reminder['user_id'])}: {text}")
        return True

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


def run_reminder_worker(interval_seconds: int = 60) -> None:
    while True:
        try:
            now = datetime.now(TZ)
            events = load_json(DATA_DIR / "events.json")
            tasks = load_json(DATA_DIR / "tasks.json")
            plan = load_json(DATA_DIR / "plan.json")
            availability = load_json(DATA_DIR / "availability.json")
            users = load_json(DATA_DIR / "users.json")
            reminders = load_json(DATA_DIR / "reminders.json")

            due = get_due_events(events, now, reminders)
            due.extend(get_due_study_reminders(tasks, plan, availability, users, now, reminders))

            existing_unscheduled = {
                (item.get("user_id"), item.get("task_id"))
                for item in reminders
                if item.get("kind") == "unscheduled_alert"
                and item.get("status") in {"pending", "sent", "failed"}
            }
            if plan:
                for row in plan:
                    if row.get("status") != "unscheduled" or not row.get("unscheduled_alerted"):
                        continue
                    task = next((item for item in tasks if item["task_id"] == row["task_id"]), None)
                    if not task:
                        continue
                    key = (task["user_id"], task["task_id"])
                    if key in existing_unscheduled:
                        continue
                    user = next((item for item in users if item["user_id"] == task["user_id"]), None)
                    if not user or not user.get("line_user_id") or not user.get("reminders_enabled", False):
                        continue
                    due.append({
                        "reminder_id": f"unscheduled_{task['task_id']}",
                        "user_id": task["user_id"],
                        "event_id": "",
                        "task_id": task["task_id"],
                        "availability_id": "",
                        "class_date": "",
                        "kind": "unscheduled_alert",
                        "scheduled_at": now.isoformat(timespec="seconds"),
                        "sent_at": "",
                        "status": "pending",
                        "retry_key": str(uuid.uuid4()),
                    })

            for reminder in due:
                reminder["retry_key"] = reminder.get("retry_key") or str(uuid.uuid4())
                existing_reminder = next(
                    (item for item in reminders if item.get("reminder_id") == reminder["reminder_id"]),
                    None,
                )
                if existing_reminder is None:
                    reminders.append(reminder)
                    existing_reminder = reminder
                save_json(DATA_DIR / "reminders.json", reminders)

                user = next((row for row in users if row["user_id"] == reminder["user_id"]), None)
                if not user or not user.get("line_user_id"):
                    continue

                if reminder["kind"] == "class_feedback":
                    text = "課後回饋時間到囉！請點選「補筆記」記錄今天的學習重點與疑問。"
                elif reminder["kind"] == "study_session":
                    text = f"讀書時段開始囉！任務：{reminder['task_id']}，請開始完成。"
                else:
                    text = "提醒：有讀書任務尚未排入，請在 Streamlit 調整時段或期限。"

                try:
                    accepted = push_line_message(user, reminder, text)
                    existing_reminder["status"] = "sent" if accepted else "failed"
                    existing_reminder["sent_at"] = now.isoformat(timespec="seconds") if accepted else ""
                    existing_reminder["retry_key"] = reminder["retry_key"]
                except Exception as exc:
                    existing_reminder["status"] = "failed"
                    existing_reminder["sent_at"] = ""
                    existing_reminder["retry_key"] = reminder["retry_key"]
                    print(f"LINE Push 失敗（保留 retry key）：{exc}")
                save_json(DATA_DIR / "reminders.json", reminders)
        except Exception as exc:
            print(f"worker 檢查失敗：{exc}")
        time.sleep(interval_seconds)


def send_unscheduled_alerts(tasks: list[dict], plan: list[dict], users: list[dict]) -> list[dict]:
    by_task = {task["task_id"]: task for task in tasks}
    due = []
    for row in plan:
        if row.get("status") != "unscheduled":
            continue
        task = by_task.get(row["task_id"])
        if not task:
            continue
        user = next((item for item in users if item["user_id"] == task["user_id"]), None)
        if not user or not user.get("line_user_id") or not user.get("reminders_enabled", False):
            continue
        if row.get("unscheduled_alerted"):
            due.append({
                "reminder_id": f"unscheduled_{row['task_id']}",
                "user_id": task["user_id"],
                "event_id": "",
                "task_id": row["task_id"],
                "availability_id": "",
                "class_date": "",
                "kind": "unscheduled_alert",
                "scheduled_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "sent_at": "",
                "status": "pending",
                "retry_key": str(uuid.uuid4()),
            })
    return due


if __name__ == "__main__":
    run_reminder_worker()
