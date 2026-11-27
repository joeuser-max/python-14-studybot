"""LINE 一日模擬：以真實展示課表與既有讀書安排組成時間軸。

不讀取 API Key、不呼叫 LINE，不會在播放事件時改動 JSON。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")


def _at(day: date, clock: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(clock), tzinfo=TZ)


def one_day_timeline(day: date, courses: list[dict], scheduled: list[dict]) -> list[dict]:
    events: list[dict] = []
    for course in courses:
        if course.get("weekday") != day.isoweekday():
            continue
        title = str(course.get("title") or "未命名課程")
        start = _at(day, course["start_time"])
        end = _at(day, course["end_time"])
        events.append({
            "at": start, "kind": "class", "title": "開始上課｜" + title,
            "message": "這是課表中的固定課程，不是 LINE 推播。",
            "course_id": course.get("event_id", ""),
        })
        events.append({
            "at": end, "kind": "class", "title": "課程結束｜" + title,
            "message": "課程結束，準備進行主動式課後回饋。",
            "course_id": course.get("event_id", ""),
        })
        if course.get("enabled", True):
            offset = max(0, int(course.get("offset_minutes") or 0))
            events.append({
                "at": end + timedelta(minutes=offset),
                "kind": "line_note",
                "title": "LINE Mock｜課後補筆記",
                "message": f"【模擬 LINE】「{title}」下課了，請回報理解程度並補記重點與疑問。",
                "course_id": course.get("event_id", ""),
            })
    for task in scheduled:
        if task.get("day") != day.isoformat():
            continue
        start = datetime.fromisoformat(task["start"])
        end = datetime.fromisoformat(task["end"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=TZ)
        if end.tzinfo is None:
            end = end.replace(tzinfo=TZ)
        label = str(task.get("title") or "讀書任務")
        events.extend([
            {
                "at": start.astimezone(TZ), "kind": "line_study",
                "title": "LINE Mock｜讀書開始",
                "message": f"【模擬 LINE】「{label}」開始了，現在可以開始讀書。",
                "task_id": task.get("task_id", ""),
            },
            {
                "at": end.astimezone(TZ), "kind": "line_checkin",
                "title": "LINE Mock｜進度回報",
                "message": f"【模擬 LINE】「{label}」時段已結束，請回覆完成／未完成及剩餘進度。",
                "task_id": task.get("task_id", ""),
            },
        ])
    return [
        {**e, "time": e["at"].strftime("%H:%M")}
        for e in sorted(events, key=lambda e: (e["at"], e["kind"], e["title"]))
    ]


def recommended_demo_day(days: list[date], courses: list[dict],
                         scheduled: list[dict]) -> date:
    """預設挑下一個有課或有讀書任務的日子，避免初次展示出現空畫面。"""
    for day in days:
        if any(c.get("weekday") == day.isoweekday() for c in courses):
            return day
        if any(task.get("day") == day.isoformat() for task in scheduled):
            return day
    return days[0]
