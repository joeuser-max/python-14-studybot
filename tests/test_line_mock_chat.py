"""LINE Mock 對話 UI 的純狀態機回歸測試：依原 Webhook 菜單逐步操作。"""
from datetime import date

import pytest

from demo_data import sample_records
from line_mock_chat import start_chat, choices, advance_chat, step_number


COURSES = sample_records()["events"]
DAY = date(2026, 11, 27)


def _next(state, selection):
    return advance_chat(state, selection, COURSES)


def test_guided_line_chat_full_flow_and_explicit_feedback_then_task():
    chat = start_chat(DAY, COURSES)
    assert chat["stage"] == "menu"
    assert "LINE Mock" in chat["messages"][0]["text"]
    assert "補筆記" in [x[0] for x in choices(chat, COURSES)]

    chat, effect = _next(chat, "補筆記")
    assert chat["stage"] == "weekday" and effect is None
    assert len(choices(chat, COURSES)) == 7

    chat, effect = _next(chat, "星期三")
    assert chat["stage"] == "class_slot" and effect is None
    available = choices(chat, COURSES)
    assert len(available) >= 2
    chosen_id, chosen_label = available[0]
    chat, effect = _next(chat, chosen_id)
    assert chat["stage"] == "progress" and effect is None
    assert "｜" in chosen_label

    chat, effect = _next(chat, "3")
    assert chat["stage"] == "note"
    assert effect is None and chat["progress"] == 3
    assert choices(chat, COURSES) == []
    assert step_number("note") == 5

    chat, effect = _next(chat, "今天學到閉迴路傳遞函數，但不理解 Routh 判別")
    assert chat["stage"] == "ai_confirm"
    assert effect["type"] == "save_feedback"
    assert effect["event_id"] == chosen_id
    assert effect["progress"] == 3
    assert effect["class_date"] != ""
    assert "【Mock AI" in chat["messages"][-1]["text"]
    assert "加入讀書任務" in [x[0] for x in choices(chat, COURSES)]

    chat["saved_feedback_id"] = "feedback_test_id"
    chat, effect = _next(chat, "加入讀書任務")
    assert chat["stage"] == "finished"
    assert effect["type"] == "add_task"
    assert effect["source_feedback_id"] == "feedback_test_id"
    assert "自動移動其他任務" in chat["messages"][-1]["text"]
    assert [x["role"] for x in chat["messages"]].count("user") == 6


def test_chat_cancel_and_skip_never_write():
    chat = start_chat(DAY, COURSES)
    chat, effect = _next(chat, "稍後")
    assert chat["stage"] == "finished" and effect is None
    chat, effect = _next(chat, "重新開始")
    chat, effect = _next(chat, "補筆記")
    chat, effect = _next(chat, "取消")
    assert chat["stage"] == "finished" and effect is None

    chat, _ = _next(chat, "重新開始")
    chat, _ = _next(chat, "補筆記")
    chat, _ = _next(chat, "星期三")
    chat, _ = _next(chat, choices(chat, COURSES)[0][0])
    chat, _ = _next(chat, "1")
    chat, cmd = _next(chat, "記得整理穩定度")
    assert cmd["type"] == "save_feedback"
    chat, cmd = _next(chat, "保留筆記")
    assert chat["stage"] == "finished" and cmd is None


def test_invalid_inputs_do_not_advance_or_write():
    chat = start_chat(DAY, COURSES)
    with pytest.raises(ValueError):
        _next(chat, "任意不合法字串")
    assert chat["stage"] == "menu"
    chat, _ = _next(chat, "補筆記")
    with pytest.raises(ValueError):
        _next(chat, "星期八")
    chat, _ = _next(chat, "星期一")
    with pytest.raises(ValueError):
        _next(chat, "no_such_event")
    chat, _ = _next(chat, choices(chat, COURSES)[0][0])
    with pytest.raises(ValueError):
        _next(chat, "0")
    chat, _ = _next(chat, "5")
    with pytest.raises(ValueError):
        _next(chat, "a")
    assert chat["stage"] == "note"


def test_view_schedule_keeps_chat_at_menu():
    chat = start_chat(DAY, COURSES)
    chat, effect = _next(chat, "查看課表")
    assert chat["stage"] == "menu" and effect is None
    assert "這一天的課表" in chat["messages"][-1]["text"]
