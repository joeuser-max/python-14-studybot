"""ClassPulse — 設定引導 + 管理控制台 + LINE 一日虛擬展示。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

import streamlit as st

from ai_assistant import AIError, ai_is_configured, analyze_learning_records
from calendar_export import export_calendar_ics, google_calendar_url, task_calendar_event
from day_demo import SCENES, advance, new_day_state, respond, visible_messages
from demo_data import mock_learning_suggestions, seed_demo_data
from task_actions import save_task_changes, delete_task_and_plan
from exporter import export_learning_markdown
from plan_bridge import merge_user_plan, normalize_plan_result
from storage import (
    DataError, TZ, add_availability, add_event, add_task_to_storage,
    clear_task_availability_preference, create_id, data_path, delete_availability,
    load_json, save_feedback, select_demo_storage, update_availability,
    update_event, update_json, update_task,
)

USER_ID = "demo_user_001"
WEEKDAYS = {1: "週一", 2: "週二", 3: "週三", 4: "週四",
            5: "週五", 6: "週六", 7: "週日"}
NAVIGATION = ("總覽", "我的任務", "時間規劃", "學習回饋",
              "AI 助理", "連接與匯出", "LINE 一日展示", "首次設定")

st.set_page_config(page_title="ClassPulse · 學習管理中樞", page_icon="◉",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {--cp-text:#14191f;--cp-muted:#68717d;}
html,body,[class*="css"] {font-family:Inter,-apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif;}
.block-container {max-width:1100px;padding-top:2.4rem;padding-bottom:5rem;}
h1 {letter-spacing:-.045em!important;font-weight:750!important;font-size:3.05rem!important;line-height:1.16!important;}
h2,h3 {letter-spacing:-.025em!important;font-weight:680!important;}
[data-testid="stSidebar"] {border-right:1px solid rgba(130,140,160,.13);}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-radius:19px!important;}
.stButton>button,.stDownloadButton>button,.stLinkButton>a {border-radius:12px!important;
  min-height:43px;transition:transform .12s ease,box-shadow .12s ease;}
.stButton>button:hover {transform:translateY(-1px);}
[data-testid="stMetricValue"] {font-weight:720!important;letter-spacing:-.035em;}
[data-testid="stChatMessage"] {border-radius:15px!important;}
[data-testid="stProgress"] {padding-top:5px;}
.cp-eyebrow {letter-spacing:.17em;font-size:.69rem;font-weight:750;color:#718091;
  text-transform:uppercase;margin-bottom:12px;}
.cp-lead {font-size:1.1rem;color:#718091;line-height:1.65;max-width:730px;}
.cp-divider {height:1px;background:rgba(128,139,150,.18);margin:28px 0;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ◉ ClassPulse")
    st.caption("把複雜的安排，交給系統。")
    st.divider()
    demo_mode = st.toggle("展示模式", value=False, key="classpulse_demo_mode")
    if demo_mode:
        st.caption("虛構課表與 Mock 回覆，不對外發送訊息。")

select_demo_storage(demo_mode)
if demo_mode:
    seed_demo_data()

def read_all() -> dict[str, list]:
    return {name: load_json(data_path(name)) for name in
            ("events", "tasks", "availability", "plan",
             "reminders", "feedback", "users")}


def own(items: list) -> list:
    return [row for row in items if row.get("user_id") == USER_ID]


def user_info(records: dict) -> dict:
    return next((u for u in records["users"] if u.get("user_id") == USER_ID),
                {"user_id": USER_ID})


def persist_user(values: dict) -> None:
    def update(users):
        old = next((u for u in users if u.get("user_id") == USER_ID), None)
        merged = {**(old or {}), "user_id": USER_ID, **values}
        return [u if u.get("user_id") != USER_ID else merged
                for u in users] if old else users + [merged]
    update_json(data_path("users"), update)


def sync_storage_context() -> None:
    """Streamlit dialog fragments may rerun without the sidebar/top-level setup.

    ContextVar is scoped to the executing context, so restore the data directory
    from this session's demo switch BEFORE any dialog read or write.
    """
    select_demo_storage(bool(st.session_state.get("classpulse_demo_mode", False)))


def saved(action, message: str) -> None:
    try:
        sync_storage_context()
        action()
    except (DataError, ValueError, OSError) as exc:
        st.error(str(exc))
    else:
        st.toast(message)
        st.rerun()


def clear_plan() -> None:
    update_json(data_path("plan"),
                lambda rows: [r for r in rows if r.get("user_id") != USER_ID])


def task_progress(task: dict) -> int:
    try:
        return min(100, max(0, int(task.get(
            "progress_percent", 100 if task.get("status") == "completed" else 0
        ))))
    except (TypeError, ValueError):
        return 0


try:
    data = read_all()
except DataError as exc:
    st.error(f"資料讀取失敗：{exc}")
    st.stop()

today = datetime.now(TZ)
settings = user_info(data)
onboarding_done = demo_mode or settings.get("onboarding_complete") is True
nav_options = NAVIGATION if onboarding_done else ("開始設定", "LINE 一日展示")
with st.sidebar:
    if not onboarding_done:
        st.info("完成引導設定後才顯示完整控制台，也可以直接跳過。")
    redirect = st.session_state.pop("cp_next_nav", None)
    if redirect in nav_options:
        st.session_state["cp_nav"] = redirect
    if st.session_state.get("cp_nav") not in nav_options:
        st.session_state["cp_nav"] = nav_options[0]
    page = st.radio("功能", nav_options, key="cp_nav")
    st.divider()
    if demo_mode and st.button("還原展示資料", use_container_width=True):
        seed_demo_data(reset=True)
        st.session_state.pop("cp_ai_demo", None)
        st.session_state["line_day_state"] = new_day_state()
        st.rerun()
    if not onboarding_done and st.button("跳過初次設定", use_container_width=True):
        saved(lambda: persist_user({"onboarding_complete": True}), "已進入控制台")
    st.caption("LINE 一日展示皆為可重播的情境，不連接真實 LINE。")
    with st.expander("Donate · Just for fun", expanded=False):
        st.caption("支持 ClassPulse 的趣味彩蛋 · 非金流服務")
        st.write("**銀行代碼：822**")
        st.code("417540472590", language=None)
        st.caption("僅顯示資訊；網站不會收款、驗證匯款或記錄捐款。")


def hero(kicker: str, heading: str, intro: str) -> None:
    st.markdown(f'<div class="cp-eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(heading)
    st.markdown(f'<p class="cp-lead">{intro}</p>', unsafe_allow_html=True)
    st.write("")


def screenshot_preview(prefix: str) -> None:
    with st.expander("上傳課表截圖（目前支援預覽）", expanded=False):
        st.caption("PNG、JPG、WebP。僅在本機網頁預覽，不會自動辨識課程或呼叫模型 API。")
        upload = st.file_uploader("課表圖片", type=["png", "jpg", "jpeg", "webp"],
                                  key=f"cp_upload_{prefix}")
        if upload is not None:
            st.image(upload, caption="上傳的課表截圖", use_container_width=True)
            st.info("請檢查圖片內容，並使用下方表單建立可編輯課程。圖片辨識尚未實作。")


def add_course_form(prefix: str) -> None:
    with st.form(f"cp_add_course_{prefix}", clear_on_submit=True):
        title = st.text_input("課程名稱", placeholder="例如：控制系統")
        weekday = st.selectbox("星期", list(WEEKDAYS),
                               format_func=lambda x: WEEKDAYS[x], key=f"{prefix}_weekday")
        a, b = st.columns(2)
        with a:
            start = st.time_input("開始時間", value=time(9, 0), step=900,
                                  key=f"{prefix}_start")
        with b:
            end = st.time_input("結束時間", value=time(11, 0), step=900,
                                key=f"{prefix}_end")
        if st.form_submit_button("新增課程", type="primary"):
            item = {"event_id": create_id("event"), "user_id": USER_ID,
                    "event_type": "class", "title": title.strip(), "weekday": weekday,
                    "start_time": start.strftime("%H:%M"),
                    "end_time": end.strftime("%H:%M"), "offset_minutes": 10,
                    "prompt_template": "class_feedback", "enabled": True}
            saved(lambda: add_event(item), "課程已加入")


def add_task_form(prefix: str) -> None:
    with st.form(f"cp_add_task_{prefix}", clear_on_submit=True):
        subject = st.text_input("科目", placeholder="例如：控制系統")
        title = st.text_input("想完成的任務", placeholder="例如：完成第三章練習")
        a, b = st.columns(2)
        with a:
            deadline = st.date_input("期限", value=today.date() + timedelta(days=7),
                                     key=f"{prefix}_deadline")
        with b:
            minutes = st.number_input("預估分鐘", 15, 600, 60, step=15,
                                      key=f"{prefix}_minutes")
        if st.form_submit_button("建立任務", type="primary"):
            item = {"task_id": create_id("task"), "user_id": USER_ID,
                    "subject": subject.strip(), "title": title.strip(),
                    "deadline": deadline.isoformat(), "estimated_minutes": int(minutes),
                    "status": "pending", "progress_percent": 0,
                    "preferred_availability_id": ""}
            saved(lambda: add_task_to_storage(item), "任務已建立")


def add_slot_form(prefix: str) -> None:
    with st.form(f"cp_add_slot_{prefix}", clear_on_submit=True):
        day = st.date_input("可用日期", value=today.date() + timedelta(days=1),
                            key=f"{prefix}_date")
        a, b = st.columns(2)
        with a:
            starts = st.time_input("開始時間", value=time(19, 0), step=900,
                                   key=f"{prefix}_start")
        with b:
            duration = st.number_input("可用分鐘", 15, 600, 90, step=15,
                                       key=f"{prefix}_duration")
        if st.form_submit_button("加入可用時段", type="primary"):
            item = {"availability_id": create_id("slot"), "user_id": USER_ID,
                    "date": day.isoformat(), "start_time": starts.strftime("%H:%M"),
                    "available_minutes": int(duration)}
            saved(lambda: add_availability(item), "可用時段已建立")


@st.dialog("修改任務")
def task_dialog(task: dict) -> None:
    sync_storage_context()
    st.caption(f"{task['subject']} · 點選後直接編輯，不需要另外找選單。")
    with st.form(f"cp_edit_task_{task['task_id']}"):
        title = st.text_input("任務名稱", value=task["title"])
        subject = st.text_input("科目", value=task["subject"])
        a, b = st.columns(2)
        with a:
            deadline = st.date_input("期限", value=date.fromisoformat(task["deadline"]))
        with b:
            estimate = st.number_input("預估分鐘", 1, 1440,
                                       int(task["estimated_minutes"]), step=15)
        percent = st.slider("完成進度", 0, 100, task_progress(task), 5,
                            help="100% 代表完成；其他進度保留為待完成。")
        completed = st.checkbox("標記為已完成", value=percent == 100)
        confirm_delete = st.checkbox("我確定要刪除此任務", value=False)
        save_click = st.form_submit_button("儲存修改", type="primary")
        delete_click = st.form_submit_button("刪除任務")
        if save_click:
            final_percent = 100 if completed or percent == 100 else percent
            edited = {**task, "title": title.strip(), "subject": subject.strip(),
                      "deadline": deadline.isoformat(),
                      "estimated_minutes": int(estimate),
                      "progress_percent": final_percent,
                      "status": "completed" if final_percent == 100 else "pending"}
            def save_task():
                save_task_changes(
                    edited, demo_mode=bool(st.session_state.get("classpulse_demo_mode", False))
                )
            saved(save_task, "任務已更新")
        if delete_click:
            if not confirm_delete:
                st.warning("請先勾選刪除確認。")
            else:
                def delete_task():
                    delete_task_and_plan(
                        task["task_id"], USER_ID,
                        demo_mode=bool(st.session_state.get("classpulse_demo_mode", False)),
                    )
                saved(delete_task, "任務已刪除")


@st.dialog("修改讀書時段")
def slot_dialog(slot: dict) -> None:
    sync_storage_context()
    with st.form(f"cp_edit_slot_{slot['availability_id']}"):
        day = st.date_input("日期", value=date.fromisoformat(slot["date"]))
        a, b = st.columns(2)
        with a:
            starts = st.time_input("開始時間",
                                   value=time.fromisoformat(slot["start_time"]))
        with b:
            duration = st.number_input("可用分鐘", 1, 1440,
                                       int(slot["available_minutes"]), step=15)
        confirm = st.checkbox("我確定要刪除此時段")
        save_click = st.form_submit_button("儲存修改", type="primary")
        delete_click = st.form_submit_button("刪除時段")
        if save_click:
            edited = {**slot, "date": day.isoformat(),
                      "start_time": starts.strftime("%H:%M"),
                      "available_minutes": int(duration)}
            def save_slot():
                update_availability(edited)
                clear_plan()
            saved(save_slot, "時段已修改，請重新排程")
        if delete_click:
            if not confirm:
                st.warning("請先勾選刪除確認。")
            else:
                def delete_slot():
                    clear_task_availability_preference(slot["availability_id"], USER_ID)
                    delete_availability(slot["availability_id"], USER_ID)
                    clear_plan()
                saved(delete_slot, "時段已刪除")


@st.dialog("修改課程")
def course_dialog(course: dict) -> None:
    sync_storage_context()
    with st.form(f"cp_edit_course_{course['event_id']}"):
        title = st.text_input("課程名稱", value=course["title"])
        weekday = st.selectbox(
            "星期", list(WEEKDAYS), index=list(WEEKDAYS).index(course["weekday"]),
            format_func=lambda x: WEEKDAYS[x])
        a, b = st.columns(2)
        with a:
            begins = st.time_input("開始",
                                   value=time.fromisoformat(course["start_time"]))
        with b:
            ends = st.time_input("結束",
                                 value=time.fromisoformat(course["end_time"]))
        offset = st.number_input("下課後提醒偏移（分鐘）", 0, 60,
                                 int(course["offset_minutes"]), step=5)
        enable = st.checkbox("啟用課後提醒", value=bool(course.get("enabled", True)))
        if st.form_submit_button("儲存課程", type="primary"):
            changed = {**course, "title": title.strip(), "weekday": weekday,
                       "start_time": begins.strftime("%H:%M"),
                       "end_time": ends.strftime("%H:%M"),
                       "offset_minutes": int(offset), "enabled": enable}
            saved(lambda: update_event(changed), "課程已更新")


def task_card(task: dict) -> None:
    pct = task_progress(task)
    with st.container(border=True):
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            if st.button(f"{task['title']}  ·  {task['subject']}",
                         key=f"cp_task_{task['task_id']}",
                         use_container_width=True):
                task_dialog(task)
            st.caption(f"期限 {task['deadline']}  ·  預估 {task['estimated_minutes']} 分鐘"
                       "  ·  點擊卡片修改")
        with right:
            st.metric("進度", f"{pct}%")
        st.progress(pct / 100)


def slot_card(slot: dict) -> None:
    with st.container(border=True):
        if st.button(f"{slot['date']}  ·  {slot['start_time']}"
                     f"  ·  {slot['available_minutes']} 分鐘",
                     key=f"cp_slot_{slot['availability_id']}",
                     use_container_width=True):
            slot_dialog(slot)
        st.caption("點擊時段即可修改日期、時間或刪除。")


def course_card(course: dict) -> None:
    with st.container(border=True):
        if st.button(
            f"{course['title']}  ·  {WEEKDAYS.get(course['weekday'],'')}"
            f"  {course['start_time']}–{course['end_time']}",
            key=f"cp_course_{course['event_id']}", use_container_width=True,
        ):
            course_dialog(course)
        st.caption("點擊課程可修改課名、星期與上課時段。")


def generate_schedule() -> None:
    from scheduler import make_plan
    result = make_plan(own(data["tasks"]), own(data["availability"]),
                       own(data["plan"]), today)
    normalized = normalize_plan_result(result, USER_ID)
    update_json(data_path("plan"),
                lambda rows: merge_user_plan(rows, USER_ID, normalized))


def go_to(target: str) -> None:
    # st.radio 已初始化後不能直接寫入其同名 key；下次 rerun 前先排隊。
    st.session_state["cp_next_nav"] = target
    st.rerun()


def render_setup() -> None:
    step = st.session_state.get("cp_setup_step", 0)
    headings = ("一個更簡單的學習流程", "先讓 ClassPulse 認識你的課表",
                "讓 LINE 成為日常互動入口", "告訴系統何時有空",
                "最後，把行程帶到手機")
    descriptions = (
        "接下來只需要完成幾個必要設定。任何步驟都可以跳過，之後再補上。",
        "先新增一門課，或上傳課表截圖預覽。還沒有完成圖片辨識，課程需手動確認。",
        "LINE 負責課前、課後提醒與筆記回覆；目前可先跳過正式綁定。",
        "先建立一項任務與一個可用時段，Scheduler 才能安排有意義的計畫。",
        "將課程與讀書計畫匯出成 .ics，再用 Google 或 Apple Calendar 開啟。",
    )
    step = min(max(step, 0), 4)
    hero(f"初次設定 · {step + 1} / 5", headings[step], descriptions[step])
    st.progress((step + 1) / 5)
    st.write("")
    if step == 0:
        with st.container(border=True):
            st.markdown("#### 三個角色，只有一條流程")
            st.write("**LINE** 蒐集課後回饋。**AI** 提出複習建議。"
                     "**ClassPulse** 負責審核、排程和資料管理。")
            st.caption("你可以先體驗右側導航的 LINE 一日展示，稍後再完成設定。")
    elif step == 1:
        screenshot_preview("onboarding")
        with st.expander("新增課程", expanded=not bool(own(data["events"]))):
            add_course_form("setup")
        st.caption(f"目前有 {len(own(data['events']))} 門課程。")
    elif step == 2:
        with st.container(border=True):
            st.markdown("#### LINE 串接")
            st.write("在 LINE 官方帳號輸入「綁定 <綁定碼>」；正式模式需要"
                     " LINE Channel 與公開 HTTPS Webhook。")
            st.info("若尚未建立 LINE Bot，可以跳過。展示頁提供全程三選一虛擬對話。")
            if st.button("先觀看 LINE 一日展示"):
                go_to("LINE 一日展示")
    elif step == 3:
        with st.expander("建立第一項任務", expanded=not bool(own(data["tasks"]))):
            add_task_form("setup")
        with st.expander("設定第一個可用時段", expanded=not bool(own(data["availability"]))):
            add_slot_form("setup")
        st.caption(f"已建立 {len(own(data['tasks']))} 項任務、"
                   f"{len(own(data['availability']))} 個可用時段。")
    elif step == 4:
        ics = export_calendar_ics(own(data["events"]), own(data["tasks"]),
                                  own(data["availability"]), own(data["plan"]), today)
        st.download_button("下載 ClassPulse 行事曆（.ics）", ics,
                           file_name="classpulse_schedule.ics", mime="text/calendar")
        st.caption("匯出是單向的；後續修改任務需重新匯出，不是即時同步。")
    a, b = st.columns([1, 1])
    with a:
        if step > 0 and st.button("上一步", use_container_width=True):
            st.session_state["cp_setup_step"] = step - 1
            st.rerun()
    with b:
        if step == 4:
            if st.button("完成設定，進入控制台", type="primary", use_container_width=True):
                def finish():
                    persist_user({"onboarding_complete": True})
                    st.session_state["cp_next_nav"] = "總覽"
                saved(finish, "已完成初次設定")
        elif st.button("下一步（也可以略過）", type="primary",
                       use_container_width=True):
            st.session_state["cp_setup_step"] = step + 1
            st.rerun()
    if st.button("跳過全部步驟，直接進入控制台"):
        def skip():
            persist_user({"onboarding_complete": True})
            st.session_state["cp_next_nav"] = "總覽"
        saved(skip, "已進入控制台")


def render_overview() -> None:
    hero("YOUR DAY, SIMPLIFIED", "今天要完成什麼？",
         "不必在每個工具裡重複管理。這裡只保留真正需要你決定的事情。")
    tasks = own(data["tasks"])
    pending = [t for t in tasks if t.get("status") != "completed"]
    c1, c2, c3 = st.columns(3)
    c1.metric("待完成任務", len(pending))
    c2.metric("已建立課程", len(own(data["events"])))
    c3.metric("已安排讀書", sum(r.get("status") == "scheduled"
                               for r in own(data["plan"])))
    st.markdown('<div class="cp-divider"></div>', unsafe_allow_html=True)
    st.subheader("現在最重要的")
    if pending:
        for task in sorted(pending, key=lambda t: t["deadline"])[:3]:
            task_card(task)
    else:
        st.success("目前沒有待完成的任務。")
    st.write("")
    st.subheader("下一步")
    a, b, c = st.columns(3)
    with a:
        if st.button("查看時間規劃", use_container_width=True):
            go_to("時間規劃")
    with b:
        if st.button("整理課後筆記", use_container_width=True):
            go_to("學習回饋")
    with c:
        if st.button("體驗 LINE 一天", use_container_width=True):
            go_to("LINE 一日展示")
    if demo_mode:
        st.caption("目前使用獨立的虛構展示資料，可在側欄還原，不影響正式資料。")


def render_tasks() -> None:
    hero("TASKS", "每個任務，都能直接調整。",
         "點擊任務卡片就能查看、修改進度百分比、標記完成或刪除。沒有額外的選擇清單。")
    tasks = sorted(own(data["tasks"]), key=lambda t: (t.get("status") == "completed",
                                                      t.get("deadline", "")))
    if tasks:
        for task in tasks:
            task_card(task)
    else:
        st.info("還沒有任務，先建立第一項。")
    with st.expander("＋ 新增任務", expanded=not bool(tasks)):
        add_task_form("tasks")


def render_schedule() -> None:
    hero("PLAN & CALENDAR", "掌握時間，不重造行事曆。",
         "ClassPulse 負責安排與修改；Google／Apple Calendar 負責讓你隨時在手機查看。")
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("每週課程")
        courses = sorted(own(data["events"]),
                         key=lambda c: (c["weekday"], c["start_time"]))
        for c in courses:
            course_card(c)
        if not courses:
            st.info("尚未建立每週課程。")
        screenshot_preview("planning")
        with st.expander("＋ 新增課程"):
            add_course_form("planning_course")
    with right:
        st.subheader("可用讀書時段")
        slots = sorted(own(data["availability"]),
                       key=lambda s: (s["date"], s["start_time"]))
        for s in slots:
            slot_card(s)
        if not slots:
            st.info("沒有可用時段，Scheduler 暫時無法安排。")
        with st.expander("＋ 新增可用時段"):
            add_slot_form("planning_slot")
    st.markdown('<div class="cp-divider"></div>', unsafe_allow_html=True)
    st.subheader("排程結果")
    if st.button("重新安排讀書任務", type="primary"):
        saved(generate_schedule, "讀書計畫已重新計算")
    by_task = {t["task_id"]: t for t in own(data["tasks"])}
    by_slot = {s["availability_id"]: s for s in own(data["availability"])}
    plan = own(data["plan"])
    if not plan:
        st.caption("建立任務與時段後，按上方按鈕安排。")
    for row in plan:
        task = by_task.get(row.get("task_id"))
        if not task or task.get("status") == "completed":
            continue
        if row.get("status") != "scheduled":
            st.warning(f"{task['title']}：{row.get('reason') or '目前沒有可用時段'}")
            continue
        slot = by_slot.get(row.get("availability_id"))
        if slot is None:
            continue
        with st.container(border=True):
            st.write(f"**{task['title']}**")
            st.caption(f"{slot['date']} {slot['start_time']}  ·  "
                       f"{task['estimated_minutes']} 分鐘")
            try:
                begins, ends = task_calendar_event(task, slot)
                url = google_calendar_url("讀書｜" + task["title"], begins, ends,
                                          "ClassPulse 讀書計畫")
                st.link_button("新增到 Google Calendar", url)
            except (ValueError, KeyError):
                st.caption("此筆時段格式不完整，暫無法產生行事曆連結。")
    st.caption("手機行事曆整包匯出請到「連接與匯出」；此頁不維護第二套行事曆資料。")


def render_feedback() -> None:
    hero("LEARNING RECORDS", "同一堂課的筆記，放在一起。",
         "依課程與日期彙整顯示，不刪除任何原始紀錄；每則筆記仍可回溯來源與時間。")
    courses = {c["event_id"]: c["title"] for c in own(data["events"])}
    grouped = defaultdict(list)
    for f in own(data["feedback"]):
        grouped[(f.get("class_date", ""), f.get("event_id", ""))].append(f)
    if not grouped:
        st.info("尚未收到課後回饋。可透過 LINE 或一日展示理解互動方式。")
        return
    for (day, event_id), notes in sorted(grouped.items(), reverse=True):
        title = courses.get(event_id, "未命名課程")
        notes.sort(key=lambda n: n.get("received_at", ""))
        with st.expander(f"{day}  ·  {title}  ·  {len(notes)} 則筆記",
                         expanded=len(grouped) == 1):
            for index, note in enumerate(notes):
                clock = note.get("received_at", "").split("T")[-1][:5]
                st.caption(f"{clock or '時間未提供'}  ·  第 {index+1} 則  ·  {note.get('source', '')}")
                st.write(note.get("content", ""))
                if note.get("progress") is not None:
                    st.caption(f"當次自評理解度：{note['progress']} / 5")
                analysis = note.get("ai_analysis")
                if isinstance(analysis, dict) and analysis.get("summary"):
                    label = "【預載展示／Mock】" if demo_mode else "AI 整理："
                    st.info(label + str(analysis["summary"]))
                if index < len(notes) - 1:
                    st.divider()
            st.caption("此項目為視覺彙整；原始 feedback_id 及筆記仍分別保存。")


def render_ai() -> None:
    hero("AI · FEEDBACK TO ACTION", "讓筆記成為下一個行動。",
         "AI 提出建議，是否加入任務仍由你決定；排程的決定性規則交給 Scheduler。")
    feedback = own(data["feedback"])
    if not feedback:
        st.info("目前沒有課後筆記，先完成 LINE 回饋或使用展示模式。")
        return
    key = "cp_demo_ai_result" if demo_mode else "cp_live_ai_result"
    if demo_mode:
        st.caption("Mock 展示：固定規則產生建議，不呼叫任何模型 API。")
        if st.button("產生一份示範 AI 建議", type="primary"):
            st.session_state[key] = mock_learning_suggestions(
                feedback, own(data["events"]), USER_ID)
            st.rerun()
    else:
        st.caption("真實 OpenAI Responses API 需自行設定憑證，並同意送出筆記資料。")
        consent = st.checkbox("我同意本次將學習紀錄送到外部 AI 模型分析",
                              key="cp_ai_consent")
        if st.button("分析學習紀錄", type="primary", disabled=not consent):
            markdown = export_learning_markdown(data, today, USER_ID)
            try:
                st.session_state[key] = analyze_learning_records(
                    feedback, USER_ID, markdown)
                st.rerun()
            except AIError as exc:
                st.error(str(exc))
    result = st.session_state.get(key)
    if not result:
        return
    st.subheader("整理結果")
    st.write(result.get("summary", ""))
    for i, suggestion in enumerate(result.get("suggestions", [])):
        with st.container(border=True):
            st.write(f"**{suggestion['suggested_task']}**")
            st.caption(f"來源筆記：{suggestion['source_feedback_id']}")
            st.caption(f"待釐清：{suggestion['unresolved_question']}")
            existing = any(t.get("source_feedback_id") == suggestion["source_feedback_id"]
                           and t.get("source") == "ai_confirmed"
                           for t in own(data["tasks"]))
            if existing:
                st.success("此來源已有確認過的任務。")
                continue
            with st.form(f"cp_confirm_ai_{i}"):
                minutes = st.number_input("預估分鐘", 15, 600, 45,
                                          step=15, key=f"cp_ai_minutes_{i}")
                due = st.date_input("期限", today.date() + timedelta(days=7),
                                    key=f"cp_ai_due_{i}")
                if st.form_submit_button("確認並加入讀書任務"):
                    task = {"task_id": create_id("task"), "user_id": USER_ID,
                            "subject": suggestion["topic"][:100],
                            "title": suggestion["suggested_task"][:300],
                            "deadline": due.isoformat(),
                            "estimated_minutes": int(minutes),
                            "status": "pending", "progress_percent": 0,
                            "preferred_availability_id": "",
                            "source_feedback_id": suggestion["source_feedback_id"],
                            "source": "ai_confirmed"}
                    saved(lambda: add_task_to_storage(task), "已確認並新增 AI 建議任務")


def render_connections() -> None:
    hero("CONNECTIONS", "連好工具，其他交給 ClassPulse。",
         "LINE 負責對話，行事曆負責手機查看。你也可以下載可重用的 Markdown 原始紀錄。")
    with st.container(border=True):
        st.subheader("LINE 提醒偏好")
        if demo_mode:
            st.info("展示模式：開關只修改隔離資料，不會傳送 LINE 通知。")
        elif settings.get("line_user_id"):
            st.success("已綁定 LINE 測試帳號。")
        else:
            st.caption("尚未綁定。請在 LINE 輸入「綁定 <綁定碼>」以連接測試帳號。")
        with st.form("cp_line_settings"):
            class_push = st.checkbox("課後提醒及未排入任務通知",
                                     value=settings.get("reminders_enabled", True))
            study_push = st.checkbox("讀書時段開始提醒",
                                     value=settings.get("study_reminders_enabled", False))
            use_ai = st.checkbox("允許課後 AI 整理",
                                 value=settings.get("ai_after_class_enabled", False),
                                 disabled=not demo_mode and not ai_is_configured())
            if st.form_submit_button("儲存提醒設定"):
                saved(lambda: persist_user({
                    "reminders_enabled": class_push,
                    "study_reminders_enabled": study_push,
                    "ai_after_class_enabled": use_ai}), "提醒偏好已保存")
    st.write("")
    with st.container(border=True):
        st.subheader("匯出到手機行事曆")
        ics = export_calendar_ics(own(data["events"]), own(data["tasks"]),
                                  own(data["availability"]), own(data["plan"]), today)
        st.download_button("下載 Calendar .ics", ics, file_name="classpulse.ics",
                           mime="text/calendar", type="primary")
        st.caption("Google Calendar／Apple Calendar 可匯入 .ics；這是單向快照，"
                   "後續修改請重新匯入，不會自動雙向同步。")
        st.link_button("開啟 Google Calendar", "https://calendar.google.com/calendar/u/0/r")
    st.write("")
    with st.container(border=True):
        st.subheader("學習資料匯出")
        markdown = export_learning_markdown(data, today, USER_ID)
        st.download_button("下載 Markdown", markdown.encode("utf-8"),
                           file_name="classpulse_learning_export.md", mime="text/markdown")
        st.caption("筆記可能含個人資訊，傳送給第三方前請先檢查。")


def render_line_day() -> None:
    hero("SIMULATED LINE · 08:00—21:00", "陪你走過完整的一天。",
         "這是能實際點選的虛擬 LINE 對話。每個場景提供三個選項，展示提醒、回覆、Mock AI、排程與晚間回顧。")
    st.info("純展示情境：不會讀取或修改正式課表，不發送 LINE 訊息，不呼叫 AI API。"
            "點選一個選項後可以前往下個時段，或一鍵演示全天。")
    if "line_day_state" not in st.session_state:
        st.session_state["line_day_state"] = new_day_state()
    state = st.session_state["line_day_state"]
    left, right = st.columns([1.65, 1], gap="large")
    with right:
        st.subheader("當日時間軸")
        st.progress(1.0 if state["completed"] else
                    (state["index"] + 1) / len(SCENES))
        for i, scene in enumerate(SCENES):
            label = "✓" if i < state["index"] or state["completed"] else (
                "●" if i == state["index"] else "·")
            st.caption(f"{label}  {scene['time']}  {scene['title']}")
        signals = state.get("signals", {})
        with st.expander("本日模擬狀態", expanded=True):
            st.caption("理解度：" + (
                f"{signals['understanding']} / 5"
                if signals.get("understanding") is not None else "尚未回報"))
            st.caption("課後筆記：" + ("已記錄" if signals.get("note") else "尚未記錄"))
            st.caption("AI 建議任務：" + (
                f"已確認（{signals['accepted_task_minutes']} 分鐘）"
                if signals.get("accepted_task_minutes") else "尚未確認"))
            st.caption("排程：" + str(signals.get("scheduled_at") or "尚未排入"))
            st.caption("任務完成度：" + (
                f"{signals['task_progress']}%"
                if signals.get("task_progress") is not None else "尚未回報"))
        st.write("")
        if st.button("一鍵播放完整一天", use_container_width=True):
            next_state = state
            while not next_state["completed"]:
                if not next_state["awaiting_next"]:
                    next_state = respond(next_state, 0)
                next_state = advance(next_state)
            st.session_state["line_day_state"] = next_state
            st.rerun()
        if st.button("從 08:00 重新開始", use_container_width=True):
            st.session_state["line_day_state"] = new_day_state()
            st.rerun()
    with left:
        with st.container(border=True):
            st.markdown("#### LINE · ClassPulse（虛擬介面）")
            st.caption("以下訊息與回覆均為展示腳本，不是真實 LINE 對話")
            messages = visible_messages(state)
            with st.container(height=510):
                if len(messages) > 9:
                    with st.expander(f"查看較早的對話（{len(messages) - 9} 則）"):
                        for old_msg in messages[:-9]:
                            st.caption(f"{old_msg['at']} · {'ClassPulse' if old_msg['role'] == 'bot' else '使用者'}")
                            st.write(old_msg["text"])
                            st.divider()
                for message in messages[-9:]:
                    is_bot = message["role"] == "bot"
                    with st.chat_message("assistant" if is_bot else "user"):
                        st.caption(f"{message['at']} · {'ClassPulse' if is_bot else '使用者'}")
                        st.write(message["text"])
            if state["completed"]:
                st.success("已完成 08:00–21:00 全日展示。")
                st.caption("可以重播，或到控制台查看真實資料與行事曆匯出。")
            elif state["awaiting_next"]:
                if st.button("繼續前往下一個時段", type="primary",
                             use_container_width=True):
                    st.session_state["line_day_state"] = advance(state)
                    st.rerun()
            else:
                scene = SCENES[state["index"]]
                st.caption(f"{scene['time']} · 請選擇一個虛擬使用者回覆")
                for i, (label, _reply) in enumerate(scene["options"]):
                    if st.button(label, key=f"cp_scene_{state['index']}_{i}",
                                 use_container_width=True):
                        st.session_state["line_day_state"] = respond(state, i)
                        st.rerun()
    with st.expander("這一天有哪些系統功能？"):
        st.write("08:00 今日規劃 → 課前提醒 → 課後理解度 → 補筆記 → "
                 "Mock AI 整理 → 人工確認新任務 → 規則式排程 → "
                 "未排入提醒 → 外部行事曆 → 晚間讀書提醒 → 進度回報 → 21:00 回顧。")
        st.caption("此對話劇情為固定示範，實際 LINE Bot 的觸發與 API 權限需另行驗證。")


if page in ("開始設定", "首次設定"):
    render_setup()
elif page == "總覽":
    render_overview()
elif page == "我的任務":
    render_tasks()
elif page == "時間規劃":
    render_schedule()
elif page == "學習回饋":
    render_feedback()
elif page == "AI 助理":
    render_ai()
elif page == "連接與匯出":
    render_connections()
elif page == "LINE 一日展示":
    render_line_day()
