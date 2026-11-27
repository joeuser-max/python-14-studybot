"""外部行事曆 UID 穩定性、重複事件、七日範圍與排程衝突回歸測試。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

import storage
from calendar_sync import (
    conflicts_with_existing_plan, export_week_ics, import_ics, preview_ics,
)

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 27, 7, 30, tzinfo=TZ)
USER = "demo_user_001"


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name), [])


def _calendar(start: str, end: str, rule: str = "") -> bytes:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        "UID:moveable-event-123\r\n"
        + f"DTSTART:{start}\r\nDTEND:{end}\r\n"
        + (f"RRULE:{rule}\r\n" if rule else "")
        + "SUMMARY:實驗室會議\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8")


def test_event_uid_survives_provider_time_change(db):
    original = preview_ics(_calendar("20261127T100000", "20261127T110000"), USER, "one.ics", NOW)
    moved = preview_ics(_calendar("20261127T110000", "20261127T120000"), USER, "renamed.ics", NOW)
    assert len(original) == len(moved) == 1
    assert original[0]["id"] == moved[0]["id"]
    assert import_ics(original, USER) == {"saved": 1, "skipped": 0}
    assert import_ics(moved, USER, overwrite=False) == {"saved": 0, "skipped": 1}
    assert storage.load_json(storage.data_path("external_events"))[0]["start"].endswith("10:00+08:00")
    assert import_ics(moved, USER, overwrite=True) == {"saved": 1, "skipped": 0}
    assert storage.load_json(storage.data_path("external_events"))[0]["start"].endswith("11:00+08:00")


def test_recurring_uid_has_distinct_occurrences(db):
    meetings = preview_ics(
        _calendar("20261127T100000", "20261127T110000", "FREQ=DAILY;COUNT=3"),
        USER, "repeat.ics", NOW,
    )
    assert len(meetings) == 3
    assert len({x["id"] for x in meetings}) == 3


def test_external_import_warns_about_existing_manual_plan(db):
    event = preview_ics(_calendar("20261127T110000", "20261127T120000"), USER, "study.ics", NOW)
    task = {
        "task_id": "study_1", "user_id": USER, "subject": "Python", "title": "複習課堂作業",
        "deadline": "2026-11-30", "estimated_minutes": 60,
        "status": "pending", "preferred_availability_id": "",
    }
    storage.save_json(storage.data_path("tasks"), [task])
    storage.save_json(storage.data_path("availability"), [{
        "availability_id": "slot_1", "user_id": USER, "date": "2026-11-27",
        "start_time": "11:00", "available_minutes": 60,
    }])
    storage.save_json(storage.data_path("plan"), [{
        "user_id": USER, "task_id": "study_1", "status": "scheduled",
        "availability_id": "slot_1", "source": "manual",
    }])
    warnings = conflicts_with_existing_plan(event, USER)
    assert len(warnings) == 1
    assert warnings[0]["task_id"] == "study_1"
    assert warnings[0]["event_title"] == "實驗室會議"
    # Conflict preview must be read-only.
    assert storage.load_json(storage.data_path("external_events")) == []
    assert len(storage.load_json(storage.data_path("plan"))) == 1


def test_week_export_omits_external_events_outside_window(db):
    storage.save_json(storage.data_path("external_events"), [
        {"id": "older", "user_id": USER, "title": "上個月行程",
         "start": "2026-10-01T10:00+08:00", "end": "2026-10-01T11:00+08:00"},
        {"id": "current", "user_id": USER, "title": "本週行程",
         "start": "2026-11-29T12:00+08:00", "end": "2026-11-29T13:00+08:00"},
    ])
    cal = Calendar.from_ical(export_week_ics(USER, NOW))
    names = [str(c.get("SUMMARY")) for c in cal.walk("VEVENT")]
    assert names == ["本週行程"]
