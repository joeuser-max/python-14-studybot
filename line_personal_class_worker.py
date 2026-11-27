"""One explicitly selected non-fixture class occurrence; no legacy sends."""
from datetime import datetime, timedelta, time as clock_time
import hashlib
import re
import time

import requests
from filelock import FileLock

import line_bot
import storage
from line_web_auth import AuthError, _owner
from line_personal_study_worker import require_config
from reminder_worker import _reserve_reminder, _mark_reminder, push_line_message

FLAG = "CLASSPULSE_FRIEND_CLASS_PUSH"
WINDOW = timedelta(minutes=15)


def occurrences(now=None, *, automatic=False):
    require_config(FLAG)
    now = (now or datetime.now(storage.TZ)).astimezone(storage.TZ)
    users = storage.load_json(storage.data_path("users"))
    events = storage.load_json(storage.data_path("events"))
    reminders = storage.load_json(storage.data_path("reminders"))
    feedback = storage.load_json(storage.data_path("feedback"))
    out = []
    for user in users:
        subject = user.get("line_user_id")
        if not isinstance(subject, str) or not re.fullmatch(r"U[0-9a-f]{32}", subject):
            continue
        try:
            uid = _owner(subject)
        except AuthError:
            continue
        if automatic and user.get("reminders_enabled") is not True:
            continue
        for course in events:
            if (course.get("user_id") != uid or course.get("event_type") != "class"
                    or not course.get("enabled", True) or course.get("demo_seed_version")):
                continue
            eid = course["event_id"]
            if sum(c.get("user_id") == uid and c.get("event_id") == eid for c in events) != 1:
                continue
            try:
                weekday = int(course["weekday"])
                end = clock_time.fromisoformat(course["end_time"])
                start = clock_time.fromisoformat(course["start_time"])
                offset = int(course.get("offset_minutes", 0))
                if not 1 <= weekday <= 7 or not 0 <= offset <= 60 or end <= start:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            # Include yesterday for a midnight-crossing reminder offset.
            for delta in range(-1, 8):
                day = now.date() + timedelta(days=delta)
                if day.isoweekday() != weekday:
                    continue
                due = datetime.combine(day, end, tzinfo=storage.TZ) + timedelta(minutes=offset)
                date = day.isoformat()
                if due + WINDOW < now:
                    continue
                if any(r.get("user_id") == uid and r.get("event_id") == eid
                       and r.get("class_date") == date and r.get("kind") == "class_feedback"
                       and r.get("status") == "sent" for r in reminders):
                    continue
                if any(n.get("user_id") == uid and n.get("event_id") == eid
                       and n.get("class_date") == date for n in feedback):
                    continue
                identity = "|".join((uid, eid, date, due.isoformat(timespec="minutes")))
                rid = "personal_class_" + hashlib.sha256(identity.encode()).hexdigest()[:32]
                out.append({"reminder_id": rid, "user_id": uid, "event_id": eid,
                            "class_date": date, "due": due, "user": user, "course": course})
                break
    return sorted(out, key=lambda s: (s["due"], s["event_id"]))


def deliver_once(selection, now=None, *, automatic=False):
    require_config(FLAG)
    now = (now or datetime.now(storage.TZ)).astimezone(storage.TZ)
    # Same lock as the official bridge: do not overwrite a conversation.
    with FileLock(str(storage.DATA_DIR / ".friend-e2e.lock"), timeout=15):
        if any(r.get("reminder_id") == selection["reminder_id"]
               and r.get("user_id") == selection["user_id"]
               and r.get("status") == "sent" for r in storage.load_json(storage.data_path("reminders"))):
            return "sent"
        matches = [s for s in occurrences(now, automatic=automatic)
                   if s["reminder_id"] == selection["reminder_id"]
                   and s["user_id"] == selection["user_id"]]
        if len(matches) != 1:
            return "invalid"
        s = matches[0]
        if s["due"] > now:
            return "waiting"
        pending = line_bot._pending_for(s["user_id"], now)
        if pending and pending.get("reminder_id") != s["reminder_id"]:
            return "busy"
        reminder = {
            "reminder_id": s["reminder_id"], "user_id": s["user_id"],
            "event_id": s["event_id"], "class_date": s["class_date"],
            "kind": "class_feedback", "task_id": "", "availability_id": "",
            "scheduled_at": s["due"].isoformat(timespec="minutes"), "sent_at": "",
            "status": "pending", "retry_key": "", "personal_class_test": True,
        }
        saved = _reserve_reminder(reminder)
        text = (f"{s['course']['title']} 已下課！({s['class_date']}) "
                "請回覆本堂理解程度 1–5：1=還不太理解，3=部分理解，5=很有把握。"
                "接著可選擇是否使用 AI 整理；輸入「取消」可放棄。")
        try:
            accepted = push_line_message(s["user"], saved, text)
        except requests.HTTPError as exc:
            resp = exc.response
            accepted = (resp is not None and resp.status_code == 409
                        and bool(resp.headers.get("x-line-accepted-request-id")))
        except requests.RequestException:
            accepted = False
        if accepted and not pending:
            line_bot._set_pending({
                "user_id": s["user_id"], "stage": "progress",
                "event_id": s["event_id"], "class_date": s["class_date"],
                "reminder_id": s["reminder_id"], "personal_class_push": True,
                "expires_at": (now + timedelta(minutes=10)).isoformat(timespec="seconds"),
            })
        status = "sent" if accepted else "failed"
        _mark_reminder(saved["reminder_id"], status,
                       now.isoformat(timespec="seconds") if accepted else "", s["user_id"])
        return status


def main():
    require_config(FLAG)
    options = occurrences()
    if not options:
        print("沒有符合條件的課程。請新增非範例課程並啟用課後 LINE 提醒。")
        return
    for i, s in enumerate(options, 1):
        print(f"{i}. {s['due']:%m/%d %H:%M} | {s['course']['title']}")
    raw = input("選擇一堂課（Enter 取消）：").strip()
    if not raw.isdecimal() or not 1 <= int(raw) <= len(options):
        return
    if input("同意此課次向自己的 LINE 發送課後提醒？輸入 SEND：").strip().upper() != "SEND":
        return
    selected = options[int(raw)-1]
    while True:
        status = deliver_once(selected)
        print(f"{datetime.now(storage.TZ):%H:%M:%S} | {status}", flush=True)
        if status in ("sent", "invalid"):
            return
        time.sleep(15 if status in ("waiting", "busy") else 30)


if __name__ == "__main__":
    main()
