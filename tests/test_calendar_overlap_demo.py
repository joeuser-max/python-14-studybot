"""FullCalendar 變更必須跳出課程衝突 Modal；展示種子符合課表與完成紀錄。"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import storage
from demo_data import DEMO_USER_ID, sample_records
from progress_insights import history_series
from streamlit.testing.v1 import AppTest
from visual_planner import class_conflicts, propose_placement

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_uploaded_timetable_demo_includes_real_class_blocks():
    """截圖只有課程時間資料會進入展示 JSON，不應混入學生身分資訊。"""
    now = datetime.now(storage.TZ)
    records = sample_records(now)
    assert len(records["events"]) == 14
    classes = {(c["title"], c["weekday"], c["start_time"], c["end_time"])
               for c in records["events"]}
    assert ("電子學 III", 1, "09:00", "11:50") in classes
    assert ("程式設計-Python", 1, "18:00", "20:50") in classes
    assert ("深度學習系統設計與應用", 2, "09:00", "11:50") in classes
    assert ("控制系統", 3, "13:00", "13:50") in classes
    assert ("先進記憶體元件物理與製造技術", 4, "14:00", "16:50") in classes
    assert ("專題實作", 6, "13:00", "15:50") in classes
    assert len({c["event_id"] for c in records["events"]}) == len(records["events"])
    assert all(c.get("room") for c in records["events"])


def test_history_has_more_completed_real_demo_records():
    now = datetime.now(storage.TZ)
    records = sample_records(now)
    completed = [t for t in records["tasks"] if t["status"] == "completed"]
    assert len(completed) >= 8
    assert len(records["progress_events"]) >= 8
    day = history_series(records["progress_events"], records["tasks"],
                         DEMO_USER_ID, "1D", now)
    week = history_series(records["progress_events"], records["tasks"],
                          DEMO_USER_ID, "1W", now)
    month = history_series(records["progress_events"], records["tasks"],
                           DEMO_USER_ID, "1M", now)
    assert day["completed"] >= 1
    assert week["completed"] >= 3
    assert month["completed"] >= 8
    assert month["completed"] >= week["completed"] >= day["completed"]


def test_partial_overlap_is_detected_and_adjacent_is_not():
    now = datetime.now(storage.TZ)
    records = sample_records(now)
    monday = now.date() + timedelta(days=((1 - now.isoweekday()) % 7 or 7))
    course = next(c for c in records["events"]
                  if c["event_id"] == "demo_class_electronics")
    start = datetime.combine(monday, datetime.strptime("10:30", "%H:%M").time(),
                             storage.TZ)
    end = start + timedelta(minutes=45)
    found = class_conflicts([course], start, end, DEMO_USER_ID)
    assert [c["event_id"] for c in found] == [course["event_id"]]
    adjacent = datetime.combine(monday, datetime.strptime("11:50", "%H:%M").time(),
                                storage.TZ)
    assert class_conflicts([course], adjacent,
                           adjacent + timedelta(minutes=15), DEMO_USER_ID) == []


def test_conflicting_schedule_requires_reason_before_writing():
    now = datetime.now(storage.TZ)
    records = sample_records(now)
    monday = now.date() + timedelta(days=((1 - now.isoweekday()) % 7 or 7))
    begin = datetime.combine(monday, datetime.strptime("09:30", "%H:%M").time(),
                             storage.TZ)
    choice = propose_placement(records["tasks"], records["availability"],
                               records["plan"], records["events"],
                               DEMO_USER_ID, "demo_task_electronics",
                               begin, begin + timedelta(minutes=45), now)
    assert "電子學 III" in [course["title"] for course in choice["classes"]]


def test_overlap_confirmation_is_dialog_in_actual_streamlit_page(monkeypatch, tmp_path):
    """模擬日曆送入的變更：確認訊息一定在 Dialog 內，而非時間表下方。"""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)

    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    app.sidebar.toggle[0].set_value(True).run(timeout=30)
    app.sidebar.radio[0].set_value("時間規劃").run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    now = datetime.now(storage.TZ)
    monday = now.date() + timedelta(days=((1 - now.isoweekday()) % 7 or 7))
    begin = datetime.combine(monday, datetime.strptime("09:15", "%H:%M").time(),
                             storage.TZ)
    app.session_state["cp_pending_timesheet"] = {
        "kind": "place", "task_id": "demo_task_electronics",
        "start": begin, "end": begin + timedelta(minutes=45),
    }
    app.run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    assert any(r.label == "重疊部分是否要覆蓋？" for r in app.radio)
    assert any("電子學 III" in t.value for t in app.markdown)
    confirm = next(b for b in app.button if b.label == "確認覆蓋並儲存")
    assert confirm.disabled

    answer = next(r for r in app.radio if r.label == "重疊部分是否要覆蓋？")
    answer.set_value("覆蓋課程時段（需說明原因）").run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    reason = next(r for r in app.radio if r.label == "請選擇原因")
    reason.set_value("請假").run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    confirm = next(b for b in app.button if b.label == "確認覆蓋並儲存")
    assert not confirm.disabled
    confirm.click().run(timeout=30)
    assert not app.exception, [str(e) for e in app.exception]
    saved_plan = storage.load_json(tmp_path / "demo" / "plan.json")
    assigned = next(row for row in saved_plan
                    if row["task_id"] == "demo_task_electronics")
    assert assigned["status"] == "scheduled"
    assert assigned["class_override"] == "請假"
    slots = storage.load_json(tmp_path / "demo" / "availability.json")
    saved_slot = next(slot for slot in slots
                      if slot["availability_id"] == assigned["availability_id"])
    assert saved_slot["start_time"] == "09:15"
    assert saved_slot["available_minutes"] == 45
