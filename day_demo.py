"""LINE 一日展示：08:00–21:00，純本機情境，絕不呼叫外部服務。"""
from __future__ import annotations

from copy import deepcopy


SCENES = (
    {"time": "08:00", "title": "早晨規劃", "kind": "今日總覽",
     "incoming": "早安！今天有課程、待複習事項和晚間讀書計畫。要先從哪裡開始？",
     "options": (
         ("查看今日安排", "已整理：09:00 課程、14:00 排程更新、19:00 晚間複習。"),
         ("查看優先任務", "目前優先處理「複習控制系統回授」，期限比其他任務更早。"),
         ("提醒我晚點查看", "已在展示情境中標記稍後查看；沒有真的設定手機推播。"),
     )},
    {"time": "08:45", "title": "上課前提醒", "kind": "課前提醒",
     "incoming": "15 分鐘後要上課了。建議先看一下上次還沒理解的主題。",
     "options": (
         ("看上次筆記", "上次標記待釐清：回授系統的相位裕度與穩定性。"),
         ("我準備好了", "收到。上課後我會再提醒你回報理解進度。"),
         ("今天沒辦法上課", "已模擬記錄缺席備註；正式缺課通知需由用戶自行處理。"),
     )},
    {"time": "09:00", "title": "課程開始", "kind": "學習入口",
     "incoming": "課程開始了。這段時間專注聽課即可，有問題可以先用快捷選項標記。",
     "options": (
         ("先標記一個疑問", "已模擬加入待整理項目：本堂有尚未理解的概念。"),
         ("查看課程目標", "今天的示範目標：理解回授與系統穩定度。"),
         ("暫不互動", "好的，課後會再提醒你整理筆記。"),
     )},
    {"time": "10:50", "title": "課後理解度", "kind": "課後回饋",
     "incoming": "下課了。這堂課你大概理解多少？用一個選項快速回報即可。",
     "options": (
         ("理解 5 / 5", "已模擬記錄理解度 5/5；我會把今天的筆記歸在同一課次。"),
         ("理解 3 / 5", "已模擬記錄理解度 3/5；接下來可以選擇待釐清問題。"),
         ("理解 1 / 5", "已模擬記錄理解度 1/5；複習建議會優先從基礎概念開始。"),
     )},
    {"time": "11:05", "title": "補記課堂重點", "kind": "LINE 回覆",
     "incoming": "請選一則示範筆記發送給 ClassPulse。真實版本可以輸入文字；這裡只用三個按鍵展示。",
     "options": (
         ("回授可改善穩態誤差", "已模擬儲存筆記：「回授可改善穩態誤差」。同課次筆記會合併顯示。"),
         ("相位裕度還不理解", "已模擬儲存疑問：「相位裕度還不理解」。可供後續 AI 分析。"),
         ("想練習穩定度題目", "已模擬儲存需求：「想練習穩定度題目」。"),
     )},
    {"time": "12:00", "title": "AI 整理", "kind": "AI 分析 · Mock",
     "incoming": "【Mock AI】已依筆記示範整理摘要：你需要釐清穩定性與相位裕度。要看哪個內容？",
     "options": (
         ("查看重點整理", "【Mock】重點：回授架構、閉迴路極點、相位裕度。未呼叫真實 AI API。"),
         ("查看待解問題", "【Mock】待釐清：相位裕度如何影響系統的穩定裕量？"),
         ("查看複習建議", "【Mock】建議任務：練習 3 題回授系統穩定度問題，預估 45 分鐘。"),
     )},
    {"time": "13:00", "title": "確認 AI 任務", "kind": "Human-in-the-loop",
     "incoming": "【Mock AI 建議】要將「練習回授系統穩定度」加入讀書任務嗎？不會自動替你決定。",
     "options": (
         ("確認加入任務", "已在一日模擬中建立待排程任務：練習回授系統穩定度，45 分鐘。"),
         ("改為 30 分鐘後加入", "已在一日模擬中建立待排程任務：練習回授系統穩定度，30 分鐘。"),
         ("先不要加入", "已保留 AI 建議，但沒有新增任務；稍後可以重新確認。"),
     )},
    {"time": "14:00", "title": "讀書排程", "kind": "Scheduler",
     "incoming": "現在可以替已確認的任務找一個可用時段。規則式 Scheduler 會檢查期限、時長與時段衝突。",
     "options": (
         ("安排 19:00", "已模擬將待處理的複習事項放在 19:00；這是展示，不改寫正式排程。"),
         ("安排 20:00", "已模擬選擇 20:00 時段；若與其他事件衝突，實際 Scheduler 會拒絕。"),
         ("查看無法排入原因", "展示可能原因：沒有足夠時段、和其他課程重疊、或晚於 Deadline。"),
     )},
    {"time": "16:30", "title": "排程異常處理", "kind": "未排入通知",
     "incoming": "某項任務暫時找不到合適空檔。要怎麼處理？",
     "options": (
         ("增加可用時段", "已模擬引導至控制台新增時間；重新排程後才能確認是否可放入。"),
         ("調整 Deadline", "已模擬要求確認期限；實際資料需要本人在任務卡片內修改。"),
         ("保留未排入", "已保留待安排狀態，不會假裝此任務已成功排入。"),
     )},
    {"time": "18:00", "title": "手機行事曆", "kind": "Calendar 匯出",
     "incoming": "晚間安排快到了。你可以把計畫輸出到手機行事曆，方便隨時查看。",
     "options": (
         ("顯示讀書計畫", "今晚示範計畫：19:00 複習，20:15 回顧。實際時間依排程結果為準。"),
         ("Google Calendar", "可在控制台開啟 Google Calendar 新增事件連結；須自行確認後加入。"),
         ("Apple Calendar", "可從控制台下載 .ics 並用 iPhone 或 Mac 行事曆匯入。"),
     )},
    {"time": "19:00", "title": "開始讀書提醒", "kind": "學習時段",
     "incoming": "【模擬 LINE 推播】你的複習時段開始了：控制系統，建議持續 45 分鐘。",
     "options": (
         ("我開始讀書了", "已模擬標記讀書開始；這不是背景計時器。"),
         ("先完成 50%", "已在一日模擬中標記 50% 進度；正式進度由控制台任務卡片調整。"),
         ("延後 15 分鐘", "已模擬延後提醒的對話；正式版需重新檢查時間衝突。"),
     )},
    {"time": "20:15", "title": "學習成果回報", "kind": "任務進度",
     "incoming": "今晚的讀書時段結束了。要怎麼回報任務完成度？",
     "options": (
         ("完成 100%", "已在一日模擬中標記 100%，任務狀態：已完成。"),
         ("完成 70%", "已在一日模擬中標記 70%，未完成部分保留待下次安排。"),
         ("沒有開始", "已在一日模擬中標記 0%，不會誤認任務已完成。"),
     )},
    {"time": "21:00", "title": "一天結束", "kind": "每日回顧",
     "incoming": "今天辛苦了！最後可以回顧成果、查看明天的計畫，或匯出學習資料。",
     "options": (
         ("查看今日統計", "展示：今天有 1 次課後回饋、1 則 AI 建議與晚間讀書回報，數值取自模擬流程。"),
         ("查看明日優先任務", "依 Deadline 與未完成狀態，明天優先整理今天還沒理解的內容。"),
         ("匯出學習紀錄", "可在控制台匯出 Markdown 與 .ics；LINE 模擬本身不會寫入正式檔案。"),
     )},
)


def new_day_state() -> dict:
    return {"index": 0, "awaiting_next": False, "messages": [],
            "decisions": {}, "completed": False,
            "signals": {"understanding": None, "note": None,
                        "accepted_task_minutes": None, "scheduled_at": None,
                        "task_progress": None}}


def incoming_for(state: dict) -> str:
    """根據既有決策避免下一場景說出互相矛盾的提示。"""
    scene = SCENES[state["index"]]
    signals = state.get("signals", {})
    if scene["time"] == "14:00" and signals.get("accepted_task_minutes") is None:
        return "你尚未確認 AI 的建議任務；本時段會展示排程器的選項，但不會宣稱已排入。"
    if scene["time"] == "19:00" and signals.get("scheduled_at") is None:
        return "【模擬 LINE 推播】晚間讀書時段到了。還沒安排 AI 建議任務，可以先查看既有計畫。"
    return scene["incoming"]


def _reply_and_signals(state: dict, scene: dict, index: int) -> str:
    """更新當天模擬狀態；不寫入 JSON，亦不與真實 LINE 連線。"""
    signals = state["signals"]
    time = scene["time"]
    if time == "10:50":
        signals["understanding"] = (5, 3, 1)[index]
    elif time == "11:05":
        signals["note"] = scene["options"][index][0]
    elif time == "13:00":
        signals["accepted_task_minutes"] = (45, 30, None)[index]
    elif time == "14:00":
        if signals["accepted_task_minutes"] is None:
            signals["scheduled_at"] = None
            return "沒有經你確認的 AI 任務，排程器不會擅自將它加入計畫。這裡只展示可用時段操作。"
        signals["scheduled_at"] = ("19:00", "20:00", None)[index]
        if index == 2:
            return "已展示其他時段與可能衝突；此時仍未確認最終排程。"
        return (f"已模擬把已確認的 {signals['accepted_task_minutes']} 分鐘複習任務"
                f"安排在 {signals['scheduled_at']}；未寫入正式資料。")
    elif time == "20:15":
        signals["task_progress"] = (100, 70, 0)[index]
    elif time == "21:00" and index == 0:
        return ("【Mock 今日統計】筆記："
                f"{1 if signals['note'] else 0} 則；"
                f"已確認 AI 任務：{1 if signals['accepted_task_minutes'] else 0} 項；"
                f"晚間回報完成度：{signals['task_progress'] if signals['task_progress'] is not None else '未提供'}%。")
    return scene["options"][index][1]


def respond(state: dict, option_index: int) -> dict:
    """點按一個虛擬選項，加入使用者訊息與相應的 LINE 虛擬回覆。"""
    if state["completed"] or state["awaiting_next"]:
        raise ValueError("目前不能選擇選項")
    if not isinstance(option_index, int) or not 0 <= option_index < 3:
        raise ValueError("請選擇三個選項之一")
    updated = deepcopy(state)
    scene = SCENES[updated["index"]]
    selected, _ = scene["options"][option_index]
    incoming = incoming_for(state)
    reply = _reply_and_signals(updated, scene, option_index)
    updated["messages"].extend([
        {"at": scene["time"], "role": "bot", "text": incoming},
        {"at": scene["time"], "role": "user", "text": selected},
        {"at": scene["time"], "role": "bot", "text": reply},
    ])
    updated["decisions"][scene["time"]] = selected
    updated["awaiting_next"] = True
    return updated


def advance(state: dict) -> dict:
    if state["completed"] or not state["awaiting_next"]:
        raise ValueError("請先完成此時段的互動")
    updated = deepcopy(state)
    if updated["index"] == len(SCENES) - 1:
        updated["completed"] = True
    else:
        updated["index"] += 1
        updated["awaiting_next"] = False
    return updated


def visible_messages(state: dict) -> list[dict]:
    """在目前時段之前的真實模擬對話，加上目前 LINE Bot 主動訊息。"""
    messages = list(state["messages"])
    if not state["awaiting_next"] and not state["completed"]:
        scene = SCENES[state["index"]]
        messages.append({"at": scene["time"], "role": "bot", "text": incoming_for(state)})
    return messages
