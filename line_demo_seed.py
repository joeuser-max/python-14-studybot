"""Step 14: seed fictional per-friend data without resetting any shared JSON.

Multiple files are not a transaction. A per-user lock, persistent seed anchor,
stable IDs, insert-only writes and a final status transition make retry safe.
The result is NOT authenticated or ready for public access.
"""
from __future__ import annotations

from datetime import datetime
import re

from filelock import FileLock, Timeout

from demo_data import sample_records
from note_tasks import candidate_tasks
from storage import (DataError, TZ, data_path, is_demo_storage, load_json,
                     update_json, validate_event, validate_task, validate_feedback)

SEED_VERSION = 1
SEEDED_STATUS = "seeded_pending_auth"
KEYS = {"events": "event_id", "availability": "availability_id",
        "tasks": "task_id", "plan": "task_id", "feedback": "feedback_id",
        "external_events": "id"}
REFERENCE_FIELDS = {"event_id", "availability_id", "preferred_availability_id",
                    "task_id", "feedback_id", "source_feedback_id",
                    "source_event_id", "webhook_event_id", "id"}


def _records(user_id: str, anchor: datetime) -> dict[str, list]:
    fixture = sample_records(anchor)
    records = {}
    for name in KEYS:
        rows = []
        for original in fixture[name]:
            row = dict(original)
            for key in REFERENCE_FIELDS:
                if row.get(key):
                    row[key] = f"{user_id}_{row[key]}"
            row["user_id"] = user_id
            row["demo_seed_version"] = SEED_VERSION
            if name == "feedback":
                # Historical demo notes must not imply actual LINE delivery.
                row["reminder_id"] = ""
            rows.append(row)
        records[name] = rows

    # One illustrative already-confirmed purple task; keep other questions
    # available for explicit human confirmation. No actual AI API calls.
    candidates = candidate_tasks(records["feedback"], records["events"],
                                 records["tasks"], user_id, anchor)
    if candidates:
        item = candidates[0]
        records["tasks"].append({
            "task_id": f"aiq_{item['source_question_key']}",
            "user_id": user_id, "subject": item["subject"],
            "title": item["suggested_task"],
            "deadline": item["deadline"], "deadline_at": item["deadline_at"],
            "estimated_minutes": 30, "status": "pending",
            "preferred_availability_id": "", "source": "ai_confirmed",
            "suggestion_method": "question_rule",
            "source_feedback_id": item["source_feedback_id"],
            "source_event_id": item["source_event_id"],
            "source_question_key": item["source_question_key"],
            "source_question": item["question"],
            "source_class_date": item["source_class_date"],
            "demo_seed_version": SEED_VERSION,
        })
    for name, validate in (("events", validate_event), ("tasks", validate_task),
                           ("feedback", validate_feedback)):
        for row in records[name]:
            validate(row)
    return records


def _append_missing(name: str, entries: list, user_id: str) -> None:
    key = KEYS[name]

    def append(rows):
        existing = {}
        for row in rows:
            existing.setdefault(row.get(key), []).append(row)
        additions = []
        for entry in entries:
            matches = existing.get(entry[key], [])
            if matches:
                if len(matches) != 1 or matches[0].get("user_id") != user_id or (
                    matches[0].get("demo_seed_version") != SEED_VERSION
                ):
                    raise DataError("Demo 資料識別碼衝突，停止初始化")
                continue
            additions.append(entry)
        return rows + additions

    update_json(data_path(name), append)


def seed_line_user(user_id: str, now: datetime | None = None) -> bool:
    """Return True only on the first completed seed. Retry keeps prior rows."""
    if is_demo_storage():
        raise DataError("不能在共用展示資料目錄初始化 LINE 好友")
    if not isinstance(user_id, str) or not re.fullmatch(r"lineuser_[0-9a-f]{12}", user_id):
        raise DataError("只允許獨立 LINE 帳號初始化")
    path = data_path("users")
    path.parent.mkdir(parents=True, exist_ok=True)
    current = now or datetime.now(TZ)
    current = current.astimezone(TZ) if current.tzinfo else current.replace(tzinfo=TZ)
    try:
        with FileLock(str(path.parent / f".seed_{user_id}.lock"), timeout=8):
            rows = load_json(path)
            user = next((row for row in rows if row.get("user_id") == user_id), None)
            if user is None or not user.get("line_user_id"):
                raise DataError("找不到已註冊的 LINE 帳號")
            if user.get("demo_status") == SEEDED_STATUS and user.get("demo_seed_version") == SEED_VERSION:
                return False
            if user.get("demo_status") != "pending_seed":
                raise DataError("此帳號不在待初始化狀態")

            anchor_text = user.get("demo_seed_started_at") or current.isoformat(timespec="seconds")

            def start(rows):
                found = False
                for row in rows:
                    if row.get("user_id") == user_id:
                        if row.get("demo_status") != "pending_seed":
                            raise DataError("帳號初始化狀態已改變")
                        row.setdefault("demo_seed_started_at", anchor_text)
                        found = True
                if not found:
                    raise DataError("帳號不存在")
                return rows

            update_json(path, start)
            anchor = datetime.fromisoformat(anchor_text)
            records = _records(user_id, anchor)
            for name, entries in records.items():
                _append_missing(name, entries, user_id)

            def finish(rows):
                found = False
                for row in rows:
                    if row.get("user_id") == user_id:
                        if row.get("demo_status") != "pending_seed":
                            raise DataError("帳號初始化狀態已改變")
                        row.update(demo_status=SEEDED_STATUS, demo_seed_version=SEED_VERSION,
                                   demo_seeded_at=current.isoformat(timespec="seconds"),
                                   reminders_enabled=False, study_reminders_enabled=False,
                                   ai_after_class_enabled=False)
                        found = True
                if not found:
                    raise DataError("帳號不存在")
                return rows

            update_json(path, finish)
            return True
    except (Timeout, OSError) as exc:
        raise DataError("LINE Demo 初始化鎖定失敗") from exc
