"""ClassPulse → 外部行事曆：只做單向 .ics 匯出及 Google 新增事件連結。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")


def _escape(value: str) -> str:
    return (str(value).replace("\\", "\\\\").replace("\r", "")
            .replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;"))


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Calendar 日期必須包含時區")
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event(uid: str, title: str, start: datetime, end: datetime,
           description: str, repeat: int = 0) -> list[str]:
    if end <= start:
        raise ValueError("行事曆結束時間必須晚於開始時間")
    lines = ["BEGIN:VEVENT", f"UID:{_escape(uid)}@classpulse.local",
             f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
             f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}",
             f"SUMMARY:{_escape(title)}", f"DESCRIPTION:{_escape(description)}"]
    if repeat:
        lines.append(f"RRULE:FREQ=WEEKLY;COUNT={repeat}")
    return lines + ["END:VEVENT"]


def export_calendar_ics(courses: list[dict], tasks: list[dict],
                        availability: list[dict], plan: list[dict],
                        now: datetime | None = None) -> bytes:
    """每週課程未來 12 次、已排程且未完成的任務；不是雙向同步。"""
    now = now or datetime.now(TZ)
    now = now.astimezone(TZ)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ClassPulse//Schedule//ZH-TW",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:ClassPulse"]
    for course in courses:
        try:
            day = now.date() + timedelta(days=(int(course["weekday"]) - now.isoweekday()) % 7)
            begins = datetime.combine(day, time.fromisoformat(course["start_time"]), TZ)
            ends = datetime.combine(day, time.fromisoformat(course["end_time"]), TZ)
            if begins < now:
                begins += timedelta(days=7)
                ends += timedelta(days=7)
            lines += _event("course-" + course["event_id"],
                            "課程｜" + course["title"], begins, ends,
                            "ClassPulse 每週課表；若在網站修改，請重新匯入更新。", 12)
        except (KeyError, TypeError, ValueError):
            continue
    by_task = {r["task_id"]: r for r in tasks if r.get("task_id")}
    by_slot = {r["availability_id"]: r for r in availability if r.get("availability_id")}
    for row in plan:
        if row.get("status") != "scheduled":
            continue
        task = by_task.get(row.get("task_id"))
        slot = by_slot.get(row.get("availability_id"))
        if not task or not slot or task.get("status") == "completed":
            continue
        try:
            begins = datetime.combine(date.fromisoformat(slot["date"]),
                                      time.fromisoformat(slot["start_time"]), TZ)
            ends = begins + timedelta(minutes=int(task["estimated_minutes"]))
            description = f"科目：{task['subject']}；期限：{task['deadline']}"
            if row.get("class_override"):
                description += f"；與課程重疊（本人標註：{row['class_override']}）"
            lines += _event("study-" + task["task_id"],
                            "讀書｜" + task["title"], begins, ends,
                            description)
        except (KeyError, TypeError, ValueError):
            continue
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def google_calendar_url(title: str, start: datetime, end: datetime,
                        description: str = "") -> str:
    """打開 Google Calendar 新增事件畫面，仍需使用者自行確認儲存。"""
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("日期需含時區，且結束時間晚於開始時間")
    params = {"action": "TEMPLATE", "text": title,
              "dates": _utc(start) + "/" + _utc(end),
              "details": description}
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def task_calendar_event(task: dict, slot: dict) -> tuple[datetime, datetime]:
    begins = datetime.combine(date.fromisoformat(slot["date"]),
                              time.fromisoformat(slot["start_time"]), TZ)
    return begins, begins + timedelta(minutes=int(task["estimated_minutes"]))
