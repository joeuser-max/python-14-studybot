import json
from types import SimpleNamespace

import pytest

import line_official_bridge as bridge
import line_friend_e2e as demo
import storage

SUBJECT = "U" + "a" * 32
SECRET = "offline-original-secret"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data" / "friend-e2e")
    storage.select_demo_storage(False)
    monkeypatch.delenv("CLASSPULSE_STAGING_TEST_USERS", raising=False)
    for key, val in {
        "CLASSPULSE_FRIEND_E2E": "1",
        "CLASSPULSE_FRIEND_INTERNAL": "1",
        "CLASSPULSE_OFFICIAL_BRIDGE": "1",
        "CLASSPULSE_PUBLIC_WEB": "0",
        "CLASSPULSE_LINE_WEB_STAGING": "1",
        "CLASSPULSE_WEB_ORIGIN": "https://example.test",
        "LINE_LOGIN_CHANNEL_ID": "123",
        "LINE_LOGIN_CHANNEL_SECRET": "fake",
        "LINE_CHANNEL_SECRET": SECRET,
        "LINE_CHANNEL_ACCESS_TOKEN": "fake",
    }.items():
        monkeypatch.setenv(key, val)
    replies, forwarded = [], []
    monkeypatch.setattr(demo, "reply_line_message", lambda token, text: replies.append(text))
    def legacy(url, data, headers, **kwargs):
        assert url == bridge.LEGACY_URL
        assert bridge.verify_line_signature(data, headers["X-Line-Signature"], SECRET)
        assert kwargs["allow_redirects"] is False
        forwarded.append(json.loads(data))
        return SimpleNamespace(status_code=200)
    monkeypatch.setattr(bridge.requests, "post", legacy)
    return bridge.create_app().test_client(), replies, forwarded


def event(eid, kind="message", **extra):
    return {"webhookEventId": eid, "type": kind,
            "source": {"type": "user", "userId": SUBJECT},
            "replyToken": "fake", **extra}


def post(client, events, secret=SECRET):
    body, headers = bridge.signed_payload({"destination": "test", "events": events}, secret)
    return client.post("/webhook", data=body, headers=headers)


def users():
    return storage.load_json(storage.data_path("users"))


def test_existing_friend_open_auto_seeds_and_legacy_events_pass_through(setup):
    client, replies, forwarded = setup
    note = event("note", message={"type": "file", "id": "1"})
    bind = event("bind", message={"type": "text", "text": "綁定 test"})
    opening = event("open", message={"type": "text", "text": "開啟網頁"})
    assert post(client, [note, opening, bind]).status_code == 200
    assert forwarded == [{"destination": "test", "events": [note, bind]}]
    assert len(users()) == 1
    assert len(storage.load_json(storage.data_path("events"))) == 14
    assert "/auth/line/start?openExternalBrowser=1" in replies[0]
    assert post(client, [opening]).status_code == 200
    assert len(replies) == 1
    assert post(client, [event("follow", "follow")]).status_code == 200
    assert len(users()) == 1 and len(replies) == 2


def test_invalid_signature_blocks_both_backends(setup):
    client, replies, forwarded = setup
    assert post(client, [event("follow", "follow")], secret="wrong").status_code == 401
    assert not users() and not replies and not forwarded


def test_empty_verify_checks_legacy_and_failure_not_acknowledged(setup, monkeypatch):
    client, replies, forwarded = setup
    assert post(client, []).status_code == 200
    assert forwarded == [{"destination": "test", "events": []}]
    monkeypatch.setattr(bridge.requests, "post", lambda *a, **k: SimpleNamespace(status_code=401))
    assert post(client, []).status_code == 502
    assert not users() and not replies


def test_group_open_stays_on_legacy_path(setup):
    client, replies, forwarded = setup
    message = event("group", message={"type": "text", "text": "開啟網頁"})
    message["source"]["type"] = "group"
    assert post(client, [message]).status_code == 200
    assert forwarded[0]["events"] == [message]
    assert not users() and not replies


def test_personal_note_sync_reads_web_course_and_writes_same_owner(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    def unexpected_ai(*args, **kwargs):
        pytest.fail("note-only sync must not call AI")
    monkeypatch.setattr(line_bot, "organize_class_feedback", unexpected_ai)
    def msg(eid, text):
        return event(eid, message={"type": "text", "text": text})
    assert post(client, [msg("open", "開啟網頁")]).status_code == 200
    uid = users()[0]["user_id"]
    day = (datetime.now(storage.TZ) - timedelta(days=1)).date()
    weekday = day.isoweekday()
    course = {"event_id": "web-test-course", "user_id": uid, "event_type": "class",
              "title": "LINE_E2E_TEST", "weekday": weekday,
              "start_time": "00:00", "end_time": "00:01",
              "enabled": True, "offset_minutes": 0, "prompt_template": "class_feedback"}
    storage.update_json(storage.data_path("events"), lambda rows: rows + [course])
    assert post(client, [msg("start", "補筆記"), msg("weekday", str(weekday))]).status_code == 200
    assert "LINE_E2E_TEST" in replies[-1]
    selected = next(line.split(".")[0] for line in replies[-1].splitlines() if "LINE_E2E_TEST" in line)
    assert post(client, [msg("class", selected), msg("rating", "3"),
                         msg("note", "LINE_E2E_NOTE_MARKER")]).status_code == 200
    matching = [n for n in storage.load_json(storage.data_path("feedback"))
                if n.get("content") == "LINE_E2E_NOTE_MARKER"]
    assert len(matching) == 1 and matching[0]["user_id"] == uid
    assert matching[0]["event_id"] == course["event_id"] and matching[0]["progress"] == 3
    assert forwarded == []
    assert post(client, [msg("note", "LINE_E2E_NOTE_MARKER")]).status_code == 200
    assert forwarded == []
    assert len([n for n in storage.load_json(storage.data_path("feedback"))
                if n.get("content") == "LINE_E2E_NOTE_MARKER"]) == 1
    assert post(client, [msg("search", "搜尋 LINE_E2E_NOTE_MARKER")]).status_code == 200
    assert "LINE_E2E_NOTE_MARKER" in replies[-1]


def test_note_sync_keeps_unregistered_and_legacy_commands_on_legacy_path(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    client, replies, forwarded = setup
    unknown = event("unknown", message={"type": "text", "text": "補筆記"})
    assert post(client, [unknown]).status_code == 200
    assert forwarded[-1]["events"] == [unknown] and not users()
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    for eid, text in [("bind", "綁定 test"), ("complete", "完成"), ("other", "你好")]:
        ev = event(eid, message={"type": "text", "text": text})
        assert post(client, [ev]).status_code == 200
        assert forwarded[-1]["events"] == [ev]


def test_note_sync_default_off_preserves_old_routing(setup, monkeypatch):
    monkeypatch.delenv("CLASSPULSE_FRIEND_NOTE_SYNC", raising=False)
    client, replies, forwarded = setup
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    ev = event("old", message={"type": "text", "text": "補筆記"})
    assert post(client, [ev]).status_code == 200
    assert forwarded[-1]["events"] == [ev]


def test_real_ai_requires_single_note_consent_and_keeps_purple_confirmation(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.setenv("CLASSPULSE_FRIEND_AI_SYNC", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    monkeypatch.setenv("OPENAI_MODEL", "offline-test")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    calls = []
    def analyze(feedback, course):
        calls.append((feedback["content"], course))
        return {"summary": "測試摘要", "key_points": ["根軌跡"],
                "unresolved_questions": ["如何處理零首項？", "如何辨識虛軸根？"],
                "topic_tags": ["根軌跡"], "suggested_task": "複習兩題",
                "estimated_minutes": 60}
    monkeypatch.setattr(line_bot, "organize_class_feedback", analyze)
    def send(eid, text):
        assert post(client, [event(eid, message={"type": "text", "text": text})]).status_code == 200
    send("open-ai", "開啟網頁")
    uid = users()[0]["user_id"]
    now = datetime.now(storage.TZ)
    day = (now - timedelta(days=1)).date()
    course = {"event_id": "ai-web-course", "user_id": uid, "event_type": "class",
              "title": "AI_E2E_TEST", "weekday": day.isoweekday(),
              "start_time": "00:00", "end_time": "00:01",
              "enabled": True, "offset_minutes": 0, "prompt_template": "class_feedback"}
    storage.update_json(storage.data_path("events"), lambda rows: rows + [course])
    def finish_note(prefix, text):
        weekday = next(k for k, v in line_bot.WEEKDAYS.items() if v == day.isoweekday())
        send(prefix+"weekday", weekday)
        selected = next(l.split(".")[0] for l in replies[-1].splitlines() if "AI_E2E_TEST" in l)
        send(prefix+"course", selected)
        send(prefix+"rating", "3")
        send(prefix+"note", text)
    send("no-consent", "同意AI整理")
    assert not calls
    send("ordinary", "補筆記")
    finish_note("ordinary-", "普通測試筆記")
    assert not calls
    send("ai-start", "AI補筆記")
    assert "OpenAI API" in replies[-1]
    send("ai-agree", "同意AI整理")
    before = len(storage.load_json(storage.data_path("tasks")))
    finish_note("real-", "不懂零首項與虛軸根的判斷")
    assert calls == [("不懂零首項與虛軸根的判斷", "AI_E2E_TEST")]
    assert len(storage.load_json(storage.data_path("tasks"))) == before
    notes = storage.load_json(storage.data_path("feedback"))
    note = next(n for n in notes if n.get("content") == calls[0][0])
    assert note["user_id"] == uid and note["ai_analysis"]["summary"] == "測試摘要"
    send("accept-first", "加入讀書任務")
    send("skip-second", "先不用")
    tasks = storage.load_json(storage.data_path("tasks"))
    created = [t for t in tasks if t.get("source_feedback_id") == note["feedback_id"]]
    assert len(tasks) == before + 1 and len(created) == 1
    assert created[0]["user_id"] == uid and created[0]["estimated_minutes"] == 30
    assert created[0]["source"] == "ai_confirmed"
    assert not any(p.get("task_id") == created[0]["task_id"]
                   for p in storage.load_json(storage.data_path("plan")))
    assert users()[0].get("ai_after_class_enabled") is False
    assert forwarded == []
    send("real-note", "不懂零首項與虛軸根的判斷")
    assert len(calls) == 1


def test_ai_command_default_off_does_not_start_paid_flow(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.delenv("CLASSPULSE_FRIEND_AI_SYNC", raising=False)
    import line_bot
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    assert post(client, [event("ai", message={"type": "text", "text": "AI補筆記"})]).status_code == 200
    assert "尚未啟用" in replies[-1]
    assert not storage.load_json(storage.data_path("pending_notes"))
    assert not forwarded
