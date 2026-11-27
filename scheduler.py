from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Taipei")


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _date_and_time(date_text: str, time_text: str) -> datetime:
    return datetime.fromisoformat(f"{date_text}T{time_text}").replace(tzinfo=TZ)


def _effective_slot_start(start: datetime, end: datetime, now: datetime) -> datetime | None:
    if start > now:
        return start
    if now >= end:
        return None

    current_minute = now.replace(second=0, microsecond=0)
    if now > current_minute:
        current_minute += timedelta(minutes=1)
    return current_minute if current_minute < end else None


def _scheduled_start(row: dict, slot: dict) -> datetime:
    value = row.get("scheduled_start")
    if value:
        start = datetime.fromisoformat(value)
        return start.astimezone(TZ) if start.tzinfo else start.replace(tzinfo=TZ)
    return _date_and_time(slot["date"], slot["start_time"])


def _task_minutes(task: dict) -> int:
    remaining = task.get("remaining_minutes")
    return int(task["estimated_minutes"] if remaining is None else remaining)


def update_task_status(tasks: list[dict], task_id: str, status: str) -> tuple[list[dict], str | None]:
    if status not in {"pending", "completed"}:
        return tasks, "status 必須為 pending 或 completed"

    found = False
    updated = []
    for task in tasks:
        item = dict(task)
        if item.get("task_id") == task_id:
            found = True
            item["status"] = status
        updated.append(item)
    if not found:
        return tasks, f"找不到任務：{task_id}"
    return updated, None


def make_plan(
    tasks: list[dict],
    availability: list[dict],
    previous_plan: list[dict],
    now: datetime,
) -> dict:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    owners = {task.get("user_id") for task in tasks}
    if len(owners) > 1:
        # Independent users may study at exactly the same time.
        combined = {"plan": [], "new_alerts": []}
        for owner in sorted(owners, key=str):
            result = make_plan(
                [task for task in tasks if task.get("user_id") == owner],
                [slot for slot in availability if slot.get("user_id") == owner],
                [row for row in previous_plan if row.get("user_id") == owner],
                now,
            )
            combined["plan"].extend({**row, "user_id": owner} for row in result["plan"])
            combined["new_alerts"].extend(result["new_alerts"])
        return combined
    owner = next(iter(owners), None)
    previous = {row["task_id"]: row for row in previous_plan if "task_id" in row
                and row.get("user_id", owner) == owner}
    new_alerts: list[str] = []
    plan: list[dict] = []
    used_slots: set[str] = set()
    used_intervals: list[tuple[datetime, datetime]] = []

    manual_entries: list[tuple[dict, dict]] = []
    for task in tasks:
        if task.get("status") != "pending":
            continue
        preferred = task.get("preferred_availability_id", "")
        if not preferred:
            continue
        slot = next(
            (item for item in availability
             if item.get("availability_id") == preferred
             and item.get("user_id") == task.get("user_id")),
            None,
        )
        manual_entries.append((task, slot or {}))

    fixed_by_task: set[str] = set()
    manual_conflict_ids: set[str] = set()
    for task, slot in manual_entries:
        task_id = task["task_id"]
        reason = None
        if not slot:
            reason = "找不到指定的可用時段"
        else:
            try:
                slot_start = _date_and_time(slot["date"], slot["start_time"])
                estimate = _task_minutes(task)
                minutes = int(slot["available_minutes"])
                deadline = datetime.fromisoformat(task["deadline"] + "T23:59").replace(tzinfo=TZ)
            except (KeyError, TypeError, ValueError):
                reason = "指定時段或任務資料格式錯誤"
            else:
                slot_end = slot_start + timedelta(minutes=minutes)
                scheduled_start = _effective_slot_start(slot_start, slot_end, now)
                if scheduled_start is None:
                    reason = "指定時段已結束"
                elif scheduled_start + timedelta(minutes=estimate) > slot_end:
                    reason = "指定時段剩餘時間不足以容納任務時長"
                elif slot_end > deadline:
                    reason = "指定時段結束時間晚於 Deadline"
                elif slot["availability_id"] in used_slots:
                    reason = "指定時段與另一固定任務衝突"
                elif any(
                    slot_start < fixed_end and fixed_start < slot_end
                    for fixed_start, fixed_end in used_intervals
                ):
                    reason = "指定時段與另一固定時段重疊"
                elif any(
                    other_slot.get("availability_id") == slot["availability_id"]
                    and other_task["task_id"] != task_id
                    for other_task, other_slot in manual_entries
                    if other_task["task_id"] not in fixed_by_task
                ):
                    reason = "指定時段與另一固定任務衝突"

        if reason:
            manual_conflict_ids.add(task_id)
            plan.append(_unscheduled(task, reason, previous, now))
        else:
            fixed_by_task.add(task_id)
            used_slots.add(slot["availability_id"])
            used_intervals.append((
                slot_start,
                slot_end,
            ))
            plan.append({
                "task_id": task_id,
                "availability_id": slot["availability_id"],
                "scheduled_start": _iso(scheduled_start),
                "status": "scheduled",
                "source": "manual",
                "reason": "",
                "unscheduled_alerted": False,
            })

    eligible = [
        task for task in tasks
        if task.get("status") == "pending"
        and task["task_id"] not in fixed_by_task
        and task["task_id"] not in manual_conflict_ids
    ]
    eligible.sort(
        key=lambda task: (
            task["deadline"],
            -_task_minutes(task),
            task["task_id"],
        )
    )

    for task in eligible:
        candidates = []
        for slot in availability:
            if slot.get("user_id") != task.get("user_id"):
                continue
            slot_id = slot["availability_id"]
            if slot_id in used_slots:
                continue
            try:
                start = _date_and_time(slot["date"], slot["start_time"])
                deadline = datetime.fromisoformat(task["deadline"] + "T23:59").replace(tzinfo=TZ)
                estimated = _task_minutes(task)
                available = int(slot["available_minutes"])
            except (KeyError, TypeError, ValueError):
                continue
            end = start + timedelta(minutes=available)
            scheduled_start = _effective_slot_start(start, end, now)
            if (
                scheduled_start is not None
                and end <= deadline
                and scheduled_start + timedelta(minutes=estimated) <= end
            ):
                if any(start < fixed_end and fixed_start < end for fixed_start, fixed_end in used_intervals):
                    continue
                remaining = int((end - scheduled_start).total_seconds() // 60) - estimated
                candidates.append((remaining, scheduled_start, slot_id, slot))

        if not candidates:
            plan.append(_unscheduled(task, "找不到足夠且不衝突的可用時段", previous, now))
            continue

        _, scheduled_start, slot_id, slot = min(
            candidates, key=lambda item: (item[0], item[1], item[2])
        )
        used_slots.add(slot_id)
        auto_start = _date_and_time(slot["date"], slot["start_time"])
        used_intervals.append((
            auto_start,
            auto_start + timedelta(minutes=int(slot["available_minutes"])),
        ))
        plan.append({
            "task_id": task["task_id"],
            "availability_id": slot_id,
            "scheduled_start": _iso(scheduled_start),
            "status": "scheduled",
            "source": "auto",
            "reason": "",
            "unscheduled_alerted": False,
        })

    completed_ids = {
        task["task_id"] for task in tasks if task.get("status") == "completed"
    }
    for task in tasks:
        if task["task_id"] in completed_ids:
            plan.append({
                "task_id": task["task_id"],
                "availability_id": "",
                "status": "unscheduled",
                "source": "auto",
                "reason": "任務已完成",
                "unscheduled_alerted": True,
            })

    for row in plan:
        if row["status"] == "unscheduled" and not row["unscheduled_alerted"]:
            old = previous.get(row["task_id"])
            if not old or old.get("status") == "scheduled":
                new_alerts.append(row["task_id"])

    return {"plan": plan, "new_alerts": new_alerts}


def _unscheduled(task: dict, reason: str, previous: dict, now: datetime) -> dict:
    old = previous.get(task["task_id"])
    previously_unscheduled = bool(old and old.get("status") == "unscheduled")
    return {
        "task_id": task["task_id"],
        "availability_id": "",
        "status": "unscheduled",
        "source": "manual" if task.get("preferred_availability_id") else "auto",
        "reason": reason,
        "unscheduled_alerted": bool(old and old.get("unscheduled_alerted")),
        "unscheduled_alert_id": (
            old.get("unscheduled_alert_id")
            if previously_unscheduled
            else f"unscheduled_{task['task_id']}_{now.strftime('%Y%m%d%H%M%S%f')}"
        ),
    }


def get_due_events(
    events: list[dict],
    now: datetime,
    reminders: list[dict],
) -> list[dict]:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    due = []
    existing = {
        (item.get("user_id"), item.get("event_id"), item.get("class_date")): item
        for item in reminders
        if item.get("kind") == "class_feedback"
        and item.get("status") in {"pending", "sent", "failed"}
    }

    for event in events:
        if event.get("event_type") != "class" or not event.get("enabled", True):
            continue
        weekday = int(event["weekday"])
        start = datetime.strptime(event["start_time"], "%H:%M").time()
        end = datetime.strptime(event["end_time"], "%H:%M").time()
        offset = max(0, min(60, int(event.get("offset_minutes", 0))))
        for days_back in range(8):
            date = (now - timedelta(days=days_back)).date()
            if date.isoweekday() != weekday:
                continue
            end_dt = datetime.combine(date, end, tzinfo=TZ) + timedelta(minutes=offset)
            class_date = date.isoformat()
            key = (event["user_id"], event["event_id"], class_date)
            old = existing.get(key)
            if old:
                if old.get("status") != "sent" and end_dt <= now:
                    due.append(dict(old))
            elif timedelta(0) <= now - end_dt <= timedelta(minutes=5):
                due.append({
                        "reminder_id": f"class_{event['event_id']}_{class_date}",
                        "user_id": event["user_id"],
                        "event_id": event["event_id"],
                        "task_id": "",
                        "availability_id": "",
                        "class_date": class_date,
                        "kind": "class_feedback",
                        "scheduled_at": _iso(end_dt),
                        "sent_at": "",
                        "status": "pending",
                        "retry_key": "",
                    })
            if end_dt <= now:
                break
    return due


def get_due_study_reminders(
    tasks: list[dict],
    plan: list[dict],
    availability: list[dict],
    users: list[dict],
    now: datetime,
    reminders: list[dict],
) -> list[dict]:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    enabled_users = {
        user["user_id"] for user in users
        if user.get("study_reminders_enabled", False)
        and user.get("line_user_id")
        and user.get("demo_status") not in ("pending_seed", "seeded_pending_auth")
    }
    existing = {
        (item.get("user_id"), item.get("task_id"), item.get("availability_id")): item
        for item in reminders
        if item.get("kind") == "study_session"
        and item.get("status") in {"pending", "sent", "failed"}
    }
    task_map = {(task.get("user_id"), task["task_id"]): task for task in tasks}
    slot_map = {(slot.get("user_id"), slot["availability_id"]): slot for slot in availability}
    due = []

    for row in plan:
        if row.get("status") != "scheduled":
            continue
        owner = row.get("user_id")
        if owner is None:
            # Legacy plan rows without owner may be resolved only if unambiguous.
            owners = {uid for uid, tid in task_map if tid == row["task_id"]}
            if len(owners) != 1:
                continue
            owner = next(iter(owners))
        task = task_map.get((owner, row["task_id"]))
        slot = slot_map.get((owner, row["availability_id"]))
        if not task or not slot or task.get("status") != "pending":
            continue
        user_id = task["user_id"]
        if user_id not in enabled_users:
            continue
        key = (user_id, task["task_id"], slot["availability_id"])
        old = existing.get(key)
        if old and old.get("status") == "sent":
            continue
        start = _scheduled_start(row, slot)
        if old:
            if old.get("status") != "sent" and start <= now:
                due.append(dict(old))
            continue
        if start <= now and start >= now - timedelta(minutes=5):
            due.append({
                "reminder_id": f"study_{task['task_id']}_{slot['availability_id']}",
                "user_id": user_id,
                "event_id": "",
                "task_id": task["task_id"],
                "availability_id": slot["availability_id"],
                "class_date": "",
                "kind": "study_session",
                "scheduled_at": _iso(start),
                "sent_at": "",
                "status": "pending",
                "retry_key": "",
            })
    return due


def get_due_study_checkins(
    tasks: list[dict],
    plan: list[dict],
    availability: list[dict],
    users: list[dict],
    now: datetime,
    reminders: list[dict],
) -> list[dict]:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    enabled_users = {
        user["user_id"] for user in users
        if user.get("study_reminders_enabled", False) and user.get("line_user_id")
        and user.get("demo_status") not in ("pending_seed", "seeded_pending_auth")
    }
    existing = {
        (item.get("user_id"), item.get("task_id"), item.get("availability_id")): item
        for item in reminders
        if item.get("kind") == "study_session_checkin"
        and item.get("status") in {"pending", "sent", "failed"}
    }
    task_map = {(task.get("user_id"), task["task_id"]): task for task in tasks}
    slot_map = {(slot.get("user_id"), slot["availability_id"]): slot for slot in availability}
    due = []

    for row in plan:
        if row.get("status") != "scheduled":
            continue
        task = task_map.get(row.get("task_id"))
        slot = slot_map.get(row.get("availability_id"))
        if not task or not slot or task.get("status") != "pending":
            continue
        user_id = task.get("user_id")
        if user_id not in enabled_users:
            continue

        key = (user_id, task["task_id"], slot["availability_id"])
        old = existing.get(key)
        if old and old.get("status") == "sent":
            continue
        start = _scheduled_start(row, slot)
        session_end = start + timedelta(minutes=_task_minutes(task))
        if old:
            if old.get("status") != "sent" and session_end <= now:
                due.append(dict(old))
            continue
        if session_end <= now and session_end >= now - timedelta(minutes=5):
            due.append({
                "reminder_id": f"checkin_{task['task_id']}_{slot['availability_id']}",
                "user_id": user_id,
                "event_id": "",
                "task_id": task["task_id"],
                "availability_id": slot["availability_id"],
                "class_date": "",
                "kind": "study_session_checkin",
                "scheduled_at": _iso(session_end),
                "sent_at": "",
                "status": "pending",
                "progress_status": "awaiting_response",
                "retry_key": "",
            })
    return due
