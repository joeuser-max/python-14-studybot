"""管理控制台的任務寫入動作：顯式指定 Demo / 正式資料庫。"""
from __future__ import annotations

import storage


def save_task_changes(task: dict, *, demo_mode: bool) -> list:
    """在指定的資料目錄更新任務，並使舊排程失效。

    不依賴 Streamlit dialog/fragment 是否已執行網頁頂部的初始化。
    """
    storage.select_demo_storage(demo_mode)
    result = storage.update_task(task)
    storage.update_json(
        storage.data_path("plan"),
        lambda items: [row for row in items if row.get("user_id") != task["user_id"]],
    )
    return result


def delete_task_and_plan(task_id: str, user_id: str, *, demo_mode: bool) -> None:
    """刪除所選使用者的任務及其排程，保護其他使用者的資料。"""
    storage.select_demo_storage(demo_mode)

    def delete(items: list) -> list:
        if not any(row.get("task_id") == task_id
                   and row.get("user_id") == user_id for row in items):
            raise storage.DataError("找不到要刪除的任務，請重新整理")
        return [row for row in items if not (row.get("task_id") == task_id
                                           and row.get("user_id") == user_id)]

    storage.update_json(storage.data_path("tasks"), delete)
    storage.update_json(
        storage.data_path("plan"),
        lambda items: [row for row in items
                       if not (row.get("task_id") == task_id
                               and row.get("user_id") == user_id)],
    )
