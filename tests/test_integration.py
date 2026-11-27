"""保留 main 回歸保障，調整為 btesting 的 LINE 互動介面。"""
import base64
import hashlib
import hmac
from io import BytesIO
import json
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import line_bot
import reminder_worker
import storage
from scheduler import get_due_events, get_due_study_reminders

TZ = ZoneInfo("Asia/Taipei")


def _post_signed(client, secret, event):
    body = json.dumps({"events": [event]}, ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode("ascii")
    return client.post(
        "/webhook", data=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def _event(event_id, text, user_id="U123"):
    return {"webhookEventId": event_id, "type": "message", "replyToken": event_id,
            "source": {"type": "user", "userId": user_id},
            "message": {"type": "text", "text": text}}


def _minimal_pdf(text):
    stream = f"BT /F1 12 Tf 50 200 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(map(len, chunks)))
        chunks.extend([f"{index} 0 obj\n".encode("ascii"), obj, b"\nendobj\n"])
    xref_offset = sum(map(len, chunks))
    chunks.append(b"xref\n0 6\n0000000000 65535 f \n")
    chunks.extend(
        f"{offset:010d} 00000 n \n".encode("ascii")
        for offset in offsets[1:]
    )
    chunks.append(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    )
    return b"".join(chunks)


def test_failed_study_reminder_retry_does_not_crash():
    when = datetime(2026, 11, 23, 19, tzinfo=TZ)
    tasks = [{"task_id": "t1", "user_id": "demo_user_001", "status": "pending"}]
    slots = [{"availability_id": "a1", "user_id": "demo_user_001", "date": "2026-11-23",
              "start_time": "19:00", "available_minutes": 60}]
    plan = [{"task_id": "t1", "availability_id": "a1", "status": "scheduled"}]
    users = [{"user_id": "demo_user_001", "line_user_id": "U123",
              "study_reminders_enabled": True}]
    failed = [{"reminder_id": "r1", "user_id": "demo_user_001", "task_id": "t1",
               "availability_id": "a1", "kind": "study_session", "status": "failed"}]
    due = get_due_study_reminders(tasks, plan, slots, users, when, failed)
    assert len(due) == 1
    assert due[0]["reminder_id"] == "r1"


def test_class_end_reminder_is_sent_when_end_time_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    event = {
        "event_id": "class-1",
        "user_id": "user-1",
        "event_type": "class",
        "title": "控制系統",
        "weekday": 5,
        "start_time": "12:00",
        "end_time": "13:17",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }
    user = {
        "user_id": "user-1",
        "line_user_id": "LINE-USER",
        "reminders_enabled": True,
    }
    previous_reminder = {
        "reminder_id": "class_class-1_2026-11-27",
        "user_id": "user-1",
        "event_id": "class-1",
        "class_date": "2026-11-27",
        "kind": "class_feedback",
        "scheduled_at": "2026-11-27T12:54+08:00",
        "status": "sent",
        "sent_at": "2026-11-27T12:54+08:00",
    }
    for name in ("tasks", "plan", "availability"):
        storage.save_json(storage.data_path(name), [])
    storage.save_json(storage.data_path("events"), [event])
    storage.save_json(storage.data_path("users"), [user])
    storage.save_json(storage.data_path("reminders"), [previous_reminder])

    pushed = []
    monkeypatch.setattr(
        reminder_worker,
        "push_line_message",
        lambda target, reminder, text: pushed.append((reminder, text)) or True,
    )
    now = datetime(2026, 11, 27, 13, 18, tzinfo=TZ)
    attempted = reminder_worker.run_reminder_worker_once(now)

    assert len(attempted) == 1
    assert attempted[0]["scheduled_at"] == "2026-11-27T13:17+08:00"
    assert attempted[0]["reminder_id"] != previous_reminder["reminder_id"]
    assert "控制系統" in pushed[0][1]
    assert "補筆記" in pushed[0][1]
    assert line_bot._find_class_reminder("user-1", "class-1", "2026-11-27") == attempted[0]["reminder_id"]
    assert reminder_worker.run_reminder_worker_once(now) == []


def test_class_end_reminder_catches_up_for_one_hour():
    event = {
        "event_id": "class-1",
        "user_id": "user-1",
        "event_type": "class",
        "title": "控制系統",
        "weekday": 5,
        "start_time": "12:00",
        "end_time": "13:17",
        "offset_minutes": 0,
        "prompt_template": "class_feedback",
        "enabled": True,
    }

    due = get_due_events(
        [event],
        datetime(2026, 11, 27, 14, 16, tzinfo=TZ),
        [],
    )
    expired = get_due_events(
        [event],
        datetime(2026, 11, 27, 14, 18, tzinfo=TZ),
        [],
    )

    assert len(due) == 1
    assert due[0]["scheduled_at"] == "2026-11-27T13:17+08:00"
    assert expired == []


def test_guided_note_flow_and_deduplication(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    secret = "test-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    replies = []
    monkeypatch.setattr(
        line_bot, "reply_line_message",
        lambda token, text, choices=None: replies.append((text, choices)),
    )

    now = datetime.now(TZ)
    day = (now - timedelta(days=1)).date()
    weekday = day.isoweekday()
    storage.save_json(storage.data_path("events"), [{
        "event_id": "event_1", "user_id": "demo_user_001",
        "event_type": "class", "title": "控制系統", "weekday": weekday,
        "start_time": "00:00", "end_time": "00:01",
        "offset_minutes": 0, "prompt_template": "class_feedback", "enabled": True,
    }])
    storage.save_json(storage.data_path("users"), [{
        "user_id": "demo_user_001", "line_user_id": "U123",
        "reminders_enabled": True, "ai_after_class_enabled": False,
    }])
    storage.save_json(storage.data_path("availability"), [{
        "availability_id": "note-study-slot", "user_id": "demo_user_001",
        "date": (now.date() + timedelta(days=1)).isoformat(),
        "start_time": "19:00", "available_minutes": 60,
    }])
    storage.save_json(storage.data_path("reminders"), [{
        "reminder_id": "r1", "user_id": "demo_user_001",
        "event_id": "event_1", "class_date": day.isoformat(),
        "kind": "class_feedback", "status": "sent",
    }])

    client = line_bot.create_app().test_client()
    weekday_text = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]
    for event_id, text in [
        ("e1", "補筆記"), ("e2", weekday_text), ("e3", "1"),
        ("e4", "3"), ("e4a", "Ch.3 p.42"), ("e5", "今天學會根軌跡"),
    ]:
        assert _post_signed(client, secret, _event(event_id, text)).status_code == 200
    assert _post_signed(client, secret, _event("e5", "今天學會根軌跡")).status_code == 200
    notes = storage.load_json(storage.data_path("feedback"))
    assert len(notes) == 1
    assert notes[0]["reminder_id"] == "r1"
    assert notes[0]["progress"] == 3
    assert notes[0]["course_progress"] == "Ch.3 p.42"
    assert notes[0]["content"] == "今天學會根軌跡"

    pending = storage.load_json(storage.data_path("pending_notes"))[0]
    assert pending["stage"] == "study_minutes"
    assert pending["reading_progress"] == "Ch.3 p.42"
    assert pending["task_title"] == "複習 Ch.3 p.42"
    assert "請輸入你決定要花多少分鐘讀" in replies[-1][0]
    assert _post_signed(client, secret, _event("e7-too-long", "90")).status_code == 200
    assert storage.load_json(storage.data_path("tasks")) == []
    assert storage.load_json(storage.data_path("pending_notes"))[0]["stage"] == "study_deadline"
    deadline = (now.date() + timedelta(days=1)).isoformat()
    assert _post_signed(client, secret, _event("e7-deadline-too-long", deadline)).status_code == 200
    assert storage.load_json(storage.data_path("tasks")) == []
    assert "不會自行拆分或安排時間" in replies[-1][0]
    for event_id, text in [
        ("e7-adjust-minutes", "分鐘 45"),
        ("e7-deadline-retry", deadline),
        ("e8", "1"),
    ]:
        assert _post_signed(client, secret, _event(event_id, text)).status_code == 200
    tasks = storage.load_json(storage.data_path("tasks"))
    plan = storage.load_json(storage.data_path("plan"))
    assert len(tasks) == len(plan) == 1
    assert tasks[0]["title"] == "複習 Ch.3 p.42"
    assert tasks[0]["estimated_minutes"] == 45
    assert tasks[0]["deadline"] == deadline
    assert tasks[0]["reading_progress"] == "Ch.3 p.42"
    assert tasks[0]["preferred_availability_id"] == "note-study-slot"
    assert plan[0]["status"] == "scheduled"
    assert plan[0]["availability_id"] == "note-study-slot"
    assert "已排在" in replies[-1][0]


def test_guided_note_flow_saves_docx_text_and_preserves_pdf_attachment(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    secret = "test-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
    replies = []
    monkeypatch.setattr(
        line_bot, "reply_line_message",
        lambda token, text, choices=None: replies.append(text),
    )

    now = datetime.now(TZ)
    day = (now - timedelta(days=1)).date()
    weekday = day.isoweekday()
    storage.save_json(storage.data_path("events"), [{
        "event_id": "event-docx", "user_id": "demo_user_001",
        "event_type": "class", "title": "控制系統", "weekday": weekday,
        "start_time": "00:00", "end_time": "00:01",
        "offset_minutes": 0, "prompt_template": "class_feedback", "enabled": True,
    }])
    storage.save_json(storage.data_path("users"), [{
        "user_id": "demo_user_001", "line_user_id": "U123",
        "reminders_enabled": True, "ai_after_class_enabled": False,
    }])

    note_text = "複習了回授控制與穩定度分析"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{escape(note_text)}</w:t></w:r></w:p></w:body></w:document>"
    )
    document = BytesIO()
    with ZipFile(document, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    docx_content = document.getvalue()
    pdf_content = _minimal_pdf("PDF control systems note")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def __init__(self, content):
            self.content = content

        def iter_content(self, chunk_size):
            yield self.content

    download_calls = []
    download_contents = {"docx-id": docx_content, "pdf-id": pdf_content}

    def fake_download(url, **kwargs):
        download_calls.append((url, kwargs))
        message_id = url.split("/message/")[1].split("/content")[0]
        return FakeResponse(download_contents[message_id])

    monkeypatch.setattr(
        line_bot.requests,
        "get",
        fake_download,
    )

    client = line_bot.create_app().test_client()
    weekday_text = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][weekday - 1]
    for event_id, text in [
        ("file-start", "補筆記"), ("file-weekday", weekday_text),
        ("file-slot", "1"), ("file-progress", "3"),
        ("file-course-progress", "Ch.4 p.18"),
    ]:
        assert _post_signed(client, secret, _event(event_id, text)).status_code == 200

    unsupported = {
        "webhookEventId": "file-unsupported",
        "type": "message",
        "replyToken": "file-unsupported",
        "source": {"userId": "U123"},
        "message": {"type": "file", "id": "doc-id", "fileName": "notes.doc", "fileSize": 100},
    }
    assert _post_signed(client, secret, unsupported).status_code == 200
    assert "支援 .docx、.pdf 與 .txt" in replies[-1]
    assert storage.load_json(storage.data_path("feedback")) == []
    assert storage.load_json(storage.data_path("pending_notes"))[0]["stage"] == "note"

    file_event = {
        "webhookEventId": "file-note",
        "type": "message",
        "replyToken": "file-note",
        "source": {"userId": "U123"},
        "message": {
            "type": "file",
            "id": "docx-id",
            "fileName": "class-notes.docx",
            "fileSize": len(docx_content),
        },
    }
    assert _post_signed(client, secret, file_event).status_code == 200

    feedback = storage.load_json(storage.data_path("feedback"))
    assert len(feedback) == 1
    assert feedback[0]["content"] == note_text
    assert feedback[0]["attachment_filename"] == "class-notes.docx"
    assert feedback[0]["progress"] == 3
    assert feedback[0]["course_progress"] == "Ch.4 p.18"
    assert _post_signed(client, secret, _event("docx-skip-task", "先不用")).status_code == 200
    assert storage.load_json(storage.data_path("pending_notes")) == []
    assert download_calls[0][0].endswith("/docx-id/content")
    assert download_calls[0][1]["headers"]["Authorization"] == "Bearer test-token"
    assert "未新增讀書任務" in replies[-1]

    for event_id, text in [
        ("pdf-start", "補筆記"), ("pdf-weekday", weekday_text),
        ("pdf-slot", "1"), ("pdf-progress", "4"),
        ("pdf-course-progress", "進度 60%"),
    ]:
        assert _post_signed(client, secret, _event(event_id, text)).status_code == 200
    pdf_event = {
        "webhookEventId": "pdf-note",
        "type": "message",
        "replyToken": "pdf-note",
        "source": {"userId": "U123"},
        "message": {
            "type": "file",
            "id": "pdf-id",
            "fileName": "control-notes.pdf",
            "fileSize": len(pdf_content),
        },
    }
    assert _post_signed(client, secret, pdf_event).status_code == 200
    feedback = storage.load_json(storage.data_path("feedback"))
    assert len(feedback) == 2
    assert feedback[1]["content"] == "PDF control systems note"
    assert feedback[1]["attachment_filename"] == "control-notes.pdf"
    assert feedback[1]["progress"] == 4
    assert feedback[1]["course_progress"] == "進度 60%"
    saved_pdf = storage.feedback_attachment_path(
        feedback[1]["feedback_id"], "demo_user_001"
    )
    assert saved_pdf.read_bytes() == pdf_content
    assert any("PDF 原檔已儲存" in reply for reply in replies)
    assert download_calls[1][0].endswith("/pdf-id/content")
    assert _post_signed(client, secret, _event("pdf-skip-task", "先不用")).status_code == 200


def test_verified_webhook_can_bind_line_id(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    secret = "test-secret"
    monkeypatch.setenv("LINE_CHANNEL_SECRET", secret)
    monkeypatch.setenv("LINE_BINDING_CODE", "safe-example-code")
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    replies = []
    monkeypatch.setattr(
        line_bot, "reply_line_message",
        lambda token, text, choices=None: replies.append(text),
    )
    client = line_bot.create_app().test_client()
    event = _event("bind1", "綁定 safe-example-code")
    for _ in range(2):
        assert _post_signed(client, secret, event).status_code == 200
    users = storage.load_json(storage.data_path("users"))
    assert len(users) == 1
    assert users[0]["line_user_id"] == "U123"
    assert len(storage.load_json(storage.data_path("processed_webhooks"))) == 1
    assert len(replies) == 1

    # 有效綁定碼也不能把現有帳號覆綁成別人的 LINE。
    assert _post_signed(client, secret, _event(
        "bind2", "綁定 safe-example-code", "U-OTHER"
    )).status_code == 200
    users = storage.load_json(storage.data_path("users"))
    assert users[0]["line_user_id"] == "U123"
    assert "已綁定其他 LINE 使用者" in replies[-1]


def test_simulated_push_is_not_treated_as_success(monkeypatch):
    from reminder_worker import push_line_message
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    assert push_line_message(
        {"line_user_id": "U123"}, {"user_id": "demo_user_001"}, "hello"
    ) is False
