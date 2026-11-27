"""Private signed friend-follow acceptance endpoint, never the legacy webhook."""
import json
import os
import re
from datetime import datetime

from filelock import FileLock
from flask import Flask, abort, request

import storage
from line_bot import verify_line_signature, reply_line_message, _mark_processed
from line_demo_registration import get_or_create_line_user
from line_demo_seed import SEEDED_STATUS, seed_line_user
from line_web_auth import config, install_routes


def create_app():
    origin, _, _ = config()
    allowed = {v.strip() for v in os.getenv("CLASSPULSE_STAGING_TEST_USERS", "").split(",") if v.strip()}
    secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if (os.getenv("CLASSPULSE_FRIEND_E2E") != "1"
            or storage.DATA_DIR != (storage.ROOT / "data" / "friend-e2e").resolve()
            or not allowed or len(allowed) > 5
            or any(not re.fullmatch(r"U[0-9a-f]{32}", v) for v in allowed)
            or not secret or not os.getenv("LINE_CHANNEL_ACCESS_TOKEN")):
        raise ValueError("Private friend E2E configuration incomplete")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    install_routes(app)

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
        for event in events:
            source = event.get("source", {})
            subject = source.get("userId")
            eid = event.get("webhookEventId")
            token = event.get("replyToken")
            if (source.get("type") != "user" or not isinstance(subject, str)
                    or subject not in allowed or event.get("mode") == "standby"
                    or not isinstance(eid, str) or not eid or len(eid) > 128):
                continue
            follow = event.get("type") == "follow"
            message = event.get("message", {})
            recover = (event.get("type") == "message" and message.get("type") == "text"
                       and message.get("text") == "開啟網頁")
            if not follow and not recover:
                continue
            storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with FileLock(str(storage.DATA_DIR / ".friend-e2e.lock"), timeout=15):
                if any(r.get("webhook_event_id") == eid
                       for r in storage.load_json(storage.data_path("processed_webhooks"))):
                    continue
                if follow:
                    user, _ = get_or_create_line_user(subject)
                    seed_line_user(user["user_id"])
                else:
                    users = [r for r in storage.load_json(storage.data_path("users"))
                             if r.get("line_user_id") == subject and r.get("demo_status") == SEEDED_STATUS]
                    if len(users) != 1:
                        continue
                # No user identifiers or tokens in the URL. Login still verifies identity.
                if isinstance(token, str) and token:
                    reply_line_message(token, "你的個人 ClassPulse Demo 已建立。請使用外部瀏覽器開啟：\n" + origin
                                       + "\n目前為私人測試，需輸入測試密碼及 LINE 登入。")
                _mark_processed(eid, datetime.now(storage.TZ))
        return {"ok": True}

    return app
