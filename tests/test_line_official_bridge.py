import json
from types import SimpleNamespace

import pytest

import line_official_bridge as bridge
import line_friend_e2e as demo
import storage

SUBJECT = "U" + "a" * 32
SECRET = "offline-original-secret"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data" / "friend-e2e")
    storage.select_demo_storage(False)
    monkeypatch.delenv("CLASSPULSE_STAGING_TEST_USERS", raising=False)
    for key, val in {
        "CLASSPULSE_FRIEND_E2E": "1",
        "CLASSPULSE_FRIEND_INTERNAL": "1",
        "CLASSPULSE_OFFICIAL_BRIDGE": "1",
        "CLASSPULSE_PUBLIC_WEB": "0",
        "CLASSPULSE_LINE_WEB_STAGING": "1",
        "CLASSPULSE_WEB_ORIGIN": "https://example.test",
        "LINE_LOGIN_CHANNEL_ID": "123",
        "LINE_LOGIN_CHANNEL_SECRET": "fake",
        "LINE_CHANNEL_SECRET": SECRET,
        "LINE_CHANNEL_ACCESS_TOKEN": "fake",
    }.items():
        monkeypatch.setenv(key, val)
    replies, forwarded = [], []
    monkeypatch.setattr(demo, "reply_line_message", lambda token, text: replies.append(text))
    def legacy(url, data, headers, **kwargs):
        assert url == bridge.LEGACY_URL
        assert bridge.verify_line_signature(data, headers["X-Line-Signature"], SECRET)
        assert kwargs["allow_redirects"] is False
        forwarded.append(json.loads(data))
        return SimpleNamespace(status_code=200)
    monkeypatch.setattr(bridge.requests, "post", legacy)
    return bridge.create_app().test_client(), replies, forwarded


def event(eid, kind="message", **extra):
    return {"webhookEventId": eid, "type": kind,
            "source": {"type": "user", "userId": SUBJECT},
            "replyToken": "fake", **extra}


def post(client, events, secret=SECRET):
    body, headers = bridge.signed_payload({"destination": "test", "events": events}, secret)
    return client.post("/webhook", data=body, headers=headers)


def users():
    return storage.load_json(storage.data_path("users"))


def test_existing_friend_open_auto_seeds_and_legacy_events_pass_through(setup):
    client, replies, forwarded = setup
    note = event("note", message={"type": "file", "id": "1"})
    bind = event("bind", message={"type": "text", "text": "綁定 test"})
    opening = event("open", message={"type": "text", "text": "開啟網頁"})
    assert post(client, [note, opening, bind]).status_code == 200
    assert forwarded == [{"destination": "test", "events": [note, bind]}]
    assert len(users()) == 1
    assert len(storage.load_json(storage.data_path("events"))) == 14
    assert "/auth/line/start?openExternalBrowser=1" in replies[0]
    assert post(client, [opening]).status_code == 200
    assert len(replies) == 1
    assert post(client, [event("follow", "follow")]).status_code == 200
    assert len(users()) == 1 and len(replies) == 2


def test_invalid_signature_blocks_both_backends(setup):
    client, replies, forwarded = setup
    assert post(client, [event("follow", "follow")], secret="wrong").status_code == 401
    assert not users() and not replies and not forwarded


def test_empty_verify_checks_legacy_and_failure_not_acknowledged(setup, monkeypatch):
    client, replies, forwarded = setup
    assert post(client, []).status_code == 200
    assert forwarded == [{"destination": "test", "events": []}]
    monkeypatch.setattr(bridge.requests, "post", lambda *a, **k: SimpleNamespace(status_code=401))
    assert post(client, []).status_code == 502
    assert not users() and not replies


def test_group_open_stays_on_legacy_path(setup):
    client, replies, forwarded = setup
    message = event("group", message={"type": "text", "text": "開啟網頁"})
    message["source"]["type"] = "group"
    assert post(client, [message]).status_code == 200
    assert forwarded[0]["events"] == [message]
    assert not users() and not replies


def test_personal_note_sync_reads_web_course_and_writes_same_owner(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    def unexpected_ai(*args, **kwargs):
        pytest.fail("note-only sync must not call AI")
    monkeypatch.setattr(line_bot, "organize_class_feedback", unexpected_ai)
    def msg(eid, text):
        return event(eid, message={"type": "text", "text": text})
    assert post(client, [msg("open", "開啟網頁")]).status_code == 200
    uid = users()[0]["user_id"]
    day = (datetime.now(storage.TZ) - timedelta(days=1)).date()
    weekday = day.isoweekday()
    course = {"event_id": "web-test-course", "user_id": uid, "event_type": "class",
              "title": "LINE_E2E_TEST", "weekday": weekday,
              "start_time": "00:00", "end_time": "00:01",
              "enabled": True, "offset_minutes": 0, "prompt_template": "class_feedback"}
    storage.update_json(storage.data_path("events"), lambda rows: rows + [course])
    assert post(client, [msg("start", "補筆記"), msg("weekday", str(weekday))]).status_code == 200
    assert "LINE_E2E_TEST" in replies[-1]
    selected = next(line.split(".")[0] for line in replies[-1].splitlines() if "LINE_E2E_TEST" in line)
    assert post(client, [msg("class", selected), msg("rating", "3"),
                         msg("note", "LINE_E2E_NOTE_MARKER")]).status_code == 200
    matching = [n for n in storage.load_json(storage.data_path("feedback"))
                if n.get("content") == "LINE_E2E_NOTE_MARKER"]
    assert len(matching) == 1 and matching[0]["user_id"] == uid
    assert matching[0]["event_id"] == course["event_id"] and matching[0]["progress"] == 3
    assert forwarded == []
    assert post(client, [msg("note", "LINE_E2E_NOTE_MARKER")]).status_code == 200
    assert forwarded == []
    assert len([n for n in storage.load_json(storage.data_path("feedback"))
                if n.get("content") == "LINE_E2E_NOTE_MARKER"]) == 1
    assert post(client, [msg("search", "搜尋 LINE_E2E_NOTE_MARKER")]).status_code == 200
    assert "LINE_E2E_NOTE_MARKER" in replies[-1]


def test_note_sync_keeps_unregistered_and_legacy_commands_on_legacy_path(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    client, replies, forwarded = setup
    unknown = event("unknown", message={"type": "text", "text": "補筆記"})
    assert post(client, [unknown]).status_code == 200
    assert forwarded[-1]["events"] == [unknown] and not users()
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    for eid, text in [("bind", "綁定 test"), ("complete", "完成"), ("other", "你好")]:
        ev = event(eid, message={"type": "text", "text": text})
        assert post(client, [ev]).status_code == 200
        assert forwarded[-1]["events"] == [ev]


def test_note_sync_default_off_preserves_old_routing(setup, monkeypatch):
    monkeypatch.delenv("CLASSPULSE_FRIEND_NOTE_SYNC", raising=False)
    client, replies, forwarded = setup
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    ev = event("old", message={"type": "text", "text": "補筆記"})
    assert post(client, [ev]).status_code == 200
    assert forwarded[-1]["events"] == [ev]


def test_real_ai_requires_single_note_consent_and_keeps_purple_confirmation(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.setenv("CLASSPULSE_FRIEND_AI_SYNC", "1")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    monkeypatch.setenv("OPENAI_MODEL", "offline-test")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    calls = []
    def analyze(feedback, course):
        calls.append((feedback["content"], course))
        return {"summary": "測試摘要", "key_points": ["根軌跡"],
                "unresolved_questions": ["如何處理零首項？", "如何辨識虛軸根？"],
                "topic_tags": ["根軌跡"], "suggested_task": "複習兩題",
                "estimated_minutes": 60}
    monkeypatch.setattr(line_bot, "organize_class_feedback", analyze)
    def send(eid, text):
        assert post(client, [event(eid, message={"type": "text", "text": text})]).status_code == 200
    send("open-ai", "開啟網頁")
    uid = users()[0]["user_id"]
    now = datetime.now(storage.TZ)
    day = (now - timedelta(days=1)).date()
    course = {"event_id": "ai-web-course", "user_id": uid, "event_type": "class",
              "title": "AI_E2E_TEST", "weekday": day.isoweekday(),
              "start_time": "00:00", "end_time": "00:01",
              "enabled": True, "offset_minutes": 0, "prompt_template": "class_feedback"}
    storage.update_json(storage.data_path("events"), lambda rows: rows + [course])
    def finish_note(prefix, text):
        weekday = next(k for k, v in line_bot.WEEKDAYS.items() if v == day.isoweekday())
        send(prefix+"weekday", weekday)
        selected = next(l.split(".")[0] for l in replies[-1].splitlines() if "AI_E2E_TEST" in l)
        send(prefix+"course", selected)
        send(prefix+"rating", "3")
        send(prefix+"note", text)
    send("no-consent", "同意AI整理")
    assert not calls
    send("ordinary", "補筆記")
    finish_note("ordinary-", "普通測試筆記")
    assert not calls
    send("ai-start", "AI補筆記")
    assert "OpenAI API" in replies[-1]
    send("ai-agree", "同意AI整理")
    before = len(storage.load_json(storage.data_path("tasks")))
    finish_note("real-", "不懂零首項與虛軸根的判斷")
    assert calls == [("不懂零首項與虛軸根的判斷", "AI_E2E_TEST")]
    assert len(storage.load_json(storage.data_path("tasks"))) == before
    notes = storage.load_json(storage.data_path("feedback"))
    note = next(n for n in notes if n.get("content") == calls[0][0])
    assert note["user_id"] == uid and note["ai_analysis"]["summary"] == "測試摘要"
    send("accept-first", "加入讀書任務")
    send("skip-second", "先不用")
    tasks = storage.load_json(storage.data_path("tasks"))
    created = [t for t in tasks if t.get("source_feedback_id") == note["feedback_id"]]
    assert len(tasks) == before + 1 and len(created) == 1
    assert created[0]["user_id"] == uid and created[0]["estimated_minutes"] == 30
    assert created[0]["source"] == "ai_confirmed"
    assert not any(p.get("task_id") == created[0]["task_id"]
                   for p in storage.load_json(storage.data_path("plan")))
    assert users()[0].get("ai_after_class_enabled") is False
    assert forwarded == []
    send("real-note", "不懂零首項與虛軸根的判斷")
    assert len(calls) == 1


def test_ai_command_default_off_does_not_start_paid_flow(setup, monkeypatch):
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.delenv("CLASSPULSE_FRIEND_AI_SYNC", raising=False)
    import line_bot
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    assert post(client, [event("open", message={"type": "text", "text": "開啟網頁"})]).status_code == 200
    assert post(client, [event("ai", message={"type": "text", "text": "AI補筆記"})]).status_code == 200
    assert "尚未啟用" in replies[-1]
    assert not storage.load_json(storage.data_path("pending_notes"))
    assert not forwarded


def test_gemini_consent_names_provider_and_rejects_provider_switch(setup, monkeypatch):
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.setenv("CLASSPULSE_FRIEND_AI_SYNC", "1")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    def send(eid, text):
        assert post(client, [event(eid, message={"type": "text", "text": text})]).status_code == 200
    send("open-g", "開啟網頁")
    send("start-g", "AI補筆記")
    assert "Google Gemini API" in replies[-1] and "改善產品" in replies[-1]
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai")
    monkeypatch.setenv("OPENAI_MODEL", "offline-model")
    send("agree-switched", "同意AI整理")
    assert "請先輸入" in replies[-1]
    assert storage.load_json(storage.data_path("pending_notes"))[0]["stage"] == "friend_ai_consent"
    assert not forwarded


def _prepare_personal_checkin(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.setenv("CLASSPULSE_FRIEND_PROGRESS_SYNC", "1")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    def msg(eid, text):
        return event(eid, message={"type": "text", "text": text})
    assert post(client, [msg("open", "開啟網頁")]).status_code == 200
    uid = users()[0]["user_id"]
    now = datetime.now(storage.TZ)
    start = now - timedelta(minutes=31)
    deadline = (now.date()+timedelta(days=5)).isoformat()
    target = {"user_id": uid, "task_id": "aiq_progress", "subject": "測試課程",
              "title": "測試任務", "status": "pending", "deadline": deadline,
              "estimated_minutes": 30, "preferred_availability_id": ""}
    other = {**target, "task_id": "other", "title": "固定任務"}
    slot = {"user_id": uid, "availability_id": "board_aiq_progress",
            "date": start.date().isoformat(), "start_time": start.strftime("%H:%M"),
            "available_minutes": 30, "board_generated": True}
    next_day = (now.date()+timedelta(days=1)).isoformat()
    other_slot = {**slot, "availability_id": "board_other", "date": next_day, "start_time": "09:00"}
    plan = {"user_id": uid, "task_id": target["task_id"], "availability_id": slot["availability_id"],
            "status": "scheduled", "source": "manual",
            "scheduled_start": start.isoformat(timespec="minutes"), "scheduled_minutes": 30}
    pinned = {**plan, "task_id": "other", "availability_id": "board_other",
              "scheduled_start": next_day+"T09:00+08:00"}
    checkin = {"user_id": uid, "task_id": target["task_id"], "availability_id": slot["availability_id"],
               "kind": "study_session_checkin", "status": "sent", "reminder_id": "personal-checkin",
               "personal_study_test": True, "progress_status": "awaiting_response",
               "session_start": plan["scheduled_start"], "session_minutes": 30}
    for name, rows in {"tasks":[target,other], "availability":[slot,other_slot],
                       "plan":[plan,pinned], "reminders":[checkin], "events":[],
                       "external_events":[]}.items():
        storage.save_json(storage.data_path(name), rows)
    return client, replies, forwarded, msg, pinned


def test_signed_personal_unfinished_and_replan_preserves_other_task(setup, monkeypatch):
    client, replies, forwarded, msg, pinned = _prepare_personal_checkin(setup, monkeypatch)
    assert post(client, [msg("unfinished", "未完成 aiq_progress")]).status_code == 200
    assert "剩餘 15" in replies[-1]
    assert post(client, [msg("invalid-minutes", "剩餘 999")]).status_code == 200
    assert "1 至 240" in replies[-1]
    assert post(client, [msg("remaining", "剩餘 15")]).status_code == 200
    target = next(t for t in storage.load_json(storage.data_path("tasks")) if t["task_id"] == "aiq_progress")
    assert target["estimated_minutes"] == 30 and target["remaining_minutes"] == 15
    plan = storage.load_json(storage.data_path("plan"))
    assert pinned in plan
    assert any(r["task_id"] == "aiq_progress" and r["source"] == "auto" for r in plan)
    assert storage.load_json(storage.data_path("reminders"))[0]["progress_status"] == "replanned"
    assert post(client, [msg("remaining", "剩餘 15")]).status_code == 200
    assert storage.load_json(storage.data_path("plan")) == plan
    assert not forwarded


def test_signed_personal_complete_only_unplaces_target(setup, monkeypatch):
    client, replies, forwarded, msg, pinned = _prepare_personal_checkin(setup, monkeypatch)
    assert post(client, [msg("done", "完成 aiq_progress")]).status_code == 200
    assert storage.load_json(storage.data_path("plan")) == [pinned]
    target = next(t for t in storage.load_json(storage.data_path("tasks")) if t["task_id"] == "aiq_progress")
    assert target["status"] == "completed"
    assert post(client, [msg("done-again", "完成 aiq_progress")]).status_code == 200
    assert storage.load_json(storage.data_path("plan")) == [pinned]
    assert not forwarded


def test_personal_checkin_does_not_intercept_notes_or_overwrite_moved_plan(setup, monkeypatch):
    client, replies, forwarded, msg, pinned = _prepare_personal_checkin(setup, monkeypatch)
    assert post(client, [msg("unfinished", "未完成 aiq_progress")]).status_code == 200
    assert post(client, [msg("start-note", "補筆記")]).status_code == 200
    assert "星期" in replies[-1]
    storage.update_json(storage.data_path("plan"), lambda rows: [
        {**r, "scheduled_start": "2030-01-01T10:00+08:00"} if r["task_id"] == "aiq_progress" else r
        for r in rows])
    saved = storage.load_json(storage.data_path("plan"))
    assert post(client, [msg("late", "剩餘 15")]).status_code == 200
    assert "已變更" in replies[-1]
    assert storage.load_json(storage.data_path("plan")) == saved
    assert not forwarded


def _prepare_class_push(setup, monkeypatch):
    from datetime import datetime, timedelta
    import line_bot
    import line_personal_class_worker as worker
    monkeypatch.setenv("CLASSPULSE_FRIEND_NOTE_SYNC", "1")
    monkeypatch.setenv("CLASSPULSE_FRIEND_CLASS_PUSH", "1")
    client, replies, forwarded = setup
    monkeypatch.setattr(line_bot, "reply_line_message",
                        lambda token, text, choices=None: replies.append(text))
    def msg(eid, text):
        return event(eid, message={"type": "text", "text": text})
    assert post(client, [msg("class-open", "開啟網頁")]).status_code == 200
    uid = users()[0]["user_id"]
    now = datetime.now(storage.TZ).replace(hour=10, minute=5, second=0, microsecond=0)
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(bridge, "datetime", FixedClock)
    course = {"event_id": "real-class-push", "user_id": uid, "event_type": "class",
              "title": "CLASS_PUSH_TEST", "weekday": now.isoweekday(),
              "start_time": "09:00", "end_time": "10:00", "offset_minutes": 5,
              "enabled": True, "prompt_template": "class_feedback"}
    storage.update_json(storage.data_path("events"), lambda rows: rows+[course])
    pushes = []
    monkeypatch.setattr(worker, "push_line_message",
                        lambda user, row, text: pushes.append((user, row, text)) or True)
    options = worker.occurrences(now)
    selected = next(s for s in options if s["event_id"] == course["event_id"])
    return client, replies, forwarded, msg, worker, now, uid, course, selected, pushes


def test_class_push_timing_dedup_and_busy_conversation(setup, monkeypatch):
    from datetime import timedelta
    import line_bot
    client, replies, forwarded, msg, worker, now, uid, course, selected, pushes = _prepare_class_push(setup, monkeypatch)
    assert worker.deliver_once(selected, now-timedelta(seconds=1)) == "waiting"
    assert not pushes
    original = {"user_id": uid, "stage": "weekday",
                "expires_at": (now+timedelta(minutes=10)).isoformat()}
    line_bot._set_pending(original)
    assert worker.deliver_once(selected, now) == "busy"
    assert line_bot._pending_for(uid, now) == original and not pushes
    line_bot._remove_pending(uid)
    assert worker.deliver_once(selected, now) == "sent"
    assert worker.deliver_once(selected, now+timedelta(seconds=15)) == "sent"
    assert len(pushes) == 1 and "CLASS_PUSH_TEST" in pushes[0][2]
    pending = line_bot._pending_for(uid, now)
    assert pending["stage"] == "progress" and pending["event_id"] == course["event_id"]
    assert pending["class_date"] == now.date().isoformat()


def test_class_push_skips_seeded_disabled_and_expired_occurrences(setup, monkeypatch):
    from datetime import timedelta
    client, replies, forwarded, msg, worker, now, uid, course, selected, pushes = _prepare_class_push(setup, monkeypatch)
    assert all(not s["course"].get("demo_seed_version") for s in worker.occurrences(now))
    storage.update_json(storage.data_path("events"), lambda rows: [
        {**r, "enabled": False} if r["event_id"] == course["event_id"] else r for r in rows])
    assert worker.deliver_once(selected, now) == "invalid"
    storage.update_json(storage.data_path("events"), lambda rows: [
        {**r, "enabled": True} if r["event_id"] == course["event_id"] else r for r in rows])
    assert worker.deliver_once(selected, now+timedelta(minutes=16)) == "invalid"
    assert not pushes


@pytest.mark.parametrize("consent", [False, True])
def test_signed_class_push_note_preserves_course_and_ai_choice(setup, monkeypatch, consent):
    import line_bot
    monkeypatch.setenv("CLASSPULSE_FRIEND_AI_SYNC", "1")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "offline")
    monkeypatch.setenv("GEMINI_MODEL", "offline")
    client, replies, forwarded, msg, worker, now, uid, course, selected, pushes = _prepare_class_push(setup, monkeypatch)
    calls = []
    def analyze(note, title):
        calls.append((note["content"], title))
        return {"summary": "測試摘要", "key_points": ["測試重點"],
                "unresolved_questions": ["如何判斷穩定？"], "topic_tags": ["控制"],
                "suggested_task": "複習穩定", "estimated_minutes": 30}
    monkeypatch.setattr(line_bot, "organize_class_feedback", analyze)
    assert worker.deliver_once(selected, now) == "sent"
    assert post(client, [msg("class-rating", "3")]).status_code == 200
    assert "Google Gemini API" in replies[-1] and not calls
    assert post(client, [msg("class-consent", "同意AI整理" if consent else "只儲存筆記")]).status_code == 200
    assert "本堂課的筆記" in replies[-1] and not calls
    before = len(storage.load_json(storage.data_path("tasks")))
    assert post(client, [msg("class-note", "不懂穩定判斷")]).status_code == 200
    notes = [n for n in storage.load_json(storage.data_path("feedback"))
             if n.get("content") == "不懂穩定判斷"]
    assert len(notes) == 1
    note = notes[0]
    assert note["event_id"] == course["event_id"] and note["class_date"] == now.date().isoformat()
    assert note["user_id"] == uid and note["progress"] == 3
    assert note["reminder_id"] == selected["reminder_id"]
    assert bool(calls) == consent
    if consent:
        assert calls == [("不懂穩定判斷", "CLASS_PUSH_TEST")]
        assert note["ai_analysis"]["summary"] == "測試摘要"
        assert len(storage.load_json(storage.data_path("tasks"))) == before
        assert post(client, [msg("class-accept", "加入讀書任務")]).status_code == 200
        tasks = [t for t in storage.load_json(storage.data_path("tasks"))
                 if t.get("source_feedback_id") == note["feedback_id"]]
        assert len(tasks) == 1 and tasks[0]["estimated_minutes"] == 30
    else:
        assert not note.get("ai_analysis")
        assert len(storage.load_json(storage.data_path("tasks"))) == before
    assert not forwarded
