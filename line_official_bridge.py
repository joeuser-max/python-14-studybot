"""Opt-in official-account bridge for the small internal demo.

Run in a separate process with the ORIGINAL OA credentials, never tester credentials.
The existing Flask at 127.0.0.1:5000 stays untouched.
"""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta

from filelock import FileLock

import requests
from flask import Flask, abort, request

import storage
import line_bot
from ai_assistant import ai_is_configured, ai_provider
from line_web_auth import AuthError, _owner
from line_bot import verify_line_signature
from line_friend_e2e import create_app as create_demo

LEGACY_URL = "http://127.0.0.1:5000/webhook"


def signed_payload(payload, secret):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return body, {"Content-Type": "application/json", "X-Line-Signature": sig}


def is_demo_event(event):
    source = event.get("source", {})
    subject = source.get("userId")
    if (source.get("type") != "user" or not isinstance(subject, str)
            or not re.fullmatch(r"U[0-9a-f]{32}", subject)
            or event.get("mode") == "standby"):
        return False
    message = event.get("message", {})
    return event.get("type") == "follow" or (
        event.get("type") == "message" and message.get("type") == "text"
        and message.get("text") == "開啟網頁")


def handle_personal_note(event):
    """Called only after original OA signature validation and with isolated storage.

    Return True if this event belongs to the personal note flow. Paid AI needs
    an explicit per-note consent and an operator opt-in. No worker sends.
    """
    source = event.get("source", {})
    subject = source.get("userId")
    eid = event.get("webhookEventId")
    if (source.get("type") != "user" or not isinstance(subject, str)
            or not re.fullmatch(r"U[0-9a-f]{32}", subject)
            or event.get("mode") == "standby" or event.get("type") != "message"
            or not isinstance(eid, str) or not eid or len(eid) > 128):
        return False
    message = event.get("message", {})
    kind = message.get("type")
    if kind not in ("text", "file"):
        return False
    text = message.get("text", "")
    text = text.strip() if isinstance(text, str) else ""
    now = datetime.now(storage.TZ)
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(storage.DATA_DIR / ".friend-e2e.lock"), timeout=15):
        # A previously handled note reply must not fall through after pending
        # state was cleared; webhook IDs are global to the isolated demo store.
        if any(r.get("webhook_event_id") == eid
               for r in storage.load_json(storage.data_path("processed_webhooks"))):
            return True
        try:
            uid = _owner(subject)
        except AuthError:
            return False
        users = storage.load_json(storage.data_path("users"))
        user = next((u for u in users if u.get("user_id") == uid
                     and u.get("line_user_id") == subject), None)
        if user is None:
            return False
        if kind == "text" and os.getenv("CLASSPULSE_FRIEND_PROGRESS_SYNC") == "1":
            from line_personal_progress import handle_progress
            result = handle_progress(event, user, now)
            if result is not None:
                line_bot._mark_processed(eid, now)
                return True
        pending = line_bot._pending_for(uid, now)
        command = (text in ("補筆記", "查看筆記", "我的筆記", "AI補筆記", "同意AI整理")
                   or text.startswith(("筆記 ", "搜尋 ")))
        # Keep legacy binding and explicit progress commands on the existing path.
        if text.startswith("綁定 ") or text == "完成" or text == "未完成" or text.startswith(("完成 ", "未完成 ")):
            return False
        if not (kind == "file" or command or pending):
            return False
        ai_ready = (os.getenv("CLASSPULSE_FRIEND_AI_SYNC") == "1" and ai_is_configured())
        provider = ai_provider() if ai_ready else ""
        token = event.get("replyToken", "")
        if kind == "text" and text == "AI補筆記":
            if ai_ready:
                line_bot._set_pending({
                    "user_id": uid, "stage": "friend_ai_consent", "friend_ai_provider": provider,
                    "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
                })
                line_bot.reply_line_message(token,
                    ("本次課名、筆記文字及自評進度將傳送至 Google Gemini API 整理。"
                     "免費方案資料可能被用於改善產品；可能依帳戶設定產生費用。"
                     if provider == "gemini" else
                     "本次課名、筆記文字及自評進度將傳送至 OpenAI API 整理，可能產生費用。") +
                    "不會傳送 LINE ID 或整份 PDF 原檔。只使用虛構測試筆記。"
                    "同意請回覆「同意AI整理」，不同意請回覆「取消」。",
                    ["同意AI整理", "取消"])
            else:
                line_bot.reply_line_message(token, "真實 AI 尚未啟用，仍可使用「補筆記」。")
            line_bot._mark_processed(eid, now)
            return True
        if kind == "text" and text == "同意AI整理":
            if (ai_ready and pending and pending.get("stage") == "friend_ai_consent"
                    and pending.get("friend_ai_provider") == provider):
                line_bot._set_pending({
                    "user_id": uid, "stage": "weekday", "friend_ai_consent": True,
                    "friend_ai_provider": provider,
                    "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
                })
                line_bot.reply_line_message(token, "本次 AI 筆記已同意。請選擇星期。",
                                            line_bot.WEEKDAY_CHOICES)
            else:
                line_bot.reply_line_message(token, "請先輸入「AI補筆記」並閱讀同意說明。")
            line_bot._mark_processed(eid, now)
            return True
        if pending and pending.get("stage") == "friend_ai_consent" and text not in ("取消", "補筆記"):
            line_bot.reply_line_message(token, "請先回覆「同意AI整理」或「取消」。")
            line_bot._mark_processed(eid, now)
            return True
        # Consent applies to this guided note only. No permanent setting change,
        # no worker consent, no API request for ordinary/quick notes.
        user = dict(user, ai_after_class_enabled=bool(
            ai_ready and pending and pending.get("friend_ai_consent") is True
            and pending.get("stage") == "note"
            and pending.get("friend_ai_provider") == provider
        ), _personal_question_only=True, _personal_note_only=True)
        if kind == "file":
            ok = line_bot._handle_file_event(event, user, now)
        else:
            ok = line_bot._handle_text_event(event, user, now)
        if ok is not False:
            line_bot._mark_processed(eid, now)
        else:
            # Handler reports retryable storage failure; do not silently forward.
            raise storage.DataError("Personal note event not completed")
        return True


def create_app():
    if os.getenv("CLASSPULSE_OFFICIAL_BRIDGE") != "1" or os.getenv("CLASSPULSE_FRIEND_INTERNAL") != "1":
        raise ValueError("Official bridge requires explicit internal-mode opt-in")
    secret = os.environ["LINE_CHANNEL_SECRET"]
    demo = create_demo(register_on_open=True)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook")
    def webhook():
        body = request.get_data(cache=True)
        if not verify_line_signature(body, request.headers.get("X-Line-Signature", ""), secret):
            abort(401)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError):
            abort(400)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            abort(400)
        events = payload["events"]
        if len(events) > 100 or any(not isinstance(e, dict)
                                  or not isinstance(e.get("source", {}), dict)
                                  or not isinstance(e.get("message", {}), dict)
                                  for e in events):
            abort(400)
        if os.getenv("CLASSPULSE_FRIEND_NOTE_SYNC") == "1" and events:
            # Preserve event order for stateful conversations, including
            # multiple messages in one signed webhook. Never send one event
            # to both the personal and legacy stores.
            for event in events:
                if is_demo_event(event):
                    forwarded, headers = signed_payload(dict(payload, events=[event]), secret)
                    with demo.test_client() as client:
                        response = client.post("/webhook", data=forwarded, headers=headers)
                    if response.status_code != 200:
                        abort(502)
                elif not handle_personal_note(event):
                    forwarded, headers = signed_payload(dict(payload, events=[event]), secret)
                    try:
                        response = requests.post(LEGACY_URL, data=forwarded, headers=headers,
                                                 timeout=(2, 90), allow_redirects=False)
                    except requests.RequestException:
                        abort(502)
                    if response.status_code != 200:
                        abort(502)
            return {"ok": True}

        legacy_events = [e for e in events if not is_demo_event(e)]
        demo_events = [e for e in events if is_demo_event(e)]
        # Forward all ordinary events without altering their contents; re-sign the
        # subset because the original signature covers the entire incoming body.
        # Empty LINE Verify requests also check the actual legacy backend.
        if legacy_events or not events:
            forwarded, headers = signed_payload(dict(payload, events=legacy_events), secret)
            try:
                response = requests.post(LEGACY_URL, data=forwarded, headers=headers,
                                         timeout=(2, 90), allow_redirects=False)
            except requests.RequestException:
                abort(502)
            if response.status_code != 200:
                abort(502)
        if demo_events:
            forwarded, headers = signed_payload(dict(payload, events=demo_events), secret)
            # Internal Flask dispatch, not an external HTTP request.
            with demo.test_client() as client:
                response = client.post("/webhook", data=forwarded, headers=headers)
            if response.status_code != 200:
                abort(502)
        return {"ok": True}

    return app
