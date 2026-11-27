"""Idempotent LINE user registration for the upcoming ClassPulse friend Demo.

Only signed LINE Webhook handlers may pass a LINE user ID into this module.
Registration alone DOES NOT seed a demo, authenticate the Streamlit UI, or
enable reminders. Do not expose users created here to the public UI yet.
"""

from __future__ import annotations

import re
from datetime import datetime

from storage import TZ, DataError, create_id, data_path, update_json

# LINE personal user IDs begin with U; permit short synthetic test IDs too.
_LINE_USER_ID = re.compile(r"^U[A-Za-z0-9_-]{2,64}$")


def is_valid_line_user_id(value: object) -> bool:
    return isinstance(value, str) and _LINE_USER_ID.fullmatch(value) is not None


def get_or_create_line_user(line_user_id: str) -> tuple[dict, bool]:
    """Atomically return (stored_user, newly_created) without changing legacy rows.

    A repeated follow/message from the same LINE account resolves to exactly
    the same ClassPulse user, even when multiple requests arrive together.
    """
    if not is_valid_line_user_id(line_user_id):
        raise DataError("無效的 LINE 個人使用者識別碼")

    result: dict = {}

    def register(users: list) -> list:
        existing = next(
            (u for u in users if u.get("line_user_id") == line_user_id),
            None,
        )
        if existing is not None:
            result["user"] = existing
            result["created"] = False
            return users

        user = {
            "user_id": create_id("lineuser"),
            "line_user_id": line_user_id,
            # This is NOT a ready-to-use personal demo yet.
            "demo_status": "pending_seed",
            "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
            # An invitation must never silently enable push or paid AI calls.
            "reminders_enabled": False,
            "study_reminders_enabled": False,
            "ai_after_class_enabled": False,
        }
        result["user"] = user
        result["created"] = True
        return users + [user]

    update_json(data_path("users"), register)
    return result["user"].copy(), result["created"]
