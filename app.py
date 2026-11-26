"""ClassPulse Streamlit 前端（蕭博軒）。執行：streamlit run app.py"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import streamlit as st
from streamlit_calendar import calendar

from ai_assistant import AIError, ai_is_configured, analyze_learning_records
from calendar_events import build_calendar_events
from exporter import export_learning_markdown
from storage import (
    DataError, TZ, add_availabilities, add_event, add_task_to_storage,
    clear_task_availability_preference, create_id, data_path,
    delete_availability, load_json, update_availability, update_event,
    update_json, update_task,
)
from tracker import calculate_response_rate, calculate_task_progress
from plan_bridge import merge_user_plan, normalize_plan_result

USER_ID = "demo_user_001"  # MVP：單一測試使用者；正式多人版須加入登入機制
WEEKDAYS = {1: "週一", 2: "週二", 3: "週三", 4: "週四", 5: "週五", 6: "週六", 7: "週日"}
CALENDAR_KEY = "classpulse_schedule_calendar"

st.set_page_config(page_title="ClassPulse", page_icon="📚", layout="wide")
st.title("ClassPulse")
st.caption("主動式學習回饋與規劃助手｜蕭博軒負責：介面、JSON、統計、Markdown、AI 分析")


def read_all() -> dict:
    return {name: load_json(data_path(name)) for name in
            ("events", "tasks", "availability", "plan", "reminders", "feedback", "users")}


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

pages = st.tabs(["課表與時段", "讀書任務與排程", "回饋與進度", "Markdown 與 AI"])

with pages[0]:
    courses = own(records["events"])
    slots = own(records["availability"])
    selected_calendar_entry = st.session_state.get("selected_calendar_entry", {})
    st.subheader("課表與可用讀書時段行事曆")
    st.caption("紅色為每週課程、綠色為可用時段、藍色為已排定讀書任務；可切換週／月／日檢視。")
    calendar(
        events=build_calendar_events(
            courses,
            slots,
            own(records["tasks"]),
            own(records["plan"]),
        ),
        options={
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay",
            },
            "initialView": "timeGridWeek",
            "firstDay": 1,
            "locale": "zh-tw",
            "timeZone": "Asia/Taipei",
            "allDaySlot": False,
            "slotMinTime": "06:00:00",
            "slotMaxTime": "24:00:00",
            "nowIndicator": True,
            "height": 650,
            "eventTimeFormat": {
                "hour": "2-digit",
                "minute": "2-digit",
                "hour12": False,
            },
        },
        callbacks=["eventClick"],
        key=CALENDAR_KEY,
        on_change=handle_calendar_change,
    )
    if selected_calendar_entry:
        st.info("已選取行事曆項目；下方修改區會自動帶入該筆資料。")
    st.divider()

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
    if current_user.get("line_user_id"):
        st.success("LINE 帳號已綁定")
    else:
        st.info("尚未綁定 LINE。請依 README 設定綁定碼，並在 LINE 輸入「綁定 <綁定碼>」。")
    with st.form("reminder_settings"):
        class_reminders = st.checkbox(
            "接收課後提醒與未排入警示",
            value=current_user.get("reminders_enabled", True),
        )
        study_reminders = st.checkbox(
            "接收讀書時段開始提醒",
            value=current_user.get("study_reminders_enabled", False),
        )
        ai_configured = ai_is_configured()
        ai_after_class_enabled = st.checkbox(
            "同意使用 AI 整理課後筆記並建議複習任務",
            value=current_user.get("ai_after_class_enabled") is True,
            key="ai_after_class_enabled",
            disabled=(
                not ai_configured
                and current_user.get("ai_after_class_enabled") is not True
            ),
        )
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

    st.subheader("新增可用讀書時段")
    now = datetime.now(TZ)
    slot_date = st.date_input(
        "日期",
        value=now.date(),
        min_value=now.date(),
        key="new_slot_date",
    )
    existing_ranges = []
    for slot in slots:
        if slot["date"] != slot_date.isoformat():
            continue
        start = time.fromisoformat(slot["start_time"])
        start_minute = start.hour * 60 + start.minute
        existing_ranges.append((start_minute, start_minute + slot["available_minutes"]))
    class_ranges = []
    for course in courses:
        if course["weekday"] != slot_date.isoweekday():
            continue
        start = time.fromisoformat(course["start_time"])
        end = time.fromisoformat(course["end_time"])
        class_ranges.append(
            (start.hour * 60 + start.minute, end.hour * 60 + end.minute)
        )
    current_minute = now.hour * 60 + now.minute
    if now.second or now.microsecond:
        current_minute += 1
    day_parts = [
        ("凌晨／清晨", 0, 360),
        ("上午", 360, 720),
        ("下午", 720, 1080),
        ("晚上", 1080, 1440),
    ]
    selected_blocks = []
    with st.form("add_slot", clear_on_submit=True):
        st.caption("勾選有空的半小時區塊；連續區塊會自動合併成一個讀書時段。")
        st.caption("灰色區塊代表已過去、與課程衝突或已設定為可用的時間。")
        time_columns = st.columns(len(day_parts))
        for column, (part_name, part_start, part_end) in zip(time_columns, day_parts):
            with column:
                st.markdown(f"**{part_name}**")
                for start_minute in range(part_start, part_end, 30):
                    end_minute = start_minute + 30
                    occupied = any(
                        start_minute < occupied_end and occupied_start < end_minute
                        for occupied_start, occupied_end in existing_ranges + class_ranges
                    )
                    past = (
                        slot_date == now.date()
                        and start_minute < current_minute
                    )
                    start_label = f"{start_minute // 60:02d}:{start_minute % 60:02d}"
                    end_label = f"{end_minute // 60:02d}:{end_minute % 60:02d}"
                    checkbox_key = (
                        f"new_slot_block_{slot_date.isoformat()}_{start_label}"
                    )
                    checked = st.checkbox(
                        f"{start_label}–{end_label}",
                        key=checkbox_key,
                        disabled=occupied or past,
                    )
                    if checked and not (occupied or past):
                        selected_blocks.append(start_minute)
        if st.form_submit_button("新增時段"):
            if not selected_blocks:
                st.error("請至少勾選一個半小時區塊")
            else:
                sorted_blocks = sorted(selected_blocks)
                windows = []
                window_start = previous_block = sorted_blocks[0]
                for block_start in sorted_blocks[1:]:
                    if block_start == previous_block + 30:
                        previous_block = block_start
                        continue
                    windows.append((window_start, previous_block - window_start + 30))
                    window_start = previous_block = block_start
                windows.append((window_start, previous_block - window_start + 30))
                new_slots = []
                for start_minute, duration in windows:
                    new_slots.append(
                        {
                            "availability_id": create_id("slot"),
                            "user_id": USER_ID,
                            "date": slot_date.isoformat(),
                            "start_time": (
                                f"{start_minute // 60:02d}:{start_minute % 60:02d}"
                            ),
                            "available_minutes": duration,
                        }
                    )
                safely(
                    lambda: add_availabilities(new_slots),
                    f"已新增 {len(new_slots)} 個讀書時段",
                )

    st.subheader("修改既有可用讀書時段")
    if slots:
        slot_ids = [slot["availability_id"] for slot in slots]
        clicked_slot_id = (
            selected_calendar_entry.get("id")
            if selected_calendar_entry.get("kind") == "availability"
            else None
        )
        selected_slot_id = clicked_slot_id if clicked_slot_id in slot_ids else slot_ids[0]
        slot_by_id = {slot["availability_id"]: slot for slot in slots}

        def slot_label(availability_id: str) -> str:
            slot = slot_by_id[availability_id]
            return (
                f"{slot['date']} {slot['start_time']}｜"
                f"{slot['available_minutes']} 分鐘"
            )

        selected_slot_id = st.selectbox(
            "選擇要修改的時段（也可先點上方行事曆）",
            slot_ids,
            index=slot_ids.index(selected_slot_id),
            format_func=slot_label,
            key=f"edit_slot_select_{selected_slot_id}",
        )
        selected_slot = slot_by_id[selected_slot_id]
        fixed_task_count = sum(
            task.get("preferred_availability_id") == selected_slot_id
            for task in own(records["tasks"])
        )
        if fixed_task_count:
            st.warning(
                f"{fixed_task_count} 個任務固定使用此時段；刪除時會解除固定並清除舊計畫。"
            )
        with st.form(f"edit_slot_form_{selected_slot_id}"):
            edit_slot_date = st.date_input(
                "日期",
                value=date.fromisoformat(selected_slot["date"]),
                key=f"edit_slot_date_{selected_slot_id}",
            )
            edit_slot_start = st.time_input(
                "開始時間",
                value=time.fromisoformat(selected_slot["start_time"]),
                step=900,
                key=f"edit_slot_start_{selected_slot_id}",
            )
            edit_slot_minutes = st.number_input(
                "可用分鐘",
                min_value=1,
                max_value=1440,
                value=selected_slot["available_minutes"],
                step=15,
                key=f"edit_slot_minutes_{selected_slot_id}",
            )
            confirm_delete = st.checkbox(
                "我確認要刪除此時段",
                key=f"confirm_delete_slot_{selected_slot_id}",
            )
            save_slot_clicked = st.form_submit_button("儲存時段修改")
            delete_slot_clicked = st.form_submit_button(
                "刪除時段", type="secondary"
            )
            if save_slot_clicked:
                updated_slot = {
                    **selected_slot,
                    "date": edit_slot_date.isoformat(),
                    "start_time": edit_slot_start.strftime("%H:%M"),
                    "available_minutes": int(edit_slot_minutes),
                }

                def save_slot_changes():
                    update_availability(updated_slot)
                    update_json(
                        data_path("plan"),
                        lambda rows: [
                            row for row in rows
                            if row.get("user_id") != USER_ID
                        ],
                    )

                safely(save_slot_changes, "時段已更新；請重新產生讀書計畫")
            elif delete_slot_clicked:
                if not confirm_delete:
                    st.error("請先勾選確認刪除此時段")
                else:
                    def delete_selected_slot():
                        update_json(
                            data_path("plan"),
                            lambda rows: [
                                row for row in rows
                                if row.get("user_id") != USER_ID
                            ],
                        )
                        clear_task_availability_preference(
                            selected_slot_id, USER_ID
                        )
                        delete_availability(selected_slot_id, USER_ID)

                    safely(
                        delete_selected_slot,
                        "時段已刪除；請重新產生讀書計畫",
                    )
    else:
        st.info("新增第一個可用時段後，即可在此修改時段。")

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
        st.subheader("修改任務名稱、狀態與期限")
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
            if st.form_submit_button("儲存任務修改"):
                updated_task = {
                    **selected_task,
                    "title": updated_title.strip(),
                    "deadline": updated_deadline.isoformat(),
                    "status": updated_status,
                }

                def save_task_changes():
                    update_task(updated_task)
                    update_json(
                        data_path("plan"),
                        lambda rows: [
                            row for row in rows
                            if row.get("user_id") != USER_ID
                        ],
                    )

                safely(
                    save_task_changes,
                    "任務名稱、期限與狀態已更新；請重新產生讀書計畫",
                )
    else:
        st.info("新增第一項任務後，即可在此修改期限與狀態。")

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
                update_json(
                    data_path("plan"),
                    lambda rows: merge_user_plan(rows, USER_ID, new_plan),
                )
                st.success("讀書計畫已重新產生")
                st.rerun()
            except (DataError, ValueError) as exc:
                st.error(f"排程失敗：{exc}")
    if own(records["plan"]):
        st.dataframe(own(records["plan"]), hide_index=True)
        task_titles = {task["task_id"]: task["title"] for task in tasks}
        for row in own(records["plan"]):
            if row.get("status") == "unscheduled":
                st.warning(
                    f"任務「{task_titles.get(row.get('task_id'), row.get('task_id'))}」尚未排入："
                    f"{row.get('reason') or '請檢查任務與可用時段。'}"
                )
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
                if row.get("progress") is not None:
                    st.caption(f"自評理解進度：{row['progress']}/5")
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
