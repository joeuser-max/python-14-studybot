"""V2 綠色排程靶：可用時間 ∩ 使用者明確標記的偏好，不是硬限制。

選擇何時要排程才進入畫筆模式；標記不依固定週期自動清除。
已過期、被課程/行程/計畫佔用的標記不在畫面顯示，也不參與計分。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from storage import DataError, TZ, data_path, load_json, update_json
from week_planner import PERIOD_BY_LABEL, _busy, _read_all, _start, _overlap, rolling_dates


def available_preference_cells(user_id: str, now: datetime | None = None,
                               records: dict | None = None) -> set[tuple[str, str]]:
    """Returns only valid green cells, honoring *current* calendar occupancy."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    records = records or _read_all()
    week = set(rolling_dates(now))
    visible = set()
    for row in load_json(data_path("preference_targets")):
        if row.get("user_id") != user_id:
            continue
        try:
            day = date.fromisoformat(row["date"])
            label = row["period"]
            if day not in week or label not in PERIOD_BY_LABEL:
                continue
            start = _start(day, label)
            end = start + timedelta(hours=1)
            if start <= now:
                continue
            occupied = _busy(
                records["events"], records["external_events"], records["tasks"],
                records["availability"], records["plan"], day, user_id,
            )
            if not any(_overlap(start, end, a, b) for a, b in occupied):
                visible.add((day.isoformat(), label))
        except (KeyError, ValueError, TypeError):
            continue
    return visible


def mark_preferences(user_id: str, cells: Iterable[dict], enabled: bool,
                     now: datetime | None = None) -> dict:
    """Validate batch against availability before atomic JSON write; no task moves."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    batch = list(cells)
    if not 1 <= len(batch) <= 112 or type(enabled) is not bool:
        raise DataError("偏好畫筆一次須指定 1–112 格，且指定新增或清除")
    records = _read_all()
    week = set(rolling_dates(now))
    valid = set()
    for item in batch:
        if not isinstance(item, dict):
            raise DataError("偏好格格式不合法")
        try:
            day = date.fromisoformat(item["date"])
            period = item["period"]
            start = _start(day, period)
        except (KeyError, ValueError, TypeError) as exc:
            raise DataError("偏好時間格式不合法") from exc
        if day not in week or start <= now:
            # Ignore past dates, even if an outdated browser tries to write them.
            continue
        end = start + timedelta(hours=1)
        if enabled:
            occupied = _busy(
                records["events"], records["external_events"], records["tasks"],
                records["availability"], records["plan"], day, user_id,
            )
            if any(_overlap(start, end, a, b) for a, b in occupied):
                continue
        valid.add((day.isoformat(), period))
    def change(rows):
        result = [
            row for row in rows
            if not (row.get("user_id") == user_id
                    and (row.get("date"), row.get("period")) in valid)
        ]
        if enabled:
            result.extend({
                "user_id": user_id, "date": day, "period": label,
                "created_at": now.isoformat(timespec="seconds"),
            } for day, label in sorted(valid))
        return result
    update_json(data_path("preference_targets"), change)
    return {"updated": len(valid), "enabled": enabled}


def clear_preferences(user_id: str) -> int:
    current = load_json(data_path("preference_targets"))
    count = sum(row.get("user_id") == user_id for row in current)
    update_json(data_path("preference_targets"), lambda rows: [
        row for row in rows if row.get("user_id") != user_id
    ])
    return count


def preference_overlap(start: datetime, end: datetime,
                       cells: set[tuple[str, str]]) -> float:
    """Green hours = total unique interval intersection, at 30-minute precision."""
    overlap=0.0
    for day, label in cells:
        if label not in PERIOD_BY_LABEL:
            continue
        try:
            slot=datetime.combine(date.fromisoformat(day),
                                  time(PERIOD_BY_LABEL[label]),tzinfo=TZ)
        except ValueError:
            continue
        actual_start=max(start,slot)
        actual_end=min(end,slot+timedelta(hours=1))
        if actual_end>actual_start:
            overlap+=(actual_end-actual_start).total_seconds()/3600
    return overlap
