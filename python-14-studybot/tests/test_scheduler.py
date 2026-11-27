from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler import (
    get_due_study_checkins,
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


def test_auto_task_can_use_remaining_time_in_active_slot():
    task = {
        "task_id": "active-task", "user_id": "u1", "subject": "Python",
        "title": "複習", "deadline": "2026-11-24", "estimated_minutes": 39,
        "status": "pending", "preferred_availability_id": "",
    }
    slot = {
        "availability_id": "active-slot", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }

    result = make_plan(
        [task], [slot], [], datetime(2026, 11, 24, 19, 20, 30, tzinfo=TZ)
    )

    assert result["plan"][0]["status"] == "scheduled"
    assert result["plan"][0]["availability_id"] == "active-slot"
    assert result["plan"][0]["scheduled_start"] == "2026-11-24T19:21+08:00"


def test_manual_task_can_use_remaining_time_in_active_preferred_slot():
    task = {
        "task_id": "manual-active-task", "user_id": "u1", "subject": "Python",
        "title": "複習", "deadline": "2026-11-24", "estimated_minutes": 30,
        "status": "pending", "preferred_availability_id": "active-slot",
    }
    slot = {
        "availability_id": "active-slot", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }

    result = make_plan(
        [task], [slot], [], datetime(2026, 11, 24, 19, 20, 30, tzinfo=TZ)
    )

    assert result["plan"][0]["status"] == "scheduled"
    assert result["plan"][0]["source"] == "manual"
    assert result["plan"][0]["scheduled_start"] == "2026-11-24T19:21+08:00"


def test_active_slot_is_rejected_when_remaining_time_is_too_short():
    task = {
        "task_id": "too-long-task", "user_id": "u1", "subject": "Python",
        "title": "複習", "deadline": "2026-11-24", "estimated_minutes": 40,
        "status": "pending", "preferred_availability_id": "",
    }
    slot = {
        "availability_id": "active-slot", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }

    result = make_plan(
        [task], [slot], [], datetime(2026, 11, 24, 19, 20, 30, tzinfo=TZ)
    )

    assert result["plan"][0]["status"] == "unscheduled"


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


def test_study_reminders_and_checkins_use_scheduled_start():
    tasks = [{
        "task_id": "active-task", "user_id": "u1", "status": "pending",
        "estimated_minutes": 30,
    }]
    plan = [{
        "task_id": "active-task", "availability_id": "active-slot",
        "status": "scheduled", "scheduled_start": "2026-11-24T19:21+08:00",
    }]
    slots = [{
        "availability_id": "active-slot", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }]
    users = [{
        "user_id": "u1", "line_user_id": "line1",
        "study_reminders_enabled": True,
    }]

    reminders = get_due_study_reminders(
        tasks, plan, slots, users, datetime(2026, 11, 24, 19, 22, tzinfo=TZ), []
    )
    checkins = get_due_study_checkins(
        tasks, plan, slots, users, datetime(2026, 11, 24, 19, 51, tzinfo=TZ), []
    )

    assert reminders[0]["scheduled_at"] == "2026-11-24T19:21+08:00"
    assert checkins[0]["scheduled_at"] == "2026-11-24T19:51+08:00"


def test_plan_uses_remaining_minutes_after_progress_report():
    task = {
        "task_id": "task-progress", "user_id": "u1", "subject": "Python",
        "title": "複習函式", "deadline": "2026-11-30",
        "estimated_minutes": 90, "remaining_minutes": 30, "status": "pending",
        "preferred_availability_id": "",
    }
    slots = [
        {"availability_id": "slot-90", "user_id": "u1", "date": "2026-11-24",
         "start_time": "19:00", "available_minutes": 90},
        {"availability_id": "slot-30", "user_id": "u1", "date": "2026-11-25",
         "start_time": "19:00", "available_minutes": 30},
    ]

    result = make_plan(
        [task], slots, [], datetime(2026, 11, 23, 12, tzinfo=TZ)
    )

    assert result["plan"][0]["availability_id"] == "slot-30"
    assert task["estimated_minutes"] == 90


def test_study_checkin_is_due_at_remaining_duration_end_and_sent_once():
    tasks = [{
        "task_id": "task-1", "user_id": "u1", "estimated_minutes": 60,
        "remaining_minutes": 25, "status": "pending",
    }]
    plan = [{"task_id": "task-1", "availability_id": "slot-1", "status": "scheduled"}]
    slots = [{
        "availability_id": "slot-1", "user_id": "u1", "date": "2026-11-24",
        "start_time": "19:00", "available_minutes": 60,
    }]
    users = [{
        "user_id": "u1", "line_user_id": "line1",
        "study_reminders_enabled": True,
    }]
    now = datetime(2026, 11, 24, 19, 25, tzinfo=TZ)

    due = get_due_study_checkins(tasks, plan, slots, users, now, [])
    assert len(due) == 1
    assert due[0]["kind"] == "study_session_checkin"
    assert due[0]["scheduled_at"] == "2026-11-24T19:25+08:00"
    assert get_due_study_checkins(
        tasks, plan, slots, users, now,
        [{**due[0], "status": "sent", "sent_at": now.isoformat()}],
    ) == []
