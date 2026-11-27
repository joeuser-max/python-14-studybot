"""Step 15: adversarial owner isolation with temporary data only."""
from datetime import datetime

import pytest

import storage
import reminder_worker as worker
from calendar_sync import import_ics, export_week_ics
from plan_bridge import normalize_plan_result, merge_user_plan
from scheduler import make_plan, get_due_study_reminders, get_due_study_checkins
from week_planner import board_payload
from line_demo_registration import get_or_create_line_user
from line_demo_seed import seed_line_user
from note_tasks import candidate_tasks, confirm_question_task

NOW = datetime(2026, 11, 28, 10, tzinfo=storage.TZ)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)


def read(name):
    return storage.load_json(storage.data_path(name))


def write(name, records):
    storage.save_json(storage.data_path(name), records)


def task(uid, tid):
    return {"user_id": uid, "task_id": tid, "title": f"private-{uid}",
            "subject": "Python", "deadline": "2026-11-30",
            "estimated_minutes": 60, "status": "pending",
            "preferred_availability_id": ""}


def slot(uid, sid):
    return {"user_id": uid, "availability_id": sid, "date": "2026-11-28",
            "start_time": "10:00", "available_minutes": 60}


def test_course_update_cannot_take_over_foreign_course():
    course = {"user_id": "B", "event_id": "class-B", "event_type": "class",
              "title": "private course", "weekday": 1, "start_time": "09:00",
              "end_time": "10:00", "offset_minutes": 10,
              "prompt_template": "class_feedback", "enabled": True}
    write("events", [course])
    with pytest.raises(storage.DataError):
        storage.update_event({**course, "user_id": "A", "title": "overwritten"})
    assert read("events") == [course]


def test_task_status_and_slot_collision_cannot_change_other_owner():
    original = task("B", "task-B")
    write("tasks", [original])
    with pytest.raises(storage.DataError):
        storage.set_task_status("task-B", "completed", "A")
    assert read("tasks") == [original]
    foreign = slot("B", "slot-B")
    write("availability", [foreign])
    with pytest.raises(storage.DataError):
        storage.add_availability({**foreign, "user_id": "A"})
    assert read("availability") == [foreign]


def test_calendar_import_cannot_overwrite_foreign_event():
    foreign = {"id": "shared", "user_id": "B", "title": "B private",
               "start": "2026-11-28T10:00+08:00", "end": "2026-11-28T11:00+08:00"}
    write("external_events", [foreign])
    with pytest.raises(storage.DataError):
        import_ics([{**foreign, "user_id": "A", "title": "A"}], "A", overwrite=True)
    assert read("external_events") == [foreign]


def test_foreign_slot_not_resolved_by_board_or_ics_export():
    write("tasks", [task("A", "task-A")])
    write("availability", [slot("B", "slot-B")])
    write("plan", [{"user_id": "A", "task_id": "task-A",
                    "availability_id": "slot-B", "status": "scheduled"}])
    board = board_payload("A", NOW)
    assert not board["scheduled"]
    assert [r["task_id"] for r in board["tasks"]] == ["task-A"]
    assert b"private-A" not in export_week_ics("A", NOW)


def test_legacy_scheduler_does_not_compete_between_users():
    result = make_plan([task("A", "a"), task("B", "b")],
                       [slot("A", "a-slot"), slot("B", "b-slot")], [], NOW)
    assert {(r["user_id"], r["status"]) for r in result["plan"]} == {
        ("A", "scheduled"), ("B", "scheduled")}


def test_plan_bridge_rejects_foreign_owner():
    foreign = [{"user_id": "B", "task_id": "t"}]
    with pytest.raises(ValueError):
        normalize_plan_result(foreign, "A")
    with pytest.raises(ValueError):
        merge_user_plan([], "A", foreign)


def test_due_study_reminders_reject_foreign_slot_or_plan():
    tasks = [task("A", "a")]
    users = [{"user_id": "A", "line_user_id": "U_A", "study_reminders_enabled": True}]
    for row, slots in [
        ({"user_id": "A", "task_id": "a", "availability_id": "b",
          "status": "scheduled"}, [slot("B", "b")]),
        ({"user_id": "B", "task_id": "a", "availability_id": "a",
          "status": "scheduled"}, [slot("A", "a")]),
    ]:
        assert not get_due_study_reminders(tasks, [row], slots, users, NOW, [])
        assert not get_due_study_checkins(tasks, [row], slots, users, NOW, [])


def test_worker_never_pushes_gated_user_even_if_preferences_enabled(monkeypatch):
    write("users", [{"user_id": "A", "line_user_id": "U_A",
                     "demo_status": "seeded_pending_auth",
                     "reminders_enabled": True, "study_reminders_enabled": True}])
    write("tasks", [task("A", "a")])
    write("plan", [{"user_id": "A", "task_id": "a", "status": "unscheduled"}])
    monkeypatch.setattr(worker, "get_due_events", lambda *args: [
        {"user_id": "A", "reminder_id": "r", "kind": "class_feedback"}])
    monkeypatch.setattr(worker, "push_line_message", lambda *args: pytest.fail("unexpected push"))
    assert worker.run_reminder_worker_once(NOW) == []
    assert read("reminders") == []


def test_worker_reminder_collision_never_reuses_foreign_retry_key():
    record = {"user_id": "B", "reminder_id": "r", "retry_key": "B-key", "status": "pending"}
    write("reminders", [record])
    with pytest.raises(storage.DataError):
        worker._reserve_reminder({**record, "user_id": "A"})
    worker._mark_reminder("r", "sent", NOW.isoformat(), "A")
    assert read("reminders") == [record]


def test_seeded_note_candidate_cannot_be_confirmed_by_other_user():
    a = get_or_create_line_user("U_owner_A")[0]["user_id"]
    b = get_or_create_line_user("U_owner_B")[0]["user_id"]
    seed_line_user(a, NOW)
    seed_line_user(b, NOW)
    before = read("tasks")
    candidate = candidate_tasks(read("feedback"), read("events"), before, b, NOW)[0]
    with pytest.raises(storage.DataError):
        confirm_question_task(a, candidate, NOW)
    assert read("tasks") == before
