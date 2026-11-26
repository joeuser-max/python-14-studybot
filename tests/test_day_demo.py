"""LINE 一日展示：08:00–21:00，三選一，不依賴外部 LINE / AI。"""
import pytest

from day_demo import SCENES, advance, new_day_state, respond, visible_messages


def test_day_covers_morning_to_night_with_three_choices_each():
    assert SCENES[0]["time"] == "08:00"
    assert SCENES[-1]["time"] == "21:00"
    assert len(SCENES) >= 12
    times = [scene["time"] for scene in SCENES]
    assert times == sorted(times)
    assert all(len(scene["options"]) == 3 for scene in SCENES)
    assert len({scene["time"] for scene in SCENES}) == len(SCENES)


def test_three_distinct_replies_and_message_order():
    replies = set()
    for i in range(3):
        state = new_day_state()
        assert visible_messages(state)[-1]["role"] == "bot"
        choice = respond(state, i)
        assert len(choice["messages"]) == 3
        assert [m["role"] for m in choice["messages"]] == ["bot", "user", "bot"]
        assert choice["messages"][0]["text"] == SCENES[0]["incoming"]
        assert choice["messages"][1]["text"] == SCENES[0]["options"][i][0]
        replies.add(choice["messages"][2]["text"])
        assert len(visible_messages(choice)) == 3
        assert state["messages"] == []  # 不 mutate 舊狀態
    assert len(replies) == 3


def test_one_day_can_finish_and_reset():
    state = new_day_state()
    while not state["completed"]:
        state = respond(state, 2)
        state = advance(state)
    assert len(state["messages"]) == len(SCENES) * 3
    assert state["decisions"]["08:00"] == SCENES[0]["options"][2][0]
    assert state["decisions"]["21:00"] == SCENES[-1]["options"][2][0]
    assert state["completed"] is True
    assert new_day_state()["index"] == 0


def test_invalid_choice_and_advance_rejected():
    initial = new_day_state()
    with pytest.raises(ValueError):
        respond(initial, 3)
    with pytest.raises(ValueError):
        respond(initial, -1)
    with pytest.raises(ValueError):
        advance(initial)
    selected = respond(initial, 0)
    with pytest.raises(ValueError):
        respond(selected, 1)
    assert advance(selected)["index"] == 1


def test_declined_ai_task_does_not_falsely_report_scheduled():
    from day_demo import incoming_for

    state = new_day_state()
    while state["index"] < 6:
        state = advance(respond(state, 1))
    assert SCENES[state["index"]]["time"] == "13:00"
    state = advance(respond(state, 2))  # 明確拒絕 AI 建議
    assert state["signals"]["accepted_task_minutes"] is None
    assert "尚未確認" in incoming_for(state)
    state = respond(state, 0)
    assert "不會擅自" in state["messages"][-1]["text"]
    assert state["signals"]["scheduled_at"] is None


def test_ai_accepted_task_updates_schedule_and_evening_progress():
    state = new_day_state()
    while state["index"] < 6:
        state = advance(respond(state, 0))
    state = advance(respond(state, 1))  # 確認 30 分鐘
    assert state["signals"]["accepted_task_minutes"] == 30
    state = advance(respond(state, 0))  # 19:00 排程
    assert state["signals"]["scheduled_at"] == "19:00"
    while SCENES[state["index"]]["time"] != "20:15":
        state = advance(respond(state, 0))
    state = advance(respond(state, 1))  # 完成 70%
    assert state["signals"]["task_progress"] == 70
    state = respond(state, 0)  # 21:00 動態回顧
    assert "70%" in state["messages"][-1]["text"]
    assert "已確認 AI 任務：1 項" in state["messages"][-1]["text"]
