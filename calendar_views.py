"""唯讀日／週／月檢視的事件投影；不執行排程或寫入 JSON。"""
from __future__ import annotations

from calendar_events import build_calendar_events

VIEWS = {
    "日": "timeGridDay",
    "週": "timeGridWeek",
    "月": "dayGridMonth",
}
MIN_HOUR = 8
MAX_HOUR = 24


def overview_events(
    courses: list[dict], availability: list[dict], tasks: list[dict],
    plan: list[dict], external_events: list[dict],
) -> list[dict]:
    """只顯示課程、既有讀書計畫、外部事件，移除過時的空閒 Standby 方塊。"""
    base = build_calendar_events(courses, availability, tasks, plan)
    result = [
        event for event in base
        if (event.get("extendedProps") or {}).get("kind") != "availability"
    ]
    for event in external_events:
        if not all(event.get(k) for k in ("id", "start", "end")):
            continue
        result.append({
            "id": event["id"],
            "title": "外部｜" + str(event.get("title") or "未命名事件"),
            "start": event["start"],
            "end": event["end"],
            "color": "#C88A21",
            "extendedProps": {"kind": "external", "external_id": event["id"]},
        })
    return result


def view_options(view: str) -> dict:
    """支援 30 分鐘閱讀與排程，並隱藏 All-day 欄位。"""
    if view not in VIEWS:
        raise ValueError("未知日曆檢視")
    return {
        "initialView": VIEWS[view],
        "headerToolbar": {
            "left": "prev,next today", "center": "title", "right": "",
        },
        "firstDay": 1,
        "locale": "zh-tw",
        "timeZone": "Asia/Taipei",
        "allDaySlot": False,
        "slotMinTime": "08:00:00",
        "slotMaxTime": "24:00:00",
        "slotDuration": "00:30:00",
        "slotLabelInterval": "01:00:00",
        "snapDuration": "00:30:00",
        "nowIndicator": True,
        "editable": False,
        "selectable": False,
        "height": 660,
        "eventTimeFormat": {
            "hour": "2-digit", "minute": "2-digit", "hour12": False,
        },
    }
