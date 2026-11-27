from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Taipei")
CLASS_COLOR = "#C94352"
AVAILABILITY_COLOR = "#23845B"
STUDY_PLAN_COLOR = "#3166CC"
AI_STUDY_COLOR = "#8356C4"


def build_calendar_events(
    courses: list[dict],
    availability: list[dict],
    tasks: list[dict] | None = None,
    plan: list[dict] | None = None,
) -> list[dict]:
    events = []

    for course in courses:
        weekday = int(course["weekday"])
        events.append({
            "id": course["event_id"],
            "title": f"課程｜{course['title']}",
            "daysOfWeek": [weekday % 7],
            "startTime": course["start_time"],
            "endTime": course["end_time"],
            "color": CLASS_COLOR,
            "extendedProps": {
                "kind": "class",
                "event_id": course["event_id"],
                "weekday": weekday,
                "reminder_enabled": course.get("enabled", True),
            },
        })

    for slot in availability:
        start = datetime.combine(
            date.fromisoformat(slot["date"]),
            time.fromisoformat(slot["start_time"]),
            tzinfo=TZ,
        )
        end = start + timedelta(minutes=int(slot["available_minutes"]))
        events.append({
            "id": slot["availability_id"],
            "title": f"可讀書｜{slot['available_minutes']} 分鐘",
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "color": AVAILABILITY_COLOR,
            "extendedProps": {
                "kind": "availability",
                "availability_id": slot["availability_id"],
                "available_minutes": slot["available_minutes"],
            },
        })

    tasks_by_id = {task["task_id"]: task for task in tasks or []}
    slots_by_id = {slot["availability_id"]: slot for slot in availability}
    for row in plan or []:
        if row.get("status") != "scheduled":
            continue
        task = tasks_by_id.get(row.get("task_id"))
        slot = slots_by_id.get(row.get("availability_id"))
        if task is None or slot is None or task.get("status") != "pending":
            continue

        scheduled_start = row.get("scheduled_start")
        if scheduled_start:
            start = datetime.fromisoformat(scheduled_start)
            if start.tzinfo is None:
                start = start.replace(tzinfo=TZ)
        else:
            start = datetime.combine(
                date.fromisoformat(slot["date"]),
                time.fromisoformat(slot["start_time"]),
                tzinfo=TZ,
            )
        end = start + timedelta(
            minutes=int(row.get("scheduled_minutes") or task.get("remaining_minutes") or task["estimated_minutes"])
        )
        events.append({
            "id": f"study-{task['task_id']}",
            "title": f"讀書｜{task['subject']}｜{task['title']}",
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "color": (AI_STUDY_COLOR if task.get("source") in
                      ("ai_confirmed", "mock_ai_confirmed") else STUDY_PLAN_COLOR),
            "extendedProps": {
                "kind": "study_plan",
                "task_id": task["task_id"],
                "availability_id": slot["availability_id"],
                "source": row.get("source", ""),
            },
        })

    return events
