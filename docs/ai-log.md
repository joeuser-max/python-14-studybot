# AI 協作紀錄

## AI 功能從構想到實作

原始 MVP 定位為 JSON 轉 Markdown 的 AI-ready 資料匯出。助教指出 AI 應用比例不足後，A 組員新增可選的 AI Feedback-to-Action：透過 OpenAI Responses API 的 Structured Outputs，將學習筆記轉成具原始 source_feedback_id 的建議，並由使用者確認才能加入任務。規則式 Greedy 排程器不是 AI。

## AI 協助工程整合

- 檢視並比對 Streamlit、Scheduler、LINE Worker、Webhook 與 JSON storage 的介面。
- 修正讀書提醒 retry 分支在 start 賦值前使用的錯誤。
- LINE Webhook 依正式 source.userId 讀取 ID，增加一次性綁定碼、星期與時段選擇、同時段課名消歧及補筆記狀態。
- 透過 storage.save_feedback 做筆記驗證及去重，避免重送增加重複筆記。
- 增加離線回歸測試；模擬的 LINE Push 不標記為成功。

## 人為判斷與風險

- LLM 僅負責學習筆記語意分析，不直接改動排程，學生自行核准任務。
- 真實 LINE Webhook、外部 AI 憑證、HTTPS 與 Worker 持續運行需要部署驗收。
- JSON 的檔案鎖不保證跨多檔案交易；Worker 仍有讀改寫併發風險。

以上記錄實際的工程修正與選擇理由，不虛構逐字 AI 對話。

## 2026-11-26：A/B 分支整合與貢獻歸屬

- **莊育哲（B）原始貢獻**：`btesting` 三筆 Commit 新增週／月／日行事曆、LINE 課後 1–5 自評與筆記、直接呼叫 AI 後整理摘要／建議，以及使用者在 LINE 確認後新增任務並重新排程。這些 Commit 透過雙親合併保留原作者資訊。
- **蕭博軒（A）整合貢獻**：從最新 `main` 建立 `feature/onlynotonly-integrate-btesting`，執行雙親 Merge Commit，將主線 CI、原有安全修正與 B 的新增功能合併；修復 LINE 提醒 Retry Key 更新、避免既有 LINE 帳號被覆綁、遷移新版 LINE 互動回歸測試，補充網頁啟動與 CI 驗證。
- **驗收方法**：CI 使用 `pytest` 執行模擬的 LINE Webhook 與 AI HTTP 回應測試，另外檢查 Streamlit 啟動及 Python 語法；此測試不保證 UI 全部互動或外部 API 真正送達。
- **工程限制**：單一測試使用者、JSON 檔案鎖、LINE Messaging API 金鑰及公開 HTTPS Tunnel 的部署仍需要實機驗證。合併工作以 PR 審查，不直接修改 `main`。

**歸屬原則：**合併程式碼不等於重新發明 B 的功能；Git 歷史與文件應區分 B 的原始功能提交和 A 的整合、修復與驗證提交。

## 2026-11-26：展示模式功能與驗證（蕭博軒／Onlynotonly）

- 移除 Streamlit 網頁頂部的組員分工字樣，保留 ClassPulse 產品標題。
- 加入可切換的展示模式；使用 Python ContextVar 指向本機隔離資料夾 `.classpulse-demo-data/`，避免 Streamlit 展示操作寫入正常模式的 JSON。
- 建立虛構且可編輯的課表、任務、回饋及提醒範例。加入清楚標示的「重設展示資料」，不覆寫一般模式資料。
- 課表設定加入圖片上傳與預覽（僅展示，不宣稱已完成 OCR／AI 解析）。
- LINE 通知設定可在展示資料中切換，並模擬選課、課後提醒及使用者自評／筆記；不對 LINE 發送訊息。
- AI 頁面加入 Mock 建議（固定規則，不冒稱真實模型回應），由使用者確認才能新增示範任務。
- 新增隔離、資料重設、筆記 ID 引用及完整展示用戶路徑回歸測試；GitHub Actions 驗證 43 個 Python 測試以及 Streamlit HTTP 服務啟動。

使用者的正式課表尚未提供，因此目前的三門課均為**虛構展示資料**，不得標成個人的實際選課。

## 2026-11-26：引導式控制台及 LINE 全天模擬（Onlynotonly）

- 將 Streamlit 原始 Tab 表單整合為首次使用引導（每步可略過）與側欄 Dashboard；新 UI 保留既有 JSON Storage / Scheduler / LINE Webhook / AI Model API 模組接口。
- 實作任務與時段卡片點擊後的編輯視窗、0–100% 任務進度以及同日同課的筆記群組顯示。
- 提供單向 .ics（Google / Apple Calendar）與 Google Calendar 新增事件連結；不宣稱具有 OAuth 雙向同步功能。
- 實作 08:00–21:00 LINE 虛擬情境：13 個場景，每一場三個固定回覆選項，保留回覆紀錄、理解度、是否接受 AI 任務、排程選擇與讀書進度。拒絕 AI 建議不應被模擬為已排程。
- 延續現有 demo_data.py 的獨立展示資料，絕不傳送真實 LINE／AI 請求；Mock 分析清楚標示非實際模型輸出。
- 針對純 Python 模擬引擎、ICS 時區、Streamlit 側欄逐頁導航及虛擬選項操作新增回歸測試。自動測試證明程式行為，但不能代替真人驗收全部視覺細節。
- 此次新增工作由蕭博軒／Onlynotonly 提交於獨立 PR #6；B 組員莊育哲先前的排程與真實 LINE 功能提交未被冒用。
