"""銜接 B scheduler.make_plan 的輸出與 A 的單使用者資料檢視。"""
from __future__ import annotations


def normalize_plan_result(result: object, user_id: str) -> list[dict]:
    """接受 B 的 {'plan': [...], 'new_alerts': [...]} 回傳，保留原排程欄位。"""
    if isinstance(result, dict):
        plan = result.get("plan")
    elif isinstance(result, tuple) and len(result) == 2:
        plan = result[0]
    else:
        plan = result
    if not isinstance(plan, list) or any(not isinstance(item, dict) for item in plan):
        raise ValueError("scheduler.make_plan 必須回傳包含 dict 清單的 plan")
    return [{**row, "user_id": user_id} for row in plan]


def merge_user_plan(rows: list[dict], user_id: str, new_plan: list[dict]) -> list[dict]:
    """Replace one user's plan while preserving alert-delivery state and other users."""
    previous = {
        row.get("task_id"): row
        for row in rows
        if row.get("user_id") == user_id
    }
    merged = []
    for row in new_plan:
        updated = {**row, "user_id": user_id}
        old = previous.get(updated.get("task_id"), {})
        if (
            updated.get("unscheduled_alert_id")
            and updated.get("unscheduled_alert_id") == old.get("unscheduled_alert_id")
            and old.get("unscheduled_alerted")
        ):
            updated["unscheduled_alerted"] = True
        merged.append(updated)
    return [row for row in rows if row.get("user_id") != user_id] + merged
