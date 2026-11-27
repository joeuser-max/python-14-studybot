"""Run one persistent dispatcher for the isolated official OA.

All delivery still uses the tested owner-scoped handlers and persisted retry keys.
No worker sends seeded examples or calls a model. No manual session selection.
"""
from datetime import datetime, timedelta
import os
import time

from filelock import FileLock, Timeout

import storage
import line_personal_class_worker as classes
import line_personal_study_worker as study

FLAG = "CLASSPULSE_FRIEND_AUTO_PUSH"


def require_config():
    study.require_config(FLAG)
    study.require_config()
    study.require_config(classes.FLAG)
    if os.getenv("CLASSPULSE_FRIEND_PROGRESS_SYNC") != "1":
        raise ValueError("Automatic push requires personal progress sync")


def tick(now=None):
    require_config()
    now = (now or datetime.now(storage.TZ)).astimezone(storage.TZ)
    sent = {(r.get("user_id"), r.get("reminder_id"))
            for r in storage.load_json(storage.data_path("reminders"))
            if r.get("status") == "sent"}
    results = []
    for session in study.sessions(now, checkin=True, automatic=True):
        key = (session["user_id"], session["reminder_id"])
        end = session["start"] + timedelta(minutes=session["minutes"])
        checkin_key = (key[0], "checkin_" + key[1])
        if key in sent and checkin_key not in sent and end <= now <= end + study.WINDOW:
            results.append(("checkin", study.deliver_checkin_once(session, now, automatic=True)))
        elif key not in sent and session["start"] <= now <= session["start"] + study.WINDOW and now < end:
            results.append(("study", study.deliver_once(session, now, automatic=True)))
    for occurrence in classes.occurrences(now, automatic=True):
        if occurrence["due"] <= now <= occurrence["due"] + classes.WINDOW:
            results.append(("class", classes.deliver_once(occurrence, now, automatic=True)))
    return results


def main():
    require_config()
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(storage.DATA_DIR / ".personal-auto-worker.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise SystemExit("Personal automatic worker already running")
    try:
        print("Personal automatic worker started; waiting for owner opt-in and due schedules.", flush=True)
        while True:
            try:
                results = tick()
                if results:
                    print(f"{datetime.now(storage.TZ):%Y-%m-%d %H:%M:%S} | {results}", flush=True)
            except Exception as exc:
                # Do not print credentials, owner IDs or note content.
                print(f"Automatic worker tick failed: {type(exc).__name__}", flush=True)
            time.sleep(15)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
