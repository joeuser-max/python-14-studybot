"""真實完成紀錄的 1D／1W／1M 統計；避免將測試資料或尚未完成算為成績。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import storage
from progress_insights import history_series, make_progress_event
from task_actions import save_task_changes

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 27, 20, tzinfo=TZ)


def test_progress_event_only_when_value_changes():
    before = {"task_id": "t1", "user_id": "u1", "estimated_minutes": 45,
              "status": "pending", "progress_percent": 30}
    assert make_progress_event(before, before, NOW) is None
    completed = {**before, "progress_percent": 100, "status": "completed"}
    event = make_progress_event(before, completed, NOW)
    assert event["status"] == "completed"
    assert event["progress_percent"] == 100
    assert event["estimated_minutes"] == 45
    assert event["source"] == "user_action"


def test_1d_1w_1m_and_reopened_task_does_not_inflate_history():
    t1 = {"task_id": "t1", "user_id": "u1", "status": "completed"}
    t2 = {"task_id": "t2", "user_id": "u1", "status": "completed"}
    t3 = {"task_id": "t3", "user_id": "u1", "status": "pending"}
    t4 = {"task_id": "t4", "user_id": "u2", "status": "completed"}
    events = [
        {"task_id": "t1", "user_id": "u1", "status": "completed",
         "timestamp": "2026-11-27T13:00:00+08:00", "estimated_minutes": 60},
        {"task_id": "t2", "user_id": "u1", "status": "completed",
         "timestamp": "2026-11-23T15:00:00+08:00", "estimated_minutes": 30},
        {"task_id": "t3", "user_id": "u1", "status": "completed",
         "timestamp": "2026-11-26T12:00:00+08:00", "estimated_minutes": 20},
        {"task_id": "t3", "user_id": "u1", "status": "pending",
         "timestamp": "2026-11-27T12:00:00+08:00", "estimated_minutes": 20},
        {"task_id": "t4", "user_id": "u2", "status": "completed",
         "timestamp": "2026-11-27T11:00:00+08:00", "estimated_minutes": 100},
    ]
    today = history_series(events, [t1,t2,t3,t4], "u1", "1D", NOW)
    assert today["completed"] == 1
    assert today["planned_minutes"] == 60
    assert len(today["rows"]) == 24
    assert today["rows"][13]["completed"] == 1
    week = history_series(events, [t1,t2,t3,t4], "u1", "1W", NOW)
    assert week["completed"] == 2
    assert week["planned_minutes"] == 90
    assert week["active_days"] == 2
    assert week["rows"][-1]["cumulative"] == 2
    month = history_series(events, [t1,t2,t3,t4], "u1", "1M", NOW)
    assert len(month["rows"]) == 30
    assert month["completed"] == 2


def test_real_task_edit_appends_history_and_replans(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)
    original = {"task_id": "t1", "user_id": "u1", "subject": "Python",
                "title": "作業", "status": "pending", "deadline": "2026-12-01",
                "estimated_minutes": 60, "progress_percent": 20,
                "preferred_availability_id": ""}
    storage.add_task_to_storage(original)
    save_task_changes({**original, "status": "completed", "progress_percent": 100},
                      demo_mode=False)
    events = storage.load_json(storage.data_path("progress_events"))
    assert len(events) == 1
    assert events[0]["progress_percent"] == 100
    assert events[0]["status"] == "completed"
    assert storage.load_json(storage.data_path("tasks"))[0]["status"] == "completed"
    plan = storage.load_json(storage.data_path("plan"))
    assert any(row["task_id"] == "t1" for row in plan)
