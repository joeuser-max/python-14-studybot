"""Offline LINE Login contract; fake endpoints, temporary storage, no live credentials."""
from urllib.parse import parse_qs, urlsplit
import hashlib
import base64

import pytest
from flask import Flask

import storage
import line_web_auth as auth
from line_demo_registration import get_or_create_line_user
from line_demo_seed import seed_line_user

ORIGIN = "https://classpulse.test"
NOW = 1800000000
A = "U" + "a" * 32
B = "U" + "b" * 32


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)
    monkeypatch.setenv("CLASSPULSE_LINE_WEB_STAGING", "1")
    monkeypatch.delenv("CLASSPULSE_PUBLIC_WEB", raising=False)
    monkeypatch.setenv("CLASSPULSE_WEB_ORIGIN", ORIGIN)
    monkeypatch.setenv("LINE_LOGIN_CHANNEL_ID", "1234567890")
    monkeypatch.setenv("LINE_LOGIN_CHANNEL_SECRET", "fake-secret")
    monkeypatch.setattr(auth, "_now", lambda: NOW)
    ids = {}
    for subject in (A, B):
        uid = get_or_create_line_user(subject)[0]["user_id"]
        seed_line_user(uid)
        ids[subject] = uid
    app = Flask(__name__)
    auth.install_routes(app)
    return app, ids


def start(client):
    response = client.get("/auth/line/start", base_url=ORIGIN)
    assert response.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlsplit(response.location).query).items()}


def callback(client, state):
    return client.get("/auth/line/callback", query_string={"state": state, "code": "fake-code",
                      "user_id": "attacker-chosen"}, base_url=ORIGIN)


def mock_line(monkeypatch, params, subject=A, **override):
    calls = []
    def post(url, data):
        calls.append((url, dict(data)))
        if url == auth.TOKEN:
            return {"id_token": "fake-id-token"}
        assert url == auth.VERIFY
        return {"iss": auth.ISSUER, "sub": subject, "aud": "1234567890",
                "nonce": params["nonce"], "exp": NOW + 7200, **override}
    monkeypatch.setattr(auth, "_post", post)
    return calls


def session_cookie(client):
    return client.get_cookie(auth.SESSION_COOKIE, domain="classpulse.test").value


def test_login_uses_pkce_verifies_nonce_and_maps_only_verified_subject(setup, monkeypatch):
    app, ids = setup
    client = app.test_client()
    params = start(client)
    assert params["scope"] == "openid"
    assert params["code_challenge_method"] == "S256"
    calls = mock_line(monkeypatch, params)
    result = callback(client, params["state"])
    assert result.status_code == 302 and result.location == "/"
    cookie_header = next(h for h in result.headers.getlist("Set-Cookie") if h.startswith(auth.SESSION_COOKIE))
    assert "Secure" in cookie_header and "HttpOnly" in cookie_header and "SameSite=Lax" in cookie_header
    assert "Domain=" not in cookie_header
    assert calls[1][1]["nonce"] == params["nonce"]
    verifier = calls[0][1]["code_verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == params["code_challenge"]
    raw = session_cookie(client)
    assert auth.resolve_session(raw) == ids[A]
    assert raw not in str(storage.load_json(storage.data_path("web_auth")))
    assert callback(client, params["state"]).status_code == 401
    assert len(calls) == 2


def test_two_browsers_cannot_swap_state_or_owner(setup, monkeypatch):
    app, ids = setup
    first, second = app.test_client(), app.test_client()
    a, b = start(first), start(second)
    calls = mock_line(monkeypatch, a)
    assert callback(second, a["state"]).status_code == 401
    assert calls == []
    assert callback(first, a["state"]).status_code == 302
    b = start(second)
    mock_line(monkeypatch, b, B)
    assert callback(second, b["state"]).status_code == 302
    assert auth.resolve_session(session_cookie(first)) == ids[A]
    assert auth.resolve_session(session_cookie(second)) == ids[B]


@pytest.mark.parametrize("override", [
    {"nonce": "wrong"}, {"aud": "999"}, {"iss": "https://wrong.test"},
    {"exp": NOW}, {"sub": "invalid"}, {"sub": "U" + "c" * 32},
])
def test_wrong_claims_and_unknown_user_fail_closed(setup, monkeypatch, override):
    app, _ = setup
    client = app.test_client()
    params = start(client)
    mock_line(monkeypatch, params, **override)
    assert callback(client, params["state"]).status_code == 401
    assert client.get_cookie(auth.SESSION_COOKIE, domain="classpulse.test") is None


def test_expired_and_revoked_session_cannot_resolve(setup, monkeypatch):
    _, ids = setup
    raw, ttl = auth.create_session(A, NOW + 60)
    assert ttl == 60 and auth.resolve_session(raw) == ids[A]
    auth.revoke_session(raw)
    with pytest.raises(auth.AuthError):
        auth.resolve_session(raw)
    raw, _ = auth.create_session(A, NOW + 60)
    monkeypatch.setattr(auth, "_now", lambda: NOW + 60)
    with pytest.raises(auth.AuthError):
        auth.resolve_session(raw)


def test_expired_login_state_cannot_exchange_code(setup, monkeypatch):
    app, _ = setup
    client = app.test_client()
    params = start(client)
    calls = mock_line(monkeypatch, params)
    monkeypatch.setattr(auth, "_now", lambda: NOW + auth.STATE_TTL)
    assert callback(client, params["state"]).status_code == 401
    assert not calls


def test_duplicate_identity_and_pending_user_cannot_login(setup):
    _, ids = setup
    path = storage.data_path("users")
    storage.update_json(path, lambda rows: rows + [
        {"line_user_id": A, "user_id": "lineuser_123456789abc"}])
    with pytest.raises(auth.AuthError):
        auth.create_session(A, NOW + 100)
    storage.update_json(path, lambda rows: [
        {**r, "demo_status": "pending_seed"} if r.get("user_id") == ids[B] else r for r in rows])
    with pytest.raises(auth.AuthError):
        auth.create_session(B, NOW + 100)


def test_default_off_and_public_flag_disable_routes(setup, monkeypatch):
    app, _ = setup
    client = app.test_client()
    monkeypatch.delenv("CLASSPULSE_LINE_WEB_STAGING")
    assert client.get("/auth/line/start", base_url=ORIGIN).status_code == 404
    monkeypatch.setenv("CLASSPULSE_LINE_WEB_STAGING", "1")
    monkeypatch.setenv("CLASSPULSE_PUBLIC_WEB", "1")
    assert client.get("/auth/line/start", base_url=ORIGIN).status_code == 404


def test_forged_cookie_and_changed_mapping_rejected(setup):
    _, ids = setup
    with pytest.raises(auth.AuthError):
        auth.resolve_session("x" * 43)
    raw, _ = auth.create_session(A, NOW + 100)
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "line_user_id": "U" + "d" * 32} if r["user_id"] == ids[A] else r for r in rows])
    with pytest.raises(auth.AuthError):
        auth.resolve_session(raw)


def test_http_origin_or_wrong_host_refused(setup, monkeypatch):
    app, _ = setup
    client = app.test_client()
    assert client.get("/auth/line/start", base_url="https://evil.test").status_code == 401
    monkeypatch.setenv("CLASSPULSE_WEB_ORIGIN", "http://classpulse.test")
    assert client.get("/auth/line/start", base_url=ORIGIN).status_code == 401


def test_flask_webhook_app_mounts_login_routes_default_off(setup, monkeypatch):
    import line_bot
    monkeypatch.delenv("CLASSPULSE_LINE_WEB_STAGING")
    app = line_bot.create_app()
    client = app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/auth/line/start", base_url=ORIGIN).status_code == 404
    assert client.get("/auth/line/callback", base_url=ORIGIN).status_code == 404


def test_staging_allowlist_revokes_access_for_removed_account(setup, monkeypatch):
    _, ids = setup
    monkeypatch.setenv("CLASSPULSE_STAGING_TEST_USERS", A + "," + B)
    raw, _ = auth.create_session(A, NOW + 100)
    assert auth.resolve_session(raw) == ids[A]
    monkeypatch.setenv("CLASSPULSE_STAGING_TEST_USERS", B)
    with pytest.raises(auth.AuthError):
        auth.resolve_session(raw)
    with pytest.raises(auth.AuthError):
        auth.create_session(A, NOW + 100)


def test_internal_direct_entry_reuses_valid_session(setup, monkeypatch):
    app, ids = setup
    monkeypatch.setenv("CLASSPULSE_FRIEND_INTERNAL", "1")
    monkeypatch.delenv("CLASSPULSE_STAGING_TEST_USERS", raising=False)
    client = app.test_client()
    params = start(client)
    mock_line(monkeypatch, params)
    assert callback(client, params["state"]).status_code == 302
    raw = session_cookie(client)
    response = client.get("/auth/line/start?openExternalBrowser=1", base_url=ORIGIN)
    assert response.status_code == 302 and response.location == "/"
    assert session_cookie(client) == raw
    assert auth.resolve_session(raw) == ids[A]
    auth.revoke_session(raw)
    assert start(client)["state"]
