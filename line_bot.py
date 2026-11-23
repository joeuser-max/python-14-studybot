import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, request

from storage import load_json, save_json


TZ = ZoneInfo("Asia/Taipei")
DATA_DIR = Path(__file__).resolve().parent / "data"


def verify_line_signature(body: bytes, signature: str, secret: str) -> bool:
    if not body or not signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def resolve_class_slot(
    user_id: str,
    weekday: int,
    start_time: str,
    end_time: str,
    now: datetime,
) -> dict:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    events = load_json(DATA_DIR / "events.json")
    candidates = [
        event for event in events
        if event.get("user_id") == user_id
        and event.get("event_type") == "class"
        and int(event.get("weekday", 0)) == weekday
        and event.get("start_time") == start_time
        and event.get("end_time") == end_time
    ]
    if not candidates:
        return {"status": "none", "options": [], "reason": "找不到已設定的課程時段"}
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "options": [
                {"event_id": event["event_id"], "title": event["title"]}
                for event in candidates
            ],
            "reason": "同一時段有多門課，請選擇課名",
        }

    event = candidates[0]
    end_clock = datetime.strptime(end_time, "%H:%M").time()
    for days_back in range(8):
        date = (now - timedelta(days=days_back)).date()
        if date.isoweekday() != weekday:
            continue
        end_dt = datetime.combine(date, end_clock, tzinfo=TZ)
        if end_dt <= now:
            return {
                "status": "resolved",
                "event_id": event["event_id"],
                "class_date": date.isoformat(),
            }
    return {"status": "none", "options": [], "reason": "找不到最近 7 天內已結束的課次"}


def save_feedback(feedback: dict, path: str | os.PathLike[str] = DATA_DIR / "feedback.json") -> dict:
    try:
        rows = load_json(path)
    except Exception as exc:
        return {"saved": False, "deduplicated": False, "error": str(exc)}

    key = feedback.get("webhook_event_id")
    for row in rows:
        if key and row.get("webhook_event_id") == key:
            return {"saved": False, "deduplicated": True, "error": ""}
        if (
            not key
            and row.get("user_id") == feedback.get("user_id")
            and row.get("event_id") == feedback.get("event_id")
            and row.get("class_date") == feedback.get("class_date")
            and row.get("received_at") == feedback.get("received_at")
        ):
            return {"saved": False, "deduplicated": True, "error": ""}
    rows.append(feedback)
    try:
        save_json(path, rows)
    except Exception as exc:
        return {"saved": False, "deduplicated": False, "error": str(exc)}
    return {"saved": True, "deduplicated": False, "error": ""}


def create_app() -> Flask:
    app = Flask(__name__)
    secret = os.getenv("LINE_CHANNEL_SECRET", "")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook")
    def webhook():
        body = request.get_data(cache=True)
        signature = request.headers.get("X-Line-Signature", "")
        if not verify_line_signature(body, signature, secret):
            abort(401)

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            abort(400)

        processed = load_json(DATA_DIR / "processed_webhooks.json")
        processed_ids = {row.get("webhook_event_id") for row in processed}
        pending = load_json(DATA_DIR / "pending_notes.json")
        now = datetime.now(TZ)

        for event in payload.get("events", []):
            event_id = event.get("webhookEventId") or event.get("webhook_event_id")
            if not event_id:
                continue
            if event_id in processed_ids:
                continue

            source = event.get("source", {})
            user_id = source.get("user_id", "")
            users = load_json(DATA_DIR / "users.json")
            user = next((row for row in users if row.get("line_user_id") == user_id), None)
            if not user:
                continue

            message = event.get("message", {})
            if event.get("type") == "message" and message.get("type") == "text":
                text = message.get("text", "").strip()
                note = next((row for row in pending if row.get("user_id") == user["user_id"]), None)
                if text == "取消" and note:
                    pending = [row for row in pending if row.get("user_id") != user["user_id"]]
                elif text and note:
                    expires = datetime.fromisoformat(note["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=TZ)
                    if expires >= now:
                        feedback = {
                            "feedback_id": f"feedback_{event_id}",
                            "user_id": user["user_id"],
                            "event_id": note["event_id"],
                            "class_date": note["class_date"],
                            "reminder_id": note.get("reminder_id", ""),
                            "received_at": now.isoformat(timespec="seconds"),
                            "content": text,
                            "source": "selected",
                            "webhook_event_id": event_id,
                        }
                        save_feedback(feedback)
                        pending = [row for row in pending if row.get("user_id") != user["user_id"]]
                    else:
                        pending = [row for row in pending if row.get("user_id") != user["user_id"]]

            processed.append({
                "webhook_event_id": event_id,
                "received_at": now.isoformat(timespec="seconds"),
            })
            processed_ids.add(event_id)

        save_json(DATA_DIR / "pending_notes.json", pending)
        save_json(DATA_DIR / "processed_webhooks.json", processed)
        return {"ok": True}

    return app


app = create_app()
