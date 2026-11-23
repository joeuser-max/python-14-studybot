import pytest

import storage
from storage import (
    DataError,
    add_availability,
    data_path,
    load_json,
    save_json,
    update_availability,
    update_event,
)


def use_test_data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    save_json(data_path("events"), [])
    save_json(data_path("availability"), [])


def test_update_event_replaces_the_existing_course(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    original = {
        "event_id": "event-1",
        "user_id": "user-1",
        "event_type": "class",
        "title": "錯誤課名",
        "weekday": 1,
        "start_time": "09:00",
        "end_time": "10:00",
        "offset_minutes": 10,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    save_json(data_path("events"), [original])

    updated = {**original, "title": "修正課名", "weekday": 2}
    update_event(updated)

    assert load_json(data_path("events")) == [updated]


def test_update_event_rejects_missing_course(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    missing = {
        "event_id": "missing",
        "user_id": "user-1",
        "event_type": "class",
        "title": "課程",
        "weekday": 1,
        "start_time": "09:00",
        "end_time": "10:00",
        "offset_minutes": 10,
        "prompt_template": "class_feedback",
        "enabled": True,
    }

    with pytest.raises(DataError, match="找不到要修改的課程"):
        update_event(missing)


def test_update_availability_saves_edit_and_rejects_overlap(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    first = {
        "availability_id": "slot-1",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 60,
    }
    second = {
        "availability_id": "slot-2",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "21:00",
        "available_minutes": 60,
    }
    add_availability(first)
    add_availability(second)

    updated = {**first, "start_time": "20:00"}
    update_availability(updated)
    assert load_json(data_path("availability")) == [updated, second]

    overlapping = {**updated, "start_time": "21:30"}
    with pytest.raises(DataError, match="彼此重疊"):
        update_availability(overlapping)
    assert load_json(data_path("availability")) == [updated, second]
