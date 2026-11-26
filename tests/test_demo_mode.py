"""展示模式的隔離、預設資料、重設與 AI Mock 行為測試。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import storage
from demo_data import mock_learning_suggestions, sample_records, seed_demo_data


TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 26, 22, 0, tzinfo=TZ)


def test_sample_fixture_is_valid_and_editable():
    records = sample_records(NOW)
    assert len(records["events"]) >= 3
    assert len(records["tasks"]) >= 2
    assert records["users"][0]["line_user_id"] == ""
    assert records["feedback"][0]["source"] == "demo"
    for event in records["events"]:
        storage.validate_event(event)
    for task in records["tasks"]:
        storage.validate_task(task)
    for feedback in records["feedback"]:
        storage.validate_feedback(feedback)


def test_demo_storage_does_not_modify_live_files(monkeypatch, tmp_path):
    live = tmp_path / "live"
    demo = tmp_path / "demo"
    monkeypatch.setattr(storage, "DATA_DIR", live)
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", demo)
    storage.select_demo_storage(False)
    storage.save_json(storage.data_path("events"), [{"event_id": "real-class"}])

    try:
        storage.select_demo_storage(True)
        assert seed_demo_data(now=NOW) is True
        original = storage.load_json(storage.data_path("events"))
        assert len(original) == 3

        # 修改展示課程後重新整理，不應重新載入覆蓋。
        edited = {**original[0], "title": "現場修改的課程"}
        storage.update_event(edited)
        assert seed_demo_data(now=NOW) is False
        assert storage.load_json(storage.data_path("events"))[0]["title"] == "現場修改的課程"

        # 明確重設才還原初始展示資料。
        assert seed_demo_data(reset=True, now=NOW) is True
        assert storage.load_json(storage.data_path("events"))[0]["title"] == original[0]["title"]
    finally:
        storage.select_demo_storage(False)

    assert storage.load_json(storage.data_path("events")) == [{"event_id": "real-class"}]


def test_seed_requires_isolated_demo_context(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    storage.select_demo_storage(False)
    with pytest.raises(RuntimeError, match="正式資料"):
        seed_demo_data(now=NOW)


def test_mock_ai_suggestions_reference_feedback_without_api():
    records = sample_records(NOW)
    result = mock_learning_suggestions(
        records["feedback"], records["events"], "demo_user_001"
    )
    assert result["summary"].startswith("【Mock 展示】")
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["source_feedback_id"] == records["feedback"][0]["feedback_id"]
    assert mock_learning_suggestions([], records["events"])["suggestions"] == []
    assert mock_learning_suggestions(records["feedback"], records["events"], "unknown")["suggestions"] == []
