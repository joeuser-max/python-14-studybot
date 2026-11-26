"""由真實任務狀態變化產出的完成量統計；不以預設假資料冒充學習成果。"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")


def make_progress_event(before: dict, after: dict,
                        now: datetime | None = None) -> dict | None:
    old_percent = int(before.get("progress_percent",
                                 100 if before.get("status") == "completed" else 0))
    percent = int(after.get("progress_percent",
                            100 if after.get("status") == "completed" else 0))
    old_completed = before.get("status") == "completed"
    completed = after.get("status") == "completed"
    if old_percent == percent and old_completed == completed:
        return None
    timestamp = (now or datetime.now(TZ)).astimezone(TZ)
    return {
        "task_id": after["task_id"], "user_id": after["user_id"],
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "old_percent": old_percent, "progress_percent": percent,
        "status": after["status"], "estimated_minutes": int(after["estimated_minutes"]),
        "source": "user_action",
    }


def history_series(events: list[dict], tasks: list[dict], user_id: str,
                   period: str, now: datetime | None = None) -> dict:
    """1日／7日／30日的真實完成事件；只計算目前仍標為 completed 的任務最後完成日。"""
    if period not in ("1D", "1W", "1M"):
        raise ValueError("統計區間必須是 1D、1W、1M")
    now = (now or datetime.now(TZ)).astimezone(TZ)
    num_days = {"1D": 1, "1W": 7, "1M": 30}[period]
    start = now.date() - timedelta(days=num_days - 1)
    own_tasks = {t["task_id"]: t for t in tasks if t.get("user_id") == user_id}
    latest: dict[str, dict] = {}
    for ev in events:
        task_id = ev.get("task_id")
        if ev.get("user_id") != user_id or task_id not in own_tasks:
            continue
        try:
            ts = datetime.fromisoformat(ev["timestamp"])
            ts = ts.replace(tzinfo=TZ) if ts.tzinfo is None else ts.astimezone(TZ)
        except (ValueError, TypeError, KeyError):
            continue
        if ts > now:
            continue
        if task_id not in latest or ts > latest[task_id]["time"]:
            latest[task_id] = {"time": ts, "event": ev}
    daily = {start + timedelta(days=i): {"completed": 0, "planned_minutes": 0}
             for i in range(num_days)}
    for task_id, entry in latest.items():
        task = own_tasks[task_id]
        ev = entry["event"]
        completed_on = entry["time"].date()
        if task.get("status") != "completed" or ev.get("status") != "completed":
            continue
        if completed_on in daily:
            daily[completed_on]["completed"] += 1
            daily[completed_on]["planned_minutes"] += max(0, int(ev.get("estimated_minutes", 0)))
    if period == "1D":
        hourly = {f"{hour:02d}:00": {"completed": 0, "planned_minutes": 0}
                  for hour in range(24)}
        for task_id, entry in latest.items():
            task = own_tasks[task_id]
            ev = entry["event"]
            if (task.get("status") != "completed" or ev.get("status") != "completed"
                    or entry["time"].date() != now.date()):
                continue
            item = hourly[f"{entry['time'].hour:02d}:00"]
            item["completed"] += 1
            item["planned_minutes"] += max(0, int(ev.get("estimated_minutes", 0)))
        rows = [{"date": clock, **data} for clock, data in hourly.items()]
    else:
        rows = [{"date": day.isoformat(), **data} for day, data in daily.items()]
    cumulative = 0
    for item in rows:
        cumulative += item["completed"]
        item["cumulative"] = cumulative
    return {
        "period": period,
        "completed": sum(x["completed"] for x in rows),
        "planned_minutes": sum(x["planned_minutes"] for x in rows),
        "active_days": sum(x["completed"] > 0 for x in rows),
        "rows": rows,
    }
