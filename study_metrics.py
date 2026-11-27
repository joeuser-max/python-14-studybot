"""個人總覽：三個可稽核、低負擔的數值；不把自填紀錄當成客觀學力。"""
from datetime import datetime
from storage import TZ


def personal_metrics(tasks: list[dict], reminders: list[dict], user_id: str) -> dict:
    mine = [t for t in tasks if t.get("user_id") == user_id]
    completed = {t["task_id"] for t in mine if t.get("status") == "completed"}
    checkins = [r for r in reminders if r.get("user_id") == user_id
                and r.get("kind") == "study_session_checkin"
                and r.get("status") == "sent"]
    seen = {}
    for row in checkins:
        # 以 reminder_id 去重，避免重試重複加分。
        seen[row.get("reminder_id")] = row
    confirmed = {
        row.get("task_id") for row in seen.values()
        if row.get("progress_status") == "completed" and row.get("task_id") in completed
    }
    progress = round(len(completed) / len(mine) * 100) if mine else None
    checkin_rate = round(sum(r.get("progress_status") == "completed"
                             for r in seen.values()) / len(seen) * 100) if seen else None
    # XP 是遊戲回饋，不是 Elo、排名、能力或防作弊驗證分數。
    xp = len(completed) * 20 + len(confirmed) * 10
    return {
        "completion": progress, "completed": len(completed), "total": len(mine),
        "checkin_rate": checkin_rate, "confirmed_sessions": len(confirmed),
        "sent_checkins": len(seen), "xp": xp, "level": 1 + xp // 100,
    }


BENCHMARK_TEMPLATES = {
    "晚間穩定型": {"name": "晚間穩定型（示範訓練菜單）", "sessions_per_week": 4,
                 "preferred_periods": ["A", "B", "C"], "maximum_blocks": 2,
                 "goal": "低干擾、固定節奏、能長期持續"},
    "短時高頻型": {"name": "短時高頻型（示範訓練菜單）", "sessions_per_week": 6,
                 "preferred_periods": ["1", "2", "5", "6", "A"],
                 "maximum_blocks": 1, "goal": "每日小步推進、降低啟動負擔"},
    "集中深度型": {"name": "集中深度型（示範訓練菜單）", "sessions_per_week": 3,
                 "preferred_periods": ["5", "6", "7", "8", "A", "B"],
                 "maximum_blocks": 3, "goal": "安排較長的連續專注區段"},
}


def anonymized_benchmark(metrics: dict, template: dict) -> dict:
    """只輸出 aggregate 與訓練策略，不包含姓名、課名、LINE ID 或學號。"""
    return {
        "plan_style": template.get("name", "自訂模板"),
        "suggested_sessions": template.get("sessions_per_week", 4),
        "preferred_periods": template.get("preferred_periods", []),
        "maximum_blocks": template.get("maximum_blocks", 2),
        "style_goal": template.get("goal", ""),
        "user_completion_rate": metrics.get("completion"),
        "user_checkin_rate": metrics.get("checkin_rate"),
    }
