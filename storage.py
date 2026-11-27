"""ClassPulse JSON 資料存取與驗證（蕭博軒）。

所有程序以同一個檔案鎖進行讀寫，再使用 os.replace 原子替換單檔。
跨多個 JSON 檔案不保證交易一致性；筆記與 webhook ID 因此放在同一筆 feedback 中。
"""
from __future__ import annotations

from contextvars import ContextVar
import json
import os
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from filelock import FileLock, Timeout

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.environ.get("CLASSPULSE_DATA_DIR", str(ROOT / "data"))).resolve()
DEMO_DATA_DIR = ROOT / ".classpulse-demo-data"
_ACTIVE_DATA_DIR: ContextVar[Path | None] = ContextVar("classpulse_active_data_dir", default=None)
FILES = {
    "events": "events.json", "tasks": "tasks.json", "availability": "availability.json",
    "plan": "plan.json", "users": "users.json", "reminders": "reminders.json",
    "feedback": "feedback.json", "pending_notes": "pending_notes.json",
    "processed_webhooks": "processed_webhooks.json",
    "external_events": "external_events.json",
    "preference_targets": "preference_targets.json",
}
TZ = ZoneInfo("Asia/Taipei")


class DataError(ValueError):
    """資料錯誤，應在 Streamlit 顯示給使用者。"""


def select_demo_storage(enabled: bool) -> None:
    """只為目前的執行 context 切換展示資料，不更動 LINE Worker 的正式資料路徑。"""
    _ACTIVE_DATA_DIR.set(DEMO_DATA_DIR if enabled else None)


def is_demo_storage() -> bool:
    return _ACTIVE_DATA_DIR.get() is not None


def data_path(name: str) -> Path:
    if name not in FILES:
        raise DataError(f"未知的資料類型：{name}")
    directory = _ACTIVE_DATA_DIR.get()
    return (directory if directory is not None else DATA_DIR) / FILES[name]


def _read_unlocked(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            result = json.load(f)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f"{path.name} 格式損壞，為避免資料遺失，已停止操作：{exc}") from exc
    except OSError as exc:
        raise DataError(f"讀取 {path.name} 失敗：{exc}") from exc
    if not isinstance(result, list):
        raise DataError(f"{path.name} 必須以 JSON 陣列儲存")
    return result


def load_json(path: str | Path) -> list:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=8):
            return _read_unlocked(path)
    except (Timeout, OSError) as exc:
        raise DataError(f"讀取 {path.name} 時無法取得鎖定：{exc}") from exc


def _write_unlocked(path: Path, data: list) -> None:
    if not isinstance(data, list):
        raise DataError("只能儲存 list 型態的 JSON 資料")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_json(path: str | Path, data: list) -> None:
    """保護損壞的舊資料不被覆蓋；不能直接拿來執行讀改寫，應使用 update_json。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=8):
            _read_unlocked(path)  # 舊檔案損壞時拒絕覆蓋
            _write_unlocked(path, data)
    except (Timeout, OSError) as exc:
        raise DataError(f"儲存 {path.name} 失敗：{exc}") from exc


def update_json(path: str | Path, update: Callable[[list], list]) -> list:
    """在同一個鎖內完成讀取、更新、寫入，避免多程序覆蓋彼此的資料。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=8):
            current = _read_unlocked(path)
            changed = update(current)
            if not isinstance(changed, list):
                raise DataError("資料更新函式必須回傳 list")
            _write_unlocked(path, changed)
            return changed
    except (Timeout, OSError) as exc:
        raise DataError(f"更新 {path.name} 失敗：{exc}") from exc


def _require_string(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{key} 不可空白")
    return value.strip()


def _clock(value: str) -> time:
    try:
        if len(value) != 5 or value[2] != ":":
            raise ValueError
        return time.fromisoformat(value)
    except ValueError as exc:
        raise DataError(f"時間格式應為 HH:MM：{value}") from exc


def validate_event(event: dict) -> dict:
    for key in ("event_id", "user_id", "title", "event_type", "prompt_template"):
        _require_string(event, key)
    if event["event_type"] != "class":
        raise DataError("MVP 只支援 event_type='class'")
    if event["prompt_template"] != "class_feedback":
        raise DataError("MVP 只支援 prompt_template='class_feedback'")
    if type(event.get("weekday")) is not int or not 1 <= event["weekday"] <= 7:
        raise DataError("星期必須為 1–7（週一～週日）")
    start = _clock(_require_string(event, "start_time"))
    end = _clock(_require_string(event, "end_time"))
    if start >= end:
        raise DataError("下課時間必須晚於上課時間")
    if type(event.get("offset_minutes")) is not int or not 0 <= event["offset_minutes"] <= 60:
        raise DataError("提醒偏移必須為 0–60 分鐘")
    if type(event.get("enabled")) is not bool:
        raise DataError("enabled 必須為 true 或 false")
    return event


def validate_task(task: dict) -> dict:
    for key in ("task_id", "user_id", "subject", "title"):
        _require_string(task, key)
    try:
        date.fromisoformat(_require_string(task, "deadline"))
    except ValueError as exc:
        raise DataError("Deadline 日期格式錯誤") from exc
    if type(task.get("estimated_minutes")) is not int or task["estimated_minutes"] <= 0:
        raise DataError("預估時間必須是正整數分鐘")
    remaining = task.get("remaining_minutes")
    if remaining is not None and (type(remaining) is not int or remaining <= 0):
        raise DataError("剩餘時間必須是正整數分鐘")
    if task.get("status") not in ("pending", "completed"):
        raise DataError("status 應為 pending 或 completed")
    if not isinstance(task.get("preferred_availability_id", ""), str):
        raise DataError("preferred_availability_id 必須是字串")
    return task


def validate_availability(slot: dict, existing: list | None = None) -> dict:
    for key in ("availability_id", "user_id"):
        _require_string(slot, key)
    try:
        selected_date = date.fromisoformat(_require_string(slot, "date"))
    except ValueError as exc:
        raise DataError("日期格式錯誤") from exc
    start = _clock(_require_string(slot, "start_time"))
    minutes = slot.get("available_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        raise DataError("可用時段長度須為正整數（最多 1440 分鐘）")
    beginning = datetime.combine(selected_date, start)
    ending = beginning + timedelta(minutes=minutes)
    if (
        ending.date() != selected_date
        and ending != datetime.combine(selected_date + timedelta(days=1), time.min)
    ):
        raise DataError("MVP 不支援跨午夜時段")
    for old in existing or []:
        if old.get("user_id") != slot["user_id"] or old.get("date") != slot["date"]:
            continue
        if old.get("availability_id") == slot["availability_id"]:
            raise DataError("時段 ID 已存在")
        old_begin = datetime.combine(selected_date, _clock(old["start_time"]))
        old_end = old_begin + timedelta(minutes=old["available_minutes"])
        if beginning < old_end and old_begin < ending:
            raise DataError("可用讀書時段彼此重疊")
    return slot


def add_event(event: dict) -> list:
    validate_event(event)
    def change(items: list) -> list:
        if any(x.get("event_id") == event["event_id"] for x in items):
            raise DataError("event_id 已存在")
        return items + [event]
    return update_json(data_path("events"), change)


def update_event(event: dict) -> list:
    validate_event(event)

    def change(items: list) -> list:
        if not any(row.get("event_id") == event["event_id"] for row in items):
            raise DataError("找不到要修改的課程，請重新整理後再試")
        return [
            event if row.get("event_id") == event["event_id"] else row
            for row in items
        ]
    return update_json(data_path("events"), change)


def add_task(data: list, task: dict) -> list:
    validate_task(task)
    if any(item.get("task_id") == task["task_id"] for item in data):
        raise DataError("task_id 已存在")
    return data + [task]


def add_task_to_storage(task: dict) -> list:
    return update_json(data_path("tasks"), lambda items: add_task(items, task))


def update_task(task: dict) -> list:
    validate_task(task)

    def change(items: list) -> list:
        existing = next(
            (
                row for row in items
                if row.get("task_id") == task["task_id"]
                and row.get("user_id") == task["user_id"]
            ),
            None,
        )
        if existing is None:
            raise DataError("找不到要修改的任務，請重新整理後再試")
        return [
            task if row is existing else row
            for row in items
        ]
    return update_json(data_path("tasks"), change)


def record_task_progress(
    task_id: str,
    user_id: str,
    completed: bool,
    remaining_minutes: int | None = None,
    previous_availability_id: str = "",
) -> list:
    if type(completed) is not bool:
        raise DataError("完成狀態必須由使用者明確回報")
    if not completed and (type(remaining_minutes) is not int or remaining_minutes <= 0):
        raise DataError("剩餘時間必須是正整數分鐘")

    def change(items: list) -> list:
        found = False
        updated_items = []
        for task in items:
            if task.get("task_id") != task_id or task.get("user_id") != user_id:
                updated_items.append(task)
                continue
            found = True
            updated = {**task, "status": "completed" if completed else "pending"}
            if completed:
                updated.pop("remaining_minutes", None)
            else:
                updated["remaining_minutes"] = remaining_minutes
                if updated.get("preferred_availability_id") == previous_availability_id:
                    updated["preferred_availability_id"] = ""
            updated_items.append(updated)
        if not found:
            raise DataError("找不到要更新的讀書任務")
        return updated_items

    return update_json(data_path("tasks"), change)


def add_availability(slot: dict) -> list:
    def change(items: list) -> list:
        validate_availability(slot, items)
        return items + [slot]
    return update_json(data_path("availability"), change)


def add_availabilities(slots: list[dict]) -> list:
    if not slots:
        raise DataError("請至少勾選一個開始時間")

    def change(items: list) -> list:
        updated_items = list(items)
        for slot in slots:
            validate_availability(slot, updated_items)
            updated_items.append(slot)
        return updated_items

    return update_json(data_path("availability"), change)


def update_availability(slot: dict) -> list:
    def change(items: list) -> list:
        existing = next(
            (
                row for row in items
                if row.get("availability_id") == slot.get("availability_id")
                and row.get("user_id") == slot.get("user_id")
            ),
            None,
        )
        if existing is None:
            raise DataError("找不到要修改的讀書時段，請重新整理後再試")
        others = [row for row in items if row is not existing]
        validate_availability(slot, others)
        return [
            slot if row is existing else row
            for row in items
        ]
    return update_json(data_path("availability"), change)


def clear_task_availability_preference(availability_id: str, user_id: str) -> list:
    def change(items: list) -> list:
        return [
            {
                **task,
                "preferred_availability_id": "",
            }
            if task.get("user_id") == user_id
            and task.get("preferred_availability_id") == availability_id
            else task
            for task in items
        ]

    return update_json(data_path("tasks"), change)


def delete_availability(availability_id: str, user_id: str) -> list:
    def change(items: list) -> list:
        if not any(
            row.get("availability_id") == availability_id
            and row.get("user_id") == user_id
            for row in items
        ):
            raise DataError("找不到要刪除的讀書時段，請重新整理後再試")
        return [
            row
            for row in items
            if not (
                row.get("availability_id") == availability_id
                and row.get("user_id") == user_id
            )
        ]

    return update_json(data_path("availability"), change)


def update_task_status(tasks: list, task_id: str, status: str) -> list:
    if status not in ("pending", "completed"):
        raise DataError("狀態不正確")
    if not any(x.get("task_id") == task_id for x in tasks):
        raise DataError("找不到指定任務")
    return [{**item, "status": status} if item.get("task_id") == task_id else item for item in tasks]


def set_task_status(task_id: str, status: str) -> list:
    return update_json(data_path("tasks"), lambda items: update_task_status(items, task_id, status))


def validate_feedback(feedback: dict) -> dict:
    for key in ("feedback_id", "user_id", "event_id", "class_date", "received_at", "source", "webhook_event_id"):
        _require_string(feedback, key)
    try:
        date.fromisoformat(feedback["class_date"])
        dt = datetime.fromisoformat(feedback["received_at"])
        if dt.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise DataError("回饋日期或時間格式錯誤（必須帶時區）") from exc
    content = feedback.get("content", "")
    if not isinstance(content, str) or len(content.strip()) < 2 or content.strip() in {"補筆記", "取消", "查看筆記"}:
        raise DataError("有效筆記至少兩個字，且不能是 LINE 選單指令")
    progress = feedback.get("progress")
    if progress is not None and (type(progress) is not int or not 1 <= progress <= 5):
        raise DataError("自評進度必須是 1 到 5 的整數")
    if feedback["source"] not in ("selected", "push", "demo"):
        raise DataError("不支援的筆記來源")
    if not isinstance(feedback.get("reminder_id", ""), str):
        raise DataError("reminder_id 必須是字串")
    tags = feedback.get("topic_tags", [])
    if (
        not isinstance(tags, list)
        or len(tags) > 10
        or any(not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 40 for tag in tags)
    ):
        raise DataError("主題標籤須為最多 10 個、每個不超過 40 字的文字")
    return feedback


def save_feedback(feedback: dict, path: str | Path | None = None) -> bool:
    """回傳 True=新增，False=Webhook 重送已存在；去重 ID 與筆記同檔原子寫入。"""
    validate_feedback(feedback)
    result = {"saved": False}
    def change(items: list) -> list:
        if any(x.get("webhook_event_id") == feedback["webhook_event_id"] for x in items):
            return items
        result["saved"] = True
        return items + [feedback]
    update_json(path or data_path("feedback"), change)
    return result["saved"]


def update_feedback_analysis(
    feedback_id: str,
    user_id: str,
    analysis: dict,
) -> list:
    if not isinstance(analysis, dict):
        raise DataError("AI 整理結果格式錯誤")

    def change(items: list) -> list:
        if not any(
            row.get("feedback_id") == feedback_id
            and row.get("user_id") == user_id
            for row in items
        ):
            raise DataError("找不到要更新的課後回饋")
        updated_items = []
        for row in items:
            if row.get("feedback_id") != feedback_id or row.get("user_id") != user_id:
                updated_items.append(row)
                continue
            updated = {**row, "ai_analysis": analysis}
            if "topic_tags" in analysis:
                updated["topic_tags"] = analysis["topic_tags"]
            updated_items.append(updated)
        return updated_items

    return update_json(data_path("feedback"), change)


def update_feedback_topic_tags(
    feedback_id: str,
    user_id: str,
    topic_tags: list[str],
) -> list:
    if (
        not isinstance(topic_tags, list)
        or len(topic_tags) > 10
        or any(not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 40 for tag in topic_tags)
    ):
        raise DataError("主題標籤須為最多 10 個、每個不超過 40 字的文字")
    tags = []
    seen = set()
    for tag in topic_tags:
        normalized = tag.strip()
        key = normalized.casefold()
        if key not in seen:
            tags.append(normalized)
            seen.add(key)

    def change(items: list) -> list:
        if not any(
            row.get("feedback_id") == feedback_id and row.get("user_id") == user_id
            for row in items
        ):
            raise DataError("找不到要更新的筆記")
        return [
            {**row, "topic_tags": tags}
            if row.get("feedback_id") == feedback_id and row.get("user_id") == user_id
            else row
            for row in items
        ]

    return update_json(data_path("feedback"), change)


def search_learning_notes(
    feedbacks: list[dict],
    user_id: str,
    event_id: str = "",
    class_date: str = "",
    topic: str = "",
) -> list[dict]:
    query = topic.strip().casefold()
    matches = []
    for feedback in feedbacks:
        if feedback.get("user_id") != user_id:
            continue
        if event_id and feedback.get("event_id") != event_id:
            continue
        if class_date and feedback.get("class_date") != class_date:
            continue
        if query:
            analysis = feedback.get("ai_analysis", {})
            tags = feedback.get("topic_tags")
            if tags is None and isinstance(analysis, dict):
                tags = analysis.get("topic_tags", [])
            if not isinstance(tags, list):
                tags = []
            if not any(query in tag.casefold() for tag in tags if isinstance(tag, str)):
                continue
        matches.append(feedback)
    return sorted(matches, key=lambda row: row.get("received_at", ""), reverse=True)


def create_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
