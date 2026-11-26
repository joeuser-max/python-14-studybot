# ClassPulse｜學習助理控制台

ClassPulse 將課後筆記、AI 建議、讀書任務和時間安排連成一條流程。**LINE 是日常互動入口；AI Model API 負責筆記分析；Streamlit 是設定與管理控制台；Google／Apple Calendar 用於手機查看。**

這是第 14 組 Python 課程的可執行 MVP，不是正式上線的多人 SaaS。

## 快速啟動網站

需 Python 3.11 以上。先 Clone 專案，在專案根目錄執行：

### macOS／Linux

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

### Windows PowerShell

    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

開啟 http://localhost:8501 即可進入網頁。尚無 LINE 或 OpenAI 憑證也可以使用一般控制台及模擬展示。

## 使用者流程

1. **首次引導**：認識產品 → 新增課程／課表截圖預覽 → LINE 說明 → 新增任務與可用時段 → 外部行事曆。每一步可略過，完成後才出現全部側欄。
2. **總覽**：顯示待辦、課程數及已排入任務。避免一次展示所有表單。
3. **我的任務**：直接點擊卡片編輯名稱、期限、預估時間、0–100% 進度或完成勾選，也可刪除。
4. **時間規劃**：點課程或可用時段卡片直接修改。Scheduler 依 Deadline、時段容量及衝突規則排程。
5. **學習回饋**：相同 (課程 ID, 課程日期) 的多則筆記合併顯示；原始筆記與 ID 保留。
6. **AI 助理**：只有在使用者明確同意後才嘗試呼叫 OpenAI；AI 建議需要再次確認才寫入任務。
7. **連接與匯出**：調整 LINE 提醒偏好，下載 .ics 和 Markdown，或為單一任務開啟 Google Calendar 新增事件畫面。

## 附加展示：LINE 從 08:00 到 21:00 的一天

側欄「LINE 一日展示」不需要 LINE API Key、Webhook 或 OpenAI API Key。它有 **13 個依時間排序的場景**，每個場景提供 **3 個預設訊息選項**，按下後立即顯示相應的 LINE 虛擬回覆，不必輸入文字。可逐段繼續、一鍵播放完整一天，或重播。

包含：08:00 早晨規劃 → 課前提醒 → 課程 → 課後理解度 → 補筆記 → Mock AI 分析 → 使用者確認任務 → 規則式排程 → 無法排入提醒 → 手機行事曆 → 19:00 讀書提醒 → 任務完成度 → 21:00 當日回顧。

虛擬引擎追蹤當天的理解度、筆記、是否接受 AI 任務、排程選項及進度，以免拒絕任務後卻顯示已完成安排。**這些都是模擬選擇；絕不對外發送 LINE、不呼叫模型、不覆寫正式任務或資料。**

## 展示模式資料

在側欄打開「展示模式」會載入獨立資料夾 .classpulse-demo-data/，包含**虛構範例課表**、任務、回饋與進度。可直接修改或按「還原展示資料」。切回一般模式不受影響。使用者實際課表需收到資料後再手動替換，**目前不宣稱已完成 OCR 辨識**。

## 外部行事曆

- 下載 **classpulse.ics**：包含接下來 12 週的固定課程，以及已排入、未完成的讀書任務。Google 或 Apple Calendar 可匯入檔案。
- 點擊排程卡片的「新增到 Google Calendar」：在 Google Calendar 預填事件，使用者自行確認後才新增。
- **目前是單向匯出**，不是 OAuth 授權或雙向同步。日後修改任務必須重新匯入，避免對使用者宣稱自動更新。

## 真正的 LINE／AI 模組

要測試真實 LINE：在私有環境設定 LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN、LINE_BINDING_CODE，並提供安全、公開的 HTTPS Webhook URL；在另外兩個終端執行：

    python -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000
    python reminder_worker.py

AI API 使用 OPENAI_API_KEY 與 OPENAI_MODEL；可使用正式 Responses API 及 JSON Schema 解析結果。沒有金鑰時可以驗證 Mock 測試，但**Mock 不等於真實 API 呼叫成功**。密鑰、真實課表與個人筆記不應提交 GitHub。

## 測試與 Git 協作

    python -m pytest -q

GitHub Actions 另做 Python 語法檢查、Streamlit HTTP 啟動檢查和 Streamlit AppTest。HTTP 啟動成功不代表每個 UI 互動都已經由真人逐項驗收。

分工以 **README(A).md**、**README(B).md** 及 GitHub Commit 歷史為準。莊育哲負責的 Scheduler 與原始 LINE 功能仍保留原作者；蕭博軒的管理介面、資料整合、行事曆匯出、LINE 一日虛擬展示及測試使用 Onlynotonly 提交。遵循最新 main → 獨立 feature branch → 測試 → PR → 審查後合併，不直接推送 main。
