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
    half=period.endswith("+")
    label=period[:-1] if half else period
    if label not in PERIOD_BY_LABEL:
        raise DataError("無效的中央大學節次")
    return datetime.combine(day, time(PERIOD_BY_LABEL[label],30 if half else 0), tzinfo=TZ)


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
    task_map = {task.get("task_id"): task for task in tasks if task.get("user_id") == user_id}
    slot_map = {slot.get("availability_id"): slot for slot in slots if slot.get("user_id") == user_id}
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
               records: dict, now: datetime, user_id: str, *, skip_self=True,
               duration_minutes: int | None = None) -> tuple[datetime, datetime]:
    if task.get("user_id") != user_id or task.get("status") != "pending":
        raise DataError("任務不存在或已完成")
    if type(blocks) is not int or not 1 <= blocks <= MAX_BLOCKS:
        raise DataError("任務長度須為 1–4 節；請用待排卡片右側把手調整")
    if day not in rolling_dates(now):
        raise DataError("只能排入今天到未來第六天（T+0 至 T+6）")
    minutes = blocks*60 if duration_minutes is None else duration_minutes
    if type(minutes) is not int or minutes<30 or minutes>240 or minutes%30:
        raise DataError("排程長度需為 30–240 分鐘，且以 30 分鐘為單位")
    start = _start(day, period)
    end = start + timedelta(minutes=minutes)
    if end.date() > day and end.time() != time.min:
        raise DataError("任務不能跨越午夜")
    if start <= now:
        raise DataError("已過去的節次不能排入")
    deadline = date.fromisoformat(task["deadline"])
    deadline_at=task.get("deadline_at")
    limit = (_datetime(deadline_at) if deadline_at
             else datetime.combine(deadline + timedelta(days=1), time.min, tzinfo=TZ))
    if end > limit:
        raise DataError("排程結束時間超過任務 Deadline（下次上課開始前）")
    occupied = _busy(records["events"], records["external_events"], records["tasks"],
                     records["availability"], records["plan"], day, user_id,
                     task["task_id"] if skip_self else "")
    if any(_overlap(start, end, a, b) for a, b in occupied):
        raise DataError("與課程、外部行事曆或其他任務衝突，未覆寫任何安排")
    return start, end


def place_manual(user_id: str, task_id: str, day: str, period: str,
                 blocks: int, now: datetime | None = None,
                 duration_minutes: int | None = None) -> dict:
    """只修改被拖動的任務；不執行自動排程。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = _read_all()
    task = next((t for t in records["tasks"] if t.get("user_id") == user_id
                 and t.get("task_id") == task_id), None)
    if not task:
        raise DataError("找不到這筆任務")
    chosen_day = date.fromisoformat(day)
    start, _ = _candidate(task, chosen_day, period, blocks, records, now, user_id,
                          duration_minutes=duration_minutes)
    minutes = blocks * 60 if duration_minutes is None else duration_minutes
    slot_id = f"board_{task_id}"
    slot = {
        "availability_id": slot_id, "user_id": user_id,
        "date": chosen_day.isoformat(), "start_time": start.strftime("%H:%M"),
        "available_minutes": minutes, "board_generated": True,
    }
    # 先建立 slot 再更新 plan，使任何已儲存的 plan 指向已存在的 slot。
    def put_slot(rows):
        if any(row.get("availability_id") == slot_id and row.get("user_id") != user_id for row in rows):
            raise DataError("時段識別碼衝突")
        return [row for row in rows if not (row.get("availability_id") == slot_id and row.get("user_id") == user_id)] + [slot]
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
    if any(p.get("user_id") == user_id and p.get("task_id") == task_id and p.get("status") == "scheduled"
           for p in plan):
        raise DataError("已排任務請先移回待排區，再拉長或縮短")
    modified = {**task, "estimated_minutes": blocks * 60,
                "preferred_availability_id": ""}
    if task.get("remaining_minutes") is not None:
        modified["remaining_minutes"] = blocks * 60
    update_task(modified)


def set_task_minutes(user_id: str, task_id: str, minutes: int) -> None:
    """Pending-only 30-minute resize. Scheduled cards use resize_scheduled."""
    if type(minutes) is not int or minutes<30 or minutes>240 or minutes%30:
        raise DataError("工時需為 30–240 分鐘（每次 30 分鐘）")
    tasks = load_json(data_path("tasks"))
    task = next((t for t in tasks if t.get("user_id")==user_id
                 and t.get("task_id")==task_id),None)
    if not task:
        raise DataError("找不到任務")
    if any(p.get("user_id")==user_id and p.get("task_id")==task_id
           and p.get("status")=="scheduled" for p in load_json(data_path("plan"))):
        raise DataError("此任務已排入，請直接在行事曆上調整長度")
    modified={**task,"estimated_minutes":minutes,"preferred_availability_id":""}
    if task.get("remaining_minutes") is not None:
        modified["remaining_minutes"]=minutes
    update_task(modified)


def resize_scheduled(user_id: str, task_id: str, minutes: int,
                     now: datetime | None = None) -> dict:
    """Resize a placed card without moving it, checking the entire new span.

    Validation precedes all JSON writes. Other plan rows stay byte-for-byte
    intact; a conflicting resize never overwrites another event.
    """
    now=(now or datetime.now(TZ)).astimezone(TZ)
    records=_read_all()
    task=next((t for t in records["tasks"] if t.get("user_id")==user_id
               and t.get("task_id")==task_id),None)
    plan=next((p for p in records["plan"] if p.get("user_id")==user_id
               and p.get("task_id")==task_id and p.get("status")=="scheduled"),None)
    slot=next((a for a in records["availability"] if plan and
               a.get("availability_id")==plan.get("availability_id") and
               a.get("user_id")==user_id),None)
    if not task or not plan or not slot:
        raise DataError("找不到已安排的任務")
    start,_=_slot_interval(slot,plan)
    label=next((n for n,h in PERIODS if h==start.hour),None)
    if label is None or start.minute not in (0,30):
        raise DataError("原時段無法以 30 分鐘格子調整")
    period=label+("+" if start.minute else "")
    _,end=_candidate(task,start.date(),period,max(1,ceil(minutes/60)),
                     records,now,user_id,duration_minutes=minutes)
    updated_plan={**plan,"scheduled_minutes":minutes}
    updated_slot={**slot,"available_minutes":minutes}
    modified={**task,"estimated_minutes":minutes}
    if task.get("remaining_minutes") is not None:
        modified["remaining_minutes"]=minutes
    # Existing API stores these in three independent JSONs. Validation is
    # atomic for all reads; concurrent modifications still need a DB migration.
    update_task(modified)
    update_json(data_path("availability"),lambda rows:[
        updated_slot if x.get("availability_id")==slot["availability_id"]
                   and x.get("user_id")==user_id else x for x in rows])
    update_json(data_path("plan"),lambda rows:[
        updated_plan if x.get("user_id")==user_id and x.get("task_id")==task_id
                     and x.get("status")=="scheduled" else x for x in rows])
    return updated_plan


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


def fill_remaining(user_id: str, now: datetime | None = None,
                   only_task_ids: set[str] | None = None) -> dict:
    """一鍵填滿：只處理未排入任務，依 Deadline→較長工時優先，再找最早連續空格。

    手動安排與既有有效排程不會移動；每個任務為單一連續區塊。
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = _read_all()
    slot_map = {slot.get("availability_id"): slot for slot in records["availability"] if slot.get("user_id") == user_id}
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
        and (only_task_ids is None or task.get("task_id") in only_task_ids)
    ), key=lambda t: (t["deadline"], -int(t.get("remaining_minutes") or t["estimated_minutes"]), t["task_id"]))
    # 新規格：偏好綠格是軟目標，絕不可把未塗綠的合法時段排除。
    from schedule_preferences import available_preference_cells, preference_overlap
    targets = available_preference_cells(user_id, now, records)
    placed, skipped = [], []
    for task in remaining:
        minutes = int(task.get("remaining_minutes") or task["estimated_minutes"])
        required = ceil(minutes / 30)*30
        blocks = ceil(required / 60)
        if blocks > MAX_BLOCKS:
            skipped.append((task["task_id"], "超過單次四節上限，請拆成較小任務"))
            continue
        choices = []
        for day in rolling_dates(now):
            if day > date.fromisoformat(task["deadline"]):
                break
            for hour_label, hour in PERIODS:
              for label in (hour_label,hour_label+"+"):
                try:
                    start, end = _candidate(task, day, label, blocks, records, now, user_id,
                                            duration_minutes=required)
                except DataError:
                    continue
                preferred = preference_overlap(start, end, targets)
                # Consider workload already scheduled that day, not class hours.
                day_workload = 0
                slots = {x["availability_id"]: x for x in records["availability"] if x.get("user_id") == user_id}
                for row in records["plan"]:
                    if (row.get("user_id") != user_id or row.get("status") != "scheduled"
                            or row.get("availability_id") not in slots):
                        continue
                    begin, finish = _slot_interval(slots[row["availability_id"]], row)
                    if begin.date() == day:
                        day_workload += (finish - begin).total_seconds() / 60
                # Soft optimization: green hit first; balance day workloads
                # and then prefer earlier available legal starts.
                score = (-preferred, day_workload, (day - now.date()).days,
                         hour, start.minute)
                choices.append((score, day, label, start, end, preferred))
        match = min(choices, key=lambda row: row[0]) if choices else None
        if not match:
            skipped.append((task["task_id"], "七日內沒有連續且不衝突的時段"))
            continue
        _, day, label, start, end, green_hits = match
        slot_id = f"board_{task['task_id']}"
        slot = {
            "availability_id": slot_id, "user_id": user_id,
            "date": day.isoformat(), "start_time": start.strftime("%H:%M"),
            "available_minutes": required, "board_generated": True,
        }
        entry = {
            "task_id": task["task_id"], "user_id": user_id, "availability_id": slot_id,
            "status": "scheduled", "source": "auto",
            "reason": (f"偏好命中 {green_hits:g} 節"
                       if green_hits else "已採用其他合法空檔（偏好並非硬限制）"),
            "preference_hits": green_hits, "preference_blocks": blocks,
            "scheduled_start": start.isoformat(timespec="minutes"),
            "scheduled_minutes": required, "unscheduled_alerted": False,
        }
        records["availability"].append(slot)
        records["plan"].append(entry)
        placed.append(entry)
    if placed:
        placed_slots = {r["availability_id"] for r in placed}
        new_slots = {slot["availability_id"]: slot for slot in records["availability"]
                     if slot.get("user_id") == user_id and slot.get("board_generated")
                     and slot.get("availability_id") in placed_slots}
        def put_slots(rows):
            if any(row.get("availability_id") in placed_slots and row.get("user_id") != user_id
                   for row in rows):
                raise DataError("時段識別碼衝突")
            return [row for row in rows if not (row.get("user_id") == user_id
                    and row.get("availability_id") in placed_slots)] + list(new_slots.values())
        update_json(data_path("availability"), put_slots)
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
    slots = {s["availability_id"]: s for s in records["availability"] if s.get("user_id") == user_id}
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
            "day": start.date().isoformat(), "hour": start.hour+start.minute/60,
            "start": start.isoformat(), "end": end.isoformat(),
            "blocks": max(1, ceil((end - start).total_seconds() / 3600)),
            "minutes": int((end-start).total_seconds()//60),
            "is_ai": task.get("source") in ("ai_confirmed","mock_ai_confirmed"),
            "source": entry.get("source", "auto"),
        })
    external = [e for e in records["external_events"] if e.get("user_id") == user_id]
    from schedule_preferences import available_preference_cells
    visible_targets = available_preference_cells(user_id, now, records)
    return {
        "days": [{"date": d.isoformat(), "label": "週" + "一二三四五六日"[d.weekday()],
                  "day_number": d.strftime("%m/%d")} for d in rolling_dates(now)],
        "periods": [{"label": label, "hour": h,
                     "time": f"{h:02d}:00–{(h+1)%24:02d}:00"} for label, h in PERIODS],
        "tasks": [{"task_id": t["task_id"], "title": t["title"], "subject": t["subject"],
                   "deadline": t["deadline"],
                   "deadline_at":t.get("deadline_at",""),
                   "minutes":max(30,min(240,ceil(int(t.get("remaining_minutes") or t["estimated_minutes"])/30)*30)),
                   "blocks": max(1, min(MAX_BLOCKS,
                   ceil(int(t.get("remaining_minutes") or t["estimated_minutes"]) / 60))),
                   "is_ai":t.get("source") in ("ai_confirmed","mock_ai_confirmed")}
                  for t in tasks if t.get("status") == "pending" and t["task_id"] not in plan],
        "scheduled": scheduled,
        "courses": [{"weekday": c["weekday"], "start": c["start_time"],
                     "end": c["end_time"], "title": c["title"]}
                    for c in records["events"] if c.get("user_id") == user_id],
        "external": external,
        "preferences": [{"date": day, "period": label}
                        for day, label in sorted(visible_targets)],
        "today": now.date().isoformat(), "now_hour": now.hour, "now_iso": now.isoformat(),
    }
