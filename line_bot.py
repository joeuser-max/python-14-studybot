import base64
import hashlib
import hmac
from io import BytesIO
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from flask import Flask, abort, request

from plan_bridge import merge_user_plan, normalize_plan_result
from scheduler import make_plan
from storage import (
    DataError,
    add_task_to_storage,
    create_id,
    data_path,
    delete_feedback_attachment,
    load_json,
    record_task_progress,
    save_feedback as storage_save_feedback,
    save_feedback_attachment,
    update_json,
    update_task,
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
PROGRESS_CHOICES = ["1", "2", "3", "4", "5"]
AI_TASK_SKIP = "先不用"
DEMO_USER_ID = "demo_user_001"
MAX_NOTE_FILE_BYTES = 10 * 1024 * 1024
MAX_NOTE_DOCX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_NOTE_CONTENT_CHARS = 50_000
LINE_FILE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{}/content"


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


def _download_line_file(message_id: str, file_size: object) -> bytes:
    if not isinstance(message_id, str) or not message_id:
        raise DataError("LINE 檔案訊息缺少檔案 ID，請重新上傳")
    if type(file_size) is int and file_size > MAX_NOTE_FILE_BYTES:
        raise DataError("檔案超過 10 MB，請縮小檔案後重新上傳")
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise DataError("尚未設定 LINE_CHANNEL_ACCESS_TOKEN，無法下載檔案")

    url = LINE_FILE_CONTENT_URL.format(quote(message_id, safe=""))
    chunks = []
    total_size = 0
    with requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=(5, 20),
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total_size += len(chunk)
            if total_size > MAX_NOTE_FILE_BYTES:
                raise DataError("檔案超過 10 MB，請縮小檔案後重新上傳")
            chunks.append(chunk)
    if not chunks:
        raise DataError("收到的檔案是空的，請重新上傳")
    return b"".join(chunks)


def _extract_note_file(filename: str, content: bytes) -> str:
    extension = filename.rpartition(".")[2].lower()
    if extension == "txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DataError("TXT 檔案需使用 UTF-8 編碼") from exc
    elif extension == "pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise DataError("加密的 PDF 無法匯入，請解除密碼後重新上傳")
            pages = []
            total_chars = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                total_chars += len(page_text)
                if total_chars > MAX_NOTE_CONTENT_CHARS:
                    raise DataError("擷取的筆記超過 50,000 字，請拆分檔案後重新上傳")
                if page_text:
                    pages.append(page_text)
        except PdfReadError as exc:
            raise DataError("無法讀取此 PDF，請確認它是有效且未損壞的檔案") from exc
        text = "\n".join(pages)
    elif extension == "docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if sum(entry.file_size for entry in entries) > MAX_NOTE_DOCX_EXPANDED_BYTES:
                    raise DataError("Word 檔解壓後大小超過 20 MB，無法匯入")
                document = archive.getinfo("word/document.xml")
                if document.file_size > MAX_NOTE_DOCX_EXPANDED_BYTES:
                    raise DataError("Word 文件內容超過可匯入大小")
                with archive.open(document) as document_stream:
                    document_xml = document_stream.read(MAX_NOTE_DOCX_EXPANDED_BYTES + 1)
                if len(document_xml) > MAX_NOTE_DOCX_EXPANDED_BYTES:
                    raise DataError("Word 文件內容超過可匯入大小")
                root = ET.fromstring(document_xml)
        except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise DataError("無法讀取此 Word 檔，請確認它是有效的 .docx 文件") from exc

        word_namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(f"{word_namespace}p"):
            paragraph_text = "".join(
                node.text or "" for node in paragraph.iter(f"{word_namespace}t")
            )
            if paragraph_text:
                paragraphs.append(paragraph_text)
        text = "\n".join(paragraphs)
    else:
        raise DataError("目前支援 .docx、.pdf 與 .txt 筆記檔，請轉換格式後重新上傳")

    text = text.strip()
    if len(text) > MAX_NOTE_CONTENT_CHARS:
        raise DataError("擷取的筆記超過 50,000 字，請拆分檔案後重新上傳")
    if len(text) < 2:
        raise DataError("檔案中找不到足夠的文字內容，請確認文件有可讀文字")
    return text


def _handle_file_event(event: dict, user: dict, now: datetime) -> bool:
    reply_token = event.get("replyToken", "")
    message = event.get("message", {})
    pending = _pending_for(user["user_id"], now)
    if not pending or pending.get("stage") != "note":
        reply_line_message(reply_token, "請先進入「補筆記」的筆記輸入步驟，再上傳 .docx、.pdf 或 .txt 檔案。")
        return True

    filename = message.get("fileName", "")
    if not isinstance(filename, str):
        reply_line_message(reply_token, "無法辨識檔案名稱，請重新上傳 .docx、.pdf 或 .txt。")
        return True
    safe_filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
    safe_filename = safe_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()[:255]
    if safe_filename.rpartition(".")[2].lower() not in {"docx", "pdf", "txt"}:
        reply_line_message(reply_token, "目前支援 .docx、.pdf 與 .txt 筆記檔，請轉換格式後重新上傳")
        return True
    try:
        content = _download_line_file(message.get("id", ""), message.get("fileSize"))
        extracted_text = _extract_note_file(safe_filename, content)
    except DataError as exc:
        reply_line_message(reply_token, str(exc))
        return True
    except requests.RequestException:
        reply_line_message(reply_token, "無法從 LINE 下載檔案，請確認連線後重新上傳。")
        return True

    text_event = {
        **event,
        "message": {**message, "type": "text", "text": extracted_text},
        "_attachment_filename": safe_filename,
    }
    if safe_filename.lower().endswith(".pdf"):
        text_event["_attachment_content"] = content
    return _handle_text_event(text_event, user, now) is not False


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
            already_bound = user.get("line_user_id")
            if already_bound and already_bound != line_user_id:
                raise DataError("示範帳號已綁定其他 LINE 使用者，請由管理員確認後再變更")
            user["line_user_id"] = line_user_id
            user.setdefault("reminders_enabled", True)
            user.setdefault("study_reminders_enabled", False)
            user.setdefault("ai_after_class_enabled", False)
            return rows
        return rows + [{
            "user_id": DEMO_USER_ID,
            "line_user_id": line_user_id,
            "reminders_enabled": True,
            "study_reminders_enabled": False,
            "ai_after_class_enabled": False,
        }]
    update_json(data_path("users"), bind)


def _find_class_reminder(user_id: str, event_id: str, class_date: str) -> str:
    reminders = load_json(data_path("reminders"))
    matching = [
        item for item in reminders
        if item.get("kind") == "class_feedback"
        and item.get("status") == "sent"
        and item.get("user_id") == user_id
        and item.get("event_id") == event_id
        and item.get("class_date") == class_date
    ]
    row = max(matching, key=lambda item: item.get("scheduled_at", ""), default=None)
    return row.get("reminder_id", "") if row else ""


def _update_checkin(
    reminder_id: str,
    user_id: str,
    expected_progress_status: str,
    updates: dict,
) -> bool:
    changed = {"value": False}

    def update(rows: list) -> list:
        updated_rows = []
        for row in rows:
            if (
                row.get("reminder_id") == reminder_id
                and row.get("user_id") == user_id
                and row.get("kind") == "study_session_checkin"
                and row.get("status") == "sent"
                and row.get("progress_status") == expected_progress_status
            ):
                updated_rows.append({**row, **updates})
                changed["value"] = True
            else:
                updated_rows.append(row)
        return updated_rows

    update_json(data_path("reminders"), update)
    return changed["value"]


def _open_checkins(user_id: str, progress_status: str) -> list[dict]:
    return sorted(
        [
            row for row in load_json(data_path("reminders"))
            if row.get("kind") == "study_session_checkin"
            and row.get("user_id") == user_id
            and row.get("status") == "sent"
            and row.get("progress_status") == progress_status
        ],
        key=lambda row: row.get("scheduled_at", ""),
        reverse=True,
    )


def _select_checkin(
    text: str,
    user_id: str,
    progress_status: str,
) -> tuple[dict | None, str]:
    command, separator, task_id = text.partition(" ")
    if command not in {"完成", "未完成"}:
        return None, ""
    checkins = _open_checkins(user_id, progress_status)
    if not checkins:
        return None, ""
    if separator:
        selected = next((row for row in checkins if row.get("task_id") == task_id.strip()), None)
        return selected, command
    if len(checkins) == 1:
        return checkins[0], command
    return None, command


def _replan_user_tasks(user_id: str, now: datetime) -> list[dict]:
    tasks = load_json(data_path("tasks"))
    availability = load_json(data_path("availability"))
    previous_plan = load_json(data_path("plan"))
    own_tasks = [row for row in tasks if row.get("user_id") == user_id]
    own_slots = [row for row in availability if row.get("user_id") == user_id]
    own_plan = [row for row in previous_plan if row.get("user_id") == user_id]
    plan_result = make_plan(own_tasks, own_slots, own_plan, now)
    new_plan = normalize_plan_result(plan_result, user_id)
    update_json(
        data_path("plan"),
        lambda rows: merge_user_plan(rows, user_id, new_plan),
    )
    return new_plan


def _handle_study_checkin(event: dict, user: dict) -> bool | None:
    text = event.get("message", {}).get("text", "")
    text = text.strip() if isinstance(text, str) else ""
    user_id = user["user_id"]
    reply_token = event.get("replyToken", "")
    webhook_event_id = event.get("webhookEventId", "")

    remaining = _open_checkins(user_id, "awaiting_remaining_minutes")
    if remaining:
        if text == "取消":
            selected = remaining[0]
            updated = _update_checkin(
                selected["reminder_id"],
                user_id,
                "awaiting_remaining_minutes",
                {"progress_status": "no_response"},
            )
            reply_line_message(
                reply_token,
                (
                    "已取消剩餘分鐘回報；任務仍保持待完成，之後可在 ClassPulse 重新排程。"
                    if updated else "這筆讀書進度已處理。"
                ),
            )
            return True
        parts = text.split()
        if len(remaining) == 1 and len(parts) == 1:
            selected = remaining[0]
            minutes_text = parts[0]
        elif len(parts) == 2:
            selected = next(
                (row for row in remaining if row.get("task_id") == parts[0]),
                None,
            )
            minutes_text = parts[1]
        else:
            reply_line_message(
                reply_token,
                "請輸入剩餘分鐘數；若有多個待回報任務，請輸入「任務代碼 分鐘數」。",
            )
            return True
        try:
            if not minutes_text.isdecimal() or int(minutes_text) <= 0:
                raise ValueError
            if selected is None:
                raise DataError("找不到這筆待回報任務，請確認任務代碼")
            minutes = int(minutes_text)
            record_task_progress(
                selected["task_id"],
                user_id,
                completed=False,
                remaining_minutes=minutes,
                previous_availability_id=selected.get("availability_id", ""),
            )
            plan = _replan_user_tasks(user_id, datetime.now(TZ))
        except (DataError, ValueError) as exc:
            reply_line_message(reply_token, f"剩餘進度未能重新安排：{exc}")
            return False

        updated = _update_checkin(
            selected["reminder_id"],
            user_id,
            "awaiting_remaining_minutes",
            {
                "progress_status": "replanned",
                "remaining_minutes": minutes,
                "progress_reply_webhook_event_id": webhook_event_id,
            },
        )
        if not updated:
            reply_line_message(reply_token, "這筆讀書進度已處理，沒有重複更新。")
            return True
        task_plan = next(
            (row for row in plan if row.get("task_id") == selected["task_id"]),
            {},
        )
        if task_plan.get("status") == "scheduled":
            slot = next(
                (
                    row for row in load_json(data_path("availability"))
                    if row.get("availability_id") == task_plan.get("availability_id")
                    and row.get("user_id") == user_id
                ),
                {},
            )
            reply_line_message(
                reply_token,
                f"已保留原始預估時間，剩餘 {minutes} 分鐘已重新安排至 "
                f"{slot.get('date')} {slot.get('start_time')}。",
            )
        else:
            reply_line_message(
                reply_token,
                f"已記錄剩餘 {minutes} 分鐘，但目前無法排入："
                f"{task_plan.get('reason') or '請到 ClassPulse 檢查可用時段與期限。'}",
            )
        return True

    if text == "取消" and _open_checkins(user_id, "awaiting_response"):
        reply_line_message(reply_token, "未收到完成狀態回報，任務仍保持待完成。")
        return True

    selected, command = _select_checkin(text, user_id, "awaiting_response")
    if command:
        if selected is None:
            checkins = _open_checkins(user_id, "awaiting_response")
            if len(checkins) > 1 and " " not in text:
                ids = "、".join(row.get("task_id", "") for row in checkins)
                reply_line_message(
                    reply_token,
                    f"有多筆待確認任務，請使用「{command} 任務代碼」。可選代碼：{ids}",
                )
            else:
                reply_line_message(reply_token, "找不到這筆待確認任務，請確認任務代碼。")
            return True

        if command == "完成":
            try:
                record_task_progress(
                    selected["task_id"],
                    user_id,
                    completed=True,
                    previous_availability_id=selected.get("availability_id", ""),
                )
                _replan_user_tasks(user_id, datetime.now(TZ))
            except (DataError, ValueError) as exc:
                reply_line_message(reply_token, f"完成狀態未能更新：{exc}")
                return False
            progress_status = "completed"
            message = "已記錄任務完成。"
        else:
            progress_status = "awaiting_remaining_minutes"
            message = "已記錄尚未完成；請輸入剩餘所需分鐘數。"
        updated = _update_checkin(
            selected["reminder_id"],
            user_id,
            "awaiting_response",
            {
                "progress_status": progress_status,
                "progress_reply_webhook_event_id": webhook_event_id,
            },
        )
        if not updated:
            reply_line_message(reply_token, "這筆讀書進度已處理，沒有重複更新。")
            return True
        reply_line_message(reply_token, message)
        return True
    return None


def _note_task_draft(user_id: str, pending: dict, availability_id: str) -> dict:
    return {
        "task_id": pending["task_id"],
        "user_id": user_id,
        "subject": pending["course_title"],
        "title": pending["task_title"],
        "deadline": pending["deadline"],
        "estimated_minutes": pending["study_minutes"],
        "status": "pending",
        "preferred_availability_id": availability_id,
        "source_feedback_id": pending["feedback_id"],
        "source_event_id": pending["event_id"],
        "source_class_date": pending["class_date"],
        "reading_progress": pending["reading_progress"],
        "source": pending.get("task_source", "note_confirmed"),
    }


def _preview_note_task_plan(
    user_id: str,
    pending: dict,
    availability_id: str,
    now: datetime,
) -> tuple[dict, dict]:
    stored_tasks = load_json(data_path("tasks"))
    existing = next(
        (
            row for row in stored_tasks
            if row.get("user_id") == user_id
            and row.get("source_feedback_id") == pending["feedback_id"]
        ),
        None,
    )
    if existing:
        pending["task_id"] = existing["task_id"]
    task = _note_task_draft(user_id, pending, availability_id)
    tasks = [
        row for row in stored_tasks
        if row.get("user_id") == user_id and row.get("task_id") != task["task_id"]
    ] + [task]
    slots = [
        row for row in load_json(data_path("availability"))
        if row.get("user_id") == user_id
    ]
    previous_plan = [
        row for row in load_json(data_path("plan"))
        if row.get("user_id") == user_id
    ]
    plan_result = make_plan(tasks, slots, previous_plan, now)
    plan = normalize_plan_result(plan_result, user_id)
    task_plan = next(
        (row for row in plan if row.get("task_id") == task["task_id"]),
        {},
    )
    return task, task_plan


def _available_note_task_slots(
    user_id: str,
    pending: dict,
    now: datetime,
) -> list[dict]:
    available = [
        row for row in load_json(data_path("availability"))
        if row.get("user_id") == user_id
    ]
    options = []
    for slot in sorted(
        available,
        key=lambda row: (row.get("date", ""), row.get("start_time", "")),
    ):
        _, plan_row = _preview_note_task_plan(
            user_id,
            pending,
            slot.get("availability_id", ""),
            now,
        )
        if (
            plan_row.get("status") == "scheduled"
            and plan_row.get("availability_id") == slot.get("availability_id")
        ):
            options.append({
                "availability_id": slot["availability_id"],
                "date": slot["date"],
                "start_time": slot["start_time"],
                "available_minutes": slot["available_minutes"],
            })
    return options


def _study_slot_prompt(options: list[dict], minutes: int) -> tuple[str, list[str]]:
    details = "\n".join(
        f"{index}. {slot['date']} {slot['start_time']}（可用 {slot['available_minutes']} 分鐘）"
        for index, slot in enumerate(options, 1)
    )
    return (
        f"請選擇你決定要讀書的時段（任務預估 {minutes} 分鐘）：\n{details}\n"
        "請回覆時段編號；若要放棄新增任務，請輸入「先不用」。",
        [str(index) for index in range(1, min(len(options), 13) + 1)],
    )


def _request_manual_note_task(
    reply_token: str,
    pending: dict,
    feedback: dict,
    course_title: str,
    now: datetime,
    prefix: str = "",
) -> None:
    pending.update({
        "feedback_id": feedback["feedback_id"],
        "course_title": course_title,
        "task_source": "note_confirmed",
        "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
    })
    reading_progress = pending.get("course_progress", "").strip()
    if reading_progress and len(reading_progress) <= 120:
        pending.update({
            "stage": "study_minutes",
            "task_title": f"複習 {reading_progress}",
            "task_id": create_id("task"),
            "reading_progress": reading_progress,
        })
        _set_pending(pending)
        reply_line_message(
            reply_token,
            prefix
            + f"已使用你回報的進度範圍「{reading_progress}」建立讀書任務草稿。"
            "請輸入你決定要花多少分鐘讀；若不新增任務，請回覆「先不用」。",
            [AI_TASK_SKIP],
        )
        return
    _set_pending(pending)
    _request_note_task_reading_range(reply_token, pending, now, prefix)


def _request_note_task_reading_range(
    reply_token: str,
    pending: dict,
    now: datetime,
    prefix: str = "",
) -> None:
    pending.update({
        "stage": "task_reading_range",
        "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
    })
    _set_pending(pending)
    reply_line_message(
        reply_token,
        prefix
        + "目前沒有提供上課進度。若要安排讀書任務，請輸入本次要讀的範圍，"
        "例如「Ch.3 p.20–30」或「Ch.3 全章」；若不新增任務，請回覆「先不用」。",
        [AI_TASK_SKIP],
    )


def _save_note_task(
    user_id: str,
    pending: dict,
    now: datetime,
) -> tuple[dict, dict]:
    task, task_plan = _preview_note_task_plan(
        user_id,
        pending,
        pending["selected_availability_id"],
        now,
    )
    if (
        task_plan.get("status") != "scheduled"
        or task_plan.get("availability_id") != pending["selected_availability_id"]
    ):
        return task, task_plan

    existing = next(
        (
            row for row in load_json(data_path("tasks"))
            if row.get("user_id") == user_id
            and row.get("task_id") == task["task_id"]
        ),
        None,
    )
    if existing:
        update_task(task)
    else:
        add_task_to_storage(task)
    tasks = [
        row for row in load_json(data_path("tasks"))
        if row.get("user_id") == user_id
    ]
    slots = [
        row for row in load_json(data_path("availability"))
        if row.get("user_id") == user_id
    ]
    previous_plan = [
        row for row in load_json(data_path("plan"))
        if row.get("user_id") == user_id
    ]
    plan_result = make_plan(tasks, slots, previous_plan, now)
    plan = normalize_plan_result(plan_result, user_id)
    update_json(
        data_path("plan"),
        lambda rows: merge_user_plan(rows, user_id, plan),
    )
    return task, next(
        (row for row in plan if row.get("task_id") == task["task_id"]),
        {},
    )


def _handle_text_event(event: dict, user: dict, now: datetime) -> bool | None:
    text = event.get("message", {}).get("text", "")
    text = text.strip() if isinstance(text, str) else ""
    reply_token = event.get("replyToken", "")
    user_id = user["user_id"]
    is_attachment = bool(event.get("_attachment_filename"))
    pending = _pending_for(user_id, now)
    if not is_attachment and not pending:
        checkin_result = _handle_study_checkin(event, user)
        if checkin_result is not None:
            return checkin_result

    if not is_attachment and text == "取消":
        if pending:
            _remove_pending(user_id)
            reply_line_message(reply_token, "已取消補筆記。")
        else:
            reply_line_message(reply_token, "目前沒有待完成的補筆記流程。")
        return

    if not is_attachment and text == "補筆記":
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

    if pending.get("stage") == "task_reading_range":
        if text in {AI_TASK_SKIP, "只存筆記"}:
            _remove_pending(user_id)
            reply_line_message(reply_token, "筆記已保存，未新增讀書任務。")
            return
        if not text or len(text) > 120:
            reply_line_message(
                reply_token,
                "請輸入 1 至 120 字的讀書進度範圍，例如「Ch.3 p.20–30」；"
                "若不新增任務，請回覆「先不用」。",
                [AI_TASK_SKIP],
            )
            return
        pending.update({
            "reading_progress": text,
            "task_title": pending.get("task_title") or f"複習 {text}",
            "task_source": pending.get("task_source", "note_confirmed"),
            "task_id": pending.get("task_id") or create_id("task"),
            "stage": "study_minutes",
            "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
        })
        _set_pending(pending)
        reply_line_message(
            reply_token,
            "請回覆你決定要花多少分鐘讀這個範圍（輸入正整數）；"
            "接著會請你提供 Deadline，再由你選擇可行時段。",
        )
        return

    if pending.get("stage") == "study_minutes":
        if text in {AI_TASK_SKIP, "只存筆記"}:
            _remove_pending(user_id)
            reply_line_message(reply_token, "筆記已保存，未新增讀書任務。")
            return
        if not pending.get("reading_progress"):
            _request_note_task_reading_range(reply_token, pending, now)
            return
        if not re.fullmatch(r"[0-9]+", text):
            reply_line_message(reply_token, "讀書時長請以分鐘輸入正整數，例如 45。")
            return
        minutes = int(text)
        if not 1 <= minutes <= 1440:
            reply_line_message(reply_token, "讀書時長需介於 1 到 1440 分鐘，請輸入你決定的時長。")
            return
        pending["study_minutes"] = minutes
        pending.update({
            "stage": "study_deadline",
            "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
        })
        _set_pending(pending)
        reply_line_message(
            reply_token,
            "請輸入這項讀書任務的 Deadline（YYYY-MM-DD）。"
            "系統不會自行假設期限；輸入「先不用」可只保留筆記。",
            [AI_TASK_SKIP],
        )
        return

    if pending.get("stage") == "study_deadline":
        if text in {AI_TASK_SKIP, "只存筆記"}:
            _remove_pending(user_id)
            reply_line_message(reply_token, "筆記已保存，未新增讀書任務。")
            return
        minutes_match = re.fullmatch(r"分鐘\s+([0-9]+)", text)
        if minutes_match:
            minutes = int(minutes_match.group(1))
            if not 1 <= minutes <= 1440:
                reply_line_message(reply_token, "讀書時長需介於 1 到 1440 分鐘，請輸入有效分鐘數。")
                return
            pending["study_minutes"] = minutes
            pending.pop("deadline", None)
            pending.pop("study_slot_options", None)
            pending["expires_at"] = (now + timedelta(minutes=10)).isoformat(timespec="seconds")
            _set_pending(pending)
            reply_line_message(
                reply_token,
                f"已更新為 {minutes} 分鐘。請輸入 Deadline（YYYY-MM-DD）重新查詢可行時段。",
            )
            return
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            reply_line_message(reply_token, "Deadline 格式須為 YYYY-MM-DD，例如 2026-12-10。")
            return
        try:
            deadline = date.fromisoformat(text)
        except ValueError:
            reply_line_message(reply_token, "這不是有效日期，請重新輸入 YYYY-MM-DD 格式的 Deadline。")
            return
        if deadline < now.date():
            reply_line_message(reply_token, "Deadline 不可早於今天，請重新輸入日期。")
            return
        pending["deadline"] = deadline.isoformat()
        options = _available_note_task_slots(user_id, pending, now)
        if not options:
            pending["expires_at"] = (now + timedelta(minutes=10)).isoformat(timespec="seconds")
            _set_pending(pending)
            reply_line_message(
                reply_token,
                f"目前沒有符合 Deadline、能容納 {pending['study_minutes']} 分鐘的可行時段。"
                "請調整 ClassPulse 的可用時段、輸入「分鐘 45」調整時長，"
                "或輸入新的 Deadline 重新查詢；"
                "系統不會自行拆分或安排時間。輸入「先不用」可只保留筆記。",
            )
            return
        pending.update({
            "stage": "study_slot",
            "study_slot_options": options,
            "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
        })
        _set_pending(pending)
        message, choices = _study_slot_prompt(options, pending["study_minutes"])
        reply_line_message(reply_token, message, choices)
        return

    if pending.get("stage") == "study_slot":
        options = pending.get("study_slot_options", [])
        if text in {AI_TASK_SKIP, "只存筆記"}:
            _remove_pending(user_id)
            reply_line_message(reply_token, "筆記已保存，未新增讀書任務。")
            return
        try:
            selected_slot = options[int(text) - 1]
        except (ValueError, IndexError):
            message, choices = _study_slot_prompt(
                options,
                pending["study_minutes"],
            )
            reply_line_message(reply_token, message, choices)
            return
        pending["selected_availability_id"] = selected_slot["availability_id"]
        try:
            task, plan_row = _save_note_task(user_id, pending, now)
        except (DataError, ValueError) as exc:
            reply_line_message(reply_token, f"任務未能排程：{exc}。請重新選擇時段或輸入「取消」。")
            return False
        if plan_row.get("status") != "scheduled":
            options = _available_note_task_slots(user_id, pending, now)
            if not options:
                pending["stage"] = "study_minutes"
                pending.pop("study_slot_options", None)
                pending.pop("selected_availability_id", None)
                pending["expires_at"] = (now + timedelta(minutes=10)).isoformat(timespec="seconds")
                _set_pending(pending)
                reply_line_message(
                    reply_token,
                    "剛才選擇的時段已不再可用，且目前沒有其他可行時段。"
                    "請調整 ClassPulse 可用時段後重新輸入分鐘數查詢。",
                )
                return
            pending.update({
                "stage": "study_slot",
                "study_slot_options": options,
                "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
            })
            _set_pending(pending)
            message, choices = _study_slot_prompt(options, pending["study_minutes"])
            reply_line_message(
                reply_token,
                "這個時段已無法排入，請從更新後的可行時段中重新選擇。\n" + message,
                choices,
            )
            return
        _remove_pending(user_id)
        reply_line_message(
            reply_token,
            f"已新增「{task['title']}」，讀書進度："
            f"{task.get('reading_progress') or '未填寫'}；"
            f"預估 {task['estimated_minutes']} 分鐘，已排在 "
            f"{selected_slot['date']} {selected_slot['start_time']}，"
            f"Deadline 為 {task['deadline']}。",
        )
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
            "stage": "progress",
            "event_id": event_id,
            "course_title": selected["title"],
            "class_date": class_date,
            "reminder_id": _find_class_reminder(user_id, event_id, class_date),
        })
        pending.pop("options", None)
        _set_pending(pending)
        reply_line_message(
            reply_token,
            f"已選擇 {selected['title']}（{class_date}）。請回覆本堂理解進度 1–5："
            "1=還不太理解，3=部分理解，5=很有把握；輸入「取消」可放棄。",
            PROGRESS_CHOICES,
        )
        return

    if pending.get("stage") == "progress":
        if text not in PROGRESS_CHOICES:
            reply_line_message(
                reply_token,
                "請回覆 1–5 表示本堂理解進度，或輸入「取消」。",
                PROGRESS_CHOICES,
            )
            return
        pending.update({"stage": "course_progress", "progress": int(text)})
        _set_pending(pending)
        reply_line_message(
            reply_token,
            "請輸入這堂課目前上到哪裡（例如 Ch.3、第三章 p.20 或進度 60%）；"
            "不確定可回覆「略過」。",
        )
        return

    if pending.get("stage") == "course_progress":
        if len(text) > 120:
            reply_line_message(reply_token, "上課進度請控制在 120 字以內，或回覆「略過」。")
            return
        pending.update({
            "stage": "note",
            "course_progress": "" if text in {"略過", "跳過"} else text,
        })
        _set_pending(pending)
        reply_line_message(
            reply_token,
            "請輸入這堂課的上課重點筆記或疑問，或上傳 .docx／.pdf／.txt 檔案；輸入「取消」可放棄。",
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
            "progress": pending["progress"],
            "course_progress": pending.get("course_progress", ""),
            "topic_tags": [],
            "source": "selected",
            "attachment_filename": event.get("_attachment_filename", ""),
            "webhook_event_id": event.get("webhookEventId", ""),
        }
        attachment_content = event.get("_attachment_content")
        if attachment_content is not None:
            try:
                save_feedback_attachment(
                    feedback["feedback_id"], user_id, attachment_content
                )
            except DataError as exc:
                reply_line_message(reply_token, f"PDF 原檔未能儲存，筆記未儲存：{exc}")
                return False
        result = save_feedback(feedback)
        if result["error"]:
            if attachment_content is not None:
                try:
                    delete_feedback_attachment(feedback["feedback_id"], user_id)
                except DataError as cleanup_error:
                    result["error"] += f"；清理暫存 PDF 也失敗：{cleanup_error}"
            reply_line_message(reply_token, f"筆記未儲存：{result['error']}")
            return False
        _remove_pending(user_id)
        if result["deduplicated"]:
            if attachment_content is not None:
                delete_feedback_attachment(feedback["feedback_id"], user_id)
            reply_line_message(reply_token, "這則回饋已存在，未重複儲存。")
            return
        prefix = "筆記與自評進度已儲存。"
        if event.get("_attachment_filename", "").lower().endswith(".pdf"):
            prefix = "筆記與 PDF 原檔已儲存；可在網頁筆記庫下載原檔。"
        if user.get("ai_after_class_enabled") is True:
            prefix += "任務排定後，AI 會在該讀書時段開始時整理這份筆記並提供重點與複習建議。"
        _request_manual_note_task(
            reply_token,
            pending,
            feedback,
            pending.get("course_title", "課程"),
            now,
            prefix,
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
            try:
                _bind_demo_user(line_user_id)
            except DataError as exc:
                reply_line_message(reply_token, f"無法綁定：{exc}")
            else:
                reply_line_message(reply_token, "LINE 帳號已綁定 ClassPulse，可以開始接收提醒。")
        else:
            reply_line_message(reply_token, "綁定碼不正確或尚未設定，請檢查後再試。")
        _mark_processed(webhook_event_id, now)
        return

    users = load_json(data_path("users"))
    user = next((row for row in users if row.get("line_user_id") == line_user_id), None)
    if user:
        if event.get("type") == "message":
            if message.get("type") == "text":
                if _handle_text_event(event, user, now) is False:
                    return
            elif message.get("type") == "file":
                if _handle_file_event(event, user, now) is False:
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
