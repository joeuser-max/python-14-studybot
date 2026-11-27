"""Step 21.4: isolated real study-start delivery, one explicitly selected session.

Run only with the original OA environment. No legacy worker changes, no seeded
task pushes, no AI API calls, no class reminders or check-ins in this phase.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timedelta

import requests
from filelock import FileLock

import storage
from line_web_auth import AuthError, _owner
from reminder_worker import _reserve_reminder, _mark_reminder, push_line_message
from line_study_ai import study_start_message
from scheduler import _scheduled_start

WINDOW = timedelta(minutes=15)


def require_config():
    if (os.getenv("CLASSPULSE_FRIEND_STUDY_PUSH") != "1"
            or os.getenv("CLASSPULSE_OFFICIAL_BRIDGE") != "1"
            or os.getenv("CLASSPULSE_FRIEND_INTERNAL") != "1"
            or os.getenv("CLASSPULSE_FRIEND_E2E") != "1"
            or os.getenv("CLASSPULSE_FRIEND_NOTE_SYNC") != "1"
            or os.getenv("CLASSPULSE_STAGING_TEST_USERS") is not None
            or storage.is_demo_storage()
            or storage.DATA_DIR != (storage.ROOT / "data" / "friend-e2e").resolve()
            or not os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            or not os.getenv("LINE_CHANNEL_SECRET")):
        raise ValueError("Personal study push requires isolated official OA opt-in")


def sessions(now=None):
    """Only user-confirmed, non-seeded AI tasks with owner-scoped note and slot."""
    require_config()
    now = (now or datetime.now(storage.TZ)).astimezone(storage.TZ)
    users = storage.load_json(storage.data_path("users"))
    tasks = storage.load_json(storage.data_path("tasks"))
    plan = storage.load_json(storage.data_path("plan"))
    slots = storage.load_json(storage.data_path("availability"))
    notes = storage.load_json(storage.data_path("feedback"))
    out = []
    for user in users:
        subject = user.get("line_user_id")
        if not isinstance(subject, str) or not re.fullmatch(r"U[0-9a-f]{32}", subject):
            continue
        try:
            uid = _owner(subject)
        except AuthError:
            continue
        for task in tasks:
            if (task.get("user_id") != uid or task.get("status") != "pending"
                    or task.get("source") != "ai_confirmed" or task.get("demo_seed_version")
                    or not task.get("source_question_key")):
                continue
            tid = task["task_id"]
            if sum(t.get("user_id") == uid and t.get("task_id") == tid for t in tasks) != 1:
                continue
            own_notes = [n for n in notes if n.get("user_id") == uid
                         and n.get("feedback_id") == task.get("source_feedback_id")
                         and not n.get("demo_seed_version")]
            if len(own_notes) != 1 or not isinstance(own_notes[0].get("ai_analysis"), dict):
                continue
            rows = [p for p in plan if p.get("user_id") == uid and p.get("task_id") == tid
                    and p.get("status") == "scheduled"]
            if len(rows) != 1:
                continue
            row = rows[0]
            matching = [s for s in slots if s.get("user_id") == uid
                        and s.get("availability_id") == row.get("availability_id")]
            if len(matching) != 1:
                continue
            try:
                start = _scheduled_start(row, matching[0])
                minutes = int(row.get("scheduled_minutes") or task.get("remaining_minutes")
                              or task["estimated_minutes"])
            except (KeyError, ValueError, TypeError):
                continue
            if not 1 <= minutes <= 240 or now > start + WINDOW:
                continue
            identity = "\0".join((uid, tid, matching[0]["availability_id"],
                                  start.isoformat(timespec="minutes")))
            rid = "personal_study_" + hashlib.sha256(identity.encode()).hexdigest()[:32]
            out.append({"reminder_id": rid, "user_id": uid, "task_id": tid,
                        "availability_id": matching[0]["availability_id"], "start": start,
                        "minutes": minutes, "user": user, "task": task, "note": own_notes[0]})
    return sorted(out, key=lambda s: (s["start"], s["task_id"]))


def deliver_once(selection, now=None):
    """Return waiting/sent/failed/invalid; only the selected exact start is armed."""
    require_config()
    now = (now or datetime.now(storage.TZ)).astimezone(storage.TZ)
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(storage.DATA_DIR / ".personal-study-worker.lock"), timeout=15):
        # Re-read owner, task, plan and slot rather than sending stale snapshots.
        matches = [s for s in sessions(now)
                   if s["reminder_id"] == selection["reminder_id"]
                   and s["user_id"] == selection["user_id"]
                   and s["minutes"] == selection["minutes"]]
        if len(matches) != 1:
            return "invalid"
        session = matches[0]
        if session["start"] > now:
            return "waiting"
        reminder = {
            "reminder_id": session["reminder_id"], "user_id": session["user_id"],
            "task_id": session["task_id"], "availability_id": session["availability_id"],
            "event_id": "", "class_date": "", "kind": "study_session",
            "scheduled_at": session["start"].isoformat(timespec="minutes"),
            "sent_at": "", "status": "pending", "retry_key": "",
            "personal_study_test": True,
        }
        saved = _reserve_reminder(reminder)
        if saved.get("status") == "sent":
            return "sent"
        # Explicit selection consents to sending cached analysis to the same
        # LINE account. A dict is required by sessions(), so no API call occurs.
        text = study_start_message(session["task"],
                                   dict(session["user"], ai_after_class_enabled=True),
                                   [session["note"]])
        try:
            accepted = push_line_message(session["user"], saved, text)
        except requests.HTTPError as exc:
            # LINE reports previously accepted retries as HTTP 409 with the
            # original accepted request ID. Other 409 responses are failures.
            resp = exc.response
            accepted = (resp is not None and resp.status_code == 409
                        and bool(resp.headers.get("x-line-accepted-request-id")))
        except requests.RequestException:
            accepted = False
        status = "sent" if accepted else "failed"
        _mark_reminder(saved["reminder_id"], status,
                       now.isoformat(timespec="seconds") if accepted else "",
                       session["user_id"])
        return status


def main():
    require_config()
    options = sessions()
    if not options:
        print("沒有可測試的已排 AI 任務。請先用 LINE AI補筆記確認任務，再拖排未來時段。")
        return
    for index, session in enumerate(options, 1):
        print(f"{index}. {session['start']:%m/%d %H:%M} | {session['minutes']} 分鐘 | "
              f"{session['task']['subject']} | {session['task']['title']}")
    raw = input("選擇一筆任務編號（Enter 取消）：").strip()
    if not raw.isdecimal() or not 1 <= int(raw) <= len(options):
        return
    selected = options[int(raw)-1]
    if input("同意在該時段將已保存的 AI 摘要推送至該任務自己的 LINE？輸入 SEND：").strip() != "SEND":
        return
    print("已選定單一讀書時段；移動/取消任務、Ctrl+C 或超過 15 分鐘窗口即停止。")
    while True:
        status = deliver_once(selected)
        print(f"{datetime.now(storage.TZ):%H:%M:%S} | {status}", flush=True)
        if status in ("sent", "invalid"):
            return
        time.sleep(15 if status == "waiting" else 30)


if __name__ == "__main__":
    main()
