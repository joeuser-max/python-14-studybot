"""Step 14: no real data, credentials, or network required."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

import storage
import line_demo_seed as seed
from line_demo_registration import get_or_create_line_user
from note_tasks import candidate_tasks

NOW = datetime(2026, 11, 28, 10, tzinfo=storage.TZ)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "live")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    monkeypatch.delenv("LINE_FRIEND_DEMO_SEED_ENABLED", raising=False)


def rows(name):
    return storage.load_json(storage.data_path(name))


def snapshot():
    return {name: rows(name) for name in storage.FILES}


def register(uid="U_seed_A"):
    return get_or_create_line_user(uid)[0]["user_id"]


def test_two_users_have_disjoint_records_and_valid_references():
    a, b = register(), register("U_seed_B")
    assert seed.seed_line_user(a, NOW)
    assert seed.seed_line_user(b, NOW)
    all_rows = snapshot()
    for user in (a, b):
        own = {name: [r for r in rs if r.get("user_id") == user]
               for name, rs in all_rows.items()}
        assert len(own["events"]) == 14
        assert len(own["tasks"]) == 15
        assert len(own["feedback"]) == 5
        assert len(own["plan"]) == 3
        assert len(own["external_events"]) == 3
        courses = {r["event_id"] for r in own["events"]}
        tasks = {r["task_id"] for r in own["tasks"]}
        slots = {r["availability_id"] for r in own["availability"]}
        notes = {r["feedback_id"] for r in own["feedback"]}
        assert all(r["event_id"] in courses for r in own["feedback"])
        assert all(r["task_id"] in tasks and r["availability_id"] in slots
                   for r in own["plan"])
        purple = [t for t in own["tasks"] if t.get("source") == "ai_confirmed"]
        assert len(purple) == 1 and purple[0]["estimated_minutes"] == 30
        assert purple[0]["source_feedback_id"] in notes
        assert purple[0]["source_event_id"] in courses
        candidates = candidate_tasks(all_rows["feedback"], all_rows["events"],
                                     all_rows["tasks"], user, NOW)
        assert candidates and all(c["source_feedback_id"] in notes for c in candidates)
        assert own["users"][0]["demo_status"] == seed.SEEDED_STATUS
        assert all(own["users"][0][k] is False for k in
                   ("reminders_enabled", "study_reminders_enabled", "ai_after_class_enabled"))
    for name, key in seed.KEYS.items():
        ids = [r[key] for r in all_rows[name]]
        assert len(ids) == len(set(ids))
    assert len({n["webhook_event_id"] for n in all_rows["feedback"]}) == 10
    assert not all_rows["reminders"]
    assert not all_rows["processed_webhooks"]


def test_reseed_does_not_overwrite_edits_or_restore_deleted_rows():
    uid = register()
    assert seed.seed_line_user(uid, NOW)
    storage.update_json(storage.data_path("events"),
                        lambda rs: [{**rs[0], "title": "edited"}] + rs[2:])
    before = snapshot()
    assert not seed.seed_line_user(uid, NOW + timedelta(days=2))
    assert snapshot() == before


def test_existing_legacy_records_and_other_users_preserved():
    legacy = {"user_id": "demo_user_001", "line_user_id": "U_legacy", "reminders_enabled": True}
    storage.save_json(storage.data_path("users"), [legacy])
    record = {"event_id": "legacy_event", "user_id": legacy["user_id"]}
    storage.save_json(storage.data_path("events"), [record])
    uid = register()
    assert seed.seed_line_user(uid, NOW)
    assert rows("users")[0] == legacy
    assert rows("events")[0] == record
    with pytest.raises(storage.DataError):
        seed.seed_line_user(legacy["user_id"], NOW)


def test_interrupted_seed_retries_with_same_anchor(monkeypatch):
    uid = register()
    original = seed._append_missing
    def fail(name, entries, user_id):
        if name == "tasks":
            raise storage.DataError("simulated failure")
        original(name, entries, user_id)
    monkeypatch.setattr(seed, "_append_missing", fail)
    with pytest.raises(storage.DataError):
        seed.seed_line_user(uid, NOW)
    assert rows("users")[0]["demo_status"] == "pending_seed"
    old_events, old_slots = rows("events"), rows("availability")
    monkeypatch.setattr(seed, "_append_missing", original)
    assert seed.seed_line_user(uid, NOW + timedelta(days=1))
    assert rows("events") == old_events and rows("availability") == old_slots
    assert rows("users")[0]["demo_seed_started_at"] == NOW.isoformat(timespec="seconds")
    assert len(rows("tasks")) == 15


def test_concurrent_seed_completes_once():
    uid = register()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: seed.seed_line_user(uid, NOW), range(6)))
    assert sum(results) == 1
    assert len(rows("events")) == 14 and len(rows("tasks")) == 15


def test_collision_rejected_without_overwriting_foreign_record():
    uid = register()
    collision = {"event_id": f"{uid}_demo_class_solid_mon", "user_id": "other"}
    storage.save_json(storage.data_path("events"), [collision])
    with pytest.raises(storage.DataError):
        seed.seed_line_user(uid, NOW)
    assert rows("events") == [collision]
    assert rows("users")[0]["demo_status"] == "pending_seed"


def test_reject_shared_demo_context():
    uid = register()
    storage.select_demo_storage(True)
    try:
        with pytest.raises(storage.DataError):
            seed.seed_line_user(uid, NOW)
    finally:
        storage.select_demo_storage(False)
    assert rows("users")[0]["demo_status"] == "pending_seed"
