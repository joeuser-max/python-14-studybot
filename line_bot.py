"""LINE webhook and guided note collection for the ClassPulse single-user MVP.

All notes are stored through storage.save_feedback (atomic validation and dedupe).
Real LINE delivery requires valid Messaging API credentials.
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, abort, request

from storage import (
    DataError, data_path, load_json, save_feedback as persist_feedback, update_json,
)

TZ = ZoneInfo("Asia/Taipei")
WEEKDAYS = ("", "一", "二", "三", "四", "五", "六", "日")
NOTE_TIMEOUT = timedelta(minutes=10)


def verify_line_signature(body: bytes, signature: str, secret: str) -> bool:
    if not body or not signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def resolve_class_slot(user_id: str, weekday: int, start_time: str,
                       end_time: str, now: datetime) -> dict:
    """Resolve the most recent completed matching class, at most seven days old."""
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    events = load_json(data_path("events"))
    candidates = [
        event for event in events
        if event.get("user_id") == user_id
        and event.get("event_type") == "class"
        and event.get("weekday") == weekday
        and event.get("start_time") == start_time
        and event.get("end_time") == end_time
    ]
    if not candidates:
        return {"status": "none", "options": [], "reason": "找不到已設定的課程時段"}
    last_date = None
    end_clock = datetime.strptime(end_time, "%H:%M").time()
    for days_back in range(8):
        day = (now - timedelta(days=days_back)).date()
        if day.isoweekday() != weekday:
            continue
        if datetime.combine(day, end_clock, tzinfo=TZ) <= now:
            last_date = day.isoformat()
            break
    if last_date is None:
        return {"status": "none", "options": [], "reason": "找不到最近 7 天內已結束的課次"}
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "options": [{"event_id": x["event_id"], "title": x["title"]} for x in candidates],
            "class_date": last_date,
            "reason": "同一時段有多門課，請選擇課名",
        }
    return {"status": "resolved", "event_id": candidates[0]["event_id"],
            "class_date": last_date}


def save_feedback(feedback: dict, path=None) -> dict:
    """Compatibility wrapper for callers of the original LINE module."""
    try:
        added = persist_feedback(feedback, path or data_path("feedback"))
        return {"saved": added, "deduplicated": not added, "error": ""}
    except (DataError, ValueError) as exc:
        return {"saved": False, "deduplicated": False, "error": str(exc)}


def _set_pending(user_id: str, state: dict | None) -> None:
    path = data_path("pending_notes")
    def change(items):
        other = [row for row in items if row.get("user_id") != user_id]
        return other + ([{"user_id": user_id, **state}] if state else [])
    update_json(path, change)


def _pending_for(user_id: str, now: datetime) -> dict | None:
    rows = load_json(data_path("pending_notes"))
    row = next((item for item in rows if item.get("user_id") == user_id), None)
    if row is not None:
        try:
            expiration = datetime.fromisoformat(row["expires_at"])
            if expiration.tzinfo is None or expiration < now:
                _set_pending(user_id, None)
                return None
        except (KeyError, ValueError, TypeError):
            _set_pending(user_id, None)
            return None
    return row


def _state(stage: str, now: datetime, **kwargs) -> dict:
    return {"stage": stage, "expires_at": (now + NOTE_TIMEOUT).isoformat(timespec="seconds"),
            **kwargs}


def _choices(items: list[str]) -> str:
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def _number(text: str, length: int) -> int | None:
    try:
        selected = int(text)
    except ValueError:
        return None
    return selected - 1 if 1 <= selected <= length else None


def _sent_reminder_id(user_id: str, event_id: str, class_date: str) -> str:
    for row in load_json(data_path("reminders")):
        if (row.get("kind") == "class_feedback" and row.get("status") == "sent"
                and row.get("user_id") == user_id and row.get("event_id") == event_id
                and row.get("class_date") == class_date):
            return row.get("reminder_id", "")
    return ""


def handle_line_text(user: dict, text: str, event_id: str, now: datetime) -> str:
    """Text-only guided flow: 補筆記 → weekday → time slot → optional class → note."""
    user_id = user["user_id"]
    if text == "取消":
        _set_pending(user_id, None)
        return "已取消補筆記。輸入「補筆記」可重新開始。"

    events = [event for event in load_json(data_path("events"))
              if event.get("user_id") == user_id and event.get("event_type") == "class"]
    if text == "補筆記":
        if not events:
            return "尚未設定課程。請先在 ClassPulse 的 Streamlit 頁面建立課表。"
        weekdays = sorted({event["weekday"] for event in events})
        _set_pending(user_id, _state("weekday", now, weekdays=weekdays))
        return ("請選星期（輸入選項數字）：\n" +
                _choices([f"週{WEEKDAYS[day]}" for day in weekdays]) + "\n輸入「取消」可離開。")

    pending = _pending_for(user_id, now)
    if not pending:
        return "輸入「補筆記」開始補登課程筆記；輸入「取消」可停止。"

    stage = pending["stage"]
    if stage == "weekday":
        days = pending["weekdays"]
        index = _number(text, len(days))
        if index is None:
            return "請輸入星期選項的數字。\n" + _choices([f"週{WEEKDAYS[d]}" for d in days])
        weekday = days[index]
        slots = sorted({(e["start_time"], e["end_time"]) for e in events
                        if e["weekday"] == weekday})
        _set_pending(user_id, _state("slot", now, weekday=weekday,
                                     slots=[list(s) for s in slots]))
        return ("請選課表時段：\n" +
                _choices([f"{s}–{e}" for s, e in slots]))

    if stage == "slot":
        slots = pending["slots"]
        index = _number(text, len(slots))
        if index is None:
            return "請輸入時段選項的數字。\n" + _choices([f"{s}–{e}" for s, e in slots])
        start, end = slots[index]
        resolved = resolve_class_slot(user_id, pending["weekday"], start, end, now)
        if resolved["status"] == "none":
            _set_pending(user_id, None)
            return resolved["reason"] + "。請稍後重新選擇。"
        if resolved["status"] == "ambiguous":
            options = resolved["options"]
            _set_pending(user_id, _state("class", now, options=options,
                                         class_date=resolved["class_date"]))
            return "同一時段有多門課，請選課名：\n" + _choices([e["title"] for e in options])
        _set_pending(user_id, _state("note", now, event_id=resolved["event_id"],
                                     class_date=resolved["class_date"]))
        return f"已選擇 {resolved['class_date']} 的課程。請直接輸入筆記（10 分鐘內）。"

    if stage == "class":
        options = pending["options"]
        index = _number(text, len(options))
        if index is None:
            return "請輸入課名選項的數字。\n" + _choices([e["title"] for e in options])
        chosen = options[index]
        _set_pending(user_id, _state("note", now, event_id=chosen["event_id"],
                                     class_date=pending["class_date"]))
        return f"已選擇 {chosen['title']}。請直接輸入筆記（10 分鐘內）。"

    if stage == "note":
        reminder_id = _sent_reminder_id(user_id, pending["event_id"], pending["class_date"])
        feedback = {
            "feedback_id": f"feedback_{event_id}", "user_id": user_id,
            "event_id": pending["event_id"], "class_date": pending["class_date"],
            "reminder_id": reminder_id, "received_at": now.isoformat(timespec="seconds"),
            "content": text, "source": "selected", "webhook_event_id": event_id,
        }
        result = save_feedback(feedback)
        if result["error"]:
            return "筆記未儲存：" + result["error"] + "。請重新輸入。"
        _set_pending(user_id, None)
        return "筆記已儲存。" if result["saved"] else "這則筆記已記錄，未重複儲存。"

    _set_pending(user_id, None)
    return "操作狀態已重設。請重新輸入「補筆記」。"


def _bind_line_user(line_user_id: str, text: str) -> str:
    """One-time binding with an operator-set code, never accept an arbitrary user ID."""
    secret = os.getenv("LINE_BIND_CODE", "")
    supplied = text.partition(" ")[2].strip()
    if not secret:
        return "管理員尚未設定 LINE_BIND_CODE，無法綁定。"
    if not hmac.compare_digest(supplied, secret):
        return "綁定碼不正確。"
    def change(users):
        current = next((u for u in users if u.get("user_id") == "demo_user_001"), None)
        if current and current.get("line_user_id") not in ("", line_user_id, None):
            raise DataError("示範帳號已綁定另一個 LINE 使用者")
        if current:
            return [{**u, "line_user_id": line_user_id} if u is current else u for u in users]
        return users + [{"user_id": "demo_user_001", "line_user_id": line_user_id,
                         "reminders_enabled": True, "study_reminders_enabled": True}]
    try:
        update_json(data_path("users"), change)
    except DataError as exc:
        return str(exc)
    return "LINE 帳號綁定成功。輸入「補筆記」即可開始。"


def _reply_line(reply_token: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or not reply_token:
        print("[LINE 模擬回覆]", text)
        return
    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]},
        timeout=10,
    )
    response.raise_for_status()


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook")
    def webhook():
        body = request.get_data(cache=True)
        signature = request.headers.get("X-Line-Signature", "")
        if not verify_line_signature(body, signature, os.getenv("LINE_CHANNEL_SECRET", "")):
            abort(401)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            abort(400)
        if not isinstance(payload, dict) or not isinstance(payload.get("events", []), list):
            abort(400)

        for event in payload.get("events", []):
            event_id = event.get("webhookEventId")
            if not event_id:
                continue
            if any(x.get("webhook_event_id") == event_id
                   for x in load_json(data_path("processed_webhooks"))):
                continue

            source = event.get("source") or {}
            line_user_id = source.get("userId", "")  # LINE uses userId, not user_id
            message = event.get("message") or {}
            if not line_user_id or event.get("type") != "message" or message.get("type") != "text":
                continue
            text = message.get("text", "").strip()
            user = next((u for u in load_json(data_path("users"))
                         if u.get("line_user_id") == line_user_id), None)
            now = datetime.now(TZ)
            if user:
                reply = handle_line_text(user, text, event_id, now)
            elif text.startswith("綁定 "):
                reply = _bind_line_user(line_user_id, text)
            else:
                reply = "尚未綁定 LINE。請向專案管理員索取一次性綁定碼並輸入「綁定 <綁定碼>」。"
            # Processing state is persisted before marking the event complete.
            _reply_line(event.get("replyToken", ""), reply)
            update_json(
                data_path("processed_webhooks"),
                lambda rows: rows if any(x.get("webhook_event_id") == event_id for x in rows)
                else rows + [{"webhook_event_id": event_id, "received_at": now.isoformat(timespec="seconds")}],
            )
        return {"ok": True}

    return app


app = create_app()
