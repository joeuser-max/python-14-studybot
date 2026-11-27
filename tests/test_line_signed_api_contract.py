"""Signed Flask LINE webhook and push contract, without real credentials or network.

This exercises the real repository's LINE code (based on joeuser-max),
not the Streamlit imitation. External HTTP responses are deliberately mocked.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import hashlib
import hmac
import json

import pytest
import storage
import line_bot
import reminder_worker


@pytest.fixture
def line_setup(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DATA_DIR",tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name),[])
    monkeypatch.setenv("LINE_CHANNEL_SECRET","test-secret")
    monkeypatch.setenv("LINE_BINDING_CODE","4321")
    sent=[]
    monkeypatch.setattr(line_bot,"reply_line_message",
                        lambda token,text,choices=None:sent.append((token,text,choices)))
    return line_bot.create_app().test_client(),sent


def signed(client,events,key="test-secret"):
    raw=json.dumps({"events":events},ensure_ascii=False).encode("utf-8")
    digest=base64.b64encode(hmac.new(key.encode(),raw,hashlib.sha256).digest()).decode()
    return client.post("/webhook",data=raw,
                       headers={"X-Line-Signature":digest,
                                "Content-Type":"application/json"})


def message(uid,ev_id,text):
    return {"type":"message","webhookEventId":ev_id,
            "replyToken":"token-"+ev_id,
            "source":{"type":"user","userId":uid},
            "message":{"type":"text","id":"msg-"+ev_id,"text":text}}


def test_signature_binding_quick_note_duplicate_and_search(line_setup):
    client,replies=line_setup
    payload=[message("U123","bind","綁定 4321")]
    assert signed(client,payload,"WRONG").status_code==401
    assert storage.load_json(storage.data_path("users"))==[]
    assert signed(client,payload).status_code==200
    users=storage.load_json(storage.data_path("users"))
    assert len(users)==1 and users[0]["line_user_id"]=="U123"
    assert "已綁定" in replies[-1][1]
    n=message("U123","n1","筆記 Routh 全零列該如何處理？")
    assert signed(client,[n]).status_code==200
    assert signed(client,[n]).status_code==200
    assert len(storage.load_json(storage.data_path("feedback")))==1
    assert len(storage.load_json(storage.data_path("processed_webhooks")))==2
    assert signed(client,[message("U123","query","搜尋 Routh")]).status_code==200
    assert "Routh" in replies[-1][1]
    # Another unbound LINE user cannot see the first user's notes.
    assert signed(client,[message("U666","unbound","查看筆記")]).status_code==200
    assert "尚未綁定" in replies[-1][1]


def test_signed_webhook_file_import_rejects_invalid_extension(line_setup,monkeypatch):
    client,replies=line_setup
    signed(client,[message("U123","bind","綁定 4321")])
    called=[]
    monkeypatch.setattr(line_bot,"download_line_file",
                        lambda msg_id,size:called.append(msg_id) or b"hello")
    incoming={"type":"message","webhookEventId":"f1","replyToken":"file-reply",
              "source":{"type":"user","userId":"U123"},
              "message":{"type":"file","id":"file-1","fileName":"bad.exe","fileSize":2}}
    assert signed(client,[incoming]).status_code==200
    assert not called
    assert not storage.load_json(storage.data_path("feedback"))
    assert "僅支援" in replies[-1][1]

    incoming2={**incoming,"webhookEventId":"f2",
               "message":{**incoming["message"],"fileName":"notes.txt"}}
    monkeypatch.setattr(line_bot,"extract_text",
                        lambda filename,raw:"需要理解 Fourier 對偶性？")
    assert signed(client,[incoming2]).status_code==200
    stored=storage.load_json(storage.data_path("feedback"))
    assert len(stored)==1 and stored[0]["attachment_filename"]=="notes.txt"
    assert len(called)==1


def test_push_uses_idempotency_retry_key_without_network(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN","fake-token")
    seen=[]
    class Fake:
        def raise_for_status(self):
            return None
    def fake_post(url,**kwargs):
        seen.append((url,kwargs))
        return Fake()
    monkeypatch.setattr(reminder_worker.requests,"post",fake_post)
    user={"user_id":"demo_user_001","line_user_id":"U123"}
    reminder={"reminder_id":"r1","retry_key":"123e4567-e89b-42d3-a456-426614174000"}
    assert reminder_worker.push_line_message(user,reminder,"課後補筆記提醒")
    assert reminder_worker.push_line_message(user,reminder,"課後補筆記提醒")
    assert seen[0][1]["headers"]["X-Line-Retry-Key"]==seen[1][1]["headers"]["X-Line-Retry-Key"]
    assert seen[0][1]["headers"]["Authorization"]=="Bearer fake-token"
    assert seen[0][1]["json"]["to"]=="U123"
    # This tests payload and HTTP contract; it is NOT a real delivered LINE push.


def test_openai_and_line_real_network_are_not_falsely_claimed(monkeypatch):
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN",raising=False)
    assert reminder_worker.push_line_message(
        {"line_user_id":"U123"},{"reminder_id":"test"},"hello") is False



def test_signed_line_ai_questions_need_separate_acceptances(line_setup,monkeypatch):
    from datetime import datetime,timedelta
    from zoneinfo import ZoneInfo
    from week_planner import board_payload

    client,replies=line_setup
    now=datetime.now(ZoneInfo("Asia/Taipei"))
    weekday=now.isoweekday()
    storage.save_json(storage.data_path("events"),[{
        "event_id":"class-ai","user_id":"demo_user_001",
        "event_type":"class","title":"電子學（三）",
        "weekday":weekday,"start_time":"09:00","end_time":"11:00",
        "offset_minutes":10,"prompt_template":"class_feedback","enabled":True,
    }])
    storage.save_json(storage.data_path("users"),[{
        "user_id":"demo_user_001","line_user_id":"U123",
        "reminders_enabled":True,"study_reminders_enabled":True,
        "ai_after_class_enabled":True,
    }])
    storage.save_json(storage.data_path("pending_notes"),[{
        "user_id":"demo_user_001","stage":"note","event_id":"class-ai",
        "class_date":now.date().isoformat(),"progress":3,
        "expires_at":(now+timedelta(minutes=10)).isoformat(),
    }])
    result={
        "summary":"課程電路模型","key_points":["回授電路","極點"],
        "unresolved_questions":["Miller Effect 是什麼？","相位裕度如何計算？"],
        "topic_tags":["Miller","相位裕度"],"suggested_task":"整理兩個疑問",
        "estimated_minutes":60,
    }
    monkeypatch.setattr(line_bot,"organize_class_feedback",
                        lambda *args:result)
    assert signed(client,[message("U123","class-note","記錄兩個疑問。")]).status_code==200
    assert len(storage.load_json(storage.data_path("tasks")))==0
    pending=storage.load_json(storage.data_path("pending_notes"))
    assert pending[0]["stage"]=="ai_question_confirmation"
    assert len(pending[0]["questions"])==2
    assert signed(client,[message("U123","confirm-q1","加入讀書任務")]).status_code==200
    tasks=storage.load_json(storage.data_path("tasks"))
    assert len(tasks)==1
    assert tasks[0]["estimated_minutes"]==30
    assert tasks[0]["source_question_key"]
    assert tasks[0]["subject"]=="電子學（三）"
    assert tasks[0]["deadline_at"]
    assert board_payload("demo_user_001")["tasks"][0]["is_ai"] is True
    assert storage.load_json(storage.data_path("pending_notes"))[0]["question_index"]==1
    assert signed(client,[message("U123","skip-q2","先不用")]).status_code==200
    assert len(storage.load_json(storage.data_path("tasks")))==1
    assert storage.load_json(storage.data_path("pending_notes"))==[]
    assert storage.load_json(storage.data_path("plan"))==[]
