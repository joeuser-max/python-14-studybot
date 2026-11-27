"""Gemini 教練：輸入輸出驗證，不依賴實際付費或免費 API 額度。"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import storage
import study_coach
from week_planner import board_payload

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 27, 7, 30, tzinfo=TZ)
USER = "demo_user_001"


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.save_json(storage.data_path("tasks"), [{
        "task_id": "t1", "user_id": USER, "subject": "電子學", "title": "複習回授",
        "status": "pending", "deadline": "2026-11-29",
        "estimated_minutes": 60, "preferred_availability_id": "",
    }])
    for name in ("events", "plan", "availability", "external_events"):
        storage.save_json(storage.data_path(name), [])
    return board_payload(USER, NOW)


def test_gemini_without_key_does_not_call_api(monkeypatch, data):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(study_coach, "_request_gemini",
                        lambda *args: pytest.fail("不能在無金鑰時呼叫 API"))
    with pytest.raises(study_coach.CoachError, match="GEMINI_API_KEY"):
        study_coach.coach_with_gemini(data, {}, {}, USER, now=NOW)


def test_gemini_contract_mock_and_local_validation(monkeypatch, data):
    answer = {
        "summary": "依期限與課表安排較短的複習時間。",
        "actions": [{
            "task_id": "t1", "date": "2026-11-27",
            "period": "1", "blocks": 1, "reason": "先完成近期任務"
        }],
    }
    captured = {}
    def fake_api(payload, api_key, model):
        captured["payload"] = payload
        captured["model"] = model
        return answer
    monkeypatch.setattr(study_coach, "_request_gemini", fake_api)
    r = study_coach.coach_with_gemini(
        data, {"completion": 20}, {"name": "短時高頻型"}, USER,
        api_key="fake-key", now=NOW,
    )
    assert captured["model"] == "gemini-2.5-flash-lite"
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
    assert len(r["actions"]) == 1
    assert not r["rejected"]


def test_ai_cannot_insert_nonexistent_task_or_past_day(data):
    r = study_coach.validate_coach_output({
        "summary": "檢查不合法輸入",
        "actions": [
            {"task_id": "invented", "date": "2026-11-27", "period": "1", "blocks": 1},
            {"task_id": "t1", "date": "2026-11-26", "period": "1", "blocks": 1},
        ],
    }, data, USER, NOW)
    assert len(r["actions"]) == 0 and len(r["rejected"]) == 2


def test_demo_mock_coach_returns_valid_candidate_without_network(monkeypatch, data):
    monkeypatch.setattr(study_coach, "_request_gemini",
                        lambda *args: pytest.fail("Mock 絕不可打到外部 API"))
    result = study_coach.mock_coach_for_demo(
        data, {"preferred_periods": ["A", "B"], "maximum_blocks": 2},
        USER, now=NOW,
    )
    assert result["summary"].startswith("【Mock")
    assert len(result["actions"]) == 1
    assert result["actions"][0]["task_id"] == "t1"
    assert result["rejected"] == []
