"""ClassPulse 回饋與任務統計（蕭博軒）。"""
from __future__ import annotations

from datetime import date
from storage import validate_feedback, DataError


def calculate_response_rate(reminders: list, feedbacks: list, user_id: str | None = None,
                            start: date | None = None, end: date | None = None) -> dict:
    """分子：至少一則有效回饋的課後提醒 ID；手動補登不列入。"""
    accepted = set()
    for row in reminders:
        if row.get("kind") != "class_feedback" or row.get("status") != "sent":
            continue
        if user_id is not None and row.get("user_id") != user_id:
            continue
        d = row.get("class_date", "")
        if (start and (not d or d < start.isoformat())) or (end and (not d or d > end.isoformat())):
            continue
        if row.get("reminder_id"):
            accepted.add(row["reminder_id"])
    answered = set()
    for row in feedbacks:
        if user_id is not None and row.get("user_id") != user_id:
            continue
        reminder_id = row.get("reminder_id")
        if reminder_id in accepted:
            try:
                validate_feedback(row)
            except (DataError, KeyError):
                continue
            answered.add(reminder_id)
    total = len(accepted)
    return {"sent": total, "answered": len(answered),
            "rate": round(len(answered) / total * 100, 1) if total else None}


def calculate_task_progress(tasks: list, user_id: str | None = None) -> dict:
    filtered = [t for t in tasks if user_id is None or t.get("user_id") == user_id]
    total = len(filtered)
    done = sum(t.get("status") == "completed" for t in filtered)
    return {"total": total, "completed": done, "rate": round(done / total * 100, 1) if total else None}
