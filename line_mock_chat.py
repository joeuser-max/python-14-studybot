"""展示用 LINE 聊天引導狀態機；不發送 LINE，也不直接改寫資料庫。

與正式 line_bot.py 的「補筆記→星期→課次→1–5→筆記→AI 任務確認」
順序相同。所有儲存動作由呼叫方確認後執行，避免 UI 刷新重送。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta

WEEKDAYS = {
    "星期一": 1, "星期二": 2, "星期三": 3, "星期四": 4,
    "星期五": 5, "星期六": 6, "星期日": 7,
}
MAX_NOTE_LENGTH = 2000
STAGES = ("menu", "weekday", "class_slot", "progress", "note", "ai_confirm", "finished")


def _bot(state: dict, message: str) -> None:
    state["messages"].append({"role": "assistant", "text": message})


def _user(state: dict, message: str) -> None:
    state["messages"].append({"role": "user", "text": message})


def start_chat(day: date, courses: list[dict]) -> dict:
    classes = [c for c in courses if c.get("weekday") == day.isoweekday()]
    title = classes[0].get("title", "課程") if classes else "今天的課程"
    state = {
        "day": day.isoformat(), "stage": "menu",
        "messages": [], "weekday": None, "course_id": "",
        "course_title": "", "class_date": "", "progress": None,
        "note": "", "suggested_title": "", "saved_feedback_id": "",
    }
    _bot(state, f"【LINE Mock｜{day:%m/%d}】「{title}」下課囉！"
                "要補筆記、稍後再說，還是查看課表？")
    return state


def choices(state: dict, courses: list[dict]) -> list[tuple[str, str]]:
    stage = state["stage"]
    if stage == "menu":
        return [(v, v) for v in ("補筆記", "稍後", "查看課表")]
    if stage == "weekday":
        return [(label, label) for label in WEEKDAYS]
    if stage == "class_slot":
        target = state.get("weekday")
        matches = sorted(
            (c for c in courses if c.get("weekday") == target),
            key=lambda c: (c["start_time"], c["end_time"], c["title"]),
        )
        return [(c["event_id"], f"{c['start_time']}–{c['end_time']}｜{c['title']}")
                for c in matches]
    if stage == "progress":
        return [(str(i), str(i)) for i in range(1, 6)]
    if stage == "ai_confirm":
        return [("加入讀書任務", "加入讀書任務"), ("保留筆記", "只保留筆記")]
    if stage == "finished":
        return [("重新開始", "重新開始")]
    return []


def step_number(stage: str) -> int:
    return {
        "menu": 1, "weekday": 2, "class_slot": 3, "progress": 4,
        "note": 5, "ai_confirm": 6, "finished": 6,
    }[stage]


def advance_chat(state: dict, choice: str, courses: list[dict]) -> tuple[dict, dict | None]:
    """回傳新狀態、待執行的展示資料指令；對任何無效輸入均不產生指令。"""
    if state.get("stage") not in STAGES:
        raise ValueError("LINE 模擬階段不合法")
    current = deepcopy(state)
    stage = current["stage"]
    effect = None

    if choice == "取消":
        _user(current, "取消")
        _bot(current, "已取消補筆記。隨時可以重新開始。")
        current["stage"] = "finished"
        return current, None
    if stage == "finished":
        if choice != "重新開始":
            raise ValueError("請選擇重新開始")
        return start_chat(date.fromisoformat(current["day"]), courses), None

    if stage == "menu":
        if choice not in {"補筆記", "稍後", "查看課表"}:
            raise ValueError("請選擇 LINE 快速回覆")
        _user(current, choice)
        if choice == "稍後":
            _bot(current, "好的，這是示範訊息，不會真的排定提醒。需要時再按「重新開始」。")
            current["stage"] = "finished"
        elif choice == "查看課表":
            listing = [
                f"{c['start_time']}–{c['end_time']} {c['title']}"
                for c in courses if c.get("weekday") == date.fromisoformat(current["day"]).isoweekday()
            ]
            _bot(current, "這一天的課表：\n" + ("\n".join(listing) if listing else "目前沒有課程")
                 + "\n\n要繼續補筆記嗎？")
        else:
            current["stage"] = "weekday"
            _bot(current, "請選擇要補筆記的星期（正式 LINE 流程會在 10 分鐘後逾時）。")
        return current, None

    if stage == "weekday":
        weekday = WEEKDAYS.get(choice)
        if weekday is None:
            raise ValueError("請選擇星期一至星期日")
        _user(current, choice)
        matches = [c for c in courses if c.get("weekday") == weekday]
        if not matches:
            _bot(current, "這一天尚未設定課程，請換一個星期，或按取消。")
            return current, None
        current["weekday"] = weekday
        current["stage"] = "class_slot"
        _bot(current, "請選擇上課時段／課程：\n" +
             "\n".join(f"{c['start_time']}–{c['end_time']}｜{c['title']}" for c in
                       sorted(matches, key=lambda c: c["start_time"])))
        return current, None

    if stage == "class_slot":
        match = next((c for c in courses if c.get("event_id") == choice
                      and c.get("weekday") == current["weekday"]), None)
        if match is None:
            raise ValueError("找不到選擇的課次")
        selected_day = date.fromisoformat(current["day"])
        offset = (int(current["weekday"]) - selected_day.isoweekday()) % 7
        class_date = selected_day + timedelta(days=offset)
        current.update(
            course_id=match["event_id"], course_title=match["title"],
            class_date=class_date.isoformat(), stage="progress",
        )
        _user(current, f"{match['start_time']}–{match['end_time']}｜{match['title']}")
        _bot(current, f"已選擇「{match['title']}」。本堂課理解程度是幾分？"
             "\n1＝還不太理解，3＝部分理解，5＝很有把握。")
        return current, None

    if stage == "progress":
        if choice not in {"1", "2", "3", "4", "5"}:
            raise ValueError("理解程度只能選 1–5")
        _user(current, choice + "／5")
        current["progress"] = int(choice)
        current["stage"] = "note"
        _bot(current, "請輸入今天學到的重點，以及還不理解的問題。")
        return current, None

    if stage == "note":
        text = choice.strip()
        if len(text) < 2 or len(text) > MAX_NOTE_LENGTH:
            raise ValueError("筆記長度須介於 2–2000 字")
        _user(current, text)
        current["note"] = text
        current["suggested_title"] = f"整理「{current['course_title']}」的課堂疑問並練習"
        current["stage"] = "ai_confirm"
        _bot(current, "【Mock AI，並未呼叫模型】筆記和自評已記錄在展示資料。\n"
             f"建議複習任務：{current['suggested_title']}（60 分鐘）。\n"
             "要加入待排盒，還是只保留筆記？")
        effect = {
            "type": "save_feedback", "event_id": current["course_id"],
            "class_date": current["class_date"],
            "progress": current["progress"], "content": text,
        }
        return current, effect

    if stage == "ai_confirm":
        if choice not in {"加入讀書任務", "保留筆記"}:
            raise ValueError("請選擇加入任務或保留筆記")
        _user(current, choice)
        if choice == "加入讀書任務":
            effect = {
                "type": "add_task", "subject": current["course_title"],
                "title": current["suggested_title"],
                "source_feedback_id": current.get("saved_feedback_id", ""),
                "class_date": current["class_date"],
            }
            _bot(current, "已將此 Mock 建議加入待排盒。請到七日規劃板自己安排，"
                 "或按「一鍵填滿」；不會自動移動其他任務。")
        else:
            _bot(current, "好的，保留筆記，不建立新任務。")
        current["stage"] = "finished"
        return current, effect

    raise ValueError("此階段不接受按鈕輸入")
