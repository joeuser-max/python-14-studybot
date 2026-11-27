"""七日手動／自動排程與 ICS 匯入匯出回歸測試。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import storage
from storage import DataError
from week_planner import (
    PERIODS, board_payload, fill_remaining, place_manual, rolling_dates,
    set_task_blocks, unplace,
)
from calendar_sync import preview_ics, import_ics, edit_imported_event, export_week_ics
from icalendar import Calendar

TZ = ZoneInfo("Asia/Taipei")
USER = "demo_user_001"
NOW = datetime(2026, 11, 27, 7, 30, tzinfo=TZ)


def t(tid, deadline="2026-11-30", minutes=60):
    return {
        "task_id": tid, "user_id": USER, "subject": "控制系統", "title": tid,
        "deadline": deadline, "estimated_minutes": minutes, "status": "pending",
        "preferred_availability_id": "",
    }


@pytest.fixture()
def empty_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name), [])
    return tmp_path


def test_rolling_seven_days_and_sixteen_periods():
    days = rolling_dates(NOW)
    assert len(days) == 7 and days[0].isoformat() == "2026-11-27"
    assert days[-1].isoformat() == "2026-12-03"
    assert len(PERIODS) == 16
    assert [label for label, _ in PERIODS] == list("1234Z56789ABCDEF")


def test_manual_drag_does_not_schedule_other_tasks(empty_db):
    storage.save_json(storage.data_path("tasks"), [t("a"), t("b")])
    placed = place_manual(USER, "a", "2026-11-27", "2", 2, NOW)
    assert placed["source"] == "manual"
    assert placed["scheduled_minutes"] == 120
    plan = storage.load_json(storage.data_path("plan"))
    assert len(plan) == 1 and plan[0]["task_id"] == "a"
    assert {r["task_id"] for r in board_payload(USER, NOW)["tasks"]} == {"b"}
    # A refresh is a read operation, not a hidden auto-fill.
    assert len(board_payload(USER, NOW)["scheduled"]) == 1
    assert len(storage.load_json(storage.data_path("plan"))) == 1


def test_fill_preserves_manual_and_is_idempotent(empty_db):
    storage.save_json(storage.data_path("tasks"), [
        t("manual", "2026-12-02"), t("urgent", "2026-11-27"),
        t("later", "2026-11-30"),
    ])
    place_manual(USER, "manual", "2026-11-27", "2", 1, NOW)
    before = storage.load_json(storage.data_path("plan"))[0]
    report = fill_remaining(USER, NOW)
    assert len(report["placed"]) == 2 and not report["skipped"]
    plan = storage.load_json(storage.data_path("plan"))
    assert len(plan) == 3
    assert next(row for row in plan if row["task_id"] == "manual") == before
    assert next(row for row in plan if row["task_id"] == "urgent")["scheduled_start"].endswith("08:00+08:00")
    assert fill_remaining(USER, NOW)["placed"] == []
    assert len(storage.load_json(storage.data_path("plan"))) == 3


def test_courses_and_imported_events_are_busy(empty_db):
    storage.save_json(storage.data_path("tasks"), [t("a"), t("b")])
    storage.save_json(storage.data_path("events"), [{
        "event_id": "e1", "user_id": USER, "event_type": "class", "weekday": 5,
        "title": "課程", "start_time": "08:00", "end_time": "09:50",
    }])
    storage.save_json(storage.data_path("external_events"), [{
        "id": "ext1", "user_id": USER, "title": "其他行事曆",
        "start": "2026-11-27T10:00:00+08:00", "end": "2026-11-27T11:00:00+08:00",
    }])
    for label in ("1", "2", "3"):
        with pytest.raises(DataError, match="衝突"):
            place_manual(USER, "a", "2026-11-27", label, 1, NOW)
    place_manual(USER, "a", "2026-11-27", "4", 1, NOW)
    with pytest.raises(DataError, match="衝突"):
        place_manual(USER, "b", "2026-11-27", "4", 1, NOW)


def test_resizing_and_unplacing_affect_one_task_only(empty_db):
    storage.save_json(storage.data_path("tasks"), [t("a"), t("b")])
    set_task_blocks(USER, "a", 3)
    assert storage.load_json(storage.data_path("tasks"))[0]["estimated_minutes"] == 180
    place_manual(USER, "a", "2026-11-27", "5", 3, NOW)
    with pytest.raises(DataError, match="先移回"):
        set_task_blocks(USER, "a", 2)
    unplace(USER, "a")
    assert not storage.load_json(storage.data_path("plan"))
    assert {r["task_id"] for r in board_payload(USER, NOW)["tasks"]} == {"a", "b"}


def test_ics_import_requires_overwrite_and_export_roundtrip(empty_db):
    ics = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test-class
DTSTART:20261127T100000
DTEND:20261127T110000
SUMMARY:External study
END:VEVENT
END:VCALENDAR
"""
    events = preview_ics(ics, USER, "external.ics", NOW)
    assert len(events) == 1
    assert import_ics(events, USER) == {"saved": 1, "skipped": 0}
    assert import_ics(events, USER) == {"saved": 0, "skipped": 1}
    changed = events[0]
    with pytest.raises(DataError, match="確認覆寫"):
        edit_imported_event(USER, changed["id"], "新的行程", NOW, NOW + timedelta(hours=1))
    edit_imported_event(
        USER, changed["id"], "新的行程", datetime(2026, 11, 27, 12, tzinfo=TZ),
        datetime(2026, 11, 27, 13, tzinfo=TZ), confirmed=True,
    )
    data = export_week_ics(USER, NOW)
    exported = Calendar.from_ical(data)
    names = [str(e.get("SUMMARY")) for e in exported.walk("VEVENT")]
    assert "新的行程" in names
    assert len(storage.load_json(storage.data_path("external_events"))) == 1


def test_line_checkin_does_not_replan_peer_tasks_in_visual_board(empty_db):
    import line_bot
    storage.save_json(storage.data_path("tasks"), [t("a"), t("b")])
    place_manual(USER, "a", "2026-11-27", "2", 1, NOW)
    place_manual(USER, "b", "2026-11-27", "3", 1, NOW)
    old = next(row for row in storage.load_json(storage.data_path("plan"))
               if row["task_id"] == "b")
    # Simulate LINE completing A, should unplace A and leave B untouched.
    storage.update_task({**t("a"), "status": "completed"})
    line_bot._replan_user_tasks(USER, NOW, changed_task_id="a")
    after = storage.load_json(storage.data_path("plan"))
    assert len(after) == 1 and after[0] == old
    assert not any(x["availability_id"] == "board_a"
                   for x in storage.load_json(storage.data_path("availability")))
