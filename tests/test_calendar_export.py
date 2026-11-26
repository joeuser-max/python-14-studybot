"""行事曆單向匯出、時區與 Google 新增事件連結的回歸測試。"""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from calendar_export import export_calendar_ics, google_calendar_url, task_calendar_event

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 26, 8, tzinfo=TZ)


def test_export_ics_with_class_and_scheduled_study():
    courses = [{"event_id": "c1", "title": "控制系統",
                "weekday": 5, "start_time": "09:00", "end_time": "11:00"}]
    tasks = [{"task_id": "t1", "subject": "控制系統",
              "title": "練習根軌跡", "deadline": "2026-12-02",
              "estimated_minutes": 45, "status": "pending"}]
    slots = [{"availability_id": "s1", "date": "2026-11-27",
              "start_time": "19:00", "available_minutes": 60}]
    plan = [{"task_id": "t1", "availability_id": "s1", "status": "scheduled"}]
    ics = export_calendar_ics(courses, tasks, slots, plan, NOW).decode("utf-8")
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 2
    assert "RRULE:FREQ=WEEKLY;COUNT=12" in ics
    assert "SUMMARY:課程｜控制系統" in ics
    assert "SUMMARY:讀書｜練習根軌跡" in ics
    assert "DTSTART:20261127T110000Z" in ics  # 19:00 台北＝11:00 UTC
    assert "DTEND:20261127T114500Z" in ics


def test_completed_task_is_not_exported():
    course = []
    task = [{"task_id": "t", "subject": "課程", "title": "完成項",
             "deadline": "2026-12-01", "estimated_minutes": 30,
             "status": "completed"}]
    slot = [{"availability_id": "s", "date": "2026-11-27",
             "start_time": "20:00"}]
    plan = [{"task_id": "t", "availability_id": "s", "status": "scheduled"}]
    assert b"BEGIN:VEVENT" not in export_calendar_ics(course, task, slot, plan, NOW)


def test_google_calendar_url_is_encoded_and_not_saved_automatically():
    start = datetime(2026, 11, 27, 19, tzinfo=TZ)
    end = start + timedelta(minutes=45)
    url = google_calendar_url("控制系統，練習", start, end, "ClassPulse 測試")
    assert url.startswith("https://calendar.google.com/calendar/render?")
    query = parse_qs(urlsplit(url).query)
    assert query["action"] == ["TEMPLATE"]
    assert query["dates"] == ["20261127T110000Z/20261127T114500Z"]
    assert query["text"] == ["控制系統，練習"]
    with pytest.raises(ValueError):
        google_calendar_url("錯誤", start, start)


def test_slot_to_event_interval():
    task = {"estimated_minutes": 60}
    slot = {"date": "2026-11-27", "start_time": "20:30"}
    start, end = task_calendar_event(task, slot)
    assert start.tzinfo == TZ
    assert end - start == timedelta(minutes=60)
