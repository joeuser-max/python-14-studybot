import pytest

import storage
from storage import (
    DataError,
    add_availability,
    add_availabilities,
    clear_task_availability_preference,
    data_path,
    delete_availability,
    load_json,
    save_json,
    update_feedback_analysis,
    update_availability,
    update_event,
    update_task,
    validate_feedback,
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


def test_add_availabilities_saves_multiple_slots_atomically(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    original = {
        "availability_id": "slot-1",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "08:00",
        "available_minutes": 60,
    }
    save_json(data_path("availability"), [original])
    selected_slots = [
        {
            "availability_id": "slot-2",
            "user_id": "user-1",
            "date": "2026-11-24",
            "start_time": "10:00",
            "available_minutes": 90,
        },
        {
            "availability_id": "slot-3",
            "user_id": "user-1",
            "date": "2026-11-24",
            "start_time": "13:00",
            "available_minutes": 90,
        },
    ]

    add_availabilities(selected_slots)

    assert load_json(data_path("availability")) == [original] + selected_slots


def test_add_availabilities_rejects_overlapping_selection_without_partial_save(
    monkeypatch, tmp_path
):
    use_test_data(monkeypatch, tmp_path)
    original = {
        "availability_id": "slot-1",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "08:00",
        "available_minutes": 60,
    }
    save_json(data_path("availability"), [original])
    selected_slots = [
        {
            "availability_id": "slot-2",
            "user_id": "user-1",
            "date": "2026-11-24",
            "start_time": "10:00",
            "available_minutes": 90,
        },
        {
            "availability_id": "slot-3",
            "user_id": "user-1",
            "date": "2026-11-24",
            "start_time": "11:00",
            "available_minutes": 90,
        },
    ]

    with pytest.raises(DataError, match="彼此重疊"):
        add_availabilities(selected_slots)

    assert load_json(data_path("availability")) == [original]


def test_add_availability_allows_block_ending_at_midnight(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    last_half_hour = {
        "availability_id": "slot-midnight",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "23:30",
        "available_minutes": 30,
    }

    add_availability(last_half_hour)

    assert load_json(data_path("availability")) == [last_half_hour]

    crossing_midnight = {
        **last_half_hour,
        "availability_id": "slot-crossing",
        "available_minutes": 31,
    }
    with pytest.raises(DataError, match="跨午夜"):
        add_availability(crossing_midnight)


def test_delete_availability_and_unpin_only_the_selected_users_tasks(
    monkeypatch, tmp_path
):
    use_test_data(monkeypatch, tmp_path)
    selected_slot = {
        "availability_id": "slot-1",
        "user_id": "user-1",
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 60,
    }
    other_users_slot = {
        **selected_slot,
        "user_id": "user-2",
    }
    save_json(data_path("availability"), [selected_slot, other_users_slot])
    tasks = [
        {
            "task_id": "task-1",
            "user_id": "user-1",
            "preferred_availability_id": "slot-1",
        },
        {
            "task_id": "task-2",
            "user_id": "user-2",
            "preferred_availability_id": "slot-1",
        },
        {
            "task_id": "task-3",
            "user_id": "user-1",
            "preferred_availability_id": "another-slot",
        },
    ]
    save_json(data_path("tasks"), tasks)

    clear_task_availability_preference("slot-1", "user-1")
    delete_availability("slot-1", "user-1")

    assert load_json(data_path("availability")) == [other_users_slot]
    assert load_json(data_path("tasks")) == [
        {**tasks[0], "preferred_availability_id": ""},
        tasks[1],
        tasks[2],
    ]


def test_delete_availability_rejects_missing_or_other_users_slot(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    other_users_slot = {
        "availability_id": "slot-1",
        "user_id": "user-2",
        "date": "2026-11-24",
        "start_time": "19:00",
        "available_minutes": 60,
    }
    save_json(data_path("availability"), [other_users_slot])

    with pytest.raises(DataError, match="找不到要刪除的讀書時段"):
        delete_availability("slot-1", "user-1")

    assert load_json(data_path("availability")) == [other_users_slot]


def test_feedback_progress_is_optional_but_must_be_one_to_five():
    feedback = {
        "feedback_id": "feedback-1",
        "user_id": "user-1",
        "event_id": "event-1",
        "class_date": "2026-11-24",
        "received_at": "2026-11-24T19:00:00+08:00",
        "content": "今天學習函式。",
        "source": "selected",
        "webhook_event_id": "webhook-1",
    }

    validate_feedback(feedback)
    with pytest.raises(DataError, match="自評進度必須是 1 到 5"):
        validate_feedback({**feedback, "progress": 6})


def test_update_feedback_analysis_is_scoped_to_feedback_owner(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    feedback = [
        {"feedback_id": "feedback-1", "user_id": "user-1"},
        {"feedback_id": "feedback-1", "user_id": "user-2"},
    ]
    analysis = {"summary": "重點摘要"}
    save_json(data_path("feedback"), feedback)

    update_feedback_analysis("feedback-1", "user-1", analysis)

    assert load_json(data_path("feedback")) == [
        {**feedback[0], "ai_analysis": analysis},
        feedback[1],
    ]
    with pytest.raises(DataError, match="找不到要更新的課後回饋"):
        update_feedback_analysis("missing", "user-1", analysis)


def test_update_task_changes_name_deadline_and_status_without_losing_other_data(
    monkeypatch, tmp_path
):
    use_test_data(monkeypatch, tmp_path)
    original = {
        "task_id": "task-1",
        "user_id": "user-1",
        "subject": "電子學3",
        "title": "完成 c13",
        "deadline": "2026-11-30",
        "estimated_minutes": 120,
        "status": "pending",
        "preferred_availability_id": "slot-1",
    }
    other_user_task = {
        **original,
        "task_id": "task-2",
        "user_id": "user-2",
    }
    save_json(data_path("tasks"), [original, other_user_task])

    updated = {
        **original,
        "title": "完成 c14",
        "deadline": "2026-12-05",
        "status": "completed",
    }
    update_task(updated)

    assert load_json(data_path("tasks")) == [updated, other_user_task]


def test_update_task_rejects_missing_task(monkeypatch, tmp_path):
    use_test_data(monkeypatch, tmp_path)
    save_json(data_path("tasks"), [])
    missing = {
        "task_id": "missing",
        "user_id": "user-1",
        "subject": "電子學3",
        "title": "讀書",
        "deadline": "2026-12-05",
        "estimated_minutes": 60,
        "status": "pending",
        "preferred_availability_id": "",
    }

    with pytest.raises(DataError, match="找不到要修改的任務"):
        update_task(missing)
