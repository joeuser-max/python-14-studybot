"""交換的同儕訓練檔只含彙總欄位，不含可識別個人日程。"""
import json
import pytest

from peer_exchange import PeerProfileError, export_profile, import_profile, combine_profiles
from pathlib import Path


def test_anonymous_profile_roundtrip_without_personal_data():
    board = {"scheduled": [
        {"task_id": "super-private-id", "title": "Sensitive course",
         "day": "2026-11-27", "hour": 19, "blocks": 2},
        {"task_id": "t2", "title": "private task", "hour": 20, "blocks": 1},
    ]}
    raw = export_profile(board, {"completion": 45, "checkin_rate": 60})
    assert b"super-private-id" not in raw
    assert b"Sensitive course" not in raw
    assert b"2026-11-27" not in raw
    template = import_profile(raw)
    assert template["sessions_per_week"] == 2
    assert template["maximum_blocks"] == 2
    assert template["source"] == "peer_uploaded_unverified"


def test_refuse_forged_ranges_and_extra_identifiers():
    raw = export_profile({"scheduled": []}, {"completion": 50, "checkin_rate": None})
    data = json.loads(raw)
    data["name"] = "姓名禁止進入匿名模板"
    with pytest.raises(PeerProfileError):
        import_profile(json.dumps(data, ensure_ascii=False).encode())
    data.pop("name")
    data["evidence"]["completion_rate"] = 150
    with pytest.raises(PeerProfileError):
        import_profile(json.dumps(data, ensure_ascii=False).encode())


def test_two_fictional_profiles_form_an_unverified_group_template():
    root = Path(__file__).resolve().parents[1] / "examples"
    night = import_profile((root / "fictional_peer_evening.json").read_bytes())
    morning = import_profile((root / "fictional_peer_morning.json").read_bytes())
    combined = combine_profiles([night, morning])
    assert combined["peer_count"] == 2
    assert combined["sessions_per_week"] == 5
    assert combined["maximum_blocks"] == 2
    assert combined["benchmark_verified"] is False
    assert combined["source"] == "local_group_profiles_unverified"
    assert "claimed_completion_rate" not in combined
    assert set(combined["preferred_periods"]).issubset({"1", "2", "5", "A", "B", "C"})


def test_group_rejects_unverified_or_too_few_profiles():
    one = import_profile(export_profile({"scheduled": []}, {"completion": 80, "checkin_rate": 50}))
    with pytest.raises(PeerProfileError):
        combine_profiles([one])
    with pytest.raises(PeerProfileError):
        combine_profiles([one, {**one, "benchmark_verified": True}])
