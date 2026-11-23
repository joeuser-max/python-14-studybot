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
