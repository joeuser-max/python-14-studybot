"""ClassPulse JSON 資料存取與驗證（蕭博軒）。

所有程序以同一個檔案鎖進行讀寫，再使用 os.replace 原子替換單檔。
跨多個 JSON 檔案不保證交易一致性；筆記與 webhook ID 因此放在同一筆 feedback 中。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from filelock import FileLock, Timeout

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CLASSPULSE_DATA_DIR", str(ROOT / "data"))).resolve()
FILES = {
    "events": "events.json", "tasks": "tasks.json", "availability": "availability.json",
    "plan": "plan.json", "users": "users.json", "reminders": "reminders.json",
    "feedback": "feedback.json", "pending_notes": "pending_notes.json",
    "processed_webhooks": "processed_webhooks.json",
}
TZ = ZoneInfo("Asia/Taipei")


class DataError(ValueError):
    """資料錯誤，應在 Streamlit 顯示給使用者。"""


def data_path(name: str) -> Path:
    if name not in FILES:
        raise DataError(f"未知的資料類型：{name}")
    return DATA_DIR / FILES[name]


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
    if ending.date() != selected_date:
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


def add_task(data: list, task: dict) -> list:
    validate_task(task)
    if any(item.get("task_id") == task["task_id"] for item in data):
        raise DataError("task_id 已存在")
    return data + [task]


def add_task_to_storage(task: dict) -> list:
    return update_json(data_path("tasks"), lambda items: add_task(items, task))


def add_availability(slot: dict) -> list:
    def change(items: list) -> list:
        validate_availability(slot, items)
        return items + [slot]
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
    if feedback["source"] not in ("selected", "push", "demo"):
        raise DataError("不支援的筆記來源")
    if not isinstance(feedback.get("reminder_id", ""), str):
        raise DataError("reminder_id 必須是字串")
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


def create_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
