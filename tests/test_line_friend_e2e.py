import base64
import hashlib
import hmac
import json

import pytest

import storage
import line_friend_e2e as e2e

SUBJECT = "U" + "a" * 32
OTHER = "U" + "b" * 32
SECRET = "test-bot-secret"
ORIGIN = "https://example.test"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data" / "friend-e2e")
    storage.select_demo_storage(False)
    for k, v in {
        "CLASSPULSE_FRIEND_E2E": "1",
        "CLASSPULSE_PUBLIC_WEB": "0",
        "CLASSPULSE_LINE_WEB_STAGING": "1",
        "CLASSPULSE_WEB_ORIGIN": ORIGIN,
        "CLASSPULSE_STAGING_TEST_USERS": SUBJECT,
        "LINE_LOGIN_CHANNEL_ID": "123",
        "LINE_LOGIN_CHANNEL_SECRET": "fake-login-secret",
        "LINE_CHANNEL_SECRET": SECRET,
        "LINE_CHANNEL_ACCESS_TOKEN": "fake-token",
    }.items():
        monkeypatch.setenv(k, v)
    replies = []
    monkeypatch.setattr(e2e, "reply_line_message", lambda token, text: replies.append(text))
    app = e2e.create_app()
    app.testing = True
    return app.test_client(), replies


def event(eid="f1", subject=SUBJECT, kind="follow", source_type="user", **extra):
    return {"type": kind, "webhookEventId": eid, "source": {
        "type": source_type, "userId": subject}, "replyToken": "fake", **extra}


def post(client, events, valid=True):
    body = json.dumps({"events": events}).encode()
    sig = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
    return client.post("/webhook", data=body, headers={"X-Line-Signature": sig if valid else "bad"})


def read(name):
    return storage.load_json(storage.data_path(name))


def test_signed_follow_creates_seed_and_link_once(setup):
    client, replies = setup
    assert post(client, []).status_code == 200
    assert read("users") == []
    assert post(client, [event()]).status_code == 200
    users = read("users")
    courses = read("events")
    assert len(users) == 1 and users[0]["demo_status"] == "seeded_pending_auth"
    assert len(courses) == 14 and all(r["user_id"] == users[0]["user_id"] for r in courses)
    assert ORIGIN in replies[0] and SUBJECT not in replies[0]
    assert post(client, [event()]).status_code == 200
    assert len(replies) == 1
    assert post(client, [event("refollow")]).status_code == 200
    assert read("users") == users and read("events") == courses
    assert len(replies) == 2


def test_wrong_signature_does_not_seed(setup):
    client, replies = setup
    assert post(client, [event()], valid=False).status_code == 401
    assert read("users") == [] and replies == []


def test_non_tester_group_standby_ignored(setup):
    client, replies = setup
    assert post(client, [event("other", OTHER), event("group", source_type="group"),
                         event("standby", mode="standby")]).status_code == 200
    assert read("users") == [] and replies == []


def test_recovery_only_after_follow_and_other_commands_ignored(setup):
    client, replies = setup
    def message(eid, text):
        return event(eid, kind="message", message={"type": "text", "text": text})
    assert post(client, [message("before", "開啟網頁")]).status_code == 200
    assert read("users") == [] and replies == []
    assert post(client, [event(), message("legacy", "綁定 secret"), message("recover", "開啟網頁")]).status_code == 200
    assert len(replies) == 2 and all(ORIGIN in r for r in replies)
    assert read("feedback")  # synthetic seed, no live notes
    assert len(read("users")) == 1


def test_isolation_guard_rejects_other_directory(setup, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    with pytest.raises(ValueError):
        e2e.create_app()


def test_internal_demo_two_seats_and_direct_link(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_INTERNAL", "1")
    monkeypatch.delenv("CLASSPULSE_STAGING_TEST_USERS")
    _, replies = setup
    client = e2e.create_app().test_client()
    third = "U" + "c" * 32
    assert post(client, [event(), event("second", OTHER), event("third", third)]).status_code == 200
    assert {u["line_user_id"] for u in read("users")} == {SUBJECT, OTHER}
    assert len(read("events")) == 28
    assert all(ORIGIN + "/auth/line/start?openExternalBrowser=1" in r for r in replies[:2])
    assert "名額已滿" in replies[2]
    assert post(client, [event("again")]).status_code == 200
    assert len(read("users")) == 2
    assert len(read("events")) == 28
    assert ORIGIN in replies[-1]


def test_internal_mode_rejects_conflicting_allowlist(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_INTERNAL", "1")
    with pytest.raises(ValueError):
        e2e.create_app()
