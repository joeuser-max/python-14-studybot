"""真實時間表互動的排程規則。FullCalendar 只負責輸入座標，後端再驗證並寫入 JSON。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import storage
from plan_bridge import merge_user_plan, normalize_plan_result
from scheduler import make_plan

TZ = ZoneInfo("Asia/Taipei")
OVERRIDE_REASONS = ("請假", "翹課", "停課")
MANUAL_PREFIX = "calendar_manual_"


def as_local(value: str | datetime) -> datetime:
    """所有視覺互動與儲存一律換算成台北時間。"""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)


def interval_overlap(a: datetime, b: datetime, x: datetime, y: datetime) -> bool:
    return a < y and x < b


def class_conflicts(courses: list[dict], start: datetime, end: datetime,
                    user_id: str) -> list[dict]:
    """回傳與選定日期、時段重疊的固定每週課程，不依賴日曆前端。"""
    found: list[dict] = []
    day = start.date()
    while day <= end.date():
        for course in courses:
            if (course.get("user_id") != user_id or
                    int(course.get("weekday", 0)) != day.isoweekday()):
                continue
            try:
                cstart = datetime.combine(day, time.fromisoformat(course["start_time"]), TZ)
                cend = datetime.combine(day, time.fromisoformat(course["end_time"]), TZ)
            except (KeyError, TypeError, ValueError):
                continue
            if interval_overlap(start, end, cstart, cend):
                found.append({"event_id": course["event_id"], "title": course["title"],
                              "start": cstart.isoformat(timespec="minutes"),
                              "end": cend.isoformat(timespec="minutes")})
        day += timedelta(days=1)
    return found


def plan_interval(row: dict, tasks: dict, slots: dict) -> tuple[datetime, datetime] | None:
    task = tasks.get(row.get("task_id"))
    slot = slots.get(row.get("availability_id"))
    if row.get("status") != "scheduled" or not task or not slot:
        return None
    start = datetime.combine(date.fromisoformat(slot["date"]),
                             time.fromisoformat(slot["start_time"]), TZ)
    return start, start + timedelta(minutes=int(task["estimated_minutes"]))


def propose_placement(tasks: list[dict], slots: list[dict], plan: list[dict],
                      courses: list[dict], user_id: str, task_id: str,
                      start: str | datetime, end: str | datetime,
                      now: datetime | None = None) -> dict:
    """判定後端是否接受拖曳：過去與其他任務重疊為硬拒絕，與課程重疊須說明。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    start, end = as_local(start), as_local(end)
    target = next((t for t in tasks
                   if t.get("task_id") == task_id and t.get("user_id") == user_id), None)
    if target is None:
        raise storage.DataError("找不到對應的讀書任務")
    if target.get("status") != "pending":
        raise storage.DataError("完成的任務不能重新排入")
    if start <= now:
        raise storage.DataError("已過去或正在進行的時間不能拖曳安排")
    minutes = int((end - start).total_seconds() / 60)
    if end <= start or not 15 <= minutes <= 600 or minutes % 15:
        raise storage.DataError("讀書方塊須介於 15–600 分鐘，且以 15 分鐘為單位")
    if end.date() != start.date() and end != datetime.combine(
            start.date() + timedelta(days=1), time.min, TZ):
        raise storage.DataError("目前不支援跨午夜的讀書方塊")
    deadline_end = datetime.combine(date.fromisoformat(target["deadline"]),
                                    time(23, 59), TZ)
    if end > deadline_end:
        raise storage.DataError("讀書時段不能晚於任務 Deadline")
    task_by_id = {t["task_id"]: t for t in tasks if t.get("user_id") == user_id}
    slot_by_id = {s["availability_id"]: s for s in slots if s.get("user_id") == user_id}
    for row in plan:
        if row.get("user_id") != user_id or row.get("task_id") == task_id:
            continue
        interval = plan_interval(row, task_by_id, slot_by_id)
        if interval and interval_overlap(start, end, *interval):
            raise storage.DataError("與另一項已安排的讀書任務衝突；請先移動或取消其中一項")
    return {"task_id": task_id, "start": start, "end": end, "minutes": minutes,
            "classes": class_conflicts(courses, start, end, user_id)}


def _eligible_availability(slots: list[dict], courses: list[dict],
                           user_id: str) -> list[dict]:
    """自動安排不能撞課；唯獨使用者手動且有原因的特例可保留。"""
    eligible = []
    for slot in slots:
        if slot.get("user_id") != user_id:
            continue
        start = datetime.combine(date.fromisoformat(slot["date"]),
                                 time.fromisoformat(slot["start_time"]), TZ)
        end = start + timedelta(minutes=int(slot["available_minutes"]))
        conflicts = class_conflicts(courses, start, end, user_id)
        if conflicts and not (slot.get("origin") == "manual_calendar"
                              and slot.get("class_override") in OVERRIDE_REASONS):
            continue
        eligible.append(slot)
    return eligible


def rebuild_plan(user_id: str, now: datetime | None = None) -> list[dict]:
    """唯一排程入口：先排除與課表重疊的自動時段，再套用固定優先＋Deadline。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    courses = storage.load_json(storage.data_path("events"))
    tasks = storage.load_json(storage.data_path("tasks"))
    slots = storage.load_json(storage.data_path("availability"))
    previous = storage.load_json(storage.data_path("plan"))
    own_tasks = [t for t in tasks if t.get("user_id") == user_id]
    own_previous = [r for r in previous if r.get("user_id") == user_id]
    eligible_tasks = [t for t in own_tasks if not t.get("planning_hold", False)]
    safe_slots = _eligible_availability(slots, courses, user_id)
    raw = make_plan(eligible_tasks, safe_slots, own_previous, now)
    plan = normalize_plan_result(raw, user_id)
    for task in own_tasks:
        if task.get("status") == "pending" and task.get("planning_hold", False):
            plan.append({"user_id": user_id, "task_id": task["task_id"],
                         "status": "unscheduled", "availability_id": "",
                         "source": "manual", "reason": "使用者移回待排區",
                         "unscheduled_alerted": True})
    override_by_slot = {s["availability_id"]: s.get("class_override")
                        for s in safe_slots if s.get("class_override")}
    for row in plan:
        if row.get("availability_id") in override_by_slot:
            row["class_override"] = override_by_slot[row["availability_id"]]
    storage.update_json(storage.data_path("plan"),
                        lambda rows: merge_user_plan(rows, user_id, plan))
    return plan


def place_task(user_id: str, task_id: str, start: str | datetime, end: str | datetime,
               override_reason: str | None = None,
               now: datetime | None = None) -> list[dict]:
    """建立／修改一個真正的時段與任務，並儲存重新排程結果。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    tasks = storage.load_json(storage.data_path("tasks"))
    slots = storage.load_json(storage.data_path("availability"))
    courses = storage.load_json(storage.data_path("events"))
    plan = storage.load_json(storage.data_path("plan"))
    proposal = propose_placement(tasks, slots, plan, courses, user_id, task_id, start, end, now)
    if proposal["classes"] and override_reason not in OVERRIDE_REASONS:
        raise storage.DataError("與課表重疊，請選擇「請假／翹課／停課」後再確認")
    if not proposal["classes"] and override_reason:
        raise storage.DataError("沒有重疊課程，不需紀錄請假／翹課／停課")
    slot_id = MANUAL_PREFIX + task_id
    slot = {"availability_id": slot_id, "user_id": user_id,
            "date": proposal["start"].date().isoformat(),
            "start_time": proposal["start"].strftime("%H:%M"),
            "available_minutes": proposal["minutes"],
            "origin": "manual_calendar",
            "class_override": override_reason or "",
            "overlap_course_ids": [c["event_id"] for c in proposal["classes"]]}
    task = next(t for t in tasks if t["task_id"] == task_id and t["user_id"] == user_id)
    updated_task = {**task, "preferred_availability_id": slot_id,
                    "planning_hold": False, "estimated_minutes": proposal["minutes"]}
    # 先在記憶體中試排一次，避免因排程失敗才發現資料已經寫入。
    proposed_slots = [row for row in slots if row.get("availability_id") != slot_id] + [slot]
    proposed_tasks = [updated_task if row.get("task_id") == task_id
                      and row.get("user_id") == user_id else row for row in tasks]
    eligible_tasks = [row for row in proposed_tasks
                      if row.get("user_id") == user_id and not row.get("planning_hold")]
    dry_run = make_plan(
        eligible_tasks, _eligible_availability(proposed_slots, courses, user_id),
        [row for row in plan if row.get("user_id") == user_id], now,
    )
    planned = next((row for row in dry_run["plan"] if row.get("task_id") == task_id), {})
    if planned.get("status") != "scheduled":
        raise storage.DataError(f"不能完成這次手動安排：{planned.get('reason', '沒有合法時段')}")

    # JSON 檔案的讀改寫各自上鎖；跨檔案交易非原子，正式多使用者環境應改 DB。
    storage.update_json(storage.data_path("availability"),
                        lambda rows: [r for r in rows
                                      if r.get("availability_id") != slot_id] + [slot])
    storage.update_task(updated_task)
    result = rebuild_plan(user_id, now)
    row = next((r for r in result if r.get("task_id") == task_id), {})
    if row.get("status") != "scheduled":
        raise storage.DataError(f"手動時段未成功排入：{row.get('reason','未知原因')}")
    return result


def unassign_task(user_id: str, task_id: str, now: datetime | None = None) -> list[dict]:
    """回到待排區；已開始或過去的安排不可透過時間表任意抹除。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    current_plan = storage.load_json(storage.data_path("plan"))
    current_slots = storage.load_json(storage.data_path("availability"))
    scheduled = next((r for r in current_plan if r.get("user_id") == user_id
                      and r.get("task_id") == task_id and r.get("status") == "scheduled"), None)
    if scheduled:
        slot = next((s for s in current_slots
                     if s.get("availability_id") == scheduled.get("availability_id")), None)
        if slot:
            started = datetime.combine(date.fromisoformat(slot["date"]),
                                       time.fromisoformat(slot["start_time"]), TZ)
            if started <= now:
                raise storage.DataError("已開始或過去的任務時間不可拖動或取消")
    tasks = storage.load_json(storage.data_path("tasks"))
    target = next((t for t in tasks if t.get("task_id") == task_id
                   and t.get("user_id") == user_id), None)
    if not target:
        raise storage.DataError("找不到任務")
    slot_id = MANUAL_PREFIX + task_id
    if target.get("preferred_availability_id") == slot_id:
        storage.update_json(storage.data_path("availability"),
                            lambda rows: [s for s in rows
                                          if s.get("availability_id") != slot_id])
    storage.update_task({**target, "preferred_availability_id": "", "planning_hold": True})
    return rebuild_plan(user_id, now)


def resume_auto(user_id: str, task_id: str,
                now: datetime | None = None) -> list[dict]:
    tasks = storage.load_json(storage.data_path("tasks"))
    target = next((t for t in tasks if t.get("task_id") == task_id
                   and t.get("user_id") == user_id), None)
    if not target:
        raise storage.DataError("找不到任務")
    slot_id = MANUAL_PREFIX + task_id
    if target.get("preferred_availability_id") == slot_id:
        storage.update_json(storage.data_path("availability"),
                            lambda rows: [s for s in rows if s.get("availability_id") != slot_id])
    storage.update_task({**target, "preferred_availability_id": "", "planning_hold": False})
    return rebuild_plan(user_id, now)


def calendar_change_candidate(value: dict, tasks: list[dict]) -> dict | None:
    """streamlit-calendar eventChange → 使用者提出的時間變更（尚未提交）。"""
    if not isinstance(value, dict) or value.get("callback") != "eventChange":
        return None
    event = value.get("eventChange", {}).get("event", {})
    event_id = str(event.get("id", ""))
    if not event_id.startswith("task:"):
        return None
    task_id = event_id.removeprefix("task:")
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if task is None:
        return None
    old_event = value.get("eventChange", {}).get("oldEvent", {})
    if event.get("allDay"):
        if old_event.get("allDay") is False:
            return {"kind": "unschedule", "task_id": task_id}
        return None
    start = event.get("start")
    if not start:
        return None
    end = event.get("end")
    beginning = as_local(start)
    # 全天待排 → 有時間的格子時，採原任務估時，下一次可直接拉長。
    ending = (beginning + timedelta(minutes=int(task["estimated_minutes"]))
              if old_event.get("allDay") is True
              else as_local(end) if end
              else beginning + timedelta(minutes=int(task["estimated_minutes"])))
    return {"kind": "place", "task_id": task_id, "start": beginning, "end": ending}


def board_events(courses: list[dict], slots: list[dict], tasks: list[dict],
                 plan: list[dict], week_date: date, now: datetime | None = None) -> list[dict]:
    """待排任務位在 FullCalendar 全天列，可拖入週／日的時間格；既有任務可拉長。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    events: list[dict] = []
    for course in courses:
        events.append({"id": "class:" + course["event_id"],
                       "title": "課程｜" + course["title"],
                       "daysOfWeek": [int(course["weekday"]) % 7],
                       "startTime": course["start_time"], "endTime": course["end_time"],
                       "color": "#B55764", "editable": False,
                       "extendedProps": {"kind": "class"}})
    for slot in slots:
        if slot.get("origin") == "manual_calendar":
            continue
        start = datetime.combine(date.fromisoformat(slot["date"]),
                                 time.fromisoformat(slot["start_time"]), TZ)
        end = start + timedelta(minutes=int(slot["available_minutes"]))
        events.append({"id": "available:" + slot["availability_id"],
                       "title": "可用時間", "start": start.isoformat(),
                       "end": end.isoformat(), "display": "background",
                       "backgroundColor": "#CBEFE0", "editable": False})
    task_by_id = {t["task_id"]: t for t in tasks}
    slot_by_id = {s["availability_id"]: s for s in slots}
    scheduled = set()
    for row in plan:
        if row.get("status") != "scheduled":
            continue
        task, slot = task_by_id.get(row.get("task_id")), slot_by_id.get(row.get("availability_id"))
        if not task or not slot or task.get("status") != "pending":
            continue
        start = datetime.combine(date.fromisoformat(slot["date"]),
                                 time.fromisoformat(slot["start_time"]), TZ)
        end = start + timedelta(minutes=int(task["estimated_minutes"]))
        scheduled.add(task["task_id"])
        ai = task.get("source") == "ai_confirmed"
        events.append({"id": "task:" + task["task_id"],
                       "title": ("✦ AI｜" if ai else "任務｜") + task["title"],
                       "start": start.isoformat(), "end": end.isoformat(),
                       "color": "#8061B6" if ai else "#2E65BD",
                       "editable": start > now,
                       "durationEditable": start > now,
                       "extendedProps": {"kind": "task", "source": task.get("source", "manual")}})
    monday = week_date - timedelta(days=week_date.weekday())
    pin_date = max(monday, now.date()) if monday <= now.date() <= monday + timedelta(days=6) else monday
    for task in tasks:
        if task["task_id"] in scheduled or task.get("status") == "completed":
            continue
        ai = task.get("source") == "ai_confirmed"
        events.append({"id": "task:" + task["task_id"], "allDay": True,
                       "title": ("✦ AI 待排｜" if ai else "待排｜") + task["title"],
                       "start": pin_date.isoformat(),
                       "color": "#8061B6" if ai else "#687787",
                       "editable": True,
                       "extendedProps": {"kind": "task", "inbox": True}})
    return events
