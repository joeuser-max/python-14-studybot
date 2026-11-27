"""回歸測試：恢復日／週／月檢視與 LINE 一日 Mock，避免 V2 功能覆蓋原有路徑。"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calendar_views import VIEWS, overview_events, view_options
from mock_day import one_day_timeline, recommended_demo_day

TZ = ZoneInfo("Asia/Taipei")


def test_calendar_views_keep_day_week_month_without_all_day_standby():
    assert set(VIEWS) == {"日", "週", "月"}
    for name, expected in VIEWS.items():
        options = view_options(name)
        assert options["initialView"] == expected
        assert options["allDaySlot"] is False
        assert options["slotDuration"] == "00:30:00"
        assert options["slotMinTime"] == "08:00:00"
        assert options["slotMaxTime"] == "24:00:00"


def test_month_week_day_show_events_not_empty_slot_blocks():
    course = {
        "event_id": "c1", "weekday": 5, "title": "控制系統",
        "start_time": "10:00", "end_time": "12:00", "enabled": True,
    }
    slot = {"availability_id": "slot1", "date": "2026-11-27",
            "start_time": "13:00", "available_minutes": 60}
    task = {"task_id": "t1", "title": "Routh", "subject": "控制系統",
            "status": "pending", "estimated_minutes": 60}
    plan = {"task_id": "t1", "availability_id": "slot1",
            "status": "scheduled", "source": "manual"}
    external = {"id": "ics1", "title": "朋友聚餐",
                "start": "2026-11-27T18:00+08:00",
                "end": "2026-11-27T19:00+08:00"}
    events = overview_events([course], [slot], [task], [plan], [external])
    kinds = [(e.get("extendedProps") or {}).get("kind") for e in events]
    assert set(kinds) == {"class", "study_plan", "external"}
    assert "availability" not in kinds
    assert len({e["id"] for e in events}) == 3


def test_one_day_mock_keeps_class_note_and_study_checkin_order():
    day = date(2026, 11, 27)  # Friday
    course = {
        "event_id": "c1", "weekday": 5, "title": "通訊原理",
        "start_time": "10:00", "end_time": "12:00",
        "offset_minutes": 10, "enabled": True,
    }
    task = {
        "task_id": "t1", "title": "練習傅立葉",
        "day": day.isoformat(),
        "start": "2026-11-27T13:00:00+08:00",
        "end": "2026-11-27T14:00:00+08:00",
    }
    sequence = one_day_timeline(day, [course], [task])
    assert [x["time"] for x in sequence] == [
        "10:00", "12:00", "12:10", "13:00", "14:00"
    ]
    assert [x["kind"] for x in sequence] == [
        "class", "class", "line_note", "line_study", "line_checkin"
    ]
    assert all(x.get("message") for x in sequence)
    assert "【模擬 LINE】" in sequence[2]["message"]


def test_one_day_mock_selects_nearest_day_with_course():
    days = [date(2026, 11, 27) + timedelta(days=i) for i in range(7)]
    courses = [{"weekday": 1, "title": "Python"}]
    assert recommended_demo_day(days, courses, []) == date(2026, 11, 30)
    assert recommended_demo_day(days, [], [{"day": "2026-11-29"}]) == date(2026, 11, 29)
