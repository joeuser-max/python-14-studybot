from calendar_events import (
    AVAILABILITY_COLOR,
    CLASS_COLOR,
    STUDY_PLAN_COLOR,
    build_calendar_events,
)


def test_calendar_includes_weekly_class_and_date_time_slot():
    courses = [{
        "event_id": "event-1",
        "title": "電子學",
        "weekday": 1,
        "start_time": "09:00",
        "end_time": "11:50",
        "enabled": True,
    }]
    availability = [{
        "availability_id": "slot-1",
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 90,
    }]

    events = build_calendar_events(courses, availability)

    assert len(events) == 2
    assert events[0]["daysOfWeek"] == [1]
    assert events[0]["startTime"] == "09:00"
    assert events[0]["endTime"] == "11:50"
    assert events[0]["color"] == CLASS_COLOR
    assert events[1]["start"] == "2026-11-24T19:00+08:00"
    assert events[1]["end"] == "2026-11-24T20:30+08:00"
    assert events[1]["color"] == AVAILABILITY_COLOR


def test_sunday_uses_fullcalendar_sunday_index():
    course = {
        "event_id": "event-sunday",
        "title": "週日課程",
        "weekday": 7,
        "start_time": "10:00",
        "end_time": "11:00",
    }

    event = build_calendar_events([course], [])[0]

    assert event["daysOfWeek"] == [0]


def test_calendar_includes_scheduled_pending_task_with_estimated_duration():
    availability = [{
        "availability_id": "slot-1",
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 90,
    }]
    tasks = [
        {
            "task_id": "task-1",
            "subject": "電子學3",
            "title": "完成 c13 (p20~p30)",
            "estimated_minutes": 60,
            "status": "pending",
        },
        {
            "task_id": "task-done",
            "subject": "Python",
            "title": "已完成任務",
            "estimated_minutes": 30,
            "status": "completed",
        },
    ]
    plan = [
        {
            "task_id": "task-1",
            "availability_id": "slot-1",
            "status": "scheduled",
            "source": "auto",
        },
        {
            "task_id": "task-done",
            "availability_id": "slot-1",
            "status": "scheduled",
            "source": "manual",
        },
        {
            "task_id": "task-unscheduled",
            "availability_id": "",
            "status": "unscheduled",
            "source": "auto",
        },
    ]

    events = build_calendar_events([], availability, tasks, plan)

    assert len(events) == 2
    study_event = events[1]
    assert study_event["title"] == "讀書｜電子學3｜完成 c13 (p20~p30)"
    assert study_event["start"] == "2026-11-24T19:00+08:00"
    assert study_event["end"] == "2026-11-24T20:00+08:00"
    assert study_event["color"] == STUDY_PLAN_COLOR
    assert study_event["extendedProps"] == {
        "kind": "study_plan",
        "task_id": "task-1",
        "availability_id": "slot-1",
        "source": "auto",
    }
