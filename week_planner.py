"""七日行事曆的排程引擎：手動拖排與自動填滿完全分離。

中大節次 1-4 / Z / 5-9 / A-D 參照校方節次；E、F 是本專題延伸的
22:00、23:00 時段，不代表學校正式開課時間。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import ceil
from uuid import uuid4

from storage import DataError, TZ, data_path, load_json, update_json, update_task

PERIODS = (
    ("1", 8), ("2", 9), ("3", 10), ("4", 11), ("Z", 12),
    ("5", 13), ("6", 14), ("7", 15), ("8", 16), ("9", 17),
    ("A", 18), ("B", 19), ("C", 20), ("D", 21), ("E", 22), ("F", 23),
)
PERIOD_BY_LABEL = {label: hour for label, hour in PERIODS}
MAX_BLOCKS = 4


def rolling_dates(now: datetime) -> list[date]:
    today = now.astimezone(TZ).date() if now.tzinfo else now.date()
    return [today + timedelta(days=i) for i in range(7)]


def _start(day: date, period: str) -> datetime:
    if period not in PERIOD_BY_LABEL:
        raise DataError("無效的中央大學節次")
    return datetime.combine(day, time(PERIOD_BY_LABEL[period]), tzinfo=TZ)


def _overlap(a: datetime, b: datetime, c: datetime, d: datetime) -> bool:
    return a < d and c < b


def _datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)


def _slot_interval(slot: dict, row: dict | None = None) -> tuple[datetime, datetime]:
    start = _datetime(row["scheduled_start"]) if row and row.get("scheduled_start") else _datetime(
        slot["date"] + "T" + slot["start_time"]
    )
    minutes = int((row or {}).get("scheduled_minutes") or slot["available_minutes"])
    return start, start + timedelta(minutes=minutes)


def _busy(courses: list, external: list, tasks: list, slots: list,
          plan: list, day: date, user_id: str, skip_task_id: str = "") -> list[tuple]:
    occupied = []
    for course in courses:
        if course.get("user_id") != user_id or course.get("weekday") != day.isoweekday():
            continue
        try:
            occupied.append((
                _datetime(day.isoformat() + "T" + course["start_time"]),
                _datetime(day.isoformat() + "T" + course["end_time"]),
            ))
        except (KeyError, ValueError):
            continue
    for event in external:
        if event.get("user_id") != user_id:
            continue
        try:
            occupied.append((_datetime(event["start"]), _datetime(event["end"])))
        except (KeyError, ValueError):
            continue
    task_map = {task.get("task_id"): task for task in tasks}
    slot_map = {slot.get("availability_id"): slot for slot in slots}
    for row in plan:
        if (row.get("user_id") != user_id or row.get("status") != "scheduled"
                or row.get("task_id") == skip_task_id):
            continue
        if task_map.get(row.get("task_id"), {}).get("status") != "pending":
            continue
        slot = slot_map.get(row.get("availability_id"))
        if slot:
            try:
                occupied.append(_slot_interval(slot, row))
            except (KeyError, ValueError):
                continue
    return occupied


def _read_all() -> dict[str, list]:
    return {name: load_json(data_path(name))
            for name in ("events", "tasks", "availability", "plan", "external_events")}


def _candidate(task: dict, day: date, period: str, blocks: int,
               records: dict, now: datetime, user_id: str, *, skip_self=True) -> tuple[datetime, datetime]:
    if task.get("user_id") != user_id or task.get("status") != "pending":
        raise DataError("任務不存在或已完成")
    if type(blocks) is not int or not 1 <= blocks <= MAX_BLOCKS:
        raise DataError("任務長度須為 1–4 節；請用待排卡片右側把手調整")
    if day not in rolling_dates(now):
        raise DataError("只能排入今天到未來第六天（T+0 至 T+6）")
    start = _start(day, period)
    end = start + timedelta(hours=blocks)
    if end.date() > day and end.time() != time.min:
        raise DataError("任務不能跨越午夜")
    if start <= now:
        raise DataError("已過去的節次不能排入")
    deadline = date.fromisoformat(task["deadline"])
    if end > datetime.combine(deadline + timedelta(days=1), time.min, tzinfo=TZ):
        raise DataError("排程結束時間超過任務 Deadline")
    occupied = _busy(records["events"], records["external_events"], records["tasks"],
                     records["availability"], records["plan"], day, user_id,
                     task["task_id"] if skip_self else "")
    if any(_overlap(start, end, a, b) for a, b in occupied):
        raise DataError("與課程、外部行事曆或其他任務衝突，未覆寫任何安排")
    return start, end


def place_manual(user_id: str, task_id: str, day: str, period: str,
                 blocks: int, now: datetime | None = None) -> dict:
    """只修改被拖動的任務；不執行自動排程。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = _read_all()
    task = next((t for t in records["tasks"] if t.get("user_id") == user_id
                 and t.get("task_id") == task_id), None)
    if not task:
        raise DataError("找不到這筆任務")
    chosen_day = date.fromisoformat(day)
    start, _ = _candidate(task, chosen_day, period, blocks, records, now, user_id)
    minutes = blocks * 60
    slot_id = f"board_{task_id}"
    slot = {
        "availability_id": slot_id, "user_id": user_id,
        "date": chosen_day.isoformat(), "start_time": start.strftime("%H:%M"),
        "available_minutes": minutes, "board_generated": True,
    }
    # 先建立 slot 再更新 plan，使任何已儲存的 plan 指向已存在的 slot。
    def put_slot(rows):
        return [row for row in rows if row.get("availability_id") != slot_id] + [slot]
    update_json(data_path("availability"), put_slot)
    entry = {
        "task_id": task_id, "user_id": user_id, "availability_id": slot_id,
        "status": "scheduled", "source": "manual", "reason": "",
        "scheduled_start": start.isoformat(timespec="minutes"),
        "scheduled_minutes": minutes, "unscheduled_alerted": False,
    }
    update_json(data_path("plan"), lambda rows: [
        row for row in rows if not (row.get("user_id") == user_id
                                   and row.get("task_id") == task_id)
    ] + [entry])
    # 視覺卡片調整的工時就是最新預估；從此無需數字輸入框。
    modified = {**task, "estimated_minutes": minutes,
                "preferred_availability_id": ""}
    if task.get("remaining_minutes") is not None:
        modified["remaining_minutes"] = minutes
    update_task(modified)
    return entry


def set_task_blocks(user_id: str, task_id: str, blocks: int) -> None:
    if type(blocks) is not int or not 1 <= blocks <= MAX_BLOCKS:
        raise DataError("長度須為 1–4 節")
    tasks = load_json(data_path("tasks"))
    task = next((t for t in tasks if t.get("user_id") == user_id
                 and t.get("task_id") == task_id), None)
    if not task:
        raise DataError("找不到任務")
    plan = load_json(data_path("plan"))
    if any(p.get("task_id") == task_id and p.get("status") == "scheduled"
           for p in plan):
        raise DataError("已排任務請先移回待排區，再拉長或縮短")
    modified = {**task, "estimated_minutes": blocks * 60,
                "preferred_availability_id": ""}
    if task.get("remaining_minutes") is not None:
        modified["remaining_minutes"] = blocks * 60
    update_task(modified)


def unplace(user_id: str, task_id: str) -> None:
    """回到待排區，但不讓其他待排任務自動移動。"""
    update_json(data_path("plan"), lambda rows: [
        row for row in rows if not (row.get("user_id") == user_id
                                   and row.get("task_id") == task_id)
    ])
    update_json(data_path("availability"), lambda rows: [
        row for row in rows if not (row.get("availability_id") == f"board_{task_id}"
                                   and row.get("user_id") == user_id)
    ])


def fill_remaining(user_id: str, now: datetime | None = None) -> dict:
    """一鍵填滿：只處理未排入任務，依 Deadline→較長工時優先，再找最早連續空格。

    手動安排與既有有效排程不會移動；每個任務為單一連續區塊。
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = _read_all()
    slot_map = {slot.get("availability_id"): slot for slot in records["availability"]}
    planned = set()
    for row in records["plan"]:
        if row.get("user_id") != user_id or row.get("status") != "scheduled":
            continue
        slot = slot_map.get(row.get("availability_id"))
        if not slot:
            continue
        try:
            _, finish = _slot_interval(slot, row)
        except (KeyError, ValueError):
            continue
        if finish > now:
            planned.add(row.get("task_id"))
    remaining = sorted((
        task for task in records["tasks"]
        if task.get("user_id") == user_id and task.get("status") == "pending"
        and task.get("task_id") not in planned
    ), key=lambda t: (t["deadline"], -int(t.get("remaining_minutes") or t["estimated_minutes"]), t["task_id"]))
    placed, skipped = [], []
    for task in remaining:
        minutes = int(task.get("remaining_minutes") or task["estimated_minutes"])
        blocks = ceil(minutes / 60)
        if blocks > MAX_BLOCKS:
            skipped.append((task["task_id"], "超過單次四節上限，請拆成較小任務"))
            continue
        match = None
        for day in rolling_dates(now):
            if day > date.fromisoformat(task["deadline"]):
                break
            for label, _ in PERIODS:
                try:
                    start, end = _candidate(task, day, label, blocks, records, now, user_id)
                except DataError:
                    continue
                match = (day, label, start, end)
                break
            if match:
                break
        if not match:
            skipped.append((task["task_id"], "七日內沒有連續且不衝突的時段"))
            continue
        day, label, start, end = match
        slot_id = f"board_{task['task_id']}"
        slot = {
            "availability_id": slot_id, "user_id": user_id,
            "date": day.isoformat(), "start_time": start.strftime("%H:%M"),
            "available_minutes": blocks * 60, "board_generated": True,
        }
        entry = {
            "task_id": task["task_id"], "user_id": user_id, "availability_id": slot_id,
            "status": "scheduled", "source": "auto", "reason": "",
            "scheduled_start": start.isoformat(timespec="minutes"),
            "scheduled_minutes": blocks * 60, "unscheduled_alerted": False,
        }
        records["availability"].append(slot)
        records["plan"].append(entry)
        placed.append(entry)
    if placed:
        update_json(data_path("availability"), lambda rows: rows + [
            slot for slot in records["availability"] if slot.get("board_generated")
            and slot.get("availability_id") in {r["availability_id"] for r in placed}
        ])
        placed_ids = {row["task_id"] for row in placed}
        update_json(data_path("plan"), lambda rows: [
            row for row in rows
            if not (row.get("user_id") == user_id
                    and row.get("task_id") in placed_ids)
        ] + placed)
    return {"placed": placed, "skipped": skipped}


def board_payload(user_id: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = _read_all()
    tasks = [t for t in records["tasks"] if t.get("user_id") == user_id]
    slots = {s["availability_id"]: s for s in records["availability"]}
    plan = {}
    for entry in records["plan"]:
        if entry.get("user_id") != user_id or entry.get("status") != "scheduled":
            continue
        slot = slots.get(entry.get("availability_id"))
        if not slot:
            continue
        try:
            _, end = _slot_interval(slot, entry)
            if end > now:
                plan[entry["task_id"]] = entry
        except (KeyError, ValueError):
            continue
    scheduled = []
    for task_id, entry in plan.items():
        task = next((t for t in tasks if t.get("task_id") == task_id
                     and t.get("status") == "pending"), None)
        slot = slots.get(entry.get("availability_id"))
        if not task or not slot:
            continue
        try:
            start, end = _slot_interval(slot, entry)
        except (KeyError, ValueError):
            continue
        if start.date() not in rolling_dates(now):
            continue
        scheduled.append({
            "task_id": task_id, "title": task["title"], "subject": task["subject"],
            "day": start.date().isoformat(), "hour": start.hour,
            "start": start.isoformat(), "end": end.isoformat(),
            "blocks": max(1, ceil((end - start).total_seconds() / 3600)),
            "source": entry.get("source", "auto"),
        })
    external = [e for e in records["external_events"] if e.get("user_id") == user_id]
    return {
        "days": [{"date": d.isoformat(), "label": "週" + "一二三四五六日"[d.weekday()],
                  "day_number": d.strftime("%m/%d")} for d in rolling_dates(now)],
        "periods": [{"label": label, "hour": h,
                     "time": f"{h:02d}:00–{(h+1)%24:02d}:00"} for label, h in PERIODS],
        "tasks": [{"task_id": t["task_id"], "title": t["title"], "subject": t["subject"],
                   "deadline": t["deadline"], "blocks": max(1, min(MAX_BLOCKS,
                   ceil(int(t.get("remaining_minutes") or t["estimated_minutes"]) / 60)))}
                  for t in tasks if t.get("status") == "pending" and t["task_id"] not in plan],
        "scheduled": scheduled,
        "courses": [{"weekday": c["weekday"], "start": c["start_time"],
                     "end": c["end_time"], "title": c["title"]}
                    for c in records["events"] if c.get("user_id") == user_id],
        "external": external,
        "today": now.date().isoformat(), "now_hour": now.hour, "now_iso": now.isoformat(),
    }
