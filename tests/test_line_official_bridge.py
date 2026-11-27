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
