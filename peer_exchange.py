"""自願交換匿名訓練模板，為多人 benchmark 建立可執行的資料介面。

注意：這是離線 JSON 交換，不是身份驗證的多人排名服務；
匯入數值為對方自行提供、無法證明真實性。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from math import ceil

from study_metrics import personal_metrics
from week_planner import PERIOD_BY_LABEL

FORMAT = "classpulse_training_profile"
SCHEMA_VERSION = 1
MAX_UPLOAD = 15000
ALLOWED_KEYS = {
    "format", "schema_version", "training", "evidence",
}


class PeerProfileError(ValueError):
    pass


def export_profile(board: dict, metric: dict, style_label: str = "自訂訓練節奏") -> bytes:
    """不輸出人名、學號、課名、LINE ID、個別事件時間或原始筆記。"""
    scheduled = board.get("scheduled", [])
    periods = []
    for row in scheduled:
        hour = row.get("hour")
        label = next((p for p, h in PERIOD_BY_LABEL.items() if h == hour), None)
        if label:
            periods.append(label)
    counts = Counter(periods)
    most_common = [label for label, _ in counts.most_common(5)]
    durations = [int(row.get("blocks", 1)) for row in scheduled]
    # 不透露個人日程；僅保留粗粒度 aggregate 與重複習慣。
    profile = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "training": {
            "name": style_label[:50],
            "sessions_per_week": min(len(scheduled), 16),
            "preferred_periods": most_common,
            "maximum_blocks": min(4, max(durations, default=1)),
            "goal": "將這種訓練節奏按收件者自身的課表、期限與空檔重新配置",
        },
        "evidence": {
            "completion_rate": metric.get("completion"),
            "checkin_rate": metric.get("checkin_rate"),
            "verification": "self_reported_unverified",
        },
    }
    return json.dumps(profile, ensure_ascii=False, indent=2).encode("utf-8")


def import_profile(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_UPLOAD:
        raise PeerProfileError("訓練模板應為不超過 15 KB 的 JSON 檔")
    try:
        profile = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PeerProfileError("訓練模板不是有效的 UTF-8 JSON") from exc
    if (not isinstance(profile, dict) or set(profile) != ALLOWED_KEYS
            or profile["format"] != FORMAT
            or profile["schema_version"] != SCHEMA_VERSION):
        raise PeerProfileError("不支援的 ClassPulse 訓練模板格式")
    training = profile["training"]
    evidence = profile["evidence"]
    if not isinstance(training, dict) or not isinstance(evidence, dict):
        raise PeerProfileError("訓練模板缺少必要資料")
    name = training.get("name")
    goal = training.get("goal")
    periods = training.get("preferred_periods")
    count = training.get("sessions_per_week")
    blocks = training.get("maximum_blocks")
    if (not isinstance(name, str) or not 1 <= len(name) <= 50
            or not isinstance(goal, str) or len(goal) > 200
            or not isinstance(periods, list) or len(periods) > 5
            or any(not isinstance(p, str) or p not in PERIOD_BY_LABEL for p in periods)
            or type(count) is not int or not 0 <= count <= 16
            or type(blocks) is not int or not 1 <= blocks <= 4
            or evidence.get("verification") != "self_reported_unverified"):
        raise PeerProfileError("訓練模板存在不合理的節次、長度或狀態")
    for k in ("completion_rate", "checkin_rate"):
        value = evidence.get(k)
        if value is not None and (type(value) not in (int, float) or not 0 <= value <= 100):
            raise PeerProfileError("參考指標不符合 0–100% 範圍")
    # Only use training rhythm for recommendation; never interpret imported score as peer rank.
    return {
        "name": name, "sessions_per_week": count,
        "preferred_periods": periods, "maximum_blocks": blocks,
        "goal": goal, "source": "peer_uploaded_unverified",
        "claimed_completion_rate": evidence.get("completion_rate"),
        "claimed_checkin_rate": evidence.get("checkin_rate"),
        "benchmark_verified": False,
    }
