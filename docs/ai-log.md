# AI 協作紀錄

本功能依規格書實作讀書排程、提醒 Worker 與 LINE Webhook。
主要採用人為確認的規則式演算法，不呼叫生成式 AI API。

## 2026-11-27：七日規劃板與第二階段 AI

- AI 參與架構設計：將使用者手動意圖與全體自動排程分成獨立操作，不再由一個拖放觸發整份計畫。
- AI 參與開發與驗證：建立七日十六節可雙向互動元件、ICS 外部事件讀寫、LINE 回報不重排、匿名訓練檔交換與 Mock API 回歸測試。
- 產品內的第二種 AI API：`study_coach.py` 支援 Gemini 2.5 Flash-Lite。模型只提出適配訓練模板的候選節次，程式驗證 task_id、期限、衝突，使用者確認才寫入。`GEMINI_API_KEY` 不提交 Git。
- 免費模型可能有額度、地區及資料使用條款限制；未經同意不傳送資料，測試使用 Mock 回應，不虛構真實 Gemini API 成功。
- 完成率、LINE 回覆率及 Focus XP 只是使用者自述／事件紀錄，可能被灌水；因此**不**宣稱防作弊 Elo 或真實 NCU 同校排行榜。
- 同學可自願互換不含課名、個別事件和 LINE ID 的匿名習慣模板；現版未建立需身份驗證的群組社交網路。
- 詳細 API 契約與 MVP／正式部署界線見 [V2 架構說明](architecture-v2.md)。

## 2026-11-28：第一次 Final 整合與原作者貢獻追溯

- Golden Baseline 嚴格固定於 PR #16 head `be687f7b96019744bdf10b9e6a4cecd0df562ab5`；由於 `main` 已與 V2 分岔，沒有直接 merge/main reset，另開整合 PR #17 以 V2 分支為目標。
- 組員莊育哲（joeuser-max）的真實貢獻：LINE 檔案附件接收與擷取、PDF 保存、Webhook 與提醒回報、課後 AI 筆記摘要、剩餘分鐘重排概念。原始參考 commit `1ef63c8e7d98d344bc7297ac744706f2a59608ec`，此處為**選擇性移植**，不將其程式宣稱為新發明。
- 自己提出並落實的新需求：V2 畫筆式綠色 Availability∩Preference；綠色是**Soft Preference**，不是 Hard Constraint。用戶點一鍵才開啟偏好畫筆、確認後才填滿，其他可用空檔仍可後備；單日排程密度納入次順位評分，不宣稱全域最佳化。
- 整合時辨認的**相容性風險**：組員 Legacy Scheduler 會在 LINE 進度回報時重排全部任務，與 V2「手動固定不動」矛盾；修正為僅處理被回報的任務。這屬新版本行為差異，不應籠統稱原作者的產品規格為 Bug。
- 整合時辨認的**搜尋契約差異**：原 V2 搜尋筆記函式只比對標籤；LINE 自然語言「搜尋」也需比對全文，因此專為 LINE 新增正文搜尋，不破壞既有網頁搜尋方式。
- 新增「筆記 <內容>」「查看筆記」「搜尋 <關鍵字>」LINE-first 入口，未分類筆記不擅自推定課程或自動更改日曆；沒有 OCR，不接受照片當成已辨識課表。
- 修正 AI 任務接受後的行為：在 V2 中只新增待排；直到使用者手動拖排或明確確認綠色一鍵安排，才寫入 schedule。
- AI 課後整理只有明確同意且具有效 OpenAI API 設定時才可呼叫；真實 LINE 外部服務尚未完成實際端到端驗收，不以 Mock 測試冒充已通。
- 相容性及測試見 `tests/test_schedule_preferences.py`、`tests/test_line_document_integration.py`、`tests/test_line_final_integration.py`、`scripts/ui_smoke.py`；完整功能、責任、貢獻與糾錯分類見 `docs/final-integration-1-audit.md`。
