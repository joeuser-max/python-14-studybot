"""ClassPulse Streamlit 前端（蕭博軒）。執行：streamlit run app.py"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import streamlit as st

from ai_assistant import analyze_learning_records, AIError
from exporter import export_learning_markdown
from storage import (
    DataError, TZ, add_availability, add_event, add_task_to_storage,
    create_id, data_path, load_json, save_json, set_task_status,
)
from tracker import calculate_response_rate, calculate_task_progress
from plan_bridge import normalize_plan_result

USER_ID = "demo_user_001"  # MVP：單一測試使用者；正式多人版須加入登入機制
WEEKDAYS = {1: "週一", 2: "週二", 3: "週三", 4: "週四", 5: "週五", 6: "週六", 7: "週日"}

st.set_page_config(page_title="ClassPulse", page_icon="📚", layout="wide")
st.title("ClassPulse")
st.caption("主動式學習回饋與規劃助手｜蕭博軒負責：介面、JSON、統計、Markdown、AI 分析")


def read_all() -> dict:
    return {name: load_json(data_path(name)) for name in
            ("events", "tasks", "availability", "plan", "reminders", "feedback")}


def own(records: list) -> list:
    return [x for x in records if x.get("user_id") == USER_ID]


def safely(action, success: str) -> None:
    try:
        action()
        st.success(success)
        st.rerun()
    except (DataError, ValueError) as exc:
        st.error(str(exc))


try:
    records = read_all()
except DataError as exc:
    st.error(f"資料載入失敗：{exc}")
    st.stop()

pages = st.tabs(["課表與時段", "讀書任務與排程", "回饋與進度", "Markdown 與 AI"])

with pages[0]:
    st.subheader("設定每週課表")
    with st.form("add_class", clear_on_submit=True):
        name = st.text_input("課程名稱", placeholder="例如：控制系統")
        weekday = st.selectbox("星期", list(WEEKDAYS), format_func=lambda v: WEEKDAYS[v])
        c1, c2, c3 = st.columns(3)
        with c1:
            starts = st.time_input("上課時間", value=time(13, 0), step=900)
        with c2:
            ends = st.time_input("下課時間", value=time(15, 0), step=900)
        with c3:
            offset = st.number_input("下課後提醒（分鐘）", 0, 60, 10, step=5)
        enabled = st.checkbox("啟用課後 LINE 提醒", value=True)
        if st.form_submit_button("新增課程"):
            event = {"event_id": create_id("event"), "user_id": USER_ID, "event_type": "class",
                     "title": name.strip(), "weekday": weekday,
                     "start_time": starts.strftime("%H:%M"), "end_time": ends.strftime("%H:%M"),
                     "offset_minutes": int(offset), "prompt_template": "class_feedback", "enabled": enabled}
            safely(lambda: add_event(event), "課程已儲存")
    courses = own(records["events"])
    if courses:
        st.dataframe([{"課程": x["title"], "星期": WEEKDAYS.get(x["weekday"], ""),
                       "上課": x["start_time"], "下課": x["end_time"],
                       "提醒": "啟用" if x["enabled"] else "停用"} for x in courses], hide_index=True)
    else:
        st.info("尚未建立課程。")

    st.subheader("新增可用讀書時段")
    with st.form("add_slot", clear_on_submit=True):
        a, b, c = st.columns(3)
        with a:
            slot_date = st.date_input("日期", value=datetime.now(TZ).date())
        with b:
            slot_start = st.time_input("開始時間", value=time(19, 0), step=900, key="slot_start")
        with c:
            minutes = st.number_input("可用分鐘", min_value=1, max_value=1440, value=90, step=15)
        if st.form_submit_button("新增時段"):
            new_slot = {"availability_id": create_id("slot"), "user_id": USER_ID,
                        "date": slot_date.isoformat(), "start_time": slot_start.strftime("%H:%M"),
                        "available_minutes": int(minutes)}
            safely(lambda: add_availability(new_slot), "讀書時段已儲存")
    slots = own(records["availability"])
    if slots:
        st.dataframe([{"時段 ID": a["availability_id"], "日期": a["date"], "開始": a["start_time"],
                       "分鐘": a["available_minutes"]} for a in slots], hide_index=True)

with pages[1]:
    st.subheader("新增讀書任務")
    slot_map = {s["availability_id"]: s for s in own(records["availability"])}
    def slot_label(sid: str) -> str:
        if not sid:
            return "自動安排（不固定）"
        s = slot_map[sid]
        return f"{s['date']} {s['start_time']}（{s['available_minutes']} 分）"
    with st.form("add_task", clear_on_submit=True):
        subject = st.text_input("科目", placeholder="例如：電子學三")
        task_name = st.text_input("讀書任務", placeholder="例如：完成 Ch.12 題目")
        a, b = st.columns(2)
        with a:
            deadline = st.date_input("Deadline", value=datetime.now(TZ).date() + timedelta(days=7))
        with b:
            estimate = st.number_input("預估分鐘", min_value=1, value=60, step=15)
        chosen_slot = st.selectbox("指定固定時段（選填）", [""] + list(slot_map), format_func=slot_label)
        if st.form_submit_button("新增任務"):
            task = {"task_id": create_id("task"), "user_id": USER_ID,
                    "subject": subject.strip(), "title": task_name.strip(),
                    "deadline": deadline.isoformat(), "estimated_minutes": int(estimate),
                    "status": "pending", "preferred_availability_id": chosen_slot}
            safely(lambda: add_task_to_storage(task), "任務已新增")

    tasks = own(records["tasks"])
    if tasks:
        st.dataframe([{"任務": x["title"], "科目": x["subject"], "期限": x["deadline"],
                       "所需分鐘": x["estimated_minutes"], "狀態": x["status"]} for x in tasks], hide_index=True)
        with st.form("task_status"):
            task_id = st.selectbox("更新任務狀態", [t["task_id"] for t in tasks],
                                   format_func=lambda tid: next(t["title"] for t in tasks if t["task_id"] == tid))
            new_status = st.radio("新狀態", ["pending", "completed"], horizontal=True)
            if st.form_submit_button("更新狀態"):
                safely(lambda: set_task_status(task_id, new_status), "任務狀態已更新")

    st.subheader("讀書排程")
    st.caption("此頁已預留 B 的 scheduler.make_plan(tasks, availability, previous_plan, now) 串接介面。")
    if st.button("產生／重新安排計畫"):
        try:
            from scheduler import make_plan  # 莊育哲的模組；不以假資料冒充完成排程
        except ImportError:
            st.warning("尚未串接莊育哲負責的 scheduler.py，無法產生真實排程。")
        else:
            try:
                plan_result = make_plan(tasks, own(records["availability"]), own(records["plan"]), datetime.now(TZ))
                new_plan = normalize_plan_result(plan_result, USER_ID)
                save_json(data_path("plan"), new_plan)
                st.success("讀書計畫已重新產生")
                st.rerun()
            except (DataError, ValueError) as exc:
                st.error(f"排程失敗：{exc}")
    if own(records["plan"]):
        st.dataframe(own(records["plan"]), hide_index=True)
    else:
        st.info("尚無已儲存的讀書計畫。")

with pages[2]:
    st.subheader("學習回饋與參與紀錄")
    reminder_stats = calculate_response_rate(records["reminders"], records["feedback"], USER_ID)
    task_stats = calculate_task_progress(records["tasks"], USER_ID)
    a, b, c = st.columns(3)
    a.metric("課後成功送出提醒", reminder_stats["sent"])
    b.metric("有回覆課次", reminder_stats["answered"])
    c.metric("提醒回覆率", f"{reminder_stats['rate']}%" if reminder_stats["rate"] is not None else "尚無資料")
    st.caption(f"明確完成讀書任務：{task_stats['completed']} / {task_stats['total']}；回覆率不等於學習完成率。")
    notes = sorted(own(records["feedback"]), key=lambda f: f.get("received_at", ""), reverse=True)
    if notes:
        courses = {e["event_id"]: e["title"] for e in own(records["events"])}
        for row in notes:
            with st.expander(f"{row.get('class_date')}｜{courses.get(row.get('event_id'), '未知課程')}"):
                st.write(row.get("content", ""))
                st.caption(f"回覆時間：{row.get('received_at')}｜來源：{row.get('source')}")
    else:
        st.info("尚無真實 LINE 回饋。須待 B 的 LINE Webhook 串接後才會顯示資料。")

with pages[3]:
    st.subheader("AI-ready Markdown 匯出")
    markdown = export_learning_markdown(records, datetime.now(TZ), USER_ID)
    st.warning("匯出檔包含你的課程與筆記。已遮蔽部分 Email／手機格式，但仍請人工檢查個資後再提供給外部 AI。")
    st.download_button("下載 classpulse_learning_export.md", data=markdown.encode("utf-8"),
                       file_name="classpulse_learning_export.md", mime="text/markdown")
    with st.expander("預覽 Markdown 內容"):
        st.code(markdown, language="markdown")

    st.subheader("AI：將課後疑問轉成待確認的複習任務")
    st.caption("以 OpenAI API 分析已蒐集的筆記。無金鑰時仍可下載 Markdown；API 失敗不修改任務。")
    consent = st.checkbox("我已檢查待傳送的資料，並同意本次將內容送往外部 AI API 分析")
    if st.button("分析學習紀錄", disabled=not consent):
        try:
            with st.spinner("分析中"):
                st.session_state["ai_result"] = analyze_learning_records(own(records["feedback"]), USER_ID, markdown)
            st.success("已產生 AI 建議；不會自動修改排程。")
        except AIError as exc:
            st.error(str(exc))
    result = st.session_state.get("ai_result")
    if result:
        st.write(result.get("summary", ""))
        suggestions = result.get("suggestions", [])
        for idx, suggestion in enumerate(suggestions):
            st.markdown(f"**建議 {idx+1}：{suggestion['suggested_task']}**")
            st.caption(f"來源筆記：{suggestion['source_feedback_id']}｜未解問題：{suggestion['unresolved_question']}")
            with st.form(f"confirm_{idx}"):
                estimate = st.number_input("預估分鐘", min_value=1, value=45, step=15, key=f"ai_min_{idx}")
                deadline = st.date_input("目標期限", value=datetime.now(TZ).date() + timedelta(days=7), key=f"ai_due_{idx}")
                subject = st.text_input("科目", value=suggestion["topic"][:80], key=f"ai_subject_{idx}")
                if st.form_submit_button("確認並新增至讀書任務"):
                    task = {"task_id": create_id("task"), "user_id": USER_ID,
                            "subject": subject.strip(), "title": suggestion["suggested_task"][:300],
                            "deadline": deadline.isoformat(), "estimated_minutes": int(estimate),
                            "status": "pending", "preferred_availability_id": "",
                            "source_feedback_id": suggestion["source_feedback_id"], "source": "ai_confirmed"}
                    safely(lambda: add_task_to_storage(task), "已依你確認的內容新增任務")
    elif not own(records["feedback"]):
        st.info("目前沒有可分析的筆記。完成 LINE Webhook 整合後即可使用此功能。")
