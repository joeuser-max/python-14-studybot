"""匯入／匯出 RFC5545 ICS；外部來源不會被默默覆寫。"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, datetime, time, timedelta

from icalendar import Calendar, Event
import recurring_ical_events

from storage import DataError, TZ, data_path, load_json, update_json
from week_planner import rolling_dates, _datetime, _slot_interval


def _aware(value) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        return (value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ)), False
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=TZ), True
    raise DataError("ICS DTSTART 格式不支援")


def preview_ics(contents: bytes, user_id: str, filename: str = "calendar.ics",
                now: datetime | None = None) -> list[dict]:
    if not isinstance(contents, bytes) or not contents or len(contents) > 2_000_000:
        raise DataError("ICS 檔案大小須在 1 byte 至 2 MB 之間")
    now = now or datetime.now(TZ)
    dates = rolling_dates(now)
    try:
        source = Calendar.from_ical(contents)
        incoming = recurring_ical_events.of(source).between(dates[0], dates[-1] + timedelta(days=1))
    except Exception as exc:
        raise DataError("無法解析 ICS，請檢查 iCalendar 檔案格式") from exc
    if len(incoming) > 500:
        raise DataError("這七天的外部事件超過 500 筆，請使用範圍較小的行事曆")
    # Expanded VEVENT instances may synthesize RECURRENCE-ID even for a
    # one-off original. Determine whether it is a real series from the source.
    originals = source.walk("VEVENT")
    original_uid_counts = Counter(str(it.get("UID") or "").strip()
                                  for it in originals if it.get("UID"))
    recurring_uids = {
        str(it.get("UID") or "").strip() for it in originals
        if it.get("UID") and (it.get("RRULE") or it.get("RECURRENCE-ID")
                             or original_uid_counts[str(it.get("UID"))] > 1)
    }
    events = []
    for item in incoming:
        if item.get("STATUS") and str(item["STATUS"]).upper() == "CANCELLED":
            continue
        try:
            raw_start = item.decoded("DTSTART")
            start, all_day = _aware(raw_start)
            raw_end = item.decoded("DTEND") if item.get("DTEND") else (
                raw_start + (timedelta(days=1) if all_day else timedelta(hours=1))
            )
            end, _ = _aware(raw_end)
        except Exception as exc:
            raise DataError("ICS 存在缺少或無效的 DTSTART／DTEND") from exc
        if end <= start:
            continue
        title = str(item.get("SUMMARY") or "未命名行程").strip()[:140]
        uid = str(item.get("UID") or "").strip()[:200]
        recurrence_id = str(item.get("RECURRENCE-ID") or "").strip()
        # A one-off UID should remain stable if the provider moves the event.
        # Recurring instances need their own identity, otherwise weekly events collapse.
        if uid:
            instance = (recurrence_id or start.isoformat()) if uid in recurring_uids else ""
            identity_key = f"{uid}|{instance}"
        else:
            # Without an ICS UID a moved event cannot be reliably matched.
            identity_key = f"{filename}|{title}|{start.isoformat()}"
        identity = hashlib.sha256(identity_key.encode()).hexdigest()[:24]
        events.append({
            "id": "ics_" + identity, "user_id": user_id,
            "title": title, "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "source_uid": uid, "source_name": filename[:140],
            "all_day": all_day, "origin": "ics",
        })
    return events


def import_ics(events: list[dict], user_id: str, overwrite: bool = False) -> dict:
    if any(e.get("user_id") != user_id for e in events):
        raise DataError("外部事件使用者 ID 不一致")
    saved, skipped = [], []
    def change(current):
        rows = list(current)
        known = {e.get("id"): i for i, e in enumerate(rows)}
        for event in events:
            if event["id"] in known:
                if rows[known[event["id"]]].get("user_id") != user_id:
                    raise DataError("外部行程識別碼衝突")
                if overwrite:
                    rows[known[event["id"]]] = event
                    saved.append(event["id"])
                else:
                    skipped.append(event["id"])
            else:
                known[event["id"]] = len(rows)
                rows.append(event)
                saved.append(event["id"])
        return rows
    update_json(data_path("external_events"), change)
    return {"saved": len(saved), "skipped": len(skipped)}



def conflicts_with_existing_plan(events: list[dict], user_id: str) -> list[dict]:
    """Show possible collisions before importing; never auto-rearrange the user plan."""
    tasks = {t["task_id"]: t for t in load_json(data_path("tasks"))
             if t.get("user_id") == user_id and t.get("status") == "pending"}
    slots = {s["availability_id"]: s for s in load_json(data_path("availability")) if s.get("user_id") == user_id}
    existing = {
        e["id"]: e for e in load_json(data_path("external_events"))
        if e.get("user_id") == user_id
    }
    plan = [
        (row, slots[row["availability_id"]]) for row in load_json(data_path("plan"))
        if row.get("user_id") == user_id and row.get("status") == "scheduled"
        and row.get("task_id") in tasks
        and row.get("availability_id") in slots
    ]
    conflicts = []
    for item in events:
        # When imported data has not changed, it will not introduce a new conflict.
        previous = existing.get(item["id"])
        if previous and all(previous.get(field) == item.get(field)
                            for field in ("title", "start", "end")):
            continue
        begin, finish = _datetime(item["start"]), _datetime(item["end"])
        for row, slot in plan:
            task_start, task_finish = _slot_interval(slot, row)
            if begin < task_finish and task_start < finish:
                task = tasks[row["task_id"]]
                conflicts.append({
                    "event_id": item["id"], "event_title": item["title"],
                    "task_id": row["task_id"], "task_title": task["title"],
                    "task_start": task_start.isoformat(timespec="minutes"),
                })
    return conflicts


def edit_imported_event(user_id: str, event_id: str, title: str, start: datetime,
                        end: datetime, confirmed: bool = False) -> None:
    if not confirmed:
        raise DataError("修改外部行事曆事件前，必須明確確認覆寫")
    if not title.strip() or end <= start or len(title) > 140:
        raise DataError("外部事件標題或時間無效")
    value = {"title": title.strip(), "start": start.astimezone(TZ).isoformat(timespec="minutes"),
             "end": end.astimezone(TZ).isoformat(timespec="minutes")}
    found = False
    def change(rows):
        nonlocal found
        changed = []
        for row in rows:
            if row.get("id") == event_id and row.get("user_id") == user_id:
                found = True
                changed.append({**row, **value, "edited_in_classpulse": True})
            else:
                changed.append(row)
        if not found:
            raise DataError("找不到要修改的外部事件")
        return changed
    update_json(data_path("external_events"), change)


def export_week_ics(user_id: str, now: datetime | None = None) -> bytes:
    now = now or datetime.now(TZ)
    week = rolling_dates(now)
    cal = Calendar()
    cal.add("prodid", "-//ClassPulse//Rolling Week Export//ZH-TW")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "ClassPulse 七日行程")
    added = set()

    def put(uid: str, title: str, begin: datetime, end: datetime):
        if uid in added:
            return
        added.add(uid)
        event = Event()
        event.add("uid", uid + "@classpulse.local")
        event.add("dtstamp", datetime.now(TZ))
        event.add("summary", title)
        event.add("dtstart", begin)
        event.add("dtend", end)
        cal.add_component(event)

    window_start = datetime.combine(week[0], time.min, tzinfo=TZ)
    window_end = datetime.combine(week[-1] + timedelta(days=1), time.min, tzinfo=TZ)
    for e in load_json(data_path("external_events")):
        if e.get("user_id") != user_id:
            continue
        begin, finish = _datetime(e["start"]), _datetime(e["end"])
        if finish <= window_start or begin >= window_end:
            continue
        put(e["id"], e["title"], begin, finish)
    for course in load_json(data_path("events")):
        if course.get("user_id") != user_id:
            continue
        for day in week:
            if day.isoweekday() != course["weekday"]:
                continue
            start = _datetime(day.isoformat() + "T" + course["start_time"])
            end = _datetime(day.isoformat() + "T" + course["end_time"])
            put(course["event_id"] + day.isoformat(), course["title"], start, end)

    tasks = {x["task_id"]: x for x in load_json(data_path("tasks")) if x.get("user_id") == user_id}
    slots = {x["availability_id"]: x for x in load_json(data_path("availability")) if x.get("user_id") == user_id}
    for row in load_json(data_path("plan")):
        if row.get("user_id") != user_id or row.get("status") != "scheduled":
            continue
        task = tasks.get(row.get("task_id"))
        slot = slots.get(row.get("availability_id"))
        if not task or not slot or task.get("status") != "pending":
            continue
        begin, end = _slot_interval(slot, row)
        if begin.date() in week:
            put("study-" + task["task_id"], task["subject"] + "｜" + task["title"], begin, end)
    return cal.to_ical()
