from datetime import datetime, timedelta
import requests
import pytest
import storage
import line_personal_study_worker as worker


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data" / "friend-e2e")
    storage.select_demo_storage(False)
    monkeypatch.delenv("CLASSPULSE_STAGING_TEST_USERS", raising=False)
    for key in ("CLASSPULSE_FRIEND_STUDY_PUSH", "CLASSPULSE_OFFICIAL_BRIDGE",
                "CLASSPULSE_FRIEND_INTERNAL", "CLASSPULSE_FRIEND_E2E",
                "CLASSPULSE_FRIEND_NOTE_SYNC", "LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET"):
        monkeypatch.setenv(key, "1")
    uid = "lineuser_" + "a"*12
    subject = "U" + "a"*32
    now = datetime(2026, 11, 28, 10, 0, tzinfo=storage.TZ)
    user = {"user_id": uid, "line_user_id": subject,
            "demo_status": "seeded_pending_auth", "demo_seed_version": 1,
            "study_reminders_enabled": False, "ai_after_class_enabled": False}
    task = {"user_id": uid, "task_id": "aiq_test", "source": "ai_confirmed",
            "status": "pending", "source_question_key": "q", "source_feedback_id": "n",
            "subject": "控制系統", "title": "測試疑問", "estimated_minutes": 30}
    slot = {"user_id": uid, "availability_id": "board_aiq_test",
            "date": now.date().isoformat(), "start_time": "10:00", "available_minutes": 30}
    plan = {"user_id": uid, "task_id": task["task_id"], "availability_id": slot["availability_id"],
            "status": "scheduled", "scheduled_start": now.isoformat(), "scheduled_minutes": 30}
    note = {"user_id": uid, "feedback_id": "n",
            "ai_analysis": {"summary": "cached summary", "key_points": ["測試重點"]}}
    for name, rows in {"users": [user], "tasks": [task], "availability": [slot],
                       "plan": [plan], "feedback": [note]}.items():
        storage.save_json(storage.data_path(name), rows)
    return now, uid, subject


def test_real_start_uses_cached_ai_and_sends_once(prepared, monkeypatch):
    now, uid, subject = prepared
    import line_study_ai
    monkeypatch.setattr(line_study_ai, "organize_class_feedback",
                        lambda *a: pytest.fail("must not call AI"))
    calls = []
    monkeypatch.setattr(worker, "push_line_message",
                        lambda user, reminder, text: calls.append((user, reminder, text)) or True)
    selected = worker.sessions(now)[0]
    assert worker.deliver_once(selected, now-timedelta(seconds=1)) == "waiting"
    assert not calls
    assert worker.deliver_once(selected, now) == "sent"
    assert worker.deliver_once(selected, now+timedelta(seconds=15)) == "sent"
    assert len(calls) == 1 and calls[0][0]["line_user_id"] == subject
    assert "cached summary" in calls[0][2]
    row = storage.load_json(storage.data_path("reminders"))[0]
    assert row["status"] == "sent" and row["user_id"] == uid and row["retry_key"]
    assert storage.load_json(storage.data_path("users"))[0]["study_reminders_enabled"] is False


def test_seeded_or_foreign_note_or_disabled_mode_never_sends(prepared, monkeypatch):
    now, uid, _ = prepared
    monkeypatch.setattr(worker, "push_line_message", lambda *a: pytest.fail("unexpected push"))
    selected = worker.sessions(now)[0]
    storage.update_json(storage.data_path("tasks"), lambda rows: [{**rows[0], "demo_seed_version": 1}])
    assert not worker.sessions(now)
    assert worker.deliver_once(selected, now) == "invalid"
    storage.update_json(storage.data_path("tasks"), lambda rows: [{k:v for k,v in rows[0].items() if k != "demo_seed_version"}])
    storage.update_json(storage.data_path("feedback"), lambda rows: [{**rows[0], "user_id": "foreign"}])
    assert not worker.sessions(now)
    monkeypatch.delenv("CLASSPULSE_FRIEND_STUDY_PUSH")
    with pytest.raises(ValueError):
        worker.sessions(now)


def test_reschedule_invalidates_selection_and_changes_identity(prepared, monkeypatch):
    now, _, _ = prepared
    monkeypatch.setattr(worker, "push_line_message", lambda *a: pytest.fail("unexpected push"))
    selected = worker.sessions(now)[0]
    storage.update_json(storage.data_path("plan"), lambda rows: [
        {**rows[0], "scheduled_start": (now+timedelta(minutes=30)).isoformat()}])
    assert worker.deliver_once(selected, now) == "invalid"
    assert worker.sessions(now)[0]["reminder_id"] != selected["reminder_id"]


def test_retry_key_reused_and_accepted_409_recognized(prepared, monkeypatch):
    now, _, _ = prepared
    selected = worker.sessions(now)[0]
    keys = []
    def push(user, reminder, text):
        keys.append(reminder["retry_key"])
        if len(keys) == 1:
            raise requests.ConnectionError("offline")
        response = requests.Response()
        response.status_code = 409
        response.headers["x-line-accepted-request-id"] = "accepted"
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(worker, "push_line_message", push)
    assert worker.deliver_once(selected, now) == "failed"
    assert worker.deliver_once(selected, now+timedelta(seconds=30)) == "sent"
    assert len(keys) == 2 and keys[0] == keys[1]


def test_expired_selection_does_not_send(prepared, monkeypatch):
    now, _, _ = prepared
    selected = worker.sessions(now)[0]
    monkeypatch.setattr(worker, "push_line_message", lambda *a: pytest.fail("unexpected push"))
    assert worker.deliver_once(selected, now+timedelta(minutes=16)) == "invalid"


def test_checkin_after_session_end_and_only_once(prepared, monkeypatch):
    now, uid, _ = prepared
    messages = []
    monkeypatch.setattr(worker, "push_line_message", lambda u, r, t: messages.append(t) or True)
    selected = worker.sessions(now)[0]
    assert worker.deliver_once(selected, now) == "sent"
    assert worker.deliver_checkin_once(selected, now+timedelta(minutes=29)) == "waiting"
    assert worker.deliver_checkin_once(selected, now+timedelta(minutes=30)) == "sent"
    assert worker.deliver_checkin_once(selected, now+timedelta(minutes=31)) == "sent"
    assert len(messages) == 2 and "未完成 aiq_test" in messages[-1]
    row = next(r for r in storage.load_json(storage.data_path("reminders"))
               if r["kind"] == "study_session_checkin")
    assert row["user_id"] == uid and row["progress_status"] == "awaiting_response"
    assert row["session_minutes"] == 30


def test_checkin_requires_successful_start_and_expires(prepared, monkeypatch):
    now, _, _ = prepared
    selected = worker.sessions(now)[0]
    monkeypatch.setattr(worker, "push_line_message", lambda *a: pytest.fail("unexpected push"))
    assert worker.deliver_checkin_once(selected, now+timedelta(minutes=30)) == "invalid"
    assert worker.deliver_checkin_once(selected, now+timedelta(minutes=46)) == "invalid"


def _auto_config(monkeypatch):
    for key in ("CLASSPULSE_FRIEND_AUTO_PUSH", "CLASSPULSE_FRIEND_CLASS_PUSH",
                "CLASSPULSE_FRIEND_PROGRESS_SYNC"):
        monkeypatch.setenv(key, "1")


def test_auto_worker_respects_owner_opt_in_and_persisted_start_end(prepared, monkeypatch):
    import line_personal_auto_worker as auto
    now, uid, _ = prepared
    _auto_config(monkeypatch)
    calls = []
    monkeypatch.setattr(worker, "push_line_message", lambda u, r, t: calls.append((r["kind"], t)) or True)
    assert auto.tick(now) == []
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": True} for r in rows])
    assert auto.tick(now-timedelta(seconds=1)) == []
    assert auto.tick(now) == [("study", "sent")]
    assert auto.tick(now+timedelta(minutes=1)) == []
    assert auto.tick(now+timedelta(minutes=30)) == [("checkin", "sent")]
    assert auto.tick(now+timedelta(minutes=31)) == []
    assert [c[0] for c in calls] == ["study_session", "study_session_checkin"]
    assert "cached summary" in calls[0][1]


def test_auto_worker_manual_task_no_model_and_revocation(prepared, monkeypatch):
    import line_personal_auto_worker as auto
    import line_study_ai
    now, uid, _ = prepared
    _auto_config(monkeypatch)
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": True} for r in rows])
    storage.update_json(storage.data_path("tasks"), lambda rows: [
        {**r, "source": "manual", "source_feedback_id": ""} for r in rows])
    monkeypatch.setattr(line_study_ai, "organize_class_feedback",
                        lambda *a: pytest.fail("no new API calls"))
    calls = []
    monkeypatch.setattr(worker, "push_line_message", lambda u, r, t: calls.append(t) or True)
    selected = worker.sessions(now, automatic=True)[0]
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": False} for r in rows])
    assert worker.deliver_once(selected, now, automatic=True) == "invalid"
    assert auto.tick(now) == [] and not calls
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": True} for r in rows])
    assert auto.tick(now) == [("study", "sent")]
    assert len(calls) == 1 and "AI 根據" not in calls[0]
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": False} for r in rows])
    assert auto.tick(now+timedelta(minutes=30)) == []


def test_auto_worker_no_late_start_or_checkin_without_start(prepared, monkeypatch):
    import line_personal_auto_worker as auto
    now, _, _ = prepared
    _auto_config(monkeypatch)
    storage.update_json(storage.data_path("users"), lambda rows: [
        {**r, "study_reminders_enabled": True} for r in rows])
    monkeypatch.setattr(worker, "push_line_message", lambda *a: pytest.fail("unexpected late push"))
    assert auto.tick(now+timedelta(minutes=30)) == []
    assert auto.tick(now+timedelta(minutes=60)) == []
