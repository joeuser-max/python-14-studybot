# ClassPulse：實際功能與測試落差審查

核查日期：2026-11-27。比較對象為 `main` 與尚未合併的 PR #9（任務編輯修正）。本文件根據程式原始碼、測試、GitHub Actions 執行紀錄；**不是正式環境的實機驗收**。

## 判斷準則

- **功能已實作**：Repository 中存在會被真正呼叫的程式路徑，而非僅 UI 文案或規格描述。
- **離線已驗證**：測試有執行對應邏輯並檢查結果（含 Mock、Flask test_client、Streamlit AppTest）。
- **實際已驗證**：以真實瀏覽器與外部服務憑證，走完使用者預期的端到端操作。
- **目前未證實**不能等同於功能失敗；沒有對外服務可用性的證據時，就不能宣稱已部署成功。

## 版本與 CI 基準

- `main` 最新被核查提交：`86d8bed01`；`main` GitHub Actions run [45854661637](https://github.com/joeuser-max/python-14-studybot/actions/runs/45854661637) **失敗**，58 個測試結果為 **56 passed、2 failed**。
- 兩個失敗：`test_demo_task_edit_from_streamlit_card_uses_demo_json`（任務看得到但修改後未寫入展示 JSON）；`test_mock_ai_suggestions_reference_feedback_without_api`（新增回饋範例後，測試仍誤把清單第一筆當作最新筆記）。
- [PR #9](https://github.com/joeuser-max/python-14-studybot/pull/9) 的 CI [45855008564](https://github.com/joeuser-max/python-14-studybot/actions/runs/45855008564) 為 **60 passed**，但目前尚未合併到 `main`。其中修改成功由可測試的儲存服務驗證；`st.dialog` 真實瀏覽器按「儲存」仍待人工驗收。
- CI 定義於 [tests.yml](../.github/workflows/tests.yml)：Python 3.11、`pytest`、語法 `compileall`、Streamlit **HTTP health check**，並無 Playwright/Selenium 真實瀏覽器，也沒有外部 LINE/OpenAI API 金鑰下的整合測試。
- **沒有**使用 `pytest-cov` 或其他分支覆蓋率儀表；因此不能負責任地報告「程式碼覆蓋率 XX%」。測試數量不等於功能覆蓋率。

## 功能－測試－真實使用落差表

| 使用者能力 | Repository 已有實作 | 現有測試範圍 | 未驗證／實際落差 | 判斷 |
|---|---|---|---|---|
| 初次設定與側欄 Dashboard | `app.py` 的五步引導、跳過和多頁導航 | `test_streamlit_smoke.py` 以 AppTest 開啟頁面／切換 Demo | 未在實際 Chrome、Safari、手機逐步填完表單驗收 | **部分驗證** |
| 建立及修改任務（含百分比／刪除） | `app.py` 對話框、`storage.update_task`；PR #9 加入獨立 `task_actions.py` | 主線儲存函式單測通過；**main 的 AppTest 提交驗證失敗**。PR #9 的新建／修改／刪除服務測試通過 | 實際 `st.dialog` 點擊「儲存」尚未由真實瀏覽器驗證 | **P0：main 已知問題** |
| 修改課程與可用時段 | `course_dialog`、`slot_dialog`、storage CRUD | `test_storage_editing.py` 涵蓋更新、重疊、刪除和跨用戶約束 | 沒有逐一驗證 dialog 的「修改／刪除 → 畫面刷新 → 儲存值」 | **部分驗證** |
| Greedy 排程、Deadline、固定時段及未排入原因 | `scheduler.make_plan` + `plan_bridge` | `test_scheduler.py`、`test_ab_integration.py` 測規則、提醒重試 | `make_plan` 的輸入沒有每週 `events` 課表；可用時段檢查只比對其他 availability，**不能保證不撞課**。無真實時間跨日完整驗收 | **核心算法驗證／跨課表仍有設計缺口** |
| 同日同課合併筆記 | `app.py` 依 `(class_date,event_id)` 群組顯示，保留原始筆記 | 展示資料與分組鍵檢查、feedback JSON 去重測試 | 尚未自動驗證真實瀏覽器中的展開、順序和多次 LINE 回覆同步呈現 | **部分驗證** |
| 展示資料與正式資料隔離 | `storage.py` ContextVar + `demo_data.py` | `test_demo_mode.py` 與 PR #9 的跨目錄讀寫測試 | 原本對話框 fragment 路徑遺失已造成實際錯誤；多 Session／多執行緒未做壓力測試 | **核心驗證，但有 UI 風險** |
| LINE 08:00–21:00 三選一展示 | `day_demo.py` 13 個固定場景，狀態儲存在 Streamlit session | `test_day_demo.py` 檢查時序、三選一與不同結果；AppTest 點選第一場 | 場景**不是**由實際 Scheduler、LINE Bot、AI 即時運算；不會真正寫入任務。若說成完整端到端實作會誤導 | **可展示的模擬流程** |
| 真正 LINE 接收與課後補筆記 | `line_bot.py` Flask Webhook、簽章、綁定、階段式回覆 | Flask `test_client`、簽章、ID 去重、筆記儲存與確認流程 | 沒有公開 HTTPS Webhook、真實 LINE 帳號來回、Token 有效性驗證 | **模擬驗證／未實機部署** |
| 真正 LINE 定時提醒 | `reminder_worker.py` + `scheduler.get_due_*` | Mock Push 成功／失敗、retry key、偏好開關 | 未測 LINE 官方服務真實送達／重送；兩個 Worker 並行及跨檔案交易沒有 exactly-once 保證 | **模擬驗證／可靠性界線** |
| AI Model API 分析與確認任務 | `ai_assistant.py` 真實 Responses API HTTP 呼叫、Structured Outputs 驗證；`line_bot.py` 人工確認 | `test_ai_assistant.py` monkeypatch `urlopen`；`test_ab_integration.py` 模擬分析結果 | 尚未驗證真實 OpenAI 回傳、模型版本／額度／延遲；不能將 Mock 回應當成模型執行成功 | **API 介面可測／未實際連外** |
| Google／Apple 行事曆 | `calendar_export.py` 產出 `.ics`，Google Calendar 預填事件連結 | `test_calendar_export.py` 檢查 ICS 字串、時區與 URL 參數 | 尚未在 Google Calendar 或 iPhone 實際匯入驗收；沒有 OAuth、刪改同步或雙向更新 | **單向匯出已驗證／同步未實作** |
| 課表截圖上傳 | `app.py` file uploader + 圖片預覽 | 無專項圖片上傳互動／檔案解析測試 | **不會 OCR 或 AI 轉課表**；只是在 UI 顯示截圖 | **展示預覽** |
| Markdown 匯出 | `exporter.py` 生成課表／任務／回饋文字 | `test_ab_integration.py`、`test_demo_mode.py` 有生成內容斷言 | 尚未測手機下載／其他 Markdown 工具讀入 | **離線邏輯已驗證** |
| 個人登入、雲端同步、多人權限 | 使用 `demo_user_001`，本機 JSON 檔案 | 有少量跨 `user_id` 資料隔離單測 | 無正式登入、資料庫、手機雲同步與安全部署；**不應稱為可公開提供多人使用的服務** | **MVP 範圍外** |

## 落差的真正大小

這是**產品驗收層級**而不是百分比估算：

1. **資料／演算法層：較接近可執行 MVP**。JSON CRUD、Greedy 排程、LINE 簽章、Mock AI 格式、ICS 字串都已有實際可呼叫邏輯及單元／整合測試。
2. **Web 互動層：有中等至顯著缺口**。頁面會渲染、按鈕可見，卻已發生一次「任務按儲存未成功」的實例；其他 dialog 的實際提交亦未逐一走完。這是目前 Demo 的最高風險。
3. **外部整合層：尚未做實機驗收**。LINE / OpenAI / 手機行事曆的「模擬或介面存在」不等於真實發送、模型完成推理或同步成功。就助教要求，可誠實將其列為 API-ready / Mock-first。
4. **部署／可靠性層：尚非正式服務**。沒有自動真實瀏覽器 E2E、壓力測試、多人認證或外部服務 SLA。

## 按優先序處理（避免繼續增加功能）

**P0 — 先修復再 Demo**

- 合併前確認 PR #9 具備成功 CI，且實際瀏覽器「新建 → 編輯 → 儲存 → 重新整理 → 再編輯 → 刪除」可在正式／展示模式都成功。不要只看 AppTest 是否能打開 dialog。
- 在正常模式做一次完整 Streamlit 手動驗收，確認任務、課程、時段的修改都真正進入 JSON，沒有跨模式覆寫。

**P1 — 檢查核心閉環是否與情境吻合**

- 準備同時有課程、任務與可用時段的真實測試案例，確認 Scheduler 不把讀書排到實際上課期間；必要時將課表衝突也納入排程規則。
- LINE 的「補筆記 → 1–5 自評 → AI Mock → 使用者確認 → 任務排程」用同一組 JSON 串起來驗收，而非只切換虛擬對話場景。
- 逐步完成新增／修改／刪除課程與時段，驗證重整後狀態是否持久。

**P2 — 可以留作展示限制**

- 手機實際匯入一次 `.ics`，錄影展示；清楚說明單向匯出。
- 保留課表截圖預覽，不要宣稱已辨識圖片。外部 API 無金鑰時以標示清楚的 Mock 取代。
- 如果要報出「測試覆蓋率」，先加入 `pytest-cov` 並配置實際覆蓋範圍，避免拿測試筆數當作覆蓋率。

## 建議的 Demo 驗收腳本（人工逐步確認）

1. 開啟展示模式 → 確認三門預設課及預設任務。
2. 在「我的任務」點某張卡片 → 修改名稱與完成度 → 儲存 → 重新整理，確認變更仍在。
3. 新建任務 → 立即修改 → 刪除，確認沒有「找不到要修改的任務」。
4. 修改課程與可用時段 → 按重新排程 → 確認日期／時間／未排入原因合理。
5. 在「學習回饋」確認同日同課兩則筆記合併顯示，原始內容都保留。
6. 執行 LINE 一日展示，刻意拒絕一次 AI 建議，確認系統**不虛構已排入任務**。
7. 再走一次接受 AI 建議的路徑，說明這是固定情境 Mock，不是真實模型計算。
8. 匯出 Markdown／ICS，於 Mac／手機行事曆實際匯入其中一份，並確認時區。

## 核查來源

- [app.py](../app.py)、[storage.py](../storage.py)、[scheduler.py](../scheduler.py)、[line_bot.py](../line_bot.py)、[reminder_worker.py](../reminder_worker.py)、[ai_assistant.py](../ai_assistant.py)
- [day_demo.py](../day_demo.py)、[calendar_export.py](../calendar_export.py)、[demo_data.py](../demo_data.py)
- [tests/](../tests/)、[GitHub Actions](../.github/workflows/tests.yml)
- [PR #9：任務寫入修正與測試](https://github.com/joeuser-max/python-14-studybot/pull/9)

**結論：** ClassPulse 現在有可運作的主要程式骨架，但不能把 Mock 與 AppTest 通過等同於已完成真實使用者流程。最划算的下一步是補真正的編輯／保存 E2E、課表撞時段檢查，及對外部服務清楚定義可驗收的界線，而不是再堆更多頁面。
