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

import requests
from flask import Flask, abort, request

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
