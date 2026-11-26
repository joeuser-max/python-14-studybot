"""日曆實際安排的限制、固定優先、課表覆蓋聲明與長度更新。"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import storage
from visual_planner import (
    MANUAL_PREFIX, board_events, calendar_change_candidate,
    class_conflicts, place_task, propose_placement, rebuild_plan, unassign_task, resume_auto,
)

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 26, 12, tzinfo=TZ)
USER = "demo_user_001"


def fixture_data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "real")
    storage.select_demo_storage(False)
    task = {"task_id": "t1", "user_id": USER, "subject": "控制系統",
            "title": "練習 Routh", "deadline": "2026-12-02",
            "estimated_minutes": 45, "status": "pending",
            "preferred_availability_id": ""}
    second = {**task, "task_id": "t2", "title": "第二項", "estimated_minutes": 30}
    course = {"event_id": "class1", "user_id": USER, "event_type": "class",
              "title": "固定課程", "weekday": 5, "start_time": "09:00",
              "end_time": "11:00", "enabled": True, "offset_minutes": 5}
    slots = [{"availability_id": "slot_a", "user_id": USER,
              "date": "2026-11-27", "start_time": "10:00", "available_minutes": 60},
             {"availability_id": "slot_b", "user_id": USER,
              "date": "2026-11-27", "start_time": "19:00", "available_minutes": 60}]
    for name, data in (("tasks", [task, second]), ("events", [course]),
                       ("availability", slots), ("plan", [])):
        storage.save_json(storage.data_path(name), data)
    return task, second, course, slots


def test_auto_scheduler_blocks_class_overlap(monkeypatch, tmp_path):
    task, _, _, slots = fixture_data(monkeypatch, tmp_path)
    plan = rebuild_plan(USER, NOW)
    first = next(row for row in plan if row["task_id"] == task["task_id"])
    assert first["status"] == "scheduled"
    assert first["availability_id"] == "slot_b"
    assert all(row.get("availability_id") != "slot_a" for row in plan)
    assert storage.load_json(storage.data_path("plan")) == plan


def test_manual_override_requires_declared_reason_and_is_saved(monkeypatch, tmp_path):
    task, _, course, _ = fixture_data(monkeypatch, tmp_path)
    beginning = datetime(2026, 11, 27, 9, 30, tzinfo=TZ)
    ending = beginning + timedelta(minutes=60)
    assert class_conflicts([course], beginning, ending, USER)
    with pytest.raises(storage.DataError, match="請假"):
        place_task(USER, "t1", beginning, ending, now=NOW)
    saved = place_task(USER, "t1", beginning, ending,
                       override_reason="請假", now=NOW)
    assigned = next(row for row in saved if row["task_id"] == "t1")
    assert assigned["status"] == "scheduled"
    assert assigned["class_override"] == "請假"
    slot = next(s for s in storage.load_json(storage.data_path("availability"))
                if s["availability_id"] == MANUAL_PREFIX + "t1")
    assert slot["start_time"] == "09:30"
    assert slot["available_minutes"] == 60
    assert slot["overlap_course_ids"] == ["class1"]
    actual_task = next(t for t in storage.load_json(storage.data_path("tasks"))
                       if t["task_id"] == "t1")
    assert actual_task["estimated_minutes"] == 60
    assert actual_task["preferred_availability_id"] == MANUAL_PREFIX + "t1"
    # 調整方塊長度到 90 分鐘，會真正變更任務與時段
    moved = place_task(USER, "t1", beginning, beginning + timedelta(minutes=90),
                       override_reason="停課", now=NOW)
    assert next(x for x in moved if x["task_id"] == "t1")["status"] == "scheduled"
    assert next(t for t in storage.load_json(storage.data_path("tasks"))
                if t["task_id"] == "t1")["estimated_minutes"] == 90


def test_placement_rejects_past_and_other_task_conflict(monkeypatch, tmp_path):
    task, _, _, _ = fixture_data(monkeypatch, tmp_path)
    with pytest.raises(storage.DataError, match="已過去"):
        propose_placement([task], [], [], [], USER, "t1",
                          NOW - timedelta(minutes=10), NOW + timedelta(minutes=35), NOW)
    existing = place_task(USER, "t1", datetime(2026, 11, 27, 19, tzinfo=TZ),
                          datetime(2026, 11, 27, 19, 45, tzinfo=TZ), now=NOW)
    with pytest.raises(storage.DataError, match="另一項"):
        propose_placement(storage.load_json(storage.data_path("tasks")),
                          storage.load_json(storage.data_path("availability")),
                          existing, storage.load_json(storage.data_path("events")),
                          USER, "t2", datetime(2026, 11, 27, 19, 15, tzinfo=TZ),
                          datetime(2026, 11, 27, 19, 45, tzinfo=TZ), NOW)


def test_unassign_then_resume_auto(monkeypatch, tmp_path):
    fixture_data(monkeypatch, tmp_path)
    beginning = datetime(2026, 11, 27, 19, tzinfo=TZ)
    place_task(USER, "t1", beginning, beginning + timedelta(minutes=45), now=NOW)
    held = unassign_task(USER, "t1", NOW)
    assert next(x for x in held if x["task_id"] == "t1")["status"] == "unscheduled"
    assert next(x for x in storage.load_json(storage.data_path("tasks"))
                if x["task_id"] == "t1")["planning_hold"] is True
    assert not any(s["availability_id"] == MANUAL_PREFIX + "t1"
                   for s in storage.load_json(storage.data_path("availability")))
    restored = resume_auto(USER, "t1", NOW)
    assert next(x for x in restored if x["task_id"] == "t1")["status"] == "scheduled"


def test_board_marks_ai_and_locks_classes_and_past():
    course = {"event_id": "course", "user_id": USER, "weekday": 5,
              "title": "控制系統", "start_time": "09:00", "end_time": "11:00"}
    tasks = [
        {"task_id": "ai", "title": "AI 複習", "status": "pending",
         "source": "ai_confirmed", "estimated_minutes": 30},
        {"task_id": "manual", "title": "自選", "status": "pending",
         "estimated_minutes": 45}
    ]
    events = board_events([course], [], tasks, [], date(2026, 11, 27), NOW)
    assert next(e for e in events if e["id"] == "class:course")["editable"] is False
    assert next(e for e in events if e["id"] == "task:ai")["allDay"]
    assert next(e for e in events if e["id"] == "task:ai")["title"].startswith("✦ AI")
    assert next(e for e in events if e["id"] == "task:manual")["editable"]


def test_calendar_event_change_to_time_or_back_to_inbox():
    tasks = [{"task_id": "t1", "estimated_minutes": 45}]
    change = {"callback": "eventChange",
              "eventChange": {"event": {
                  "id": "task:t1", "allDay": False,
                  "start": "2026-11-27T19:00:00+08:00",
                  "end": "2026-11-27T20:00:00+08:00"}}}
    candidate = calendar_change_candidate(change, tasks)
    assert candidate["kind"] == "place"
    assert (candidate["end"] - candidate["start"]).total_seconds() == 3600
    back = {"callback": "eventChange",
            "eventChange": {"oldEvent": {"allDay": False},
                            "event": {"id": "task:t1", "allDay": True,
                                      "start": "2026-11-27"}}}
    assert calendar_change_candidate(back, tasks) == {"kind": "unschedule", "task_id": "t1"}


def test_deadline_rejection_has_no_side_effect(monkeypatch, tmp_path):
    task, _, _, _ = fixture_data(monkeypatch, tmp_path)
    before_tasks = storage.load_json(storage.data_path("tasks"))
    before_slots = storage.load_json(storage.data_path("availability"))
    with pytest.raises(storage.DataError, match="Deadline"):
        place_task(USER, "t1", "2026-12-03T19:00:00+08:00",
                   "2026-12-03T20:00:00+08:00", now=NOW)
    assert storage.load_json(storage.data_path("tasks")) == before_tasks
    assert storage.load_json(storage.data_path("availability")) == before_slots


def test_past_manual_session_cannot_be_unassigned(monkeypatch, tmp_path):
    fixture_data(monkeypatch, tmp_path)
    start = datetime(2026, 11, 27, 19, tzinfo=TZ)
    place_task(USER, "t1", start, start + timedelta(minutes=45), now=NOW)
    with pytest.raises(storage.DataError, match="已開始"):
        unassign_task(USER, "t1", now=start + timedelta(minutes=5))
    assert any(row["task_id"] == "t1" and row["status"] == "scheduled"
               for row in storage.load_json(storage.data_path("plan")))


def test_drag_from_all_day_uses_original_estimate():
    tasks = [{"task_id": "t1", "estimated_minutes": 45}]
    change = {
        "callback": "eventChange",
        "eventChange": {
            "oldEvent": {"allDay": True},
            "event": {"id": "task:t1", "allDay": False,
                      "start": "2026-11-27T19:00:00+08:00",
                      "end": "2026-11-28T00:00:00+08:00"}
        }
    }
    result = calendar_change_candidate(change, tasks)
    assert result["end"] - result["start"] == timedelta(minutes=45)
