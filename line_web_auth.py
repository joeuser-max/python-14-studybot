"""Private LINE Login staging. No client-provided user_id or decoded JWT is trusted."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import requests
from flask import abort, make_response, redirect, request

from storage import DataError, data_path, load_json, update_json, is_demo_storage
from line_demo_seed import SEEDED_STATUS, SEED_VERSION

AUTHORIZE = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN = "https://api.line.me/oauth2/v2.1/token"
VERIFY = "https://api.line.me/oauth2/v2.1/verify"
ISSUER = "https://access.line.me"
LOGIN_COOKIE = "__Host-classpulse_login"
SESSION_COOKIE = "__Host-classpulse_session"
STATE_TTL = 600
SESSION_TTL = 3600


class AuthError(ValueError):
    pass


def staging_enabled():
    return (os.getenv("CLASSPULSE_LINE_WEB_STAGING") == "1"
            and os.getenv("CLASSPULSE_PUBLIC_WEB") != "1")


def config():
    origin = os.getenv("CLASSPULSE_WEB_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    channel = os.getenv("LINE_LOGIN_CHANNEL_ID", "")
    secret = os.getenv("LINE_LOGIN_CHANNEL_SECRET", "")
    if (not staging_enabled() or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.path or parsed.query
            or parsed.fragment or not re.fullmatch(r"[0-9]+", channel) or not secret):
        raise AuthError("LINE Login 尚未安全設定")
    return origin, channel, secret


def _now():
    return int(time.time())


def _new():
    return secrets.token_urlsafe(32)


def _valid(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is not None


def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _store():
    if is_demo_storage():
        raise AuthError("禁止在共用展示目錄建立登入狀態")
    return data_path("web_auth")


def _live(rows, now):
    return [r for r in rows if type(r.get("expires_at")) is int and r["expires_at"] > now]


def begin_login():
    origin, channel, _ = config()
    browser, state, nonce, verifier = (_new() for _ in range(4))
    now = _now()
    entry = {"kind": "login", "browser_hash": _digest(browser),
             "state_hash": _digest(state), "nonce": nonce, "verifier": verifier,
             "expires_at": now + STATE_TTL}
    update_json(_store(), lambda rows: _live(rows, now) + [entry])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    url = AUTHORIZE + "?" + urlencode({
        "response_type": "code", "client_id": channel,
        "redirect_uri": origin + "/auth/line/callback",
        "state": state, "nonce": nonce, "scope": "openid",
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return browser, url


def consume_login(browser, state):
    if not _valid(browser) or not _valid(state):
        raise AuthError("登入驗證失敗")
    result = []
    now = _now()
    def consume(rows):
        remaining = []
        for row in _live(rows, now):
            if (row.get("kind") == "login" and row.get("browser_hash") == _digest(browser)
                    and row.get("state_hash") == _digest(state)):
                result.append(row)
            else:
                remaining.append(row)
        return remaining
    update_json(_store(), consume)
    if len(result) != 1:
        raise AuthError("登入驗證失敗")
    return result[0]


def _post(url, data):
    try:
        response = requests.post(url, data=data, timeout=10, allow_redirects=False)
        if response.status_code != 200:
            raise AuthError("LINE 身份驗證失敗")
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise AuthError("LINE 身份驗證失敗") from exc
    if not isinstance(result, dict):
        raise AuthError("LINE 身份驗證失敗")
    return result


def verified_subject(code, attempt):
    origin, channel, secret = config()
    if not isinstance(code, str) or not 1 <= len(code) <= 2048:
        raise AuthError("登入授權碼無效")
    response = _post(TOKEN, {"grant_type": "authorization_code", "code": code,
                            "redirect_uri": origin + "/auth/line/callback",
                            "client_id": channel, "client_secret": secret,
                            "code_verifier": attempt["verifier"]})
    token = response.get("id_token")
    if not isinstance(token, str) or not token:
        raise AuthError("LINE 未提供身份憑證")
    claims = _post(VERIFY, {"id_token": token, "client_id": channel,
                            "nonce": attempt["nonce"]})
    subject, expiry = claims.get("sub"), claims.get("exp")
    nonce = claims.get("nonce")
    if (claims.get("iss") != ISSUER or claims.get("aud") != channel
            or not isinstance(nonce, str) or not hmac.compare_digest(nonce, attempt["nonce"])
            or type(expiry) is not int or expiry <= _now()
            or not isinstance(subject, str) or not re.fullmatch(r"U[0-9a-f]{32}", subject)):
        raise AuthError("LINE 身份驗證失敗")
    return subject, expiry


def _owner(subject):
    if is_demo_storage():
        raise AuthError("無效的登入資料範圍")
    allowlist = os.getenv("CLASSPULSE_STAGING_TEST_USERS")
    if allowlist is not None and subject not in {s.strip() for s in allowlist.split(",") if s.strip()}:
        raise AuthError("此帳號不在私人驗收名單中")
    rows = load_json(data_path("users"))
    matches = [r for r in rows if r.get("line_user_id") == subject]
    if len(matches) != 1:
        raise AuthError("請先加入 ClassPulse 好友並完成個人資料初始化")
    user = matches[0]
    uid = user.get("user_id")
    if (not isinstance(uid, str) or not re.fullmatch(r"lineuser_[0-9a-f]{12}", uid)
            or sum(r.get("user_id") == uid for r in rows) != 1
            or user.get("demo_status") != SEEDED_STATUS
            or user.get("demo_seed_version") != SEED_VERSION):
        raise AuthError("個人 Demo 尚未開放登入")
    return uid


def create_session(subject, token_expiry):
    config()
    uid = _owner(subject)
    now = _now()
    expires = min(now + SESSION_TTL, token_expiry)
    if expires <= now:
        raise AuthError("登入已過期")
    raw = _new()
    entry = {"kind": "session", "session_hash": _digest(raw), "user_id": uid,
             "line_user_id": subject, "expires_at": expires}
    update_json(_store(), lambda rows: _live(rows, now) + [entry])
    return raw, expires - now


def resolve_session(raw):
    """Resolve server-side identity on every Streamlit run, never from URL/widgets."""
    config()
    if not _valid(raw):
        raise AuthError("請先登入 LINE")
    matches = [r for r in _live(load_json(_store()), _now())
               if r.get("kind") == "session" and r.get("session_hash") == _digest(raw)]
    if len(matches) != 1:
        raise AuthError("登入已失效")
    row = matches[0]
    if _owner(row["line_user_id"]) != row.get("user_id"):
        raise AuthError("登入已失效")
    return row["user_id"]


def revoke_session(raw):
    if _valid(raw):
        update_json(_store(), lambda rows: [
            r for r in _live(rows, _now())
            if not (r.get("kind") == "session" and r.get("session_hash") == _digest(raw))])


def install_routes(app):
    def guard():
        if not staging_enabled():
            abort(404)
        origin, _, _ = config()
        # Step 17 must preserve Host and terminate TLS at the trusted proxy.
        if request.host.lower() != urlsplit(origin).netloc.lower():
            raise AuthError("無效的登入入口")

    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def failed():
        response = make_response("LINE 登入未完成，請回到 ClassPulse 重新登入。", 401)
        response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="Lax")
        return headers(response)

    @app.get("/auth/line/start")
    def line_login_start():
        try:
            guard()
            browser, url = begin_login()
        except (AuthError, DataError):
            return failed()
        response = redirect(url)
        response.set_cookie(LOGIN_COOKIE, browser, max_age=STATE_TTL, secure=True,
                            httponly=True, samesite="Lax", path="/")
        return headers(response)

    @app.get("/auth/line/callback")
    def line_login_callback():
        try:
            guard()
            if len(request.args.getlist("state")) != 1 or len(request.args.getlist("code")) != 1:
                raise AuthError("登入驗證失敗")
            attempt = consume_login(request.cookies.get(LOGIN_COOKIE), request.args.get("state"))
            subject, expiry = verified_subject(request.args.get("code"), attempt)
            raw, max_age = create_session(subject, expiry)
            revoke_session(request.cookies.get(SESSION_COOKIE))
        except (AuthError, DataError):
            return failed()
        response = redirect("/")
        response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="Lax")
        response.set_cookie(SESSION_COOKIE, raw, max_age=max_age, secure=True,
                            httponly=True, samesite="Lax", path="/")
        return headers(response)
