"""ClassPulse — 設定引導 + 管理控制台 + LINE 一日虛擬展示。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json

import streamlit as st
from version_info import get_version_info
from streamlit_calendar import calendar as editable_calendar

from ai_assistant import AIError, ai_is_configured, analyze_learning_records
from calendar_export import export_calendar_ics, google_calendar_url, task_calendar_event
from day_demo import SCENES, advance, new_day_state, respond, visible_messages
from progress_insights import history_series
from visual_planner import (board_events, calendar_change_candidate, place_task,
                            propose_placement, unassign_task, resume_auto, rebuild_plan)
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

version = get_version_info()
with st.sidebar:
    st.markdown("### ◉ ClassPulse")
    st.caption("把複雜的安排，交給系統。")
    st.caption(f"目前程式：{version['branch']} · {version['sha']}")
    if version["branch"] not in ("main", "未取得 Git 分支"):
        st.warning("你正在使用功能分支，不是已合併的 main。")
    with st.expander("查看執行目錄及版本", expanded=False):
        st.code(version["directory"], language=None)
        st.caption("這是此網頁實際載入 app.py 的資料夾；若不是你更新的專案目錄，請關閉舊網站。")
        st.caption("請使用 start_mac.sh 或 start_windows.ps1 更新 main，統一由 localhost:8502 開啟。")
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
             "reminders", "feedback", "users", "progress_events")}


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
    with st.expander("校園資源", expanded=False):
        st.link_button("中央大學 K 書空間預約", "https://mwa.lib.ncu.edu.tw/pwaspace/", use_container_width=True)
        st.link_button("中央大學 ee-class", "https://ncueeclass.ncu.edu.tw", use_container_width=True)
        st.caption("資料與公告以學校官方網站為準。")
    with st.expander("Donate", expanded=False):
        st.caption("支持 ClassPulse · 資訊展示，非金流服務")
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
                    "preferred_availability_id": "", "source": "manual_user"}
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
            ai_label = "  ·  ✦ AI 建議" if task.get("source") == "ai_confirmed" else ""
            if st.button(f"{task['title']}  ·  {task['subject']}{ai_label}",
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
    rebuild_plan(USER_ID, today)
    refresh_timesheet()


def go_to(target: str) -> None:
    # st.radio 已初始化後不能直接寫入其同名 key；下次 rerun 前先排隊。
    st.session_state["cp_next_nav"] = target
    st.rerun()


def render_progress_insights(prefix: str = "overview") -> None:
    """只統計實際完成的任務，圖表不將預估時間誤當作實際讀書時間。"""
    st.subheader("學習成果")
    st.caption("完成後才計入；分鐘數是任務的「預估時間」，不是實際測得的 K 書時間。")
    period = st.radio("統計區間", ["1D", "1W", "1M"], index=1,
                      horizontal=True, key=f"cp_stats_period_{prefix}")
    summary = history_series(own(data["progress_events"]), own(data["tasks"]),
                             USER_ID, period, today)
    c1, c2, c3 = st.columns(3)
    c1.metric("完成任務", summary["completed"])
    c2.metric("完成任務預估時間", f"{summary['planned_minutes']} 分鐘")
    c3.metric("有完成紀錄的日數", summary["active_days"])
    if summary["completed"]:
        st.area_chart(summary["rows"], x="date", y="cumulative",
                      height=230, use_container_width=True)
    else:
        st.info("這個期間尚無完成紀錄。將任務標記為完成後，數據才會累積。")
    if demo_mode:
        st.caption("目前為展示資料；正式模式僅計算真實的進度修改紀錄。")


def refresh_timesheet() -> None:
    """重新建立前端日曆，確保取消拖曳與儲存後不留下虛假的視覺狀態。"""
    st.session_state["cp_timesheet_epoch"] = st.session_state.get("cp_timesheet_epoch", 0) + 1
    st.session_state.pop("cp_last_timesheet_change", None)


def render_timesheet() -> None:
    """拖曳與拉長的視覺排程：時間座標須由後端檢核並確認才真正儲存。"""
    st.subheader("拖曳式時間表")
    st.caption("「全天」列的待排任務可以拖進下方週／日時間格。"
               "拖動方塊上下邊緣可調整時長（15 分鐘）；"
               "紅色是課程、淺綠是可用時間、藍色是手動任務、紫色 ✦ 是 AI 建議。")
    week_date = st.date_input("規劃日期", today.date(), key="cp_timesheet_focus")
    events = board_events(own(data["events"]), own(data["availability"]),
                          own(data["tasks"]), own(data["plan"]), week_date, today)
    options = {
        "initialDate": week_date.isoformat(), "initialView": "timeGridWeek",
        "editable": True, "selectable": True, "eventOverlap": True,
        "eventResizableFromStart": True, "slotDuration": "00:15:00",
        "snapDuration": "00:15:00", "defaultTimedEventDuration": "00:45:00",
        "allDaySlot": True, "dayMaxEvents": False, "height": 650,
        "nowIndicator": True, "timeZone": "Asia/Taipei",
        "slotMinTime": "07:00:00", "slotMaxTime": "24:00:00",
        "headerToolbar": {"left": "today prev,next", "center": "title",
                          "right": "timeGridDay,timeGridWeek,dayGridMonth"},
        "buttonText": {"today": "今天", "week": "週", "day": "日", "month": "月"},
        "firstDay": 1, "locale": "zh-tw",
    }
    css = """
    .fc{font-family:-apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif}
    .fc .fc-toolbar-title{font-size:1.13rem;font-weight:700}
    .fc .fc-event{border-radius:7px;padding:2px 5px;cursor:grab}
    .fc .fc-timegrid-now-indicator-line{border-color:#F59E0B}
    .fc .fc-day-today{background:rgba(70,114,190,.04)!important}
    .fc .fc-timegrid-all-day{background:rgba(117,128,145,.06)}
    """
    try:
        response = editable_calendar(events=events, options=options, custom_css=css,
                                     key=f"cp_timesheet_calendar_{week_date.isoformat()}_v{st.session_state.get('cp_timesheet_epoch', 0)}")
    except Exception as exc:
        st.error(f"互動日曆無法載入：{exc}")
        response = None
    candidate = calendar_change_candidate(response, own(data["tasks"]))
    if candidate:
        signature = json.dumps(response.get("eventChange", {}), sort_keys=True, ensure_ascii=False)
        if signature != st.session_state.get("cp_last_timesheet_change"):
            st.session_state["cp_last_timesheet_change"] = signature
            st.session_state["cp_pending_timesheet"] = candidate

    with st.expander("待排任務盒", expanded=True):
        scheduled_ids = {p["task_id"] for p in own(data["plan"])
                         if p.get("status") == "scheduled"}
        waiting = [t for t in own(data["tasks"])
                   if t.get("status") == "pending" and t["task_id"] not in scheduled_ids]
        if not waiting:
            st.caption("目前沒有待排任務。請新增任務後再拖入時間格。")
        for task in waiting:
            a, b = st.columns([4, 1], vertical_alignment="center")
            icon = "✦ AI 建議" if task.get("source") == "ai_confirmed" else "手動建立"
            a.write(f"**{task['title']}** · {icon} · {task['estimated_minutes']} 分鐘")
            if task.get("planning_hold"):
                if b.button("恢復自動排程", key=f"cp_resume_{task['task_id']}"):
                    saved(lambda tid=task["task_id"]: resume_auto(USER_ID, tid, today),
                          "已恢復自動安排")
            else:
                if b.button("指定時間", key=f"cp_pick_{task['task_id']}"):
                    st.session_state["cp_timesheet_pick_task"] = task["task_id"]
                    st.rerun()

    with st.expander("觸控／手機備用：指定時間與長度",
                     expanded=bool(st.session_state.get("cp_timesheet_pick_task"))):
        available_tasks = [t for t in own(data["tasks"]) if t.get("status") == "pending"]
        if available_tasks:
            lookup = {t["task_id"]: t for t in available_tasks}
            selected = st.session_state.get("cp_timesheet_pick_task")
            ix = list(lookup).index(selected) if selected in lookup else 0
            with st.form("cp_timesheet_manual_form"):
                task_id = st.selectbox("任務", list(lookup), index=ix,
                                       format_func=lambda tid:
                                       ("✦ AI " if lookup[tid].get("source") == "ai_confirmed" else "")
                                       + lookup[tid]["title"])
                day = st.date_input("日期", today.date() + timedelta(days=1),
                                    key="cp_timesheet_manual_date")
                clock = st.time_input("開始時間", time(19, 0), step=900,
                                      key="cp_timesheet_manual_start")
                original_minutes = int(lookup[task_id]["estimated_minutes"])
                minutes = st.number_input("時長（分鐘）", 15, 600,
                                          min(600, max(15, ((original_minutes + 14) // 15) * 15)),
                                          step=15, key="cp_timesheet_manual_duration")
                if st.form_submit_button("預覽安排"):
                    beginning = datetime.combine(day, clock, TZ)
                    st.session_state["cp_pending_timesheet"] = {
                        "kind": "place", "task_id": task_id,
                        "start": beginning,
                        "end": beginning + timedelta(minutes=int(minutes)),
                    }
                    st.rerun()

    pending = st.session_state.get("cp_pending_timesheet")
    if not pending:
        st.caption("拖曳或拉長之後，請在這裡確認；未確認不會變更儲存資料。")
        return
    task = next((t for t in own(data["tasks"])
                 if t.get("task_id") == pending.get("task_id")), None)
    if not task:
        st.session_state.pop("cp_pending_timesheet", None)
        return
    st.divider()
    st.markdown("#### 確認時間表變更")
    if pending.get("kind") == "unschedule":
        st.info(f"將「{task['title']}」移回待排盒；此任務將暫停自動排程。")
        a, b = st.columns(2)
        if a.button("確認移回待排", type="primary", key="cp_unassign"):
            def do_unassign():
                unassign_task(USER_ID, task["task_id"], today)
                st.session_state.pop("cp_pending_timesheet", None)
                refresh_timesheet()
            saved(do_unassign, "已移回待排")
        if b.button("取消", key="cp_unassign_no"):
            st.session_state.pop("cp_pending_timesheet", None)
            refresh_timesheet()
            st.rerun()
        return
    try:
        proposal = propose_placement(
            own(data["tasks"]), own(data["availability"]), own(data["plan"]),
            own(data["events"]), USER_ID, task["task_id"],
            pending["start"], pending["end"], today)
    except (DataError, ValueError) as exc:
        st.error(f"不能儲存這個時段：{exc}")
        if st.button("取消此次移動", key="cp_bad_drop"):
            st.session_state.pop("cp_pending_timesheet", None)
            refresh_timesheet()
            st.rerun()
        return
    st.write(f"**{task['title']}**：{proposal['start']:%Y-%m-%d %H:%M} — "
             f"{proposal['end']:%H:%M}（{proposal['minutes']} 分鐘）")
    override = None
    if proposal["classes"]:
        names = "、".join(item["title"] for item in proposal["classes"])
        st.warning(f"這個時段覆蓋課程：「{names}」。"
                   "如仍要安排，必須明確說明這次課程如何處理。")
        override = st.radio("課程衝突原因", ("請假", "翹課", "停課"),
                            index=None, key="cp_conflict_reason")
        st.caption("這只是本人對此單次課程的紀錄，不會自動通知學校或改動 ee-class。")
    a, b = st.columns(2)
    if a.button("確認並儲存", type="primary", key="cp_placement_confirm",
                disabled=bool(proposal["classes"]) and not override):
        def commit_placement():
            place_task(USER_ID, task["task_id"], proposal["start"],
                       proposal["end"], override, today)
            st.session_state.pop("cp_pending_timesheet", None)
            refresh_timesheet()
        saved(commit_placement, "任務時段已保存，排程已重新計算")
    if b.button("取消變更", key="cp_placement_cancel"):
        st.session_state.pop("cp_pending_timesheet", None)
        refresh_timesheet()
        st.rerun()


def render_setup() -> None:
    """每次只提出一個具體目標；說明資料是如何經 LINE、AI、Scheduler 流動。"""
    step = min(max(int(st.session_state.get("cp_setup_step", 0)), 0), 4)
    titles = (
        "先認識 ClassPulse",
        "建立你的每週課表",
        "了解 LINE 與 AI 的角色",
        "加入任務與可以讀書的時間",
        "將安排帶到手機，完成設定",
    )
    intros = (
        "這不是另一個要每天填寫的行事曆。網站管理計畫；LINE 接收筆記；AI 整理建議；最後由排程規則決定時間。",
        "先讓系統知道哪些時段有固定課程。這會在後續排程時保留你的上課時間。",
        "課後從 LINE 回覆理解度與筆記，AI 才能提出複習方向；你確認後，建議才會變成任務。",
        "排程需要兩種資訊：你想完成什麼、何時有空。完成後，可到視覺化時間表拖曳並調整長度。",
        "你可以把已排好的計畫匯出到 Google／Apple Calendar；也可以先跳過，之後再來下載。",
    )
    hero(f"SETUP · 步驟 {step+1}/5", titles[step], intros[step])
    st.progress((step + 1) / 5)
    st.caption("每一步都可跳過。不必先準備 LINE Token、AI API Key，或一次填完所有資料。")

    if step == 0:
        st.subheader("整個使用流程")
        a, b, c = st.columns(3)
        with a:
            with st.container(border=True):
                st.markdown("**1. 設定**")
                st.write("填入每週課表、待辦任務與可用時段。")
                st.caption("使用網站控制台")
        with b:
            with st.container(border=True):
                st.markdown("**2. 課後回饋**")
                st.write("LINE 收集筆記，AI 提出複習建議；你決定是否接受。")
                st.caption("正式串接前可先看模擬")
        with c:
            with st.container(border=True):
                st.markdown("**3. 規劃與回顧**")
                st.write("Scheduler 避開固定課程；時間表可手動拖曳，完成後生成統計。")
                st.caption("結果可匯出至手機行事曆")
        st.info("如果只是期末展示：先開左側「展示模式」，即可使用獨立的虛構課表及 LINE 一日展示。"
                "它不會發出真實 LINE 訊息，也不會修改正式資料。")
        st.caption(f"目前執行版本：{version['branch']} · {version['sha']}。如果看不到新 Timesheet，"
                   "請先檢查是否從舊的 localhost:8501 開啟。")

    elif step == 1:
        st.markdown("#### 現在請做：新增一門固定課程")
        st.write("例如「週三 13:00–15:00 控制系統」。系統會在時間表上用固定方塊顯示它，"
                 "自動排程會避開與課程重疊的可用時段。")
        screenshot_preview("onboarding")
        st.caption("課表截圖目前只能預覽，不會自動讀圖建立課程。請使用下方表單手動確認。")
        with st.expander("＋ 新增一門課程", expanded=not bool(own(data["events"]))):
            add_course_form("setup")
        count = len(own(data["events"]))
        if count:
            st.success(f"已建立 {count} 門課程。可以繼續，日後在「時間規劃」點擊課程修改。")
        else:
            st.info("還沒有建立課程。如果暫時沒有課表，可以直接下一步，稍後補充。")

    elif step == 2:
        st.markdown("#### 這一步的資料如何流動？")
        st.write("**LINE 課後訊息 → 你回報筆記與理解度 → AI 分析 → 你確認建議 → 讀書任務**")
        st.write("AI 只提出待辦與複習方向，不會直接代替你決定讀書時間；"
                 "時間仍由 Scheduler 按期限與可用時段排入。")
        if demo_mode:
            st.success("目前為展示模式：可直接體驗三選一的虛擬 LINE 對話與 Mock AI。")
        elif settings.get("line_user_id"):
            st.success("此資料中已有 LINE 綁定資訊。正式訊息能否送達仍要驗證 Webhook 與服務運作。")
        else:
            st.info("尚未連接 LINE，並不影響其他功能。真正連接需要 LINE 官方帳號、"
                    "公開 HTTPS Webhook 與綁定碼；不必把 Token 填在展示畫面。")
        if st.button("先體驗 08:00–21:00 LINE 一日展示", key="cp_setup_line_demo"):
            go_to("LINE 一日展示")
        st.caption("這裡的模擬只展示對話情境；真實 LINE 推播須另行啟動 Bot／提醒 Worker。")

    elif step == 3:
        st.markdown("#### 現在請做：建立一個任務，再告訴系統何時有空")
        st.write("例如「完成回授穩定度練習，60 分鐘，週五前完成」，"
                 "再新增「週四 19:00–20:30 可讀書」。")
        with st.expander("① 建立讀書任務", expanded=not bool(own(data["tasks"]))):
            add_task_form("setup")
        with st.expander("② 新增可用讀書時段", expanded=not bool(own(data["availability"]))):
            add_slot_form("setup")
        task_count = len(own(data["tasks"]))
        slot_count = len(own(data["availability"]))
        st.caption(f"目前任務 {task_count} 項、可用時段 {slot_count} 個。")
        if task_count and slot_count:
            st.success("已有任務和可用時間。完成設定後到「時間規劃」拖動任務方塊，"
                       "或使用「重新安排其他任務」。")
        else:
            st.info("至少一項任務與一段可用時間，才能看到有意義的自動排程結果。"
                    "但現在仍可以跳過。")
        st.caption("紅色課程不可直接移動；手動安排若與課程重疊，會要求你確認請假／翹課／停課的原因。")

    elif step == 4:
        st.markdown("#### 最後：把已規劃的時間帶到手機")
        st.write("ClassPulse 是任務與時間的管理來源；Google／Apple Calendar 可以用來在手機查看。")
        ics = export_calendar_ics(own(data["events"]), own(data["tasks"]),
                                  own(data["availability"]), own(data["plan"]), today)
        st.download_button("下載我的行事曆（.ics）", ics,
                           file_name="classpulse_schedule.ics", mime="text/calendar",
                           type="primary")
        scheduled = sum(p.get("status") == "scheduled" for p in own(data["plan"]))
        if scheduled:
            st.success(f"目前有 {scheduled} 個已安排讀書時段可匯出。")
        else:
            st.info("目前沒有已安排的讀書任務。可以先完成設定，再回「時間規劃」安排後重新匯出。")
        st.caption("提醒：.ics 是一次性快照，不會自動同步。之後修改時間，須重新匯入更新。")

    st.divider()
    previous, forward = st.columns(2)
    with previous:
        if step > 0 and st.button("上一步", key="cp_setup_previous",
                                 use_container_width=True):
            st.session_state["cp_setup_step"] = step - 1
            st.rerun()
    with forward:
        if step < 4:
            if st.button("繼續下一步", type="primary", key="cp_setup_continue",
                         use_container_width=True):
                st.session_state["cp_setup_step"] = step + 1
                st.rerun()
        elif st.button("完成並進入 Dashboard", type="primary",
                       key="cp_setup_finish", use_container_width=True):
            def finish():
                persist_user({"onboarding_complete": True})
                st.session_state["cp_next_nav"] = "總覽"
            saved(finish, "初次設定已完成")
    if st.button("略過剩餘設定，直接進入 Dashboard", key="cp_setup_skip"):
        def skip():
            persist_user({"onboarding_complete": True})
            st.session_state["cp_next_nav"] = "總覽"
        saved(skip, "已進入 Dashboard；稍後可以回到「首次設定」補齊")



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
    st.write("")
    render_progress_insights("overview")
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
    hero("VISUAL PLANNER", "把任務拖進你的時間裡。",
         "上方待排任務盒連到時間格；拉動方塊長度後，確認儲存才會改變真正排程。")
    render_timesheet()
    st.write("")
    if st.toggle("顯示進階管理（課程與可用時間）", value=False,
                 key="cp_show_advanced_time_settings"):
        left, right = st.columns(2, gap="large")
        with left:
            st.subheader("每週課程")
            courses = sorted(own(data["events"]),
                             key=lambda c: (c["weekday"], c["start_time"]))
            for course in courses:
                course_card(course)
            screenshot_preview("planning")
            with st.expander("＋ 新增課程"):
                add_course_form("planning_course")
        with right:
            st.subheader("可用讀書時段")
            slots = sorted((s for s in own(data["availability"])
                            if s.get("origin") != "manual_calendar"),
                           key=lambda s: (s["date"], s["start_time"]))
            for slot in slots:
                slot_card(slot)
            with st.expander("＋ 新增可用時段"):
                add_slot_form("planning_slot")
    st.divider()
    a, b = st.columns([1, 2], vertical_alignment="center")
    with a:
        if st.button("重新安排其他任務", type="primary", key="cp_timesheet_rebuild"):
            saved(generate_schedule, "已重新排程；手動安排會優先保留")
    with b:
        st.caption("手動安排優先；其他任務依 Deadline 與時段容量自動安排。"
                   "自動排程排除課程重疊時段。")
    st.subheader("目前安排")
    task_lookup = {task["task_id"]: task for task in own(data["tasks"])}
    slot_lookup = {slot["availability_id"]: slot for slot in own(data["availability"])}
    for row in own(data["plan"]):
        task = task_lookup.get(row.get("task_id"))
        if not task or task.get("status") == "completed":
            continue
        if row.get("status") != "scheduled":
            st.warning(f"{task['title']}：{row.get('reason') or '尚未安排'}")
            continue
        slot = slot_lookup.get(row.get("availability_id"))
        if not slot:
            continue
        with st.container(border=True):
            st.write("**" + ("✦ AI 建議 · " if task.get("source") == "ai_confirmed" else "")
                     + task["title"] + "**")
            st.caption(f"{slot['date']} {slot['start_time']} · "
                       f"{task['estimated_minutes']} 分鐘 · "
                       f"{'手動安排' if row.get('source') == 'manual' else '自動安排'}")
            if row.get("class_override"):
                st.warning(f"覆蓋課程：{row['class_override']}（僅本人紀錄，未通知學校）")
            try:
                beginning, ending = task_calendar_event(task, slot)
                st.link_button("加入 Google Calendar",
                               google_calendar_url("讀書｜" + task["title"],
                                                   beginning, ending))
                if beginning > today:
                    if st.button("移回待排", key=f"cp_unplan_{task['task_id']}"):
                        saved(lambda task_id=task["task_id"]:
                              unassign_task(USER_ID, task_id, today), "已移回待排")
            except (ValueError, KeyError):
                st.caption("此排程時間格式不完整，無法產生單一行事曆連結。")
    st.caption("整體匯出請在「連接與匯出」下載 .ics。匯入手機後不是即時同步。")


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
