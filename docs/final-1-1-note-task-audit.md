# Final 1.1 審核紀錄：來源筆記 → AI／規則候選 → 紫色任務

**界線：**此 PR #18 的目標是 V2 功能分支 `feature/rich-demo-fixtures`，不是已與 V2 分岔的 `main`。不覆寫莊育哲原有 LINE 模組，也不導入其 Streamlit UI／舊時段勾選頁。以已驗收的 V2/Final 1 為基準。

## 已實作（對照需求與問題）

| 問題或新需求 | 實際處理、判斷邊界 | 驗證 |
|---|---|---|
| AI 建議原在「Markdown 與 AI」，且為每份紀錄單一任務 | 移至「任務管理」，一則筆記的每個「？」／疑問標籤／既有 AI `unresolved_questions` 形成獨立候選，不把模型結果直接寫 `tasks.json` | `tests/test_note_task_lifecycle.py`、Playwright |
| AI 任務沒有正確顏色及來源追溯 | 候選保留 `source_feedback_id`、`source_question_key`、`source_question`、`source_event_id`；使用者逐項確認才建立。紫色 `#8356C4` 用於待排、已排、日／週／月行事曆 | 單元／瀏覽器回歸 |
| AI 原用 45 分鐘、課後七天、模型 topic 作科目 | 新疑問任務**預設30分鐘**，科目讀取來源課程 event_id 指向的課名，精確 `deadline_at` 設下次上課開始前（仍保留 `deadline` 日期兼容 Legacy）；來源是未分類 LINE Inbox 時先請使用者指定課程，不由模型猜測 | 來源／期限／分類測試 |
| V2 一小時格造成30分鐘任務占滿60分鐘 | 保留每天 16 節校內節次視覺標籤，資料與 Grid 實際可切 30 分鐘。新增 `1+` 等半小時時點；`scheduled_minutes`、PDF/ICS 活動衝突與時程比較依真實分鐘驗證 | 30分鐘前後相鄰任務、衝突測試 |
| 已排方塊只能移動，不能直接伸縮 | 七日已排任務增加底部把手 30min 伸縮；後端 `resize_scheduled` 先驗證新區間的衝突、Deadline、限制，再只更新該任務及 slot/plan；不動其他手排 | 排程測試／實際 Chromium 拖曳 |
| 拖到原本已占用時段缺乏通知 | 前端 drop 到 study/external 時有可見錯誤，後端不合法修改被 `DataError` 阻止並在日曆板錯誤列顯示 | 後端衝突回歸 |
| 筆記選單冗長 | 依課程名稱 pills → 學期週次 pills → 該週筆記，保留獨立主題標籤搜尋。學期開始日由使用者在進階設定決定；未分類 LINE 筆記需指定來源後計算 Deadline | UI 回歸 |
| 設定占用主畫面、舊 LINE 時間軸與快速填寫曝光 | 課表／課表照片預覽／LINE 開關／學期週次收進展開的進階設定；舊 LINE 工具預設隱藏但程式保留，LINE 主 Mock 聊天泡泡維持 | Playwright |
| K 書中心／ee-class 不見 | 恢復 NCU 正式快捷網址為頂端常駐按鈕 | UI |
| 課後疑問行動是否真實模型生成不透明 | Demo 明確標示「規則候選」，真實 OpenAI 需逐次勾選同意；一次最多32疑問，分批8個，Structured Outputs 逐題核對來源 `source_question_key`，不得少題、重複或亂生 key；模型不自行設定課程／Deadline，也不直接寫時程 | `tests/test_note_task_lifecycle.py` mock model |
| LINE 互動需跟莊育哲原功能對接 | 保留組員已完成的 LINE HMAC Webhook、綁定、TXT/DOCX/PDF 擷取、重試鍵與 Worker；課後 AI 的 `unresolved_questions` 改為逐題詢問是否新增30分鐘紫色任務，不採用其網頁或 Legacy 全表重排 | `tests/test_line_signed_api_contract.py` 與 `tests/test_ab_integration.py` |

## 原作者貢獻及真實糾錯

1. 莊育哲（`joeuser-max`）原本 LINE Webhook、訊息處理、綁定、PDF/DOCX/TXT 擷取、提醒 Worker、課後 OpenAI 結構化整理與進度回報是本次沿用的重要後端。參考源 commit `1ef63c8e7d98d344bc7297ac744706f2a59608ec`，移植歷史見 `docs/final-integration-1-audit.md`。**不能把原本功能算成本次重新發明。**
2. 本次修正的是 V2 整合後的契約差異：筆記一對多疑問任務、分鐘級 Deadline 與 30 分鐘格、相同問題多次確認不重複、前端日曆不覆蓋原排程、LINE 不回退 Legacy 全表重新計算。應標明為新需求導致的改動，不可將隊友不同規格一概稱作既有 Bug。
3. 實際查出的缺口：原 V2 將 Markdown/AI 分在任務管理以外、沒有已排伸縮、沒有對使用者顯示衝突，AI 任務預設分鐘和排程實際占格不符。PR 提交分檔繁體中文 commit 保留原因與修正。
4. **目前 JSON 多檔案不是資料庫交易**，即使先驗證再寫入，也尚不保證多個並行程序的完全原子一致性；真正多人雲端版要遷移共用 DB。

## 測試證據的正確表述

- Python tests + Playwright Chromium 覆蓋已驗收的 V2 七日與日週月、豐富 Demo、LINE Mock 對話、逐題紫色卡顯示和已排卡半小時伸縮。
- 對 LINE 的測試會對真實 Flask `/webhook` 路徑建立 **有效與無效簽章測試請求**，檢查綁定、文字／檔案訊息（下載內容以 Mock 代替）、Webhook 去重、筆記搜尋／隔離、AI 逐題選擇、Push 格式／Retry Key（HTTP Mock）。
- **沒有正式 LINE Channel Secret/Access Token、公開 HTTPS Webhook、真實手機與 API Key，不能宣稱對外實際推播、真實模型請求或正式部署成功**。外部驗收步驟見 README 5.1–5.7，使用者自行保管憑證。
- 負責任 AI：有明確 consent 才送出待釐清問題、科目及必要筆記短摘錄到 OpenAI；不送 LINE User ID，未經使用者接受一律不寫入任務或日曆。Gemini Coach 仍屬 V2 既有可選功能，不刪匿名同儕 JSON。

## 不在這次範圍

課表圖片 OCR／AI 看圖、完整多用戶身份安全、正式雲端資料庫、LINE → Web 的安全登入連結、掃描型 PDF OCR、真實 LINE Push 電信／網路送達保證，均未宣稱完成。
