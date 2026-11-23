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
    DataError,
    create_id,
    data_path,
    load_json,
    save_feedback as storage_save_feedback,
    update_json,
)


TZ = ZoneInfo("Asia/Taipei")
WEEKDAYS = {
    "週一": 1, "星期一": 1, "1": 1,
    "週二": 2, "星期二": 2, "2": 2,
    "週三": 3, "星期三": 3, "3": 3,
    "週四": 4, "星期四": 4, "4": 4,
    "週五": 5, "星期五": 5, "5": 5,
    "週六": 6, "星期六": 6, "6": 6,
    "週日": 7, "星期日": 7, "星期天": 7, "7": 7,
}
WEEKDAY_CHOICES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
DEMO_USER_ID = "demo_user_001"


def verify_line_signature(body: bytes, signature: str, secret: str) -> bool:
    if not body or not signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def _class_date(weekday: int, end_time: str, now: datetime) -> str | None:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    end_clock = datetime.strptime(end_time, "%H:%M").time()
    for days_back in range(8):
        date = (now - timedelta(days=days_back)).date()
        if date.isoweekday() != weekday:
            continue
        end_dt = datetime.combine(date, end_clock, tzinfo=TZ)
        if end_dt <= now:
            return date.isoformat()
    return None


def resolve_class_slot(
    user_id: str,
    weekday: int,
    start_time: str,
    end_time: str,
    now: datetime,
) -> dict:
    events = load_json(data_path("events"))
    candidates = [
        event for event in events
        if event.get("user_id") == user_id
        and event.get("event_type") == "class"
        and int(event.get("weekday", 0)) == weekday
        and event.get("start_time") == start_time
        and event.get("end_time") == end_time
    ]
    class_date = _class_date(weekday, end_time, now)
    if not candidates:
        return {"status": "none", "options": [], "reason": "找不到已設定的課程時段"}
    if class_date is None:
        return {"status": "none", "options": [], "reason": "找不到最近 7 天內已結束的課次"}
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "class_date": class_date,
            "options": [
                {"event_id": event["event_id"], "title": event["title"]}
                for event in candidates
            ],
            "reason": "同一時段有多門課，請選擇課名",
        }
    return {
        "status": "resolved",
        "event_id": candidates[0]["event_id"],
        "class_date": class_date,
    }


def save_feedback(
    feedback: dict,
    path: str | os.PathLike[str] | None = None,
) -> dict:
    try:
        saved = storage_save_feedback(feedback, path)
    except DataError as exc:
        return {"saved": False, "deduplicated": False, "error": str(exc)}
    return {"saved": saved, "deduplicated": not saved, "error": ""}


def reply_line_message(reply_token: str, text: str, choices: list[str] | None = None) -> None:
    if not reply_token:
        print(f"[LINE Reply 模擬] {text}")
        return
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        print(f"[LINE Reply 模擬] {text}")
        return

    message = {"type": "text", "text": text}
    if choices:
        message["quickReply"] = {
            "items": [
                {"type": "action", "action": {"type": "message", "label": choice[:20], "text": choice}}
                for choice in choices[:13]
            ]
        }
    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [message]},
        timeout=10,
    )
    response.raise_for_status()


def _pending_for(user_id: str, now: datetime) -> dict | None:
    pending = load_json(data_path("pending_notes"))
    record = next((row for row in pending if row.get("user_id") == user_id), None)
    if not record:
        return None
    expires = datetime.fromisoformat(record["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=TZ)
    if expires <= now:
        _remove_pending(user_id)
        return None
    return record


def _set_pending(record: dict) -> None:
    def replace(rows: list) -> list:
        return [row for row in rows if row.get("user_id") != record["user_id"]] + [record]
    update_json(data_path("pending_notes"), replace)


def _remove_pending(user_id: str) -> None:
    update_json(
        data_path("pending_notes"),
        lambda rows: [row for row in rows if row.get("user_id") != user_id],
    )


def _mark_processed(webhook_event_id: str, received_at: datetime) -> None:
    record = {
        "webhook_event_id": webhook_event_id,
        "received_at": received_at.isoformat(timespec="seconds"),
    }

    def append_once(rows: list) -> list:
        if any(row.get("webhook_event_id") == webhook_event_id for row in rows):
            return rows
        return rows + [record]
    update_json(data_path("processed_webhooks"), append_once)


def _bind_demo_user(line_user_id: str) -> None:
    def bind(rows: list) -> list:
        user = next((row for row in rows if row.get("user_id") == DEMO_USER_ID), None)
        if user:
            user["line_user_id"] = line_user_id
            user.setdefault("reminders_enabled", True)
            user.setdefault("study_reminders_enabled", False)
            return rows
        return rows + [{
            "user_id": DEMO_USER_ID,
            "line_user_id": line_user_id,
            "reminders_enabled": True,
            "study_reminders_enabled": False,
        }]
    update_json(data_path("users"), bind)


def _find_class_reminder(user_id: str, event_id: str, class_date: str) -> str:
    reminders = load_json(data_path("reminders"))
    row = next(
        (
            item for item in reminders
            if item.get("kind") == "class_feedback"
            and item.get("status") == "sent"
            and item.get("user_id") == user_id
            and item.get("event_id") == event_id
            and item.get("class_date") == class_date
        ),
        None,
    )
    return row.get("reminder_id", "") if row else ""


def _handle_text_event(event: dict, user: dict, now: datetime) -> bool | None:
    text = event.get("message", {}).get("text", "")
    text = text.strip() if isinstance(text, str) else ""
    reply_token = event.get("replyToken", "")
    user_id = user["user_id"]
    pending = _pending_for(user_id, now)

    if text == "取消":
        if pending:
            _remove_pending(user_id)
            reply_line_message(reply_token, "已取消補筆記。")
        else:
            reply_line_message(reply_token, "目前沒有待完成的補筆記流程。")
        return

    if text == "補筆記":
        record = {
            "user_id": user_id,
            "stage": "weekday",
            "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
        }
        _set_pending(record)
        reply_line_message(reply_token, "請選擇要補筆記的星期（流程 10 分鐘後逾時）。", WEEKDAY_CHOICES)
        return

    if not pending:
        return

    if pending.get("stage") == "weekday":
        weekday = WEEKDAYS.get(text)
        if weekday is None:
            reply_line_message(reply_token, "請從星期一到星期日選擇，或輸入「取消」。", WEEKDAY_CHOICES)
            return
        events = load_json(data_path("events"))
        options = sorted(
            [
                {
                    "event_id": row["event_id"],
                    "title": row["title"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                }
                for row in events
                if row.get("user_id") == user_id
                and row.get("event_type") == "class"
                and int(row.get("weekday", 0)) == weekday
            ],
            key=lambda row: (row["start_time"], row["end_time"], row["title"]),
        )
        if not options:
            reply_line_message(reply_token, "該星期沒有已設定的課表，請重新選星期或輸入「取消」。")
            return
        pending.update({"stage": "class_slot", "weekday": weekday, "options": options})
        _set_pending(pending)
        choices = [str(index) for index in range(1, min(len(options), 13) + 1)]
        details = "\n".join(
            f"{index}. {row['start_time']}–{row['end_time']}｜{row['title']}"
            for index, row in enumerate(options, 1)
        )
        reply_line_message(reply_token, f"請選擇課表時段編號：\n{details}", choices)
        return

    if pending.get("stage") == "class_slot":
        options = pending.get("options", [])
        try:
            selected = options[int(text) - 1]
        except (ValueError, IndexError):
            reply_line_message(reply_token, "請輸入清單中的時段編號，或輸入「取消」。")
            return
        match = resolve_class_slot(
            user_id,
            int(pending["weekday"]),
            selected["start_time"],
            selected["end_time"],
            now,
        )
        if match["status"] == "none":
            reply_line_message(reply_token, match["reason"])
            return
        class_date = match["class_date"]
        event_id = selected["event_id"]
        pending.update({
            "stage": "note",
            "event_id": event_id,
            "class_date": class_date,
            "reminder_id": _find_class_reminder(user_id, event_id, class_date),
        })
        pending.pop("options", None)
        _set_pending(pending)
        reply_line_message(
            reply_token,
            f"已選擇 {selected['title']}（{class_date}）。請輸入筆記或疑問；輸入「取消」可放棄。",
        )
        return

    if pending.get("stage") == "note":
        feedback = {
            "feedback_id": create_id("feedback"),
            "user_id": user_id,
            "event_id": pending["event_id"],
            "class_date": pending["class_date"],
            "reminder_id": pending.get("reminder_id", ""),
            "received_at": now.isoformat(timespec="seconds"),
            "content": text,
            "source": "selected",
            "webhook_event_id": event.get("webhookEventId", ""),
        }
        result = save_feedback(feedback)
        if result["error"]:
            reply_line_message(reply_token, f"筆記未儲存：{result['error']}")
            return False
        _remove_pending(user_id)
        reply_line_message(
            reply_token,
            "這則回饋已存在，未重複儲存。" if result["deduplicated"] else "筆記已儲存！",
        )


def _process_event(event: dict, now: datetime) -> None:
    webhook_event_id = event.get("webhookEventId")
    if not webhook_event_id:
        return
    processed = load_json(data_path("processed_webhooks"))
    if any(row.get("webhook_event_id") == webhook_event_id for row in processed):
        return

    line_user_id = event.get("source", {}).get("userId", "")
    message = event.get("message", {})
    raw_text = message.get("text", "") if isinstance(message, dict) else ""
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    reply_token = event.get("replyToken", "")
    if text.startswith("綁定 "):
        binding_code = os.getenv("LINE_BINDING_CODE", "")
        supplied_code = text.partition(" ")[2].strip()
        if not line_user_id:
            reply_line_message(reply_token, "目前只支援 LINE 個人帳號綁定。")
        elif binding_code and hmac.compare_digest(binding_code, supplied_code):
            _bind_demo_user(line_user_id)
            reply_line_message(reply_token, "LINE 帳號已綁定 ClassPulse，可以開始接收提醒。")
        else:
            reply_line_message(reply_token, "綁定碼不正確或尚未設定，請檢查後再試。")
        _mark_processed(webhook_event_id, now)
        return

    users = load_json(data_path("users"))
    user = next((row for row in users if row.get("line_user_id") == line_user_id), None)
    if user:
        if event.get("type") == "message" and message.get("type") == "text":
            if _handle_text_event(event, user, now) is False:
                return
    elif event.get("type") == "follow":
        reply_line_message(
            reply_token,
            "請先在此 LINE 帳號輸入「綁定 <綁定碼>」，再回到 ClassPulse 啟用提醒。",
        )
    elif text:
        reply_line_message(
            reply_token,
            "此 LINE 帳號尚未綁定，請輸入「綁定 <綁定碼>」。",
        )
    _mark_processed(webhook_event_id, now)


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
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("events", []), list)
            or any(
                not isinstance(event, dict)
                or not isinstance(event.get("source", {}), dict)
                or not isinstance(event.get("message", {}), dict)
                for event in payload.get("events", [])
            )
        ):
            abort(400)
        now = datetime.now(TZ)
        for event in payload.get("events", []):
            _process_event(event, now)
        return {"ok": True}

    return app


app = create_app()
