"""ClassPulse Streamlit 前端（蕭博軒）。執行：streamlit run app.py"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import streamlit as st

from ai_assistant import AIError, ai_is_configured, analyze_learning_records
from demo_data import mock_learning_suggestions, seed_demo_data
from exporter import export_learning_markdown
from storage import (
    DataError, TZ, add_availabilities, add_event, add_task_to_storage,
    clear_task_availability_preference, create_id, data_path,
    delete_availability, load_json, update_availability, update_event,
    search_learning_notes, update_feedback_topic_tags, update_json, update_task,
    save_feedback, select_demo_storage,
)
from tracker import calculate_response_rate, calculate_task_progress
from week_planner import (
    PERIODS, board_payload, fill_remaining, place_manual,
    set_task_blocks, unplace,
)
from week_board import render_week_board
from calendar_sync import preview_ics, import_ics, export_week_ics, edit_imported_event
from study_metrics import personal_metrics, BENCHMARK_TEMPLATES, anonymized_benchmark
from study_coach import CoachError, coach_with_gemini

USER_ID = "demo_user_001"  # MVP：單一測試使用者；正式多人版須加入登入機制
WEEKDAYS = {1: "週一", 2: "週二", 3: "週三", 4: "週四", 5: "週五", 6: "週六", 7: "週日"}
CALENDAR_KEY = "classpulse_schedule_calendar"

st.set_page_config(page_title="ClassPulse", page_icon="📚", layout="wide")
st.title("ClassPulse")
st.caption("主動式學習回饋與規劃助手")
demo_mode = st.toggle("展示模式（使用獨立的範例資料）", key="classpulse_demo_mode", value=False)
select_demo_storage(demo_mode)
if demo_mode:
    seed_demo_data()
    st.info("目前為展示模式：課表、LINE 回覆和 AI 建議均為模擬；資料只寫到展示資料夾，不會發送 LINE 或呼叫外部 AI。")
    if st.button("重設展示資料", help="還原預設課程、任務、範例筆記與提醒設定"):
        seed_demo_data(reset=True)
        st.session_state.pop("demo_ai_result", None)
        st.rerun()



def read_all() -> dict:
    return {name: load_json(data_path(name)) for name in
            ("events", "tasks", "availability", "plan", "reminders", "feedback", "users", "external_events")}


def own(records: list) -> list:
    return [x for x in records if x.get("user_id") == USER_ID]


def safely(action, success: str) -> None:
    try:
        action()
        st.success(success)
        st.rerun()
    except (DataError, ValueError) as exc:
        st.error(str(exc))


def handle_calendar_change() -> None:
    value = st.session_state.get(CALENDAR_KEY, {})
    clicked = value.get("eventClick", {}).get("event", {})
    props = clicked.get("extendedProps", {})
    kind = props.get("kind")
    if kind not in {"class", "availability"}:
        return
    item_id = props.get("event_id") if kind == "class" else props.get("availability_id")
    if item_id:
        st.session_state["selected_calendar_entry"] = {"kind": kind, "id": item_id}


try:
    records = read_all()
except DataError as exc:
    st.error(f"資料載入失敗：{exc}")
    st.stop()

pages = st.tabs(["七日規劃板", "任務管理", "總覽與回饋", "Markdown 與 AI"])

with pages[0]:
    courses = own(records["events"])
    slots = own(records["availability"])
    selected_calendar_entry = st.session_state.get("selected_calendar_entry", {})
    st.subheader("七日規劃板")
    st.caption("左側待排卡片可拖到任意空白節次；拉動右側把手修改工時。一鍵填滿才會自動排其他任務。")
    board_now = datetime.now(TZ)
    action = render_week_board(board_payload(USER_ID, board_now))
    if action:
        nonce = action.get("nonce")
        if nonce and st.session_state.get("last_board_nonce") != nonce:
            st.session_state["last_board_nonce"] = nonce
            try:
                if action.get("type") == "drop":
                    place_manual(USER_ID, action["task_id"], action["date"],
                                 action["period"], int(action["blocks"]), board_now)
                    st.rerun()
                elif action.get("type") == "resize":
                    set_task_blocks(USER_ID, action["task_id"], int(action["blocks"]))
                    st.rerun()
                elif action.get("type") == "unplace":
                    unplace(USER_ID, action["task_id"])
                    st.rerun()
                elif action.get("type") == "fill":
                    outcome = fill_remaining(USER_ID, board_now)
                    st.session_state["week_fill_result"] = (
                        f"本次新增 {len(outcome['placed'])} 項安排、"
                        f"仍有 {len(outcome['skipped'])} 項無法排入。"
                    )
                    st.rerun()
                elif action.get("type") == "external_edit":
                    st.session_state["editing_external_event_id"] = action.get("id")
            except (DataError, KeyError, ValueError) as exc:
                st.error(f"規劃操作未儲存：{exc}")
    if st.session_state.get("week_fill_result"):
        st.info(st.session_state.pop("week_fill_result"))

    st.subheader("匯入與匯出外部行事曆")
    with st.expander("外部行事曆（Google／Outlook／Apple 的 .ics）", expanded=False):
        st.caption("匯入最近七天及重複事件展開結果；原本的外部帳號不會被改動。"
                   "如有覆寫需求，請明確選擇。")
        ics_file = st.file_uploader("選擇 ICS 檔案", type=["ics"], key="external_ics")
        replace_existing = st.checkbox("確認覆寫具有相同來源 UID 與開始時間的本機事件",
                                       value=False, key="ics_overwrite")
        if ics_file:
            try:
                candidate_events = preview_ics(ics_file.getvalue(), USER_ID, ics_file.name, board_now)
                st.caption(f"預覽：七日內共 {len(candidate_events)} 筆外部事件")
                if st.button("匯入外部行事曆到 ClassPulse"):
                    counts = import_ics(candidate_events, USER_ID, overwrite=replace_existing)
                    st.success(f"新增／更新 {counts['saved']} 筆，略過重複 {counts['skipped']} 筆")
                    st.rerun()
            except (DataError, ValueError) as exc:
                st.error(str(exc))
        st.download_button("匯出七日行事曆（ICS）", data=export_week_ics(USER_ID, board_now),
                           file_name=f"classpulse_{board_now:%Y%m%d}_7days.ics",
                           mime="text/calendar", key="week_export_ics")

    selected_external_id = st.session_state.get("editing_external_event_id")
    if selected_external_id:
        found_external = next(
            (e for e in own(records["external_events"]) if e.get("id") == selected_external_id), None
        )
        if found_external:
            @st.dialog("確認覆寫外部行事曆事件")
            def edit_external_dialog(event):
                st.warning("此操作只覆寫 ClassPulse 的本機匯入副本。"
                           "原始 Google／Outlook／Apple 行事曆不會自動變更；"
                           "需要再匯出 ICS 並由你自行匯入外部日曆。")
                initial_start = datetime.fromisoformat(event["start"]).astimezone(TZ)
                initial_end = datetime.fromisoformat(event["end"]).astimezone(TZ)
                with st.form("edit_external_form"):
                    new_title = st.text_input("事件名稱", value=event["title"])
                    start_date = st.date_input("開始日期", value=initial_start.date())
                    start_time = st.time_input("開始時間", value=initial_start.time())
                    end_date = st.date_input("結束日期", value=initial_end.date())
                    end_time = st.time_input("結束時間", value=initial_end.time())
                    confirmed = st.form_submit_button("確認覆寫本機事件")
                    if confirmed:
                        try:
                            edit_imported_event(
                                USER_ID, event["id"], new_title,
                                datetime.combine(start_date, start_time, tzinfo=TZ),
                                datetime.combine(end_date, end_time, tzinfo=TZ),
                                confirmed=True,
                            )
                            st.session_state.pop("editing_external_event_id", None)
                            st.rerun()
                        except (DataError, ValueError) as exc:
                            st.error(str(exc))
                if st.button("取消修改", key="cancel_external_dialog"):
                    st.session_state.pop("editing_external_event_id", None)
                    st.rerun()
            edit_external_dialog(found_external)
        else:
            st.session_state.pop("editing_external_event_id", None)
    st.divider()

    st.subheader("設定每週課表")
    with st.expander("上傳課表截圖（預覽展示）", expanded=demo_mode):
        st.caption("可上傳 PNG、JPG 或 WebP 課表圖；目前僅顯示預覽，不會自動 OCR 辨識、建立課程或傳到 AI API。")
        uploaded_schedule = st.file_uploader(
            "選擇課表截圖", type=["png", "jpg", "jpeg", "webp"],
            key="classpulse_schedule_image",
        )
        if uploaded_schedule is not None:
            st.image(uploaded_schedule, caption=f"課表截圖預覽：{uploaded_schedule.name}",
                     use_container_width=True)
            st.caption("如需轉為可編輯課程，請使用下方「新增課程」；之後可擴充圖片辨識流程。")
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

    st.subheader("修改既有課程")
    if courses:
        course_ids = [course["event_id"] for course in courses]
        clicked_course_id = (
            selected_calendar_entry.get("id")
            if selected_calendar_entry.get("kind") == "class"
            else None
        )
        selected_course_id = clicked_course_id if clicked_course_id in course_ids else course_ids[0]
        course_by_id = {course["event_id"]: course for course in courses}

        def course_label(event_id: str) -> str:
            course = course_by_id[event_id]
            return (
                f"{course['title']}｜{WEEKDAYS.get(course['weekday'], '')} "
                f"{course['start_time']}–{course['end_time']}"
            )

        selected_course_id = st.selectbox(
            "選擇要修改的課程（也可先點上方行事曆）",
            course_ids,
            index=course_ids.index(selected_course_id),
            format_func=course_label,
            key=f"edit_course_select_{selected_course_id}",
        )
        selected_course = course_by_id[selected_course_id]
        with st.form(f"edit_course_form_{selected_course_id}"):
            edit_course_name = st.text_input(
                "課程名稱",
                value=selected_course["title"],
                key=f"edit_course_name_{selected_course_id}",
            )
            edit_weekday = st.selectbox(
                "星期",
                list(WEEKDAYS),
                index=list(WEEKDAYS).index(selected_course["weekday"]),
                format_func=lambda value: WEEKDAYS[value],
                key=f"edit_course_weekday_{selected_course_id}",
            )
            edit_start_column, edit_end_column, edit_offset_column = st.columns(3)
            with edit_start_column:
                edit_start_time = st.time_input(
                    "上課時間",
                    value=time.fromisoformat(selected_course["start_time"]),
                    step=900,
                    key=f"edit_course_start_{selected_course_id}",
                )
            with edit_end_column:
                edit_end_time = st.time_input(
                    "下課時間",
                    value=time.fromisoformat(selected_course["end_time"]),
                    step=900,
                    key=f"edit_course_end_{selected_course_id}",
                )
            with edit_offset_column:
                edit_offset_minutes = st.number_input(
                    "下課後提醒（分鐘）",
                    min_value=0,
                    max_value=60,
                    value=selected_course["offset_minutes"],
                    step=5,
                    key=f"edit_course_offset_{selected_course_id}",
                )
            edit_course_enabled = st.checkbox(
                "啟用課後 LINE 提醒",
                value=selected_course["enabled"],
                key=f"edit_course_enabled_{selected_course_id}",
            )
            if st.form_submit_button("儲存課程修改"):
                updated_course = {
                    **selected_course,
                    "title": edit_course_name.strip(),
                    "weekday": edit_weekday,
                    "start_time": edit_start_time.strftime("%H:%M"),
                    "end_time": edit_end_time.strftime("%H:%M"),
                    "offset_minutes": int(edit_offset_minutes),
                    "enabled": edit_course_enabled,
                }
                safely(lambda: update_event(updated_course), "課程已更新，行事曆已同步")
    else:
        st.info("新增第一門課後，即可在此修改課程。")

    st.subheader("LINE 提醒設定")
    users = own(records["users"])
    current_user = users[0] if users else {"user_id": USER_ID}
    if demo_mode:
        st.info("展示模式：下方開關與訊息都只用於模擬，不代表 LINE 帳號已綁定或真的收到推播。")
    elif current_user.get("line_user_id"):
        st.success("LINE 帳號已綁定")
    else:
        st.info("尚未綁定 LINE。請依 README 設定綁定碼，並在 LINE 輸入「綁定 <綁定碼>」。")
    with st.form("reminder_settings"):
        class_reminders = st.checkbox(
            "接收課後提醒與未排入警示",
            value=current_user.get("reminders_enabled", True),
        )
        study_reminders = st.checkbox(
            "接收讀書開始提醒與結束進度確認",
            value=current_user.get("study_reminders_enabled", False),
        )
        ai_configured = ai_is_configured()
        ai_after_class_enabled = st.checkbox(
            "同意使用 AI 整理課後筆記並建議複習任務",
            value=current_user.get("ai_after_class_enabled") is True,
            key="ai_after_class_enabled",
            disabled=(
                not demo_mode
                and not ai_configured
                and current_user.get("ai_after_class_enabled") is not True
            ),
        )
        if demo_mode:
            st.caption("展示模式不會呼叫 LINE 或 OpenAI；此處僅模擬提醒及 AI 同意設定。")
        else:
            st.caption(
                "啟用後，課程名稱、你輸入的筆記與 1–5 自評進度會傳送至 OpenAI；"
                "AI 建議的任務仍須由你在 LINE 確認才會新增。OpenAI API 可能依帳戶方案計費。"
            )
            if not ai_configured:
                st.caption("設定 OPENAI_API_KEY 與 OPENAI_MODEL 後，才能啟用課後 AI 整理。")
        if st.form_submit_button("儲存提醒設定"):
            def save_reminder_settings():
                user = {
                    **current_user,
                    "user_id": USER_ID,
                    "reminders_enabled": class_reminders,
                    "study_reminders_enabled": study_reminders,
                    "ai_after_class_enabled": ai_after_class_enabled,
                }
                update_json(
                    data_path("users"),
                    lambda rows: [
                        row for row in rows if row.get("user_id") != USER_ID
                    ] + [user],
                )
            safely(save_reminder_settings, "提醒設定已儲存")

    if demo_mode:
        with st.expander("模擬 LINE 課後提醒與補筆記", expanded=True):
            st.caption("以下訊息僅為網頁展示，不會送到 LINE，也不需要 Webhook／API Key。")
            if courses:
                demo_course_by_id = {c["event_id"]: c for c in courses}
                demo_selected_id = st.selectbox(
                    "示範課程", list(demo_course_by_id),
                    format_func=lambda eid: demo_course_by_id[eid]["title"],
                    key="demo_line_selected_course",
                )
                demo_course = demo_course_by_id[demo_selected_id]
                st.info(f"【LINE 模擬通知】「{demo_course['title']}」下課後，請回報理解進度並記錄筆記。")
                with st.form("demo_line_feedback_form", clear_on_submit=False):
                    demo_progress = st.slider("模擬理解進度", 1, 5, 3)
                    demo_note = st.text_area(
                        "模擬 LINE 回覆的課堂筆記",
                        value="今天學到一個新概念，但還有部分題目需要複習。",
                        key="demo_line_note",
                    )
                    if st.form_submit_button("模擬回覆並存入展示資料"):
                        demo_feedback = {
                            "feedback_id": create_id("feedback"),
                            "user_id": USER_ID,
                            "event_id": demo_selected_id,
                            "class_date": datetime.now(TZ).date().isoformat(),
                            "reminder_id": "",
                            "received_at": datetime.now(TZ).isoformat(timespec="seconds"),
                            "content": demo_note.strip(),
                            "progress": int(demo_progress),
                            "source": "demo",
                            "webhook_event_id": create_id("demo_webhook"),
                        }
                        safely(lambda: save_feedback(demo_feedback), "模擬回覆已儲存到展示資料（未傳送 LINE）")
            else:
                st.info("請先在展示模式新增課程，才能預覽 LINE 課後提醒。")


with pages[1]:
    st.subheader("新增讀書任務")
    slot_map = {s["availability_id"]: s for s in own(records["availability"])}
    task_notes = sorted(
        own(records["feedback"]),
        key=lambda row: row.get("received_at", ""),
        reverse=True,
    )
    task_note_map = {row["feedback_id"]: row for row in task_notes}
    course_map = {row["event_id"]: row for row in own(records["events"])}

    def task_note_label(feedback_id: str) -> str:
        note = task_note_map[feedback_id]
        course = course_map.get(note.get("event_id"), {})
        return (
            f"{course.get('title', '未知課程')}｜{note.get('class_date', '')}｜"
            f"{note.get('content', '')[:40]}"
        )

    with st.form("add_task", clear_on_submit=True):
        subject = st.text_input("科目", placeholder="例如：電子學三")
        task_name = st.text_input("讀書任務", placeholder="例如：完成 Ch.12 題目")
        a, b = st.columns(2)
        with a:
            deadline = st.date_input("Deadline", value=datetime.now(TZ).date() + timedelta(days=7))
        with b:
            st.caption("初始 60 分鐘；新增後可在七日規劃板用卡片把手調整。")
        source_feedback_id = st.selectbox(
            "關聯課程進度／筆記（選填）",
            [""] + list(task_note_map),
            format_func=lambda feedback_id: (
                "不關聯筆記" if not feedback_id else task_note_label(feedback_id)
            ),
        )
        if st.form_submit_button("新增任務"):
            task = {"task_id": create_id("task"), "user_id": USER_ID,
                    "subject": subject.strip(), "title": task_name.strip(),
                    "deadline": deadline.isoformat(), "estimated_minutes": 60,
                    "status": "pending", "preferred_availability_id": ""}
            if source_feedback_id:
                source_note = task_note_map[source_feedback_id]
                task.update({
                    "source_feedback_id": source_feedback_id,
                    "source_event_id": source_note["event_id"],
                    "source_class_date": source_note["class_date"],
                })
            safely(lambda: add_task_to_storage(task), "任務已新增")

    tasks = own(records["tasks"])
    if tasks:
        st.dataframe([{
            "任務": x["title"],
            "科目": x["subject"],
            "期限": x["deadline"],
            "原始預估分鐘": x["estimated_minutes"],
            "剩餘分鐘": x.get("remaining_minutes", x["estimated_minutes"]),
            "狀態": x["status"],
        } for x in tasks], hide_index=True)
        st.subheader("修改科目、任務名稱、狀態與期限")
        task_by_id = {task["task_id"]: task for task in tasks}

        def task_label(task_id: str) -> str:
            task = task_by_id[task_id]
            return f"{task['title']}｜{task['subject']}｜期限 {task['deadline']}"

        selected_task_id = st.selectbox(
            "選擇要修改的任務",
            list(task_by_id),
            format_func=task_label,
            key="edit_task_select",
        )
        selected_task = task_by_id[selected_task_id]
        with st.form(f"edit_task_form_{selected_task_id}"):
            updated_title = st.text_input(
                "任務名稱",
                value=selected_task["title"],
                key=f"edit_task_title_{selected_task_id}",
            )
            updated_subject = st.text_input(
                "科目名稱",
                value=selected_task["subject"],
                key=f"edit_task_subject_{selected_task_id}",
            )
            updated_deadline = st.date_input(
                "Deadline",
                value=date.fromisoformat(selected_task["deadline"]),
                key=f"edit_task_deadline_{selected_task_id}",
            )
            updated_status = st.radio(
                "任務狀態",
                ["pending", "completed"],
                index=["pending", "completed"].index(selected_task["status"]),
                horizontal=True,
                key=f"edit_task_status_{selected_task_id}",
            )
            st.caption("要改變任務工時，請在「七日規劃板」待排卡片上橫向拖曳把手。")
            if st.form_submit_button("儲存任務修改"):
                updated_task = {
                    **selected_task,
                    "title": updated_title.strip(),
                    "subject": updated_subject.strip(),
                    "deadline": updated_deadline.isoformat(),
                    "status": updated_status,
                }
                if updated_status == "completed":
                    updated_task.pop("remaining_minutes", None)
                    if selected_task.get("status") != "completed":
                        updated_task["completed_at"] = datetime.now(TZ).isoformat(timespec="seconds")
                else:
                    updated_task.pop("completed_at", None)

                def save_task_changes():
                    update_task(updated_task)
                    # 只解排本任務。其他任務無論自動或手動均保留原安排。
                    if (updated_status != selected_task.get("status")
                            or updated_deadline.isoformat() != selected_task["deadline"]):
                        unplace(USER_ID, selected_task_id)

                safely(save_task_changes, "任務已更新；其他排程保持不變")
    else:
        st.info("新增第一項任務後，即可在此修改期限與狀態。")

    st.subheader("排程狀態")
    st.caption("手動拖排與『一鍵填滿剩餘任務』位於七日規劃板；此頁不會自動重排其他任務。")
    if own(records["plan"]):
        st.dataframe(own(records["plan"]), hide_index=True)
        task_titles = {task["task_id"]: task["title"] for task in tasks}
        notes_by_id = {note["feedback_id"]: note for note in own(records["feedback"])}
        for row in own(records["plan"]):
            if row.get("status") == "unscheduled":
                st.warning(
                    f"任務「{task_titles.get(row.get('task_id'), row.get('task_id'))}」尚未排入："
                    f"{row.get('reason') or '請檢查任務與可用時段。'}"
                )
            elif row.get("status") == "scheduled":
                task = next(
                    (item for item in tasks if item.get("task_id") == row.get("task_id")),
                    {},
                )
                source_note = notes_by_id.get(task.get("source_feedback_id"))
                related_notes = (
                    [source_note]
                    if source_note
                    else [
                        note for note in own(records["feedback"])
                        if task.get("source_event_id")
                        and note.get("event_id") == task.get("source_event_id")
                    ]
                )
                with st.expander(
                    f"讀書時段回想筆記｜{task_titles.get(row.get('task_id'), row.get('task_id'))}"
                ):
                    if related_notes:
                        for note in related_notes:
                            course = course_map.get(note.get("event_id"), {})
                            st.caption(
                                f"{course.get('title', '未知課程')}｜{note.get('class_date', '')}"
                            )
                            st.write(note.get("content", ""))
                            tags = note.get("topic_tags")
                            if tags is None and isinstance(note.get("ai_analysis"), dict):
                                tags = note["ai_analysis"].get("topic_tags", [])
                            if not isinstance(tags, list):
                                tags = []
                            if tags:
                                st.caption("主題：" + "、".join(tags))
                            analysis = note.get("ai_analysis", {})
                            if isinstance(analysis, dict) and analysis.get("summary"):
                                st.markdown("**整理摘要**")
                                st.write(analysis["summary"])
                    else:
                        st.caption("此任務尚未關聯課後筆記；可在新增任務時選擇來源筆記。")
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
    st.subheader("學習儀表板")
    metric = personal_metrics(records["tasks"], records["reminders"], USER_ID)
    completed_label = (f"{metric['completion']}%" if metric["completion"] is not None else "尚無資料")
    checkin_label = (f"{metric['checkin_rate']}%" if metric["checkin_rate"] is not None
                     else "尚無可核對紀錄")
    m1, m2, m3 = st.columns(3)
    m1.metric("任務完成率", completed_label, help="使用者自行勾選完成的任務數／全部任務數")
    m2.metric("LINE 回報完成率", checkin_label,
              help="成功送出 LINE 結束確認後，回報完成的比例；不代表客觀效率")
    m3.metric("Focus XP", f"{metric['xp']}｜Lv.{metric['level']}",
              help="完成任務 +20 XP；有對應 LINE 回報且完成再 +10 XP。遊戲點數不是 Elo 或學習能力排名")
    st.caption("這些是行為紀錄，不等於考試成績或學習效率。"
               "LINE 回報比自行點完成多一道事件紀錄，但仍不能防止虛報；目前沒有學校排行榜。")

    with st.expander("AI 訓練教練｜把別人的學習節奏適配到自己的七日課表", expanded=False):
        st.caption("現階段提供三種**匿名示範訓練模板**，不代表真實中央大學學生平均值、"
                   "附近的人或已加入的群組。AI 會考慮你已有課程、時間衝突、Deadline 和待排任務；"
                   "不會直接改行事曆。")
        style_name = st.selectbox("選擇參考訓練型態", list(BENCHMARK_TEMPLATES),
                                  key="coach_template_style")
        template = BENCHMARK_TEMPLATES[style_name]
        st.caption(f"{template['name']}｜每週 {template['sessions_per_week']} 次｜"
                   f"單次最多 {template['maximum_blocks']} 節｜{template['goal']}")
        profile = anonymized_benchmark(metric, template)
        st.json(profile, expanded=False)
        if demo_mode:
            st.info("目前為展示模式；不呼叫 Gemini API，以上為可供 AI 適配的規則模板。")
        else:
            consent_gemini = st.checkbox(
                "我同意本次將待排任務名稱、課程時段、外部行程時段與彙總指標送至 Google Gemini API；"
                "免費層資料使用條款與配額可能不同於付費方案",
                value=False, key="coach_gemini_consent",
            )
            if st.button("讓 AI 將訓練模板適配到我的課表", disabled=not consent_gemini,
                         key="coach_analyze"):
                try:
                    current_board = board_payload(USER_ID)
                    suggestions = coach_with_gemini(current_board, metric, template, USER_ID)
                    st.session_state["coach_suggestions"] = suggestions
                    st.success("已取得模型建議；沒有自動修改任何排程")
                except (CoachError, DataError, ValueError) as exc:
                    st.error(str(exc))
            coach_result = st.session_state.get("coach_suggestions")
            if coach_result:
                st.write(coach_result["summary"])
                if coach_result.get("rejected"):
                    st.warning(f"已由本地規則拒絕 {len(coach_result['rejected'])} 項無效或衝突建議")
                if not coach_result["actions"]:
                    st.info("暫無可用的 AI 排程建議")
                for suggestion in coach_result["actions"]:
                    with st.container(border=True):
                        st.write(f"**{suggestion['title']}**｜{suggestion['date']} "
                                 f"{suggestion['period']} 節起｜{suggestion['blocks']} 節")
                        st.caption(suggestion["reason"])
                        if st.button("確認並排入這項 AI 建議",
                                     key=f"coach_accept_{suggestion['task_id']}_{suggestion['date']}"):
                            try:
                                place_manual(USER_ID, suggestion["task_id"], suggestion["date"],
                                             suggestion["period"], suggestion["blocks"])
                                st.session_state["coach_suggestions"] = None
                                st.rerun()
                            except (DataError, KeyError, ValueError) as exc:
                                st.error(f"無法接受 AI 建議：{exc}")
    st.subheader("可搜尋筆記庫")
    library_courses = own(records["events"])
    library_notes = own(records["feedback"])
    course_titles = {event["event_id"]: event["title"] for event in library_courses}
    course_options = [""] + list(course_titles)
    note_dates = [""] + sorted(
        {note.get("class_date", "") for note in library_notes if note.get("class_date")},
        reverse=True,
    )
    filter_columns = st.columns(3)
    with filter_columns[0]:
        selected_note_course = st.selectbox(
            "依課程篩選",
            course_options,
            format_func=lambda event_id: (
                "所有課程" if not event_id else course_titles[event_id]
            ),
            key="note_library_course",
        )
    with filter_columns[1]:
        selected_note_date = st.selectbox(
            "依課次日期篩選",
            note_dates,
            format_func=lambda value: value or "所有日期",
            key="note_library_date",
        )
    with filter_columns[2]:
        selected_note_topic = st.text_input(
            "依主題標籤搜尋",
            placeholder="例如：函式",
            key="note_library_topic",
        )
    notes = search_learning_notes(
        records["feedback"],
        USER_ID,
        event_id=selected_note_course,
        class_date=selected_note_date,
        topic=selected_note_topic,
    )
    if notes:
        for row in notes:
            with st.expander(
                f"{row.get('class_date')}｜{course_titles.get(row.get('event_id'), '未知課程')}"
            ):
                st.write(row.get("content", ""))
                if row.get("progress") is not None:
                    st.caption(f"自評理解進度：{row['progress']}/5")
                with st.form(f"note_tags_form_{row.get('feedback_id')}"):
                    current_tags = row.get("topic_tags")
                    if current_tags is None and isinstance(row.get("ai_analysis"), dict):
                        current_tags = row["ai_analysis"].get("topic_tags", [])
                    if not isinstance(current_tags, list):
                        current_tags = []
                    updated_tags = st.text_input(
                        "主題標籤（以逗號分隔，可新增、修改或移除）",
                        value=", ".join(current_tags),
                        key=f"note_tags_{row.get('feedback_id')}",
                    )
                    if st.form_submit_button("儲存主題標籤"):
                        tags = [
                            tag.strip()
                            for tag in updated_tags.replace("，", ",").replace("、", ",").split(",")
                            if tag.strip()
                        ]
                        safely(
                            lambda: update_feedback_topic_tags(
                                row["feedback_id"], USER_ID, tags
                            ),
                            "筆記主題標籤已更新",
                        )
                analysis = row.get("ai_analysis", {})
                if analysis:
                    st.markdown("**AI 整理摘要**")
                    st.write(analysis.get("summary", ""))
                    if analysis.get("key_points"):
                        st.markdown("**課堂重點**")
                        for point in analysis["key_points"]:
                            st.markdown(f"- {point}")
                    if analysis.get("unresolved_questions"):
                        st.markdown("**待釐清問題**")
                        for question in analysis["unresolved_questions"]:
                            st.markdown(f"- {question}")
                    if analysis.get("suggested_task"):
                        st.markdown("**AI 建議複習任務**")
                        st.write(
                            f"{analysis['suggested_task']} "
                            f"（約 {analysis.get('estimated_minutes', '未提供')} 分鐘）"
                        )
                        task_status = (
                            "已加入讀書任務"
                            if any(
                                task.get("source_feedback_id") == row.get("feedback_id")
                                and task.get("source") == "ai_confirmed"
                                for task in own(records["tasks"])
                            )
                            else "尚未加入讀書任務"
                        )
                        st.caption(task_status)
                st.caption(f"回覆時間：{row.get('received_at')}｜來源：{row.get('source')}")
    else:
        st.info("目前沒有符合篩選條件的筆記；可清除篩選或先記錄一筆課後回饋。")

with pages[3]:
    st.subheader("AI-ready Markdown 匯出")
    markdown = export_learning_markdown(records, datetime.now(TZ), USER_ID)
    st.warning("匯出檔包含你的課程與筆記。已遮蔽部分 Email／手機格式，但仍請人工檢查個資後再提供給外部 AI。")
    st.download_button("下載 classpulse_learning_export.md", data=markdown.encode("utf-8"),
                       file_name="classpulse_learning_export.md", mime="text/markdown")
    with st.expander("預覽 Markdown 內容"):
        st.code(markdown, language="markdown")

    st.subheader("AI：將課後疑問轉成待確認的複習任務")
    ai_result_key = "demo_ai_result" if demo_mode else "ai_result"
    if demo_mode:
        st.caption("展示模式使用標示為 Mock 的固定範例回應，不會呼叫 OpenAI；仍需使用者確認才能新增任務。")
        if st.button("展示 AI 建議（Mock，不呼叫 API）"):
            st.session_state[ai_result_key] = mock_learning_suggestions(
                own(records["feedback"]), own(records["events"]), USER_ID
            )
            st.success("已產生 Mock 展示結果，未呼叫外部 AI。")
    else:
        st.caption("以 OpenAI API 分析已蒐集的筆記。無金鑰時仍可下載 Markdown；API 失敗不修改任務。")
        consent = st.checkbox("我已檢查待傳送的資料，並同意本次將內容送往外部 AI API 分析")
        if st.button("分析學習紀錄", disabled=not consent):
            try:
                with st.spinner("分析中"):
                    st.session_state[ai_result_key] = analyze_learning_records(
                        own(records["feedback"]), USER_ID, markdown
                    )
                st.success("已產生 AI 建議；不會自動修改排程。")
            except AIError as exc:
                st.error(str(exc))
    result = st.session_state.get(ai_result_key)
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
                    source_note = next(
                        (
                            note for note in own(records["feedback"])
                            if note.get("feedback_id") == suggestion["source_feedback_id"]
                        ),
                        {},
                    )
                    task = {"task_id": create_id("task"), "user_id": USER_ID,
                            "subject": subject.strip(), "title": suggestion["suggested_task"][:300],
                            "deadline": deadline.isoformat(), "estimated_minutes": int(estimate),
                            "status": "pending", "preferred_availability_id": "",
                            "source_feedback_id": suggestion["source_feedback_id"],
                            "source_event_id": source_note.get("event_id", ""),
                            "source_class_date": source_note.get("class_date", ""),
                            "source": "ai_confirmed"}
                    safely(lambda: add_task_to_storage(task), "已依你確認的內容新增任務")
    elif not own(records["feedback"]):
        st.info("目前沒有可分析的筆記。完成 LINE Webhook 整合後即可使用此功能。")
