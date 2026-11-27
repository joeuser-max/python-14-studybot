import base64
import hashlib
import hmac
import json
import os

from line_demo_registration import get_or_create_line_user, is_valid_line_user_id
from line_demo_seed import SEEDED_STATUS, seed_line_user
from line_web_auth import install_routes
from line_note_files import clean_filename, download_line_file, extract_text
from note_attachments import save_pdf_attachment
from note_tasks import extract_questions, candidate_tasks, confirm_question_task, next_class_start
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, abort, request

from ai_assistant import AIError, organize_class_feedback
from storage import (
    DataError,
    add_task_to_storage,
    create_id,
    data_path,
    load_json,
    record_task_progress,
    save_feedback as storage_save_feedback,
    search_learning_notes,
    update_feedback_analysis,
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
PROGRESS_CHOICES = ["1", "2", "3", "4", "5"]
PROGRESS_LABELS = {
    1: "目前還不太理解",
    2: "大部分還不熟悉",
    3: "部分理解，仍有疑問",
    4: "大致理解，少數地方需複習",
    5: "很有把握",
}
AI_TASK_ACCEPT = "加入讀書任務"
AI_TASK_SKIP = "先不用"
DEMO_USER_ID = "demo_user_001"
PENDING_DEMO_REPLY = "你的 ClassPulse 帳號已建立，個人 Demo 資料尚未準備完成；目前暫不開放筆記、任務或 AI 功能。"
SEEDED_DEMO_REPLY = "你的個人虛構 Demo 資料已建立，尚待網頁身份驗證與安全驗收；目前暫不開放筆記、任務或 AI 功能。"


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


def _save_quick_note(event: dict, user_id: str, now: datetime, text: str) -> dict:
    """LINE-first 快速收件箱：不用重選課次、不猜測筆記科目。

    課程歸屬可到 V2 中控台確認；不自動產生排程或呼叫第三方模型。
    """
    note = text.strip()
    if not 2 <= len(note) <= 50_000:
        raise DataError("筆記應有 2–50,000 字")
    feedback = {
        "feedback_id": create_id("feedback"), "user_id": user_id,
        "event_id": "inbox", "class_date": now.date().isoformat(),
        "received_at": now.isoformat(timespec="seconds"),
        "content": note, "progress": None, "topic_tags": [],
        "source": "selected", "reminder_id": "",
        "webhook_event_id": event.get("webhookEventId",""),
        "attachment_filename": event.get("_attachment_filename", ""),
    }
    result = save_feedback(feedback)
    if result["error"]:
        raise DataError(result["error"])
    if result["saved"] and event.get("_attachment_content") is not None:
        save_pdf_attachment(user_id, feedback["feedback_id"], event["_attachment_content"])
    return {**result, "feedback_id": feedback["feedback_id"]}


def _notes_reply(user_id: str, query: str = "") -> str:
    all_notes = load_json(data_path("feedback"))
    # LINE 自然語言查詢須包含筆記全文與主題標籤，不能套用
    # V2「只依標籤搜尋」的網頁舊邏輯。
    owned = [n for n in all_notes if n.get("user_id") == user_id]
    needle = query.strip().casefold()
    matched = [
        n for n in owned
        if not needle or needle in str(n.get("content") or "").casefold()
        or any(needle in str(tag).casefold() for tag in
               (n.get("topic_tags") if isinstance(n.get("topic_tags"), list) else []))
    ]
    if not matched:
        return "找不到符合條件的筆記；可以傳送「筆記 內容」、PDF、DOCX 或 TXT 新增。"
    events = {e.get("event_id"): e.get("title", "課堂") for e in load_json(data_path("events"))
              if e.get("user_id") == user_id}
    recent = sorted(matched,key=lambda n:n.get("received_at",""),reverse=True)[:5]
    sections=[]
    for item in recent:
        title=events.get(item.get("event_id"), "未分類筆記")
        excerpt=" ".join(str(item.get("content") or "").split())[:220]
        date_text=item.get("class_date") or item.get("received_at","")[:10]
        sections.append(f"{date_text}｜{title}\n{excerpt}")
    return "最近筆記" + (f"（搜尋：{query}）" if query else "") + "：\n\n" + "\n\n".join(sections)


def _handle_file_event(event: dict, user: dict, now: datetime) -> bool:
    """Only the verified Webhook may download LINE files (never unsigned URLs)."""
    reply_token=event.get("replyToken","")
    message=event.get("message") or {}
    try:
        name=clean_filename(message.get("fileName",""))
        raw=download_line_file(message.get("id",""),message.get("fileSize"))
        text=extract_text(name,raw)
    except DataError as exc:
        reply_line_message(reply_token,str(exc))
        return True
    except requests.RequestException:
        reply_line_message(reply_token,"無法從 LINE 下載檔案，請稍後再傳")
        return True
    pending=_pending_for(user["user_id"],now)
    if pending and pending.get("stage")!="note":
        reply_line_message(reply_token,"目前正在填寫其他資訊，請完成或輸入「取消」再傳筆記")
        return True
    synthetic={
        **event,
        "message":{**message,"type":"text","text":text if pending else "筆記 "+text},
        "_attachment_filename":name,
    }
    if name.lower().endswith(".pdf"):
        synthetic["_attachment_content"]=raw
    return _handle_text_event(synthetic,user,now) is not False


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
        if any(row.get("line_user_id") == line_user_id
               and row.get("user_id") != DEMO_USER_ID for row in rows):
            raise DataError("此 LINE 帳號已有獨立 ClassPulse 帳號，不可重新綁定示範帳號")
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


def _visual_board_enabled(user_id: str, availability: list[dict]) -> bool:
    return any(row.get("user_id") == user_id and row.get("board_generated")
               for row in availability)


def _replan_user_tasks(user_id: str, now: datetime,
                       changed_task_id: str = "") -> list[dict]:
    """V2-only：LINE 回報時只調整被回報的任務。

    不使用 legacy make_plan 全表重排；無論有沒有 board_generated
    既有時段，都不得把其他任務移動。
    """
    if not changed_task_id:
        return [row for row in load_json(data_path("plan"))
                if row.get("user_id") == user_id]
    from week_planner import unplace, fill_remaining
    unplace(user_id, changed_task_id)
    task = next(
        (row for row in load_json(data_path("tasks"))
         if row.get("user_id") == user_id and row.get("task_id") == changed_task_id),
        None,
    )
    if task and task.get("status") == "pending":
        outcome = fill_remaining(user_id, now, only_task_ids={changed_task_id})
        return outcome["placed"]
    return []


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
            plan = _replan_user_tasks(user_id, datetime.now(TZ), selected["task_id"])
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
                _replan_user_tasks(user_id, datetime.now(TZ), selected["task_id"])
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


def _schedule_confirmed_ai_task(
    user_id: str,
    pending: dict,
    now: datetime,
) -> tuple[dict, dict]:
    tasks = load_json(data_path("tasks"))
    task = next(
        (
            row for row in tasks
            if row.get("user_id") == user_id
            and row.get("source_feedback_id") == pending["feedback_id"]
            and row.get("source") == "ai_confirmed"
        ),
        None,
    )
    if task is None:
        course=next((c for c in load_json(data_path("events"))
                     if c.get("user_id")==user_id and c.get("event_id")==pending.get("event_id")),None)
        next_start=next_class_start(course,now) if course else None
        deadline = next_start.date().isoformat() if next_start else (now.date()+timedelta(days=7)).isoformat()
        task = {
            "task_id": create_id("task"),
            "user_id": user_id,
            "subject": pending["course_title"],
            "title": pending["suggested_task"],
            "deadline": deadline,
            "estimated_minutes": 30,
            **({"deadline_at":next_start.isoformat(timespec="minutes")} if next_start else {}),
            "status": "pending",
            "preferred_availability_id": "",
            "source_feedback_id": pending["feedback_id"],
            "source_event_id": pending["event_id"],
            "source_class_date": pending["class_date"],
            "source": "ai_confirmed",
        }
        add_task_to_storage(task)
        tasks = load_json(data_path("tasks"))

    # LINE 接受 AI 建議只建立待排任務；V2 的拖排／偏好畫筆
    # 必須由使用者在 Streamlit 中控台明確確認。
    return task, {}


def _format_class_feedback_analysis(analysis: dict, progress: int) -> str:
    lines = [
        f"AI 已整理這堂課（你的自評：{progress}/5｜{PROGRESS_LABELS[progress]}）",
        f"摘要：{analysis['summary']}",
    ]
    if analysis["key_points"]:
        lines.append("課堂重點：")
        lines.extend(f"・{point}" for point in analysis["key_points"])
    if analysis["unresolved_questions"]:
        lines.append("待釐清：")
        lines.extend(f"・{question}" for question in analysis["unresolved_questions"])
    if analysis.get("topic_tags"):
        lines.append("主題標籤：" + "、".join(analysis["topic_tags"]))
    return "\n".join(lines)


def _handle_text_event(event: dict, user: dict, now: datetime) -> bool | None:
    text = event.get("message", {}).get("text", "")
    text = text.strip() if isinstance(text, str) else ""
    reply_token = event.get("replyToken", "")
    user_id = user["user_id"]
    checkin_result = _handle_study_checkin(event, user)
    if checkin_result is not None:
        return checkin_result
    pending = _pending_for(user_id, now)

    # LINE-first 直接操作：查筆記與臨時筆記可略過逐欄課次引導。
    # 仍保存來源，不把未確認的文本推定成正式課程。
    if not pending and text in {"查看筆記", "我的筆記"}:
        reply_line_message(reply_token, _notes_reply(user_id))
        return
    if not pending and text.startswith("搜尋 "):
        reply_line_message(reply_token, _notes_reply(user_id, text[3:].strip()))
        return
    if not pending and text.startswith("筆記 "):
        try:
            saved = _save_quick_note(event,user_id,now,text[3:])
        except DataError as exc:
            reply_line_message(reply_token, f"筆記尚未保存：{exc}")
            return False
        if saved["deduplicated"]:
            reply_line_message(reply_token,"這則筆記已存在，未重複儲存")
        else:
            reply_line_message(reply_token,"已存入 ClassPulse 未分類筆記庫。"
                "稍後可在網頁歸檔；目前不會自動覆寫日曆或產生讀書任務。")
        return

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

    if pending and pending.get("stage") == "ai_question_confirmation":
        choices=[AI_TASK_ACCEPT,AI_TASK_SKIP]
        index=int(pending.get("question_index",0))
        questions=pending.get("questions",[])
        if index>=len(questions):
            _remove_pending(user_id)
            reply_line_message(reply_token,"所有疑問已處理，可至 ClassPulse 任務管理查看紫色任務。")
            return
        if text not in choices:
            reply_line_message(reply_token,
                f"第 {index+1}/{len(questions)} 題：{questions[index]} "
                "要新增 30 分鐘紫色任務嗎？Deadline 為下次上課前。",
                choices)
            return
        if text==AI_TASK_ACCEPT:
            notes=load_json(data_path("feedback"))
            note=next((n for n in notes if n.get("feedback_id")==pending["feedback_id"]
                       and n.get("user_id")==user_id),None)
            courses=load_json(data_path("events"))
            if note is None:
                reply_line_message(reply_token,"來源筆記不存在，請先回到網站檢查")
                return False
            candidate=next(
                (c for c in candidate_tasks([note],courses,
                                            load_json(data_path("tasks")),user_id,now)
                 if c["question"]==questions[index]),None,
            )
            if candidate is not None:
                try:
                    confirm_question_task(user_id,candidate,now)
                except DataError as exc:
                    reply_line_message(reply_token,f"這題尚未新增：{exc}")
                    return False
            # An already confirmed question may be absent from candidate_tasks.
        index+=1
        if index<len(questions):
            pending["question_index"]=index
            pending["expires_at"]=(now+timedelta(minutes=10)).isoformat(timespec="seconds")
            _set_pending(pending)
            reply_line_message(reply_token,
                f"已處理本題。第 {index+1}/{len(questions)} 題：{questions[index]} "
                "確認新增 30 分鐘任務，或先不用？",choices)
        else:
            _remove_pending(user_id)
            reply_line_message(reply_token,
                "本次所有疑問已逐題確認。已接受的任務只進紫色待排區，"
                "不會自動覆寫課表；請至 ClassPulse 確認安排。")
        return

    if pending and pending.get("stage") == "ai_task_confirmation":
        if text == AI_TASK_SKIP:
            _remove_pending(user_id)
            reply_line_message(reply_token, "已保留整理後的筆記，未新增讀書任務。")
            return
        if text != AI_TASK_ACCEPT:
            reply_line_message(
                reply_token,
                "要把 AI 建議加入讀書計畫嗎？期限預設為課後 7 天，之後可在網站修改。",
                [AI_TASK_ACCEPT, AI_TASK_SKIP],
            )
            return
        try:
            task, plan_row = _schedule_confirmed_ai_task(user_id, pending, now)
        except (DataError, ValueError) as exc:
            reply_line_message(
                reply_token,
                f"任務或排程處理失敗：{exc}。可再回覆「{AI_TASK_ACCEPT}」重試。",
                [AI_TASK_ACCEPT, AI_TASK_SKIP],
            )
            return False
        _remove_pending(user_id)
        if plan_row.get("status") == "scheduled":
            slot = next(
                (
                    row for row in load_json(data_path("availability"))
                    if row.get("availability_id") == plan_row.get("availability_id")
                    and row.get("user_id") == user_id
                ),
                {},
            )
            reply_line_message(
                reply_token,
                f"已新增「{task['title']}」並排入 {slot.get('date')} "
                f"{slot.get('start_time')}（{task['estimated_minutes']} 分鐘）。"
                "如需調整期限或時段，請到 ClassPulse 修改後重新排程。",
            )
        else:
            reason = plan_row.get("reason") or "目前沒有合適的可用時段"
            reply_line_message(
                reply_token,
                f"已新增「{task['title']}」，但目前尚未排入：{reason}"
                "。請到 ClassPulse 調整可用時段或期限後重新排程。",
            )
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
            "stage": "progress",
            "event_id": event_id,
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
        pending.update({"stage": "note", "progress": int(text)})
        _set_pending(pending)
        reply_line_message(
            reply_token,
            "請輸入這堂課的上課重點筆記或疑問；輸入「取消」可放棄。",
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
            "topic_tags": [],
            "source": "selected",
            "webhook_event_id": event.get("webhookEventId", ""),
            "attachment_filename": event.get("_attachment_filename",""),
        }
        result = save_feedback(feedback)
        if result["error"]:
            reply_line_message(reply_token, f"筆記未儲存：{result['error']}")
            return False
        _remove_pending(user_id)
        if result["deduplicated"]:
            reply_line_message(reply_token, "這則回饋已存在，未重複儲存。")
            return
        if event.get("_attachment_content") is not None:
            try:
                save_pdf_attachment(user_id,feedback["feedback_id"],event["_attachment_content"])
            except DataError as exc:
                reply_line_message(reply_token,
                    f"筆記文字已保存，但 PDF 原檔保存失敗：{exc}")
                return
        if user.get("ai_after_class_enabled") is not True:
            reply_line_message(reply_token, "筆記與自評進度已儲存。")
            return

        course = next(
            (
                row for row in load_json(data_path("events"))
                if row.get("user_id") == user_id
                and row.get("event_id") == pending["event_id"]
            ),
            {},
        )
        try:
            analysis = organize_class_feedback(feedback, course.get("title", ""))
        except AIError as exc:
            reply_line_message(
                reply_token,
                f"筆記與進度已保存，但 AI 整理失敗：{exc}",
            )
            return
        try:
            update_feedback_analysis(
                feedback["feedback_id"],
                user_id,
                analysis,
            )
        except DataError as exc:
            reply_line_message(
                reply_token,
                f"筆記已保存，但 AI 整理結果未能保存：{exc}",
            )
            return

        response_text = _format_class_feedback_analysis(
            analysis,
            pending["progress"],
        )
        questions=extract_questions({**feedback,"ai_analysis":analysis})
        if questions:
            pending.update({
                "stage":"ai_question_confirmation",
                "questions":questions,
                "question_index":0,
                "feedback_id":feedback["feedback_id"],
                "expires_at":(now+timedelta(minutes=10)).isoformat(timespec="seconds"),
            })
            _set_pending(pending)
            reply_line_message(
                reply_token,response_text+
                f"\n已辨識 {len(questions)} 項獨立疑問。第 1 題：{questions[0]}"
                "\n要新增 30 分鐘紫色任務嗎？期限預設下次上課前。",
                [AI_TASK_ACCEPT,AI_TASK_SKIP],
            )
            return
        if not analysis["suggested_task"]:
            reply_line_message(reply_token, response_text + "\n目前沒有足夠資訊提出複習任務。")
            return

        pending.update({
            "stage": "ai_task_confirmation",
            "feedback_id": feedback["feedback_id"],
            "course_title": course["title"],
            "suggested_task": analysis["suggested_task"],
            "estimated_minutes": analysis["estimated_minutes"],
            "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
        })
        _set_pending(pending)
        reply_line_message(
            reply_token,
            response_text
            + f"\n建議任務：{analysis['suggested_task']}（約 {analysis['estimated_minutes']} 分鐘）。"
            "\n要加入讀書計畫嗎？期限預設為課後 7 天，可在網站修改。",
            [AI_TASK_ACCEPT, AI_TASK_SKIP],
        )


def _process_event(event: dict, now: datetime) -> None:
    webhook_event_id = event.get("webhookEventId")
    if not webhook_event_id:
        return
    processed = load_json(data_path("processed_webhooks"))
    if any(row.get("webhook_event_id") == webhook_event_id for row in processed):
        return

    source = event.get("source", {})
    line_user_id = source.get("userId", "")
    # Never process private notes or binding commands in group/room contexts.
    # Missing source.type is retained for the legacy signed test contract.
    if source.get("type") not in (None, "user") or event.get("mode") == "standby":
        _mark_processed(webhook_event_id, now)
        return
    if event.get("type") == "follow" and os.getenv("LINE_FRIEND_DEMO_ENABLED") == "1":
        # No account creation from group/room or standby events.
        if (source.get("type") == "user" and event.get("mode") != "standby"
                and is_valid_line_user_id(line_user_id)):
            # Storage failures must not acknowledge a successful registration.
            registered, _ = get_or_create_line_user(line_user_id)
            status = registered.get("demo_status")
            if status == "pending_seed" and os.getenv("LINE_FRIEND_DEMO_SEED_ENABLED") == "1":
                seed_line_user(registered["user_id"], now)
                status = SEEDED_STATUS
            if status in ("pending_seed", SEEDED_STATUS):
                reply_line_message(event.get("replyToken", ""),
                                   SEEDED_DEMO_REPLY if status == SEEDED_STATUS else PENDING_DEMO_REPLY)
            else:
                reply_line_message(event.get("replyToken", ""), "你的 ClassPulse 帳號已存在，歡迎回來。")
        _mark_processed(webhook_event_id, now)
        return

    message = event.get("message", {})
    raw_text = message.get("text", "") if isinstance(message, dict) else ""
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    reply_token = event.get("replyToken", "")
    # Pending users cannot enter legacy commands or download attachments,
    # even after the opt-in switch is disabled again.
    if line_user_id:
        existing = next((row for row in load_json(data_path("users"))
                         if row.get("line_user_id") == line_user_id), None)
        if existing and existing.get("demo_status") in ("pending_seed", SEEDED_STATUS):
            if event.get("type") == "message" and source.get("type") == "user":
                reply_line_message(reply_token, SEEDED_DEMO_REPLY
                                   if existing.get("demo_status") == SEEDED_STATUS else PENDING_DEMO_REPLY)
            _mark_processed(webhook_event_id, now)
            return
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
    user = next((row for row in users if line_user_id and row.get("line_user_id") == line_user_id), None)
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
    install_routes(app)
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
