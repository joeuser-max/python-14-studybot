"""交換的同儕訓練檔只含彙總欄位，不含可識別個人日程。"""
import json
import pytest

from peer_exchange import PeerProfileError, export_profile, import_profile


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
