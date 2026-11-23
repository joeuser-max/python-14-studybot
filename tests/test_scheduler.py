from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler import (
    get_due_study_reminders,
    make_plan,
    update_task_status,
)


TZ = ZoneInfo("Asia/Taipei")


def test_manual_task_keeps_preferred_slot():
    tasks = [{
        "task_id": "task_1", "user_id": "u1", "subject": "Python",
        "title": "專題", "deadline": "2026-11-30", "estimated_minutes": 60,
        "status": "pending", "preferred_availability_id": "a1",
    }]
    slots = [{
        "availability_id": "a1", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }]
    result = make_plan(tasks, slots, [], datetime(2026, 11, 23, 12, tzinfo=TZ))
    assert result["plan"][0]["status"] == "scheduled"
    assert result["plan"][0]["source"] == "manual"
    assert result["plan"][0]["availability_id"] == "a1"


def test_manual_conflict_is_unscheduled():
    tasks = [
        {"task_id": "a", "user_id": "u1", "title": "A", "deadline": "2026-11-30",
         "estimated_minutes": 30, "status": "pending", "preferred_availability_id": "slot"},
        {"task_id": "b", "user_id": "u1", "title": "B", "deadline": "2026-11-30",
         "estimated_minutes": 30, "status": "pending", "preferred_availability_id": "slot"},
    ]
    slots = [{"availability_id": "slot", "user_id": "u1", "date": "2026-11-24",
              "start_time": "19:00", "available_minutes": 30}]
    result = make_plan(tasks, slots, [], datetime(2026, 11, 23, 12, tzinfo=TZ))
    assert all(row["status"] == "unscheduled" for row in result["plan"])


def test_completed_task_is_not_studied():
    tasks = [{
        "task_id": "task_1", "user_id": "u1", "title": "專題",
        "deadline": "2026-11-30", "estimated_minutes": 30, "status": "pending",
    }]
    updated, error = update_task_status(tasks, "task_1", "completed")
    assert error is None
    assert updated[0]["status"] == "completed"


def test_study_reminder_only_due_once():
    tasks = [{"task_id": "t1", "user_id": "u1", "status": "pending"}]
    plan = [{"task_id": "t1", "availability_id": "a1", "status": "scheduled"}]
    slots = [{"availability_id": "a1", "user_id": "u1", "date": "2026-11-23",
              "start_time": "19:00", "available_minutes": 60}]
    users = [{"user_id": "u1", "line_user_id": "line1", "study_reminders_enabled": True}]
    now = datetime(2026, 11, 23, 19, tzinfo=TZ)
    due = get_due_study_reminders(tasks, plan, slots, users, now, [])
    assert len(due) == 1
