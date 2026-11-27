"""Step 13: signed Webhook integration without real LINE requests."""
import base64
import hashlib
import hmac
import json

import pytest

import line_bot
import storage

SECRET = "offline-test-secret"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)
    monkeypatch.setenv("LINE_CHANNEL_SECRET", SECRET)
    monkeypatch.setenv("LINE_BINDING_CODE", "test-code")
    monkeypatch.setenv("LINE_FRIEND_DEMO_ENABLED", "1")
    monkeypatch.delenv("LINE_FRIEND_DEMO_SEED_ENABLED", raising=False)
    replies = []
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    app = line_bot.create_app()
    app.testing = True
    return app.test_client(), replies


def event(eid, uid="U_friend_A", kind="follow", source_type="user", **extra):
    return {"webhookEventId": eid, "type": kind,
            "source": {"type": source_type, "userId": uid},
            "replyToken": "fake", **extra}


def post(client, e, signed=True):
    body = json.dumps({"events": [e]}).encode()
    signature = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
    return client.post("/webhook", data=body,
                       headers={"X-Line-Signature": signature if signed else "invalid"},
                       content_type="application/json")


def users():
    return storage.load_json(storage.data_path("users"))


def test_signed_follows_register_independent_pending_users(setup):
    client, replies = setup
    first = event("first")
    assert post(client, first).status_code == 200
    a = users()[0]
    assert post(client, first).status_code == 200
    assert len(replies) == 1
    assert post(client, event("refollow")).status_code == 200
    assert users() == [a]
    assert post(client, event("second", "U_friend_B")).status_code == 200
    assert len(users()) == 2
    assert len({row["user_id"] for row in users()}) == 2
    assert all(row["demo_status"] == "pending_seed" for row in users())
    assert all(not row["reminders_enabled"] and not row["ai_after_class_enabled"]
               for row in users())
    assert len(replies) == 3
    assert all("尚未準備完成" in text for text in replies)
    for name in ("events", "feedback", "tasks"):
        assert storage.load_json(storage.data_path(name)) == []


def test_default_off_preserves_binding_instructions(setup, monkeypatch):
    client, replies = setup
    monkeypatch.delenv("LINE_FRIEND_DEMO_ENABLED")
    assert post(client, event("off")).status_code == 200
    assert users() == []
    assert "綁定" in replies[0]


def test_invalid_signature_never_registers(setup):
    client, replies = setup
    assert post(client, event("bad"), signed=False).status_code == 401
    assert not users()
    assert not replies


@pytest.mark.parametrize("bad_event", [
    event("group", source_type="group"),
    event("room", source_type="room"),
    event("missing", uid=""),
    event("invalid", uid="not-line"),
    event("standby", mode="standby"),
])
def test_nonpersonal_or_invalid_follow_does_not_register(setup, bad_event):
    client, replies = setup
    assert post(client, bad_event).status_code == 200
    assert not users()
    assert not replies


def test_pending_messages_and_binding_are_blocked_even_if_switch_off(setup, monkeypatch):
    client, replies = setup
    assert post(client, event("follow")).status_code == 200
    original = users()
    monkeypatch.delenv("LINE_FRIEND_DEMO_ENABLED")
    def unexpected(*args, **kwargs):
        pytest.fail("pending user must not reach message/file handling")
    monkeypatch.setattr(line_bot, "_handle_text_event", unexpected)
    monkeypatch.setattr(line_bot, "_handle_file_event", unexpected)
    for i, msg in enumerate([{"type": "text", "text": "綁定 test-code"},
                             {"type": "text", "text": "筆記 private"},
                             {"type": "file", "id": "fake"}]):
        assert post(client, event(f"msg{i}", kind="message", message=msg)).status_code == 200
    assert users() == original
    assert all("尚未準備完成" in text for text in replies)
    with pytest.raises(storage.DataError):
        line_bot._bind_demo_user("U_friend_A")
    assert users() == original


def test_legacy_account_refollow_preserves_preferences(setup):
    client, replies = setup
    legacy = {"user_id": "demo_user_001", "line_user_id": "U_friend_A",
              "reminders_enabled": True, "ai_after_class_enabled": True}
    storage.save_json(storage.data_path("users"), [legacy])
    assert post(client, event("legacy")).status_code == 200
    assert users() == [legacy]
    assert "已存在" in replies[0]


def test_storage_failure_does_not_mark_event_processed(setup, monkeypatch):
    client, replies = setup
    def fail(uid):
        raise storage.DataError("offline storage failure")
    monkeypatch.setattr(line_bot, "get_or_create_line_user", fail)
    with pytest.raises(storage.DataError):
        post(client, event("failure"))
    assert storage.load_json(storage.data_path("processed_webhooks")) == []
    assert not replies


def test_opt_in_follow_seeds_only_once_and_still_blocks_messages(setup, monkeypatch):
    client, replies = setup
    monkeypatch.setenv("LINE_FRIEND_DEMO_SEED_ENABLED", "1")
    assert post(client, event("seed")).status_code == 200
    a = users()[0]
    assert a["demo_status"] == "seeded_pending_auth"
    assert "尚待網頁身份驗證" in replies[-1]
    courses = storage.load_json(storage.data_path("events"))
    assert len(courses) == 14
    assert post(client, event("seed")).status_code == 200
    assert post(client, event("seed-again")).status_code == 200
    assert users() == [a]
    assert storage.load_json(storage.data_path("events")) == courses
    monkeypatch.delenv("LINE_FRIEND_DEMO_ENABLED")
    def unexpected(*args, **kwargs):
        pytest.fail("seeded but unauthenticated user must remain gated")
    monkeypatch.setattr(line_bot, "_handle_text_event", unexpected)
    assert post(client, event("note", kind="message",
                              message={"type": "text", "text": "筆記 test"})).status_code == 200
    assert "尚待網頁身份驗證" in replies[-1]


def test_seed_flag_alone_does_not_enable_registration(setup, monkeypatch):
    client, replies = setup
    monkeypatch.delenv("LINE_FRIEND_DEMO_ENABLED")
    monkeypatch.setenv("LINE_FRIEND_DEMO_SEED_ENABLED", "1")
    assert post(client, event("off-seed")).status_code == 200
    assert users() == []
    assert "綁定" in replies[-1]
