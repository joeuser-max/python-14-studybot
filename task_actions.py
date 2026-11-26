"""編輯任務：確保資料路徑明確、任務進度有歷史紀錄，重新排程可持久化。"""
from __future__ import annotations

import storage
from progress_insights import make_progress_event
from visual_planner import MANUAL_PREFIX, rebuild_plan


def _remove_manual_slot(task_id: str) -> None:
    slot_id = MANUAL_PREFIX + task_id
    storage.update_json(
        storage.data_path("availability"),
        lambda rows: [r for r in rows if r.get("availability_id") != slot_id],
    )


def save_task_changes(task: dict, *, demo_mode: bool) -> list:
    """編輯後重新排程；完成度變更才寫入真實的 progress_events。"""
    storage.select_demo_storage(demo_mode)
    current = storage.load_json(storage.data_path("tasks"))
    previous = next((t for t in current if t.get("task_id") == task["task_id"]
                     and t.get("user_id") == task["user_id"]), None)
    if not previous:
        raise storage.DataError("找不到要修改的任務，請重新整理後再試")
    updated = dict(task)
    if updated.get("status") == "completed":
        _remove_manual_slot(updated["task_id"])
        if updated.get("preferred_availability_id") == MANUAL_PREFIX + updated["task_id"]:
            updated["preferred_availability_id"] = ""
    result = storage.update_task(updated)
    event = make_progress_event(previous, updated)
    if event:
        storage.update_json(storage.data_path("progress_events"),
                            lambda rows: rows + [event])
    rebuild_plan(updated["user_id"])
    return result


def delete_task_and_plan(task_id: str, user_id: str, *, demo_mode: bool) -> None:
    """刪除任務以及對應的手動時間；統計只計算仍存在的任務。"""
    storage.select_demo_storage(demo_mode)

    def delete(items: list) -> list:
        if not any(row.get("task_id") == task_id
                   and row.get("user_id") == user_id for row in items):
            raise storage.DataError("找不到要刪除的任務，請重新整理")
        return [row for row in items if not (row.get("task_id") == task_id
                                           and row.get("user_id") == user_id)]
    storage.update_json(storage.data_path("tasks"), delete)
    _remove_manual_slot(task_id)
    rebuild_plan(user_id)
