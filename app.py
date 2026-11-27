"""ClassPulse Streamlit 前端（蕭博軒）。執行：streamlit run app.py"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape as escape_html
import os
from uuid import uuid4

import streamlit as st
from streamlit_calendar import calendar

from ai_assistant import AIError, ai_is_configured, generate_question_actions
from demo_data import mock_learning_suggestions, seed_demo_data
from calendar_views import overview_events, view_options
from mock_day import one_day_timeline, recommended_demo_day
from line_mock_chat import start_chat, choices as mock_chat_choices, advance_chat, step_number
from note_attachments import attachment_path
from note_tasks import candidate_tasks, confirm_question_task, assign_note_course
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
    PERIODS, board_payload, fill_remaining, place_manual, rolling_dates,
    set_task_blocks, set_task_minutes, resize_scheduled, unplace,
)
from week_board import render_week_board
from schedule_preferences import mark_preferences, clear_preferences
from calendar_sync import preview_ics, import_ics, export_week_ics, edit_imported_event, conflicts_with_existing_plan
from study_metrics import personal_metrics, BENCHMARK_TEMPLATES, anonymized_benchmark
from study_coach import CoachError, coach_with_gemini, mock_coach_for_demo
from peer_exchange import PeerProfileError, export_profile, import_profile, combine_profiles

USER_ID = "demo_user_001"  # MVP：單一測試使用者；正式多人版須加入登入機制
WEEKDAYS = {1: "週一", 2: "週二", 3: "週三", 4: "週四", 5: "週五", 6: "週六", 7: "週日"}
CALENDAR_KEY = "classpulse_schedule_calendar"

st.set_page_config(page_title="ClassPulse", page_icon="📚", layout="wide")
# The legacy UI has no authenticated identity yet. Fail closed if configured for public use.
if os.getenv("CLASSPULSE_PUBLIC_WEB") == "1":
    st.error("公開網頁身份驗證尚未完成；目前不可開放個人資料。")
    st.stop()
st.title("ClassPulse")
st.caption("主動式學習回饋與規劃助手")
quick1,quick2,_=st.columns([1.2,1.2,6])
with quick1:
    st.link_button("ee-class", "https://ncueeclass.ncu.edu.tw/", use_container_width=True)
with quick2:
    st.link_button("K 書中心預約", "https://mwa.lib.ncu.edu.tw/pwaspace/", use_container_width=True)
demo_mode = st.toggle("展示模式（使用獨立的範例資料）", key="classpulse_demo_mode", value=False)
select_demo_storage(demo_mode)
if demo_mode:
    seed_demo_data()
    st.info("目前為展示模式：課表、LINE 回覆和 AI 建議均為模擬；資料只寫到展示資料夾，不會發送 LINE 或呼叫外部 AI。")
    if st.button("重設展示資料", help="還原預設課程、任務、範例筆記與提醒設定"):
        seed_demo_data(reset=True)
        st.session_state.pop("demo_ai_result", None)
        st.session_state.pop("line_mock_chat_state", None)
        st.rerun()



def read_all() -> dict:
    return {name: [row for row in load_json(data_path(name)) if row.get("user_id") == USER_ID] for name in
            ("events", "tasks", "availability", "plan", "reminders", "feedback", "users", "external_events", "semester_settings")}


def own(records: list) -> list:
    return [x for x in records if x.get("user_id") == USER_ID]


def safely(action, success: str) -> None:
    try:
        action()
        st.success(success)
        st.rerun()
    except (DataError, ValueError) as exc:
        st.error(str(exc))


def handle_calendar_change(key: str) -> None:
    value = st.session_state.get(key, {})
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

if demo_mode:
    demo_courses = own(records["events"])
    demo_tasks = own(records["tasks"])
    demo_planned = [row for row in own(records["plan"]) if row.get("status") == "scheduled"]
    demo_pinned_ids = {row["task_id"] for row in demo_planned}
    demo_waiting = [task for task in demo_tasks
                    if task.get("status") == "pending"
                    and task.get("task_id") not in demo_pinned_ids]
    if len(demo_courses) < 10:
        st.warning("目前還是舊版精簡展示資料。請按上方「重設展示資料」一次，"
                   "即可載入含完整課表、待排與預排任務的豐富展示情境；"
                   "只重設展示資料，不會影響正式使用者。")
    st.caption(
        f"虛構展示情境｜{len(demo_courses)} 門每週課程 · "
        f"{len(demo_waiting)} 項待排 · {len(demo_planned)} 項已排 · "
        f"{sum(t.get('status') == 'completed' for t in demo_tasks)} 項已完成 · "
        f"{len(own(records['feedback']))} 則課後回饋 · "
        f"{len(own(records['external_events']))} 筆外部活動"
    )

pages = st.tabs(["行事曆與拖排", "操作引導", "LINE 一日 Mock", "任務管理", "總覽與回饋", "Markdown 與 AI"])

with pages[0]:
    courses = own(records["events"])
    slots = own(records["availability"])
    selected_calendar_entry = st.session_state.get("selected_calendar_entry", {})
    board_now = datetime.now(TZ)
    st.caption("七日拖排只是排程模式；日、週、月仍可自由切換查看完整行事曆。")
    calendar_view = st.segmented_control(
        "行事曆檢視", ["七日拖排", "日", "週", "月"],
        default="七日拖排", key="classpulse_calendar_view",
    )
    if calendar_view == "七日拖排":
        st.subheader("七日規劃板")
        st.caption("左側卡片可自由拖排；按一鍵安排先進入綠色偏好畫筆，再確認排入。綠色優先而非只能排綠色；已手動固定的任務不會移動。")
        payload = board_payload(USER_ID, board_now)
        payload["preference_mode"] = st.session_state.get("classpulse_preference_mode", False)
        payload["error"] = st.session_state.get("board_last_error","")
        action = render_week_board(payload)
        if action:
            nonce = action.get("nonce")
            if nonce and st.session_state.get("last_board_nonce") != nonce:
                st.session_state["last_board_nonce"] = nonce
                try:
                    st.session_state.pop("board_last_error",None)
                    if action.get("type") == "drop":
                        minutes=int(action.get("duration_minutes") or int(action["blocks"])*60)
                        place_manual(USER_ID, action["task_id"], action["date"],
                                     action["period"], int(action["blocks"]), board_now,
                                     duration_minutes=minutes)
                        st.rerun()
                    elif action.get("type") == "resize":
                        if action.get("minutes"):
                            set_task_minutes(USER_ID,action["task_id"],int(action["minutes"]))
                        else:
                            set_task_blocks(USER_ID, action["task_id"], int(action["blocks"]))
                        st.rerun()
                    elif action.get("type") == "resize_scheduled":
                        resize_scheduled(USER_ID,action["task_id"],int(action["minutes"]),board_now)
                        st.rerun()
                    elif action.get("type") == "unplace":
                        unplace(USER_ID, action["task_id"])
                        st.rerun()
                    elif action.get("type") == "pref_begin":
                        st.session_state["classpulse_preference_mode"] = True
                        st.rerun()
                    elif action.get("type") == "pref_cancel":
                        st.session_state["classpulse_preference_mode"] = False
                        st.rerun()
                    elif action.get("type") == "pref_clear":
                        clear_preferences(USER_ID)
                        st.rerun()
                    elif action.get("type") == "pref_paint":
                        mark_preferences(
                            USER_ID, action.get("cells", []),
                            action.get("enabled"), board_now,
                        )
                        st.rerun()
                    elif action.get("type") == "fill":
                        outcome = fill_remaining(USER_ID, board_now)
                        hits = sum(int(x.get("preference_hits") or 0) for x in outcome["placed"])
                        st.session_state["classpulse_preference_mode"] = False
                        st.session_state["week_fill_result"] = (
                            f"本次新增 {len(outcome['placed'])} 項安排、"
                            f"{len(outcome['skipped'])} 項無法排入；"
                            f"新安排命中 {hits} 個偏好節次。"
                            "綠色不足時會使用其他合法空檔。"
                        )
                        st.rerun()
                    elif action.get("type") == "external_edit":
                        st.session_state["editing_external_event_id"] = action.get("id")
                except (DataError, KeyError, ValueError) as exc:
                    st.session_state["board_last_error"]=f"規劃操作未儲存：{exc}"
                    st.rerun()
        if st.session_state.get("week_fill_result"):
            st.info(st.session_state.pop("week_fill_result"))

    else:
        st.subheader(f"{calendar_view}行事曆")
        st.caption("可用左右箭頭切換不同日期；顯示固定課、已排任務和外部行程，"
                   "不顯示 All-day 待排任務。此檢視僅供查看，不會自動重排。")
        overview_key = CALENDAR_KEY + "_" + calendar_view
        calendar(
            events=overview_events(
                courses, slots, own(records["tasks"]),
                own(records["plan"]), own(records["external_events"]),
            ),
            options=view_options(calendar_view),
            callbacks=["eventClick"],
            key=overview_key,
            on_change=lambda: handle_calendar_change(overview_key),
        )
        if selected_calendar_entry:
            st.info("已選取課程；下方「修改既有課程」可編輯。")
        st.divider()

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
                existing_ids = {event["id"] for event in own(records["external_events"])}
                applicable = [e for e in candidate_events
                              if replace_existing or e["id"] not in existing_ids]
                conflicts = conflicts_with_existing_plan(applicable, USER_ID)
                confirmed_conflicts = True
                if conflicts:
                    st.warning(f"偵測到 {len(conflicts)} 個與目前讀書安排重疊的時段。"
                               "匯入不會自動移動或覆寫讀書任務，請先檢查。")
                    st.dataframe([{
                        "外部事件": item["event_title"], "原讀書任務": item["task_title"],
                        "原排程": item["task_start"]
                    } for item in conflicts[:10]], hide_index=True)
                    confirmed_conflicts = st.checkbox(
                        "我已了解時間衝突，先保留原讀書任務，匯入後自行調整",
                        value=False, key="ics_conflicts_acknowledged")
                if st.button("匯入外部行事曆到 ClassPulse",
                             disabled=not confirmed_conflicts):
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

    with st.expander("進階設定｜每週課表、課表截圖與 LINE 提醒", expanded=False):
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



        st.divider()
        st.markdown("**筆記庫週次設定**")
        initial_semester = next((r.get("start") for r in records["semester_settings"]
                                 if r.get("user_id")==USER_ID),"")
        today_semester=datetime.now(TZ).date()
        default_semester=date(today_semester.year,9,1) if today_semester.month>=8 else date(today_semester.year,2,1)
        with st.form("semester_settings_form"):
            semester_start=st.date_input(
                "學期第 1 週的起始日（課程 → 週次筆記索引）",
                value=date.fromisoformat(initial_semester) if initial_semester else default_semester,
            )
            if st.form_submit_button("儲存週次設定"):
                update_json(data_path("semester_settings"),lambda rows:[
                    x for x in rows if x.get("user_id")!=USER_ID
                ]+[{"user_id":USER_ID,"start":semester_start.isoformat()}])
                st.rerun()
        st.toggle("顯示 LINE 一日 Mock 的舊版測試工具",
                  value=False,key="show_legacy_line_debug",
                  help="只影響測試頁面顯示，不刪除時間軸與快速填寫功能")

with pages[1]:
    st.subheader("引導式操作｜從課表到 AI 建議")
    st.caption("逐步完成核心流程；每個步驟由你決定何時操作，不會在切換或刷新時偷偷重新排程。")
    steps = ["建立課表", "建立待排任務", "手動拖入一項", "一鍵填滿剩餘", "LINE Mock 與 AI"]
    current = max(0, min(4, int(st.session_state.get("classpulse_guide_step", 0))))
    st.progress((current + 1) / len(steps), text=f"第 {current + 1}／5 步：{steps[current]}")
    left, center, right = st.columns([1, 4, 1])
    with left:
        if st.button("上一步", disabled=current == 0, key="guide_prev"):
            st.session_state["classpulse_guide_step"] = current - 1
            st.rerun()
    with right:
        if st.button("下一步", disabled=current == 4, key="guide_next"):
            st.session_state["classpulse_guide_step"] = current + 1
            st.rerun()
    if current == 0:
        st.write(f"目前有 **{len(own(records['events']))}** 門每週課程。"
                 "展示模式內已提供虛構課表；也可以在這裡直接加入自己的課程。")
        with st.form("guide_add_class", clear_on_submit=True):
            guide_class_title = st.text_input("課程名稱", placeholder="例如：控制系統")
            c1, c2, c3 = st.columns(3)
            with c1:
                guide_weekday = st.selectbox("星期", list(WEEKDAYS),
                                             format_func=lambda k: WEEKDAYS[k], key="guide_weekday")
            with c2:
                guide_start = st.time_input("上課", value=time(13, 0), key="guide_start")
            with c3:
                guide_end = st.time_input("下課", value=time(15, 0), key="guide_end")
            if st.form_submit_button("儲存課程"):
                event = {
                    "event_id": create_id("event"), "user_id": USER_ID,
                    "event_type": "class", "title": guide_class_title.strip(),
                    "weekday": guide_weekday,
                    "start_time": guide_start.strftime("%H:%M"),
                    "end_time": guide_end.strftime("%H:%M"),
                    "offset_minutes": 10, "prompt_template": "class_feedback", "enabled": True,
                }
                safely(lambda: add_event(event), "課程已新增；進入下一步建立任務")
    elif current == 1:
        st.write(f"目前有 **{len([t for t in own(records['tasks']) if t['status'] == 'pending'])}** 筆待排任務。"
                 "新增後會留在待排盒，不會自動排進日曆。")
        with st.form("guide_add_task", clear_on_submit=True):
            guide_subject = st.text_input("科目", placeholder="例如：Python")
            guide_title = st.text_input("讀書任務", placeholder="例如：練習函式題目")
            guide_due = st.date_input("期限", value=datetime.now(TZ).date() + timedelta(days=5),
                                      key="guide_due")
            if st.form_submit_button("加入待排盒"):
                task = {
                    "task_id": create_id("task"), "user_id": USER_ID,
                    "subject": guide_subject.strip(), "title": guide_title.strip(),
                    "deadline": guide_due.isoformat(), "estimated_minutes": 60,
                    "status": "pending", "preferred_availability_id": "",
                }
                safely(lambda: add_task_to_storage(task), "新增完成，任務留在待排盒")
    elif current == 2:
        st.info("切換到上方「行事曆與拖排」→ 選「七日拖排」，"
                "在左側拉動一項任務右側把手，再拖進右側未來空格。"
                "手動安排一項時，其他待排任務絕不自行移動。")
        st.write(f"目前已排 **{len(board_payload(USER_ID)['scheduled'])}** 項，"
                 f"待排 **{len(board_payload(USER_ID)['tasks'])}** 項。")
    elif current == 3:
        st.info("此步不直接執行排程：請按下方按鈕啟動綠色偏好畫筆，"
                "再切換到「行事曆與拖排 → 七日拖排」，自行在合法空格畫綠，"
                "最後按「確認偏好並一鍵安排」。未畫綠的合法空檔仍可使用，"
                "任何既有手排都不會被移動。")
        if st.button("開始設定綠色偏好（尚不自動排程）", key="guide_fill_remaining"):
            st.session_state["classpulse_preference_mode"] = True
            st.success("已進入偏好畫筆模式，請回到上方「行事曆與拖排」。")
            st.rerun()
    else:
        st.info("切換到上方「LINE 一日 Mock」：選擇一天，逐事件查看課程提醒、"
                "讀書開始及結束回報，還能提交模擬課堂筆記。"
                "再前往「總覽與回饋」或「Markdown 與 AI」查看分析結果。")
        if not demo_mode:
            st.warning("請先開啟最上方的展示模式，LINE 模擬完全不需要真實金鑰。")

with pages[2]:
    st.subheader("LINE 一日 Mock｜一整天的提醒、互動與回饋")
    st.caption("逐段演示一天的提醒時間軸；這是網頁模擬，不發送任何 LINE 推播或 AI API 請求。")
    if not demo_mode:
        st.info("請先開啟網頁頂端的「展示模式」，即可用虛構課表體驗完整一日模擬。")
    else:
        demo_board = board_payload(USER_ID)
        days = rolling_dates(datetime.now(TZ))
        preferred_day = recommended_demo_day(days, courses, demo_board["scheduled"])
        mock_day = st.selectbox(
            "選擇模擬日期",
            days,
            index=days.index(preferred_day),
            format_func=lambda d: f"{d:%m/%d}（{WEEKDAYS[d.isoweekday()]}）",
            key="line_mock_date",
        )
        st.subheader("LINE 虛擬對話｜按鈕引導式補筆記")
        st.caption("這是可操作的聊天室 Mock。選擇「補筆記 → 星期 → 課次 → 進度 → 筆記 → AI 建議」；"
                   "訊息只會存進展示資料夾，不連結真實 LINE。")
        chat_key = "line_mock_chat_state"
        chat_state = st.session_state.get(chat_key)
        if not chat_state or chat_state.get("day") != mock_day.isoformat():
            chat_state = start_chat(mock_day, courses)
            st.session_state[chat_key] = chat_state

        def submit_line_mock(value: str) -> None:
            try:
                next_chat, effect = advance_chat(
                    st.session_state[chat_key], value, courses)
                if effect and effect["type"] == "save_feedback":
                    new_feedback_id = create_id("feedback")
                    saved = save_feedback({
                        "feedback_id": new_feedback_id, "user_id": USER_ID,
                        "event_id": effect["event_id"],
                        "class_date": effect["class_date"],
                        "received_at": datetime.now(TZ).isoformat(timespec="seconds"),
                        "content": effect["content"], "progress": effect["progress"],
                        "source": "demo", "reminder_id": "",
                        "webhook_event_id": create_id("mock_chat_event"),
                    })
                    if not saved:
                        raise DataError("這則模擬筆記已存在，未重複寫入")
                    next_chat["saved_feedback_id"] = new_feedback_id
                elif effect and effect["type"] == "add_task":
                    new_task = {
                        "task_id": create_id("task"),
                        "user_id": USER_ID,
                        "subject": effect["subject"],
                        "title": effect["title"],
                        "deadline": (
                            date.fromisoformat(effect["class_date"]) + timedelta(days=7)
                        ).isoformat(),
                        "estimated_minutes": 60,
                        "status": "pending",
                        "preferred_availability_id": "",
                        "source": "mock_ai_confirmed",
                        "source_feedback_id": effect["source_feedback_id"],
                    }
                    add_task_to_storage(new_task)
                st.session_state[chat_key] = next_chat
                st.rerun()
            except (DataError, KeyError, ValueError) as exc:
                st.error(f"LINE Mock 無法完成本步驟：{exc}")

        with st.container(border=True):
            st.progress(
                step_number(chat_state["stage"]) / 6,
                text=f"LINE 補筆記引導｜第 {step_number(chat_state['stage'])}／6 步",
            )
            st.markdown("""
            <style>
            .classpulse-line-phone {
              background:#dce9f2; border:1px solid #b8c8d4; border-radius:15px;
              padding:12px; max-height:430px; overflow-y:auto; margin:5px 0 13px;
              font-family:system-ui,sans-serif;
            }
            .classpulse-line-phone .chat-head {
              font-size:12px;font-weight:700;color:#40556b;text-align:center;
              border-bottom:1px solid #c0d1da;padding:3px 0 10px;margin-bottom:10px;
            }
            .classpulse-line-phone .chat-row {display:flex;margin:8px 0;clear:both}
            .classpulse-line-phone .chat-row.bot {justify-content:flex-start}
            .classpulse-line-phone .chat-row.student {justify-content:flex-end}
            .classpulse-line-phone .chat-bubble {
              border-radius:12px;padding:10px 12px;max-width:83%;
              font-size:13px;line-height:1.55;color:#253544;overflow-wrap:anywhere;
              white-space:normal;box-shadow:0 1px 2px #22334414;
            }
            .classpulse-line-phone .bot .chat-bubble {
              background:#fff;border-top-left-radius:3px
            }
            .classpulse-line-phone .student .chat-bubble {
              background:#a9e97d;border-top-right-radius:3px
            }
            </style>
            """, unsafe_allow_html=True)
            chat_rows = []
            for message in chat_state["messages"]:
                side = "student" if message["role"] == "user" else "bot"
                safe_text = escape_html(message["text"]).replace("\n", "<br>")
                chat_rows.append(
                    f'<div class="chat-row {side}"><div class="chat-bubble">'
                    f'{safe_text}</div></div>'
                )
            st.markdown(
                '<div class="classpulse-line-phone">'
                '<div class="chat-head">ClassPulse｜LINE 虛擬聊天（非真實訊息）</div>'
                + "".join(chat_rows) + '</div>',
                unsafe_allow_html=True,
            )
            if chat_state["stage"] == "note":
                with st.form("line_mock_chat_note_form", clear_on_submit=False):
                    note_text = st.text_area(
                        "輸入要傳送的課堂筆記或疑問",
                        key="line_mock_chat_note",
                        placeholder="例如：今天學到閉迴路傳遞函數，但穩定度判斷還不熟。",
                    )
                    if st.form_submit_button("傳送筆記"):
                        submit_line_mock(note_text)
            else:
                menu = mock_chat_choices(chat_state, courses)
                if menu:
                    cols = st.columns(min(4, len(menu)))
                    for index, (value, label) in enumerate(menu):
                        with cols[index % len(cols)]:
                            if st.button(
                                label, key=f"line_chat_option_{chat_state['stage']}_{index}",
                                use_container_width=True,
                            ):
                                submit_line_mock(value)
            if chat_state["stage"] not in {"menu", "finished"}:
                if st.button("取消這次補筆記", key="line_mock_chat_cancel"):
                    submit_line_mock("取消")
            if st.button("重設 LINE 虛擬對話", key="line_mock_chat_restart"):
                st.session_state[chat_key] = start_chat(mock_day, courses)
                st.rerun()
        st.caption("虛擬對話中的 AI 建議為明確標示的 Mock；"
                   "只有按「加入讀書任務」才會把任務放進待排盒，不會自動填入日曆。")
        if st.session_state.get("show_legacy_line_debug",False):
            with st.expander("本日提醒事件時間軸（可選）", expanded=False):
                daily_events = one_day_timeline(mock_day, courses, demo_board["scheduled"])
                if not daily_events:
                    st.info("這一天尚無課程或已排讀書任務。可選其他日期，或先建立課表、拖排任務。")
                else:
                    selected_index = st.selectbox(
                        "選擇這一天的事件",
                        list(range(len(daily_events))),
                        format_func=lambda i: f"{daily_events[i]['time']}  {daily_events[i]['title']}",
                        key="line_mock_timeline_index",
                    )
                    st.progress((selected_index + 1) / len(daily_events),
                                text=f"第 {selected_index + 1}／{len(daily_events)} 個事件")
                    event = daily_events[selected_index]
                    st.markdown(f"**{event['time']}｜{event['title']}**")
                    st.info(event["message"])
                    st.caption("上面的通知只顯示在瀏覽器，不代表 LINE API 已傳送成功。")

    if demo_mode and st.session_state.get("show_legacy_line_debug",False):
        with st.expander("模擬 LINE 課後提醒與補筆記｜快速填寫（舊版）", expanded=False):
            st.caption("以下訊息僅為網頁展示，不會送到 LINE，也不需要 Webhook／API Key。")
            if any(c.get("weekday") == mock_day.isoweekday() for c in courses):
                demo_course_by_id = {c["event_id"]: c for c in courses if c.get("weekday") == mock_day.isoweekday()}
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
                            "class_date": mock_day.isoformat(),
                            "reminder_id": "",
                            "received_at": datetime.now(TZ).isoformat(timespec="seconds"),
                            "content": demo_note.strip(),
                            "progress": int(demo_progress),
                            "source": "demo",
                            "webhook_event_id": create_id("demo_webhook"),
                        }
                        safely(lambda: save_feedback(demo_feedback), "模擬回覆已儲存到展示資料（未傳送 LINE）")
            else:
                st.info("這一天沒有課，請選擇其他有課的日期，或在「操作引導」先新增課程。")



with pages[3]:
    st.subheader("AI：從課後疑問逐項建立複習任務")
    st.caption(
        "路徑：LINE／網站保存筆記 → 疑問標籤、？或 AI 未解問題 "
        "→ 每個疑問各一項候選 → 確認新增 → 紫色待排卡 → 手排／一鍵排入。"
        "沒有確認前不修改任何任務、時段或期限。"
    )
    question_candidates=candidate_tasks(
        own(records["feedback"]),own(records["events"]),own(records["tasks"]),USER_ID,
    )
    current_ai_actions=st.session_state.get("question_ai_actions",{})
    if demo_mode:
        st.info("展示模式使用筆記疑問規則候選，不呼叫 OpenAI；確認後紫色待排卡可實際拖排。")
    else:
        if question_candidates:
            consent_question_ai=st.checkbox(
                "同意本次將待釐清問題、來源科目與少量筆記摘錄傳至 OpenAI，逐題產生複習行動",
                key="question_ai_consent",value=False,
            )
            if st.button("讓 OpenAI 逐項生成複習行動",
                         disabled=not consent_question_ai,
                         key="question_ai_generate"):
                try:
                    with st.spinner("逐項分析疑問"):
                        current_ai_actions=generate_question_actions(question_candidates)
                        st.session_state["question_ai_actions"]=current_ai_actions
                    st.success("每題已對應一個 AI 建議；尚未新增任何任務")
                except AIError as exc:
                    st.error(str(exc))
        st.caption("沒有 API Key 時仍可使用規則候選；規則建議不冒充真實 LLM 生成。")
    if question_candidates:
        st.caption(f"待確認 {len(question_candidates)} 個獨立疑問。30 分鐘為預設；"
                   "期限由來源課程計算到下一次上課開始，沒有課程歸屬的筆記會要求先分類。")
        for candidate in question_candidates:
            key=candidate["source_question_key"]
            is_model=key in current_ai_actions
            with st.container(border=True):
                st.markdown(
                    f"**{'AI 複習建議' if is_model else '疑問規則候選'}｜"
                    f"{candidate['subject'] or '未分類'}**"
                )
                st.write(candidate["question"])
                suggested=current_ai_actions.get(key,candidate["suggested_task"])
                st.write(f"**擬新增任務：** {suggested}")
                st.caption(
                    f"30 分鐘｜期限：{candidate['deadline_at'] or '請先指定來源課程'}"
                    f"｜來源筆記：{candidate['source_feedback_id']}"
                )
                if candidate["needs_classification"]:
                    st.warning("這份筆記尚未關聯課程，不能猜測科目或下次上課日期。"
                               "請先在筆記庫為它指定來源課程。")
                else:
                    if st.button("確認新增到紫色待排區",key="confirm_question_"+key):
                        try:
                            item={**candidate,"suggestion_method":
                                  "openai" if is_model else "question_rule"}
                            confirm_question_task(USER_ID,item,title=suggested)
                            st.success("已新增紫色任務。請到七日拖排安排時間。")
                            st.rerun()
                        except (DataError,ValueError,KeyError) as exc:
                            st.error(f"尚未新增：{exc}")
    else:
        st.info("目前沒有尚未確認的疑問。"
                "從 LINE 傳送含「？」的筆記、標記「疑問」，"
                "或使用課後 AI 產生未解問題，即會出現在這裡。")
    st.divider()
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

with pages[4]:
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
        st.download_button(
            "匯出我的匿名訓練模板（JSON）",
            data=export_profile(board_payload(USER_ID), metric),
            file_name="classpulse_anonymous_training.json",
            mime="application/json",
            key="peer_export_profile",
            help="只包含每週安排數量、常用節次、單次時長與自填總覽指標；不含課名或個人身分。",
        )
        uploaded_trainings = st.file_uploader(
            "匯入同學自願分享的訓練模板（可同時選擇多份 JSON）",
            type=["json"], accept_multiple_files=True, key="peer_training_upload",
        )
        imported_profiles = []
        for uploaded in uploaded_trainings[:12]:
            try:
                imported_profiles.append(import_profile(uploaded.getvalue()))
            except PeerProfileError as exc:
                st.error(f"{uploaded.name}：{exc}")
        if len(uploaded_trainings) > 12:
            st.warning("一次最多合成 12 份模板；其餘尚未載入")
        if imported_profiles:
            st.info(f"已載入 {len(imported_profiles)} 份匿名模板。"
                    "這些資料由分享者自行提供，未查證身分或學習成效，"
                    "僅能比較學習節奏，不能計算校內排名。")
        choices = list(BENCHMARK_TEMPLATES)
        if imported_profiles:
            choices.append("同學分享的第一份模板")
        if len(imported_profiles) >= 2:
            choices.append("匿名小組綜合模板")
        style_name = st.selectbox("選擇參考訓練型態", choices,
                                  key="coach_template_style")
        if style_name == "匿名小組綜合模板":
            template = combine_profiles(imported_profiles)
        elif style_name == "同學分享的第一份模板":
            template = imported_profiles[0]
        else:
            template = BENCHMARK_TEMPLATES[style_name]
        st.caption(f"{template['name']}｜每週 {template['sessions_per_week']} 次｜"
                   f"單次最多 {template['maximum_blocks']} 節｜{template['goal']}")
        profile = anonymized_benchmark(metric, template)
        st.json(profile, expanded=False)
        if demo_mode:
            st.info("展示模式僅產生【Mock 模型回應】，可測試 JSON Schema、"
                    "本地衝突檢查與確認後排入；不呼叫 Gemini API。")
            if st.button("體驗教練產生候選方案（Mock，不呼叫 API）",
                         key="demo_coach_generate"):
                st.session_state["coach_suggestions"] = mock_coach_for_demo(
                    board_payload(USER_ID), template, USER_ID)
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
    st.caption("先選課程、再選第幾週，進入該週筆記。主題標籤可繼續搜尋。")
    library_courses=own(records["events"])
    library_notes=own(records["feedback"])
    course_titles={event["event_id"]:event["title"] for event in library_courses}
    course_names=["所有課程"]+sorted(set(course_titles.values()))+["未分類筆記"]
    selected_course=st.pills(
        "選擇課程",course_names,selection_mode="single",
        default="所有課程",key="note_library_course_pills",
    ) or "所有課程"
    initial_semester=next(
        (row.get("start") for row in records["semester_settings"]
         if row.get("user_id")==USER_ID),""
    )
    today_semester=datetime.now(TZ).date()
    semester_default=(date(today_semester.year,9,1)
                      if today_semester.month>=8 else date(today_semester.year,2,1))
    semester_anchor=date.fromisoformat(initial_semester) if initial_semester else semester_default

    def week_of(note: dict) -> str:
        try:
            days=(date.fromisoformat(note.get("class_date",""))-semester_anchor).days
        except ValueError:
            return "日期未設定"
        return "學期前" if days<0 else f"第 {days//7+1} 週"

    matched_courses=[
        note for note in library_notes
        if selected_course=="所有課程"
        or (selected_course=="未分類筆記"
            and note.get("event_id") not in course_titles)
        or course_titles.get(note.get("event_id"))==selected_course
    ]
    weeks=["全部週次"]+sorted(
        {week_of(note) for note in matched_courses},
        key=lambda key:(key=="學期前",
                        -int(key.replace("第 ","").replace(" 週",""))
                        if key.startswith("第 ") else 0),
    )
    selected_week=st.pills(
        "選擇週次",weeks,selection_mode="single",
        default="全部週次",key="note_library_week_pills",
    ) or "全部週次"
    selected_note_topic=st.text_input(
        "搜尋主題標籤",placeholder="例如：回授、Miller、Routh",
        key="note_library_topic",
    )
    tag_matches=search_learning_notes(records["feedback"],USER_ID,
                                       topic=selected_note_topic)
    ids={note["feedback_id"] for note in matched_courses
         if selected_week=="全部週次" or week_of(note)==selected_week}
    notes=[note for note in tag_matches if note.get("feedback_id") in ids]
    if notes:
        for row in notes:
            with st.expander(
                f"{row.get('class_date')}｜{course_titles.get(row.get('event_id'), '未分類筆記')}"
            ):
                st.write(row.get("content", ""))
                if row.get("event_id") not in course_titles and library_courses:
                    st.caption("此 LINE 筆記尚未指定來源課程；指定後才能產生下次上課前的 AI 任務。")
                    selected_source=st.selectbox(
                        "指定來源課程",list(course_titles),
                        format_func=lambda event_id:course_titles[event_id],
                        key="classify_note_"+row["feedback_id"],
                    )
                    if st.button("儲存這份筆記的課程歸屬",
                                 key="classify_confirm_"+row["feedback_id"]):
                        safely(lambda:assign_note_course(USER_ID,row["feedback_id"],selected_source),
                               "已指定來源課程；相關疑問任務將重新顯示")
                filename = row.get("attachment_filename","")
                if filename:
                    st.caption("LINE 附件：" + filename)
                    if str(filename).lower().endswith(".pdf"):
                        pdf_path=attachment_path(USER_ID,row["feedback_id"])
                        if pdf_path.is_file():
                            st.download_button(
                                "下載 PDF 原始筆記",
                                data=pdf_path.read_bytes(),
                                file_name=filename,
                                mime="application/pdf",
                                key="note_pdf_"+row["feedback_id"],
                            )
                        else:
                            st.caption("此筆記有檔名，但原始 PDF 未保存；擷取文字仍在上方。")
                    else:
                        st.caption("已保存擷取文字；目前不保存 TXT／DOCX 原檔。")
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

with pages[5]:
    st.subheader("AI-ready Markdown 匯出")
    markdown = export_learning_markdown(records, datetime.now(TZ), USER_ID)
    st.warning("匯出檔包含你的課程與筆記。已遮蔽部分 Email／手機格式，但仍請人工檢查個資後再提供給外部 AI。")
    st.download_button("下載 classpulse_learning_export.md", data=markdown.encode("utf-8"),
                       file_name="classpulse_learning_export.md", mime="text/markdown")
    with st.expander("預覽 Markdown 內容"):
        st.code(markdown, language="markdown")

    st.caption("筆記疑問產生任務已移到「任務管理」；此頁保留可匯出的 AI-ready Markdown。")
