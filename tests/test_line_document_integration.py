"""LINE-first document imports and search: offline, signed-webhook adjacent tests."""
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
import zipfile

import pytest

import storage
import line_bot
import line_note_files
from note_attachments import attachment_path, save_pdf_attachment
from storage import DataError

TZ=ZoneInfo("Asia/Taipei")
NOW=datetime(2026,11,27,18,0,tzinfo=TZ)
USER="demo_user_001"


@pytest.fixture
def empty_db(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,"DATA_DIR",tmp_path)
    for name in storage.FILES:
        storage.save_json(storage.data_path(name),[])
    storage.save_json(storage.data_path("users"),[{
        "user_id":USER,"line_user_id":"Uxxx",
        "reminders_enabled":True,"ai_after_class_enabled":False,
    }])
    return tmp_path


def test_txt_and_docx_plaintext_extraction():
    assert line_note_files.extract_text("a.txt",b"\xef\xbb\xbfhello notes")=="hello notes"
    buf=BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("word/document.xml",
          '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:body><w:p><w:r><w:t>第一段落</w:t></w:r></w:p>'
          '<w:p><w:r><w:t>第二段落</w:t></w:r></w:p></w:body></w:document>')
    assert line_note_files.extract_text("note.docx",buf.getvalue())=="第一段落\n第二段落"


def test_bad_files_rejected_before_storage():
    with pytest.raises(DataError,match="ICS"):
        line_note_files.clean_filename("../calendar.ics")
    with pytest.raises(DataError,match="空|找不到|解析"):
        line_note_files.extract_text("scan.pdf",b"%PDF-1.7\ninvalid")
    with pytest.raises(DataError,match="UTF-8"):
        line_note_files.extract_text("notes.txt",b"\xff\xfe")
    with pytest.raises(DataError,match="10 MB"):
        line_note_files.extract_text("too-large.txt",b"x"*(10*1024*1024+1))
    assert line_note_files.clean_filename("../../hello.docx")=="hello.docx"


def test_line_quick_note_and_search_without_weekday_wizard(empty_db,monkeypatch):
    replies=[]
    monkeypatch.setattr(line_bot,"reply_line_message",
                        lambda token,text,choices=None:replies.append(text))
    event={
        "type":"message","webhookEventId":"evt-1","replyToken":"reply",
        "source":{"userId":"Uxxx"},
        "message":{"type":"text","text":"筆記 今天要讀電子學第三章與 MOS 元件"},
    }
    line_bot._process_event(event,NOW)
    stored=storage.load_json(storage.data_path("feedback"))
    assert len(stored)==1
    assert stored[0]["event_id"]=="inbox"
    assert stored[0]["content"]=="今天要讀電子學第三章與 MOS 元件"
    assert storage.load_json(storage.data_path("plan"))==[]
    line_bot._process_event(event,NOW)  # same webhook idempotent
    assert len(storage.load_json(storage.data_path("feedback")))==1

    for id_,text in [("evt-2","查看筆記"),("evt-3","搜尋 MOS")]:
        line_bot._process_event({**event,"webhookEventId":id_,
                                 "message":{"type":"text","text":text}},NOW)
    assert any("今天要讀電子學" in x for x in replies)
    assert any("MOS" in x for x in replies)


def test_line_file_event_uses_same_quick_note_inbox(empty_db,monkeypatch):
    replies=[]
    monkeypatch.setattr(line_bot,"reply_line_message",
                        lambda token,text,choices=None:replies.append(text))
    monkeypatch.setattr(line_bot,"download_line_file",
                        lambda mid,size:b"hello from Word")
    monkeypatch.setattr(line_bot,"extract_text",
                        lambda name,data:"從 DOCX 擷取的筆記內容")
    event={
        "type":"message","webhookEventId":"file1","replyToken":"reply",
        "source":{"userId":"Uxxx"},
        "message":{"type":"file","id":"file123","fileName":"notes.docx",
                   "fileSize":45},
    }
    line_bot._process_event(event,NOW)
    notes=storage.load_json(storage.data_path("feedback"))
    assert len(notes)==1
    assert notes[0]["attachment_filename"]=="notes.docx"
    assert notes[0]["content"]=="從 DOCX 擷取的筆記內容"
    assert len(storage.load_json(storage.data_path("plan")))==0


def test_pdf_attachment_uses_hashed_name_and_own_data_dir(empty_db):
    path=save_pdf_attachment(USER,"f1",b"%PDF-1.7\nexample")
    assert path==attachment_path(USER,"f1")
    assert path.name!="f1.pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert path!=attachment_path("other","f1")
