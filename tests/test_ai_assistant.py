import json

import pytest

import ai_assistant
from ai_assistant import AIError, organize_class_feedback, validate_class_feedback_analysis


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        output = {
            "output": [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(self.value, ensure_ascii=False),
                }],
            }],
        }
        return json.dumps(output, ensure_ascii=False).encode("utf-8")


def test_organize_class_feedback_sends_only_opted_in_feedback_fields(monkeypatch):
    expected = {
        "summary": "本堂介紹函式與清單。",
        "key_points": ["函式可以重複使用"],
        "unresolved_questions": ["參數預設值尚不清楚"],
        "suggested_task": "練習撰寫含參數的函式",
        "estimated_minutes": 45,
    }

    def fake_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        prompt = payload["input"]
        assert "今天學習函式和清單" in prompt
        assert "U-private" not in prompt
        assert "feedback-secret-id" not in prompt
        assert payload["store"] is False
        assert timeout == 30
        return FakeResponse(expected)

    monkeypatch.setattr(ai_assistant.request, "urlopen", fake_urlopen)
    result = organize_class_feedback(
        {
            "user_id": "U-private",
            "feedback_id": "feedback-secret-id",
            "content": "今天學習函式和清單。",
            "progress": 3,
        },
        "程式設計",
        api_key="test-key",
        model="test-model",
    )

    assert result == expected


def test_class_feedback_analysis_rejects_task_without_realistic_duration():
    with pytest.raises(AIError, match="至少須為 15 分鐘"):
        validate_class_feedback_analysis({
            "summary": "摘要",
            "key_points": [],
            "unresolved_questions": [],
            "suggested_task": "複習",
            "estimated_minutes": 0,
        })


def test_class_feedback_requires_progress_and_api_configuration(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(AIError, match="設定 OPENAI_API_KEY"):
        organize_class_feedback(
            {"content": "課堂筆記", "progress": 3},
            "程式設計",
        )

    with pytest.raises(AIError, match="進度必須介於 1 到 5"):
        organize_class_feedback(
            {"content": "課堂筆記", "progress": 6},
            "程式設計",
            api_key="test-key",
            model="test-model",
        )
