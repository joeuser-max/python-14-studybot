"""Reviewable LINE backend integration tests; no real API or push involved."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import line_study_ai
import line_bot
import storage
from storage import DataError
from week_planner import place_manual, board_payload

TZ=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,27,7,30,tzinfo=TZ)
U="demo_user_001"


@pytest.fixture
def db(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,"DATA_DIR",tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name),[])
    return tmp_path


def _task(tid,source_feedback_id=""):
    return {"task_id":tid,"user_id":U,"subject":"控制系統","title":"學習任務",
            "status":"pending","deadline":"2026-11-30",
            "estimated_minutes":60,"preferred_availability_id":"",
            "source_feedback_id":source_feedback_id}


def test_study_ai_requires_opt_in_and_preserves_original(db,monkeypatch):
    record={"feedback_id":"f1","user_id":U,"content":"今天學了 Routh 判別。"}
    storage.save_json(storage.data_path("feedback"),[record])
    task=_task("task","f1")
    monkeypatch.setattr(line_study_ai,"organize_class_feedback",
        lambda *args: pytest.fail("opt-out must never call the model"))
    text=line_study_ai.study_start_message(task,{"user_id":U,"ai_after_class_enabled":False},[record])
    assert "讀書時段開始" in text
    assert "AI 根據" not in text
    assert storage.load_json(storage.data_path("feedback"))[0]==record


def test_study_ai_caches_summary_in_learning_library(db,monkeypatch):
    record={"feedback_id":"f1","user_id":U,"content":"Routh與根的位置"}
    storage.save_json(storage.data_path("feedback"),[record])
    task=_task("task","f1")
    calls=[]
    analysis={"summary":"Routh 穩定度","key_points":["全正系數不一定穩定"],
        "unresolved_questions":["有全零列怎麼辦"],"topic_tags":["控制系統"],
        "suggested_task":"完成一組 Routh 題目","estimated_minutes":45}
    def analyze(note,subject):
        calls.append((note["feedback_id"],subject))
        return analysis
    monkeypatch.setattr(line_study_ai,"organize_class_feedback",analyze)
    user={"user_id":U,"ai_after_class_enabled":True}
    first=line_study_ai.study_start_message(task,user,[record])
    assert "Routh 穩定度" in first
    assert calls==[("f1","控制系統")]
    cached=storage.load_json(storage.data_path("feedback"))[0]
    assert cached["ai_analysis"]["summary"]=="Routh 穩定度"
    again=line_study_ai.study_start_message(task,user,[cached])
    assert "Routh 穩定度" in again and len(calls)==1


def test_line_unfinished_replans_only_selected_task(db):
    storage.save_json(storage.data_path("tasks"),[_task("a"),_task("b")])
    first=place_manual(U,"a","2026-11-27","2",1,NOW)
    stable=place_manual(U,"b","2026-11-27","3",1,NOW)
    # Simulate the explicit LINE remaining-minutes reply.
    storage.update_task({**_task("a"),"remaining_minutes":60})
    result=line_bot._replan_user_tasks(U,NOW,changed_task_id="a")
    assert len(result)==1
    assert result[0]["task_id"]=="a"
    assert result[0]["source"]=="auto"
    plan=storage.load_json(storage.data_path("plan"))
    assert len(plan)==2
    assert next(row for row in plan if row["task_id"]=="b")==stable
    assert result[0]["scheduled_start"]!=first["scheduled_start"]


def test_line_complete_unplaces_only_selected_task(db):
    storage.save_json(storage.data_path("tasks"),[_task("a"),_task("b")])
    place_manual(U,"a","2026-11-27","2",1,NOW)
    pinned=place_manual(U,"b","2026-11-27","3",1,NOW)
    storage.update_task({**_task("a"),"status":"completed"})
    assert line_bot._replan_user_tasks(U,NOW,"a")==[]
    assert storage.load_json(storage.data_path("plan"))==[pinned]
