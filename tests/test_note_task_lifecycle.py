"""First-principles regression: one source question → one confirmed, schedulable task."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import storage
from storage import DataError
from note_tasks import (
    extract_questions, candidate_tasks, confirm_question_task, assign_note_course,
    next_class_start,
)
from week_planner import board_payload, place_manual, resize_scheduled, fill_remaining
from calendar_events import build_calendar_events
from ai_assistant import generate_question_actions, AIError

TZ=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,27,7,30,tzinfo=TZ)
USER="demo_user_001"


@pytest.fixture
def db(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,"DATA_DIR",tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name),[])
    return tmp_path


def event(eid="e1",weekday=5,start="09:00",title="控制系統"):
    return {
        "event_id":eid,"user_id":USER,"event_type":"class",
        "title":title,"weekday":weekday,"start_time":start,"end_time":"11:00",
        "offset_minutes":10,"prompt_template":"class_feedback","enabled":True,
    }


def note(fid="f1",event_id="e1",content="Routh 全零列怎麼判？為什麼根可能在虛軸？"):
    return {
        "feedback_id":fid,"user_id":USER,"event_id":event_id,
        "class_date":"2026-11-20","received_at":NOW.isoformat(),
        "content":content,"topic_tags":["Routh"],
        "progress":3,"source":"selected","webhook_event_id":"web-"+fid,
    }


def task(tid="fixed",minutes=60):
    return {
        "task_id":tid,"user_id":USER,"subject":"控制系統","title":tid,
        "deadline":"2026-12-03","estimated_minutes":minutes,
        "status":"pending","preferred_availability_id":"",
    }


def test_two_question_marks_two_distinct_candidates_and_confirmation(db):
    n=note()
    storage.save_json(storage.data_path("events"),[event()])
    storage.save_json(storage.data_path("feedback"),[n])
    qs=extract_questions(n)
    assert len(qs)==2
    suggestions=candidate_tasks([n],[event()],[],USER,NOW)
    assert len(suggestions)==2
    assert len({x["source_question_key"] for x in suggestions})==2
    assert all(x["estimated_minutes"]==30 for x in suggestions)
    assert all(x["subject"]=="控制系統" for x in suggestions)
    # NOW Friday 07:30, next class starts 09:00 the same day.
    assert all(x["deadline_at"].startswith("2026-11-27T09:00") for x in suggestions)
    first=confirm_question_task(USER,suggestions[0],NOW)
    assert first["deadline_at"].startswith("2026-11-27T09:00")
    assert first["source_feedback_id"]=="f1"
    with pytest.raises(DataError,match="已新增"):
        confirm_question_task(USER,suggestions[0],NOW)
    second=confirm_question_task(USER,suggestions[1],NOW)
    assert len(storage.load_json(storage.data_path("tasks")))==2
    board=board_payload(USER,NOW)
    assert len(board["tasks"])==2
    assert all(t["is_ai"] and t["minutes"]==30 for t in board["tasks"])
    # First task fits 08:00–08:30, second 08:30–09:00, both before class.
    a=place_manual(USER,first["task_id"],"2026-11-27","1",1,NOW,duration_minutes=30)
    b=place_manual(USER,second["task_id"],"2026-11-27","1+",1,NOW,duration_minutes=30)
    assert a["scheduled_minutes"]==b["scheduled_minutes"]==30
    assert b["scheduled_start"].endswith("08:30+08:00")
    assert all(t["is_ai"] for t in board_payload(USER,NOW)["scheduled"])
    with pytest.raises(DataError,match="Deadline"):
        place_manual(USER,first["task_id"],"2026-11-27","2",1,NOW,duration_minutes=30)


def test_question_tag_without_question_marks_is_split_per_line(db):
    n=note(content="Routh 全零列\n分析穩定度條件")
    n["topic_tags"]=["疑問","控制系統"]
    assert extract_questions(n)==["Routh 全零列","分析穩定度條件"]
    n["ai_analysis"]={"unresolved_questions":["還有哪個例外?"]}
    assert len(extract_questions(n))==1  # explicit AI question takes priority


def test_inbox_requires_classification_and_isolation(db):
    n=note(event_id="inbox")
    storage.save_json(storage.data_path("feedback"),[n])
    storage.save_json(storage.data_path("events"),[event()])
    candidates=candidate_tasks([n],[event()],[],USER,NOW)
    assert candidates[0]["needs_classification"]
    with pytest.raises(DataError,match="未分類"):
        confirm_question_task(USER,candidates[0],NOW)
    with pytest.raises(DataError,match="不存在"):
        assign_note_course("other","f1","e1")
    assign_note_course(USER,"f1","e1")
    edited=storage.load_json(storage.data_path("feedback"))[0]
    assert edited["event_id"]=="e1"
    confirmed=confirm_question_task(USER,
        candidate_tasks([edited],[event()],[],USER,NOW)[0],NOW)
    assert confirmed["subject"]=="控制系統"


def test_one_explicit_question_per_ai_analysis_and_no_duplication(db):
    n=note(content="本週很多重點要讀。")
    n["ai_analysis"]={"unresolved_questions":["Q1","Q2","Q2"],"suggested_task":"整理筆記"}
    assert extract_questions(n)==["Q1","Q2"]
    n["content"]="Routh 根位置？"
    assert len(extract_questions(n))==3


def test_scheduled_resize_conflict_and_thirty_minute_accurate_color(db):
    storage.save_json(storage.data_path("tasks"),[task("a"),task("b")])
    first=place_manual(USER,"a","2026-11-27","1",1,NOW,duration_minutes=30)
    second=place_manual(USER,"b","2026-11-27","1+",1,NOW,duration_minutes=30)
    with pytest.raises(DataError,match="衝突"):
        resize_scheduled(USER,"a",60,NOW)
    assert storage.load_json(storage.data_path("plan"))==[first,second]
    resize_scheduled(USER,"b",60,NOW)
    board=board_payload(USER,NOW)
    assert next(x for x in board["scheduled"] if x["task_id"]=="b")["minutes"]==60
    assert next(x for x in board["scheduled"] if x["task_id"]=="a")["minutes"]==30
    events=build_calendar_events([],storage.load_json(storage.data_path("availability")),
                    storage.load_json(storage.data_path("tasks")),
                    storage.load_json(storage.data_path("plan")))
    e=next(e for e in events if e["id"]=="study-a")
    assert e["end"].startswith("2026-11-27T08:30")


def test_auto_fill_preserves_30_minute_duration_and_exact_deadline(db):
    n=note()
    storage.save_json(storage.data_path("events"),[event()])
    storage.save_json(storage.data_path("feedback"),[n])
    suggestions=candidate_tasks([n],[event()],[],USER,NOW)
    for s in suggestions:
        confirm_question_task(USER,s,NOW)
    outcome=fill_remaining(USER,NOW)
    assert len(outcome["placed"])==2
    assert {entry["scheduled_minutes"] for entry in outcome["placed"]}=={30}
    assert all(entry["scheduled_start"][:10]=="2026-11-27" for entry in outcome["placed"])


def test_model_generation_is_per_question_and_refuses_missing_or_extra(monkeypatch):
    candidates=[
        {"source_question_key":"k1","question":"何謂等效電阻？","subject":"電子學"},
        {"source_question_key":"k2","question":"Routh 零列如何處理？","subject":"控制系統"},
    ]
    monkeypatch.setenv("OPENAI_API_KEY","mock-key")
    monkeypatch.setenv("OPENAI_MODEL","mock-model")
    def simulated(payload,key):
        assert payload["store"] is False
        assert len(payload["input"])>0
        return {"actions":[
            {"source_question_key":"k1","review_action":"用一個例題比較電阻"},
            {"source_question_key":"k2","review_action":"練習 Routh 零列判別"},
        ]}
    import ai_assistant
    monkeypatch.setattr(ai_assistant,"_request_structured_output",simulated)
    result=generate_question_actions(candidates)
    assert len(result)==2 and result["k1"]=="用一個例題比較電阻"
    monkeypatch.setattr(ai_assistant,"_request_structured_output",
                        lambda *args:{"actions":[{"source_question_key":"k1",
                                                    "review_action":"僅回傳一題"}]})
    with pytest.raises(AIError,match="每個疑問"):
        generate_question_actions(candidates)
