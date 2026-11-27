"""Step 12.1: per-friend registration tests (no LINE credentials or network)."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import storage
from line_demo_registration import get_or_create_line_user


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    # Keep real local LINE users and notes completely untouched.
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.select_demo_storage(False)


def test_each_line_friend_has_separate_identity_and_retries_are_idempotent():
    first, created_first = get_or_create_line_user("U_demo_person_A")
    repeated, created_again = get_or_create_line_user("U_demo_person_A")
    second, created_second = get_or_create_line_user("U_demo_person_B")

    assert (created_first, created_again, created_second) == (True, False, True)
    assert first["user_id"] == repeated["user_id"]
    assert first["user_id"] != second["user_id"]
    assert first["user_id"] != "demo_user_001"
    assert first["demo_status"] == "pending_seed"
    assert not first["reminders_enabled"]
    assert not first["study_reminders_enabled"]
    assert not first["ai_after_class_enabled"]

    users = storage.load_json(storage.data_path("users"))
    assert len(users) == 2
    assert {u["line_user_id"] for u in users} == {
        "U_demo_person_A", "U_demo_person_B"
    }


def test_legacy_bound_user_is_not_overwritten_or_rebound():
    legacy = {
        "user_id": "demo_user_001",
        "line_user_id": "U_legacy_123",
        "reminders_enabled": True,
    }
    storage.save_json(storage.data_path("users"), [legacy])
    same, created = get_or_create_line_user("U_legacy_123")

    assert not created
    assert same == legacy
    assert storage.load_json(storage.data_path("users")) == [legacy]


@pytest.mark.parametrize("invalid", ["", "not-line", "U", "U space", "U/../../bad", None])
def test_invalid_line_identity_never_adds_a_record(invalid):
    with pytest.raises(storage.DataError):
        get_or_create_line_user(invalid)
    assert storage.load_json(storage.data_path("users")) == []


def test_concurrent_registration_of_same_friend_stays_one_record():
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(get_or_create_line_user, ["U_concurrent_friend"] * 12))

    assert len({u["user_id"] for u, _ in results}) == 1
    assert sum(1 for _, created in results if created) == 1
    assert len(storage.load_json(storage.data_path("users"))) == 1
