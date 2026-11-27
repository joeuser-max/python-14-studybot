import json
from io import BytesIO

import pytest

import ai_assistant as ai


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai")
    monkeypatch.setenv("OPENAI_MODEL", "offline-model")


def test_gemini_class_feedback_rest_contract(gemini, monkeypatch):
    calls = []
    result = {"summary": "測試摘要", "key_points": ["根軌跡"],
              "unresolved_questions": ["如何判斷虛軸根？"], "topic_tags": ["根軌跡"],
              "suggested_task": "複習虛軸根", "estimated_minutes": 30}
    def fake(req, timeout):
        body = json.loads(req.data)
        calls.append(body)
        assert req.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
        assert req.get_header("X-goog-api-key") == "offline-gemini"
        assert req.get_header("Authorization") is None
        assert timeout == 30
        assert body["generationConfig"]["responseJsonSchema"] == ai.CLASS_FEEDBACK_SCHEMA
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["maxOutputTokens"] == 4096
        assert "systemInstruction" in body and "tools" not in body
        assert "private-id" not in json.dumps(body)
        return BytesIO(json.dumps({"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"thought": True, "text": "ignored"}, {"text": json.dumps(result)}]
        }}]}).encode())
    monkeypatch.setattr(ai.request, "urlopen", fake)
    assert ai.ai_is_configured()
    out = ai.organize_class_feedback({"content": "不懂虛軸根", "progress": 3,
                                      "line_user_id": "private-id"}, "控制系統")
    assert out == result and len(calls) == 1


@pytest.mark.parametrize("response", [
    {"candidates": []},
    {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]},
])
def test_gemini_invalid_output_rejected(gemini, monkeypatch, response):
    monkeypatch.setattr(ai.request, "urlopen", lambda *a, **k: BytesIO(json.dumps(response).encode()))
    with pytest.raises(ai.AIError):
        ai.organize_class_feedback({"content": "測試筆記", "progress": 3}, "控制系統")


def test_missing_gemini_key_never_falls_back_to_openai(gemini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setattr(ai.request, "urlopen", lambda *a, **k: pytest.fail("unexpected network"))
    assert not ai.ai_is_configured()
    with pytest.raises(ai.AIError, match="GEMINI_API_KEY"):
        ai.organize_class_feedback({"content": "測試筆記", "progress": 3}, "控制系統")


def test_openai_stays_default(gemini, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER")
    assert ai.ai_provider() == "openai"
    assert ai._credentials() == ("offline-openai", "offline-model")
