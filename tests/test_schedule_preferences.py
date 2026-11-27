"""First final integration: green Availability ∩ Preference is a soft target."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import storage
from schedule_preferences import (
    available_preference_cells, clear_preferences, mark_preferences,
)
from week_planner import board_payload, fill_remaining, place_manual

TZ=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,27,7,30,tzinfo=TZ)
USER="demo_user_001"


def task(tid,deadline="2026-11-30"):
    return {
        "task_id":tid,"user_id":USER,"subject":"電子學","title":tid,
        "deadline":deadline,"status":"pending","estimated_minutes":60,
        "preferred_availability_id":"",
    }


@pytest.fixture
def db(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,"DATA_DIR",tmp_path)
    for file in storage.FILES:
        storage.save_json(storage.data_path(file),[])
    return tmp_path


def test_only_available_future_empty_cells_can_be_marked(db):
    storage.save_json(storage.data_path("events"),[{
        "user_id":USER,"event_id":"c1","event_type":"class",
        "weekday":5,"start_time":"09:00","end_time":"11:00","title":"控制",
    }])
    cells=[
        {"date":"2026-11-27","period":"1"},
        {"date":"2026-11-27","period":"2"},
        {"date":"2026-11-28","period":"5"},
        {"date":"2026-11-26","period":"3"},
    ]
    result=mark_preferences(USER,cells,True,NOW)
    assert result["updated"] == 2
    assert available_preference_cells(USER,NOW)=={
        ("2026-11-27","1"),("2026-11-28","5")
    }
    assert len(storage.load_json(storage.data_path("plan")))==0
    mark_preferences(USER,[{"date":"2026-11-27","period":"1"}],False,NOW)
    assert available_preference_cells(USER,NOW)=={("2026-11-28","5")}
    assert clear_preferences(USER)==1
    assert not available_preference_cells(USER,NOW)


def test_green_preferred_but_not_green_only(db):
    storage.save_json(storage.data_path("tasks"),[
        task("green"),task("fallback","2026-11-27"),
    ])
    # Green late on Saturday, but the fallback task must meet Friday deadline.
    mark_preferences(USER,[{"date":"2026-11-28","period":"5"}],True,NOW)
    result=fill_remaining(USER,NOW)
    assert len(result["placed"]) == 2
    chosen={p["task_id"]:p for p in result["placed"]}
    assert chosen["green"]["scheduled_start"].startswith("2026-11-28T13:00")
    assert chosen["green"]["preference_hits"]==1
    assert chosen["fallback"]["preference_hits"]==0
    assert chosen["fallback"]["scheduled_start"].startswith("2026-11-27T08:00")
    assert len(board_payload(USER,NOW)["scheduled"])==2


def test_hand_pinned_task_is_not_moved_when_green_enabled(db):
    storage.save_json(storage.data_path("tasks"),[task("manual"),task("remaining")])
    pinned=place_manual(USER,"manual","2026-11-27","2",1,NOW)
    mark_preferences(USER,[{"date":"2026-11-27","period":"2"},
                          {"date":"2026-11-28","period":"2"}],True,NOW)
    # Occupied Friday 09:00 cannot be marked, so Saturday is the preference.
    assert available_preference_cells(USER,NOW)=={("2026-11-28","2")}
    placed=fill_remaining(USER,NOW)
    assert len(placed["placed"])==1
    rows=storage.load_json(storage.data_path("plan"))
    assert next(p for p in rows if p["task_id"]=="manual")==pinned
    assert next(p for p in rows if p["task_id"]=="remaining")["preference_hits"]==1


def test_calendar_changes_invalidate_green_without_erasing_user_choice(db):
    mark_preferences(USER,[{"date":"2026-11-28","period":"2"}],True,NOW)
    assert len(available_preference_cells(USER,NOW))==1
    storage.save_json(storage.data_path("events"),[{
        "user_id":USER,"event_id":"new","event_type":"class",
        "weekday":6,"start_time":"09:00","end_time":"10:00","title":"新課",
    }])
    assert available_preference_cells(USER,NOW)==set()
    assert board_payload(USER,NOW)["preferences"]==[]
    assert len(storage.load_json(storage.data_path("preference_targets")))==1
    # No forced weekly reset; old preference is simply outside the current range.
    next_week=NOW+timedelta(days=8)
    assert available_preference_cells(USER,next_week)==set()


def test_green_saved_for_one_user_cannot_affect_another(db):
    mark_preferences(USER,[{"date":"2026-11-28","period":"2"}],True,NOW)
    assert available_preference_cells("other_student",NOW)==set()
    assert clear_preferences("other_student")==0
    assert len(available_preference_cells(USER,NOW))==1
