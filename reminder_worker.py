import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from scheduler import get_due_events, get_due_study_checkins, get_due_study_reminders
from line_study_ai import study_start_message
from storage import DataError, data_path, load_json, update_json


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
        matches = [row for row in rows if row.get("reminder_id") == reminder["reminder_id"]]
        if len(matches) > 1 or any(row.get("user_id") != reminder.get("user_id") for row in matches):
            raise DataError("提醒識別碼與所有者衝突")
        existing = matches[0] if matches else None
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


def _mark_reminder(reminder_id: str, status: str, sent_at: str, user_id: str) -> None:
    """只更新目標提醒的送出狀態，不覆寫其他 Worker 的資料。"""
    def update(rows: list) -> list:
        return [{**row, "status": status, "sent_at": sent_at}
                if row.get("reminder_id") == reminder_id and row.get("user_id") == user_id else row for row in rows]
    update_json(data_path("reminders"), update)


def _mark_unscheduled_alerted(alert_id: str, user_id: str) -> None:
    def update(rows: list) -> list:
        for row in rows:
            if row.get("unscheduled_alert_id") == alert_id and row.get("user_id") == user_id:
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
    feedbacks = load_json(data_path("feedback"))

    due = get_due_events(events, now, reminders)
    due.extend(get_due_study_reminders(tasks, plan, availability, users, now, reminders))
    due.extend(get_due_study_checkins(tasks, plan, availability, users, now, reminders))
    task_map = {(task.get("user_id"), task["task_id"]): task for task in tasks}
    user_map = {user["user_id"]: user for user in users}
    existing_ids = {(row.get("user_id"), row.get("reminder_id")) for row in reminders}

    for row in plan:
        if row.get("status") != "unscheduled" or row.get("unscheduled_alerted"):
            continue
        task = task_map.get((row.get("user_id"), row.get("task_id")))
        user = user_map.get(task.get("user_id")) if task else None
        if (
            not task
            or not user
            or not user.get("line_user_id")
            or user.get("demo_status") in ("pending_seed", "seeded_pending_auth")
            or not user.get("reminders_enabled", False)
        ):
            continue
        alert_id = row.get("unscheduled_alert_id") or f"unscheduled_{row['task_id']}"
        if (task["user_id"], alert_id) in existing_ids:
            existing = next(item for item in reminders if item.get("reminder_id") == alert_id and item.get("user_id") == task["user_id"])
            if existing.get("status") == "sent":
                _mark_unscheduled_alerted(alert_id, task["user_id"])
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
            or user.get("demo_status") in ("pending_seed", "seeded_pending_auth")
            or (
                reminder["kind"] in {"class_feedback", "unscheduled_alert"}
                and not user.get("reminders_enabled", False)
            )
        ):
            continue
        if reminder["kind"] != "class_feedback" and (reminder["user_id"], reminder.get("task_id")) not in task_map:
            continue
        if reminder["kind"] in {"study_session", "study_session_checkin"} and not user.get("study_reminders_enabled", False):
            continue
        try:
            saved = _reserve_reminder({**reminder, "status": "pending"})
        except DataError:
            continue
        if saved.get("status") == "sent":
            continue

        if reminder["kind"] == "class_feedback":
            text = (
                "課後回饋時間到囉！請在 LINE 輸入「補筆記」，"
                "回報本堂理解進度並記錄學習重點與疑問。"
            )
        elif reminder["kind"] == "study_session":
            task = task_map.get((reminder["user_id"], reminder["task_id"]), {})
            text = study_start_message(task, user, feedbacks)
        elif reminder["kind"] == "study_session_checkin":
            task = task_map.get((reminder["user_id"], reminder["task_id"]), {})
            task_id = reminder["task_id"]
            text = (
                f"讀書時段結束囉！任務：{task.get('title', task_id)}。"
                f"請回覆「完成 {task_id}」或「未完成 {task_id}」；"
                "若未完成，接著輸入剩餘所需分鐘數。"
            )
        else:
            task = task_map.get((reminder["user_id"], reminder["task_id"]), {})
            subject = task.get("subject") or "未指定科目"
            title = task.get("title") or reminder["task_id"]
            text = (
                f"提醒：科目「{subject}」，任務「{title}」尚未排入。原因："
            )
            plan_row = next((p for p in plan if p.get("task_id") == reminder["task_id"] and p.get("user_id") == reminder["user_id"]), {})
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

        _mark_reminder(saved["reminder_id"], status, sent_at, reminder["user_id"])
        if accepted and reminder["kind"] == "unscheduled_alert":
            _mark_unscheduled_alerted(reminder["reminder_id"], reminder["user_id"])
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
