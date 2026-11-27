"""Explicit personal check-in replies, never implicit completion or note capture."""
import line_bot
import storage
from scheduler import _scheduled_start


def handle_progress(event, user, now):
    text = event.get("message", {}).get("text", "")
    if not isinstance(text, str):
        return None
    parts = text.strip().split()
    if not parts or parts[0] not in ("完成", "未完成", "剩餘", "取消回報"):
        return None
    command = parts[0]
    uid = user["user_id"]
    stage = "awaiting_remaining_minutes" if command in ("剩餘", "取消回報") else "awaiting_response"
    personal = [r for r in storage.load_json(storage.data_path("reminders"))
                if r.get("user_id") == uid and r.get("kind") == "study_session_checkin"
                and r.get("personal_study_test") is True and r.get("status") == "sent"]
    rows = [r for r in personal if r.get("progress_status") == stage]
    token = event.get("replyToken", "")
    def reply(message):
        line_bot.reply_line_message(token, message)
        return True
    if not rows:
        # Explicit personal task IDs and dedicated progress commands must
        # never fall through to the legacy store after completion/replay.
        if command in ("剩餘", "取消回報") or (len(parts) >= 2 and any(
                r.get("task_id") == parts[1] for r in personal)):
            return reply("目前沒有符合此指令的待回報任務。")
        return None
    if command == "剩餘":
        if len(parts) == 2:
            tid, minute_text = None, parts[1]
        elif len(parts) == 3:
            tid, minute_text = parts[1:]
        else:
            return reply("請輸入「剩餘 15」或「剩餘 任務代碼 15」。")
        if not minute_text.isdecimal() or not 1 <= int(minute_text) <= 240:
            return reply("剩餘分鐘數需介於 1 至 240。")
        minutes = int(minute_text)
    else:
        if len(parts) > 2:
            return reply(f"請輸入「{command} 任務代碼」。")
        tid = parts[1] if len(parts) == 2 else None
    if tid is not None:
        rows = [r for r in rows if r.get("task_id") == tid]
    if len(rows) != 1:
        return reply("找不到唯一待回報任務，請使用提醒內的任務代碼。")
    row = rows[0]
    tid = row["task_id"]
    updates = {"progress_reply_webhook_event_id": event.get("webhookEventId", "")}
    if command == "取消回報":
        updates["progress_status"] = "no_response"
        line_bot._update_checkin(row["reminder_id"], uid, stage, updates)
        return reply("已取消進度回報，任務仍維持待完成。")
    # Reject late replies after the user has changed/removed the session.
    tasks = [t for t in storage.load_json(storage.data_path("tasks"))
             if t.get("user_id") == uid and t.get("task_id") == tid and t.get("status") == "pending"]
    plans = [p for p in storage.load_json(storage.data_path("plan"))
             if p.get("user_id") == uid and p.get("task_id") == tid and p.get("status") == "scheduled"
             and p.get("availability_id") == row.get("availability_id")]
    slots = [s for s in storage.load_json(storage.data_path("availability"))
             if s.get("user_id") == uid and s.get("availability_id") == row.get("availability_id")]
    valid = len(tasks) == len(plans) == len(slots) == 1
    if valid:
        try:
            start = _scheduled_start(plans[0], slots[0]).isoformat(timespec="minutes")
            duration = int(plans[0].get("scheduled_minutes") or tasks[0].get("remaining_minutes")
                           or tasks[0]["estimated_minutes"])
            valid = start == row.get("session_start") and duration == row.get("session_minutes")
        except (KeyError, ValueError, TypeError):
            valid = False
    if not valid:
        line_bot._update_checkin(row["reminder_id"], uid, stage,
                                 {**updates, "progress_status": "no_response"})
        return reply("原讀書時段已變更或任務已完成，這次回報不會覆寫目前排程。")
    if command == "未完成":
        updates["progress_status"] = "awaiting_remaining_minutes"
        line_bot._update_checkin(row["reminder_id"], uid, stage, updates)
        return reply("已記錄尚未完成。請輸入「剩餘 15」（將 15 改為實際所需分鐘）。")
    try:
        storage.record_task_progress(tid, uid, completed=command == "完成",
                                     remaining_minutes=minutes if command == "剩餘" else None,
                                     previous_availability_id=row.get("availability_id", ""))
        placed = line_bot._replan_user_tasks(uid, now, changed_task_id=tid)
    except (storage.DataError, ValueError):
        # Cross-file updates are not transactional. Stop rather than silently
        # forwarding to legacy or implying the original plan was restored.
        return reply("進度或重新排程未完整更新，請至網頁核對任務及排程。")
    if command == "完成":
        updates["progress_status"] = "completed"
        message = "已記錄任務完成，僅移除本任務的讀書安排。"
    else:
        updates.update(progress_status="replanned", remaining_minutes=minutes)
        plan = next((p for p in placed if p.get("task_id") == tid), None)
        if plan:
            message = (f"剩餘 {minutes} 分鐘已重新安排至 {plan['scheduled_start']}。"
                       "原始預估保留，行事曆以 30 分鐘格安排。")
        else:
            message = f"已記錄剩餘 {minutes} 分鐘；目前無合法時段，任務保留在待排區。"
    line_bot._update_checkin(row["reminder_id"], uid, stage, updates)
    return reply(message)
