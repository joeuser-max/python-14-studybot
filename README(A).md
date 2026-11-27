# ClassPulse｜A 組員：蕭博軒

本文件說明已整合至 `joeuser-max/python-14-studybot` 的 A 模組。B 組員（莊育哲）負責 `scheduler.py`、`line_bot.py`、`reminder_worker.py`；兩人的程式已在同一個 Repository，完整部署仍須驗收。

## A 模組及實際用途

| 檔案 | 職責 |
| --- | --- |
| `app.py` | Streamlit 課表、可用讀書時段、任務狀態、排程、LINE 提醒設定與 Markdown 匯出 |
| `storage.py` | JSON 驗證、檔案鎖、原子寫入與筆記去重 |
| `tracker.py` | 課後回覆率、任務進度統計 |
| `exporter.py` | 匯出課表、Deadline、排程、回饋與統計為 Markdown |
| `ai_assistant.py` | 透過 OpenAI Responses API 的 Structured Outputs 整理課後筆記與複習建議 |
| `plan_bridge.py` | 將 B 的排程結果轉為 A 的使用者資料格式 |

## 排程與資料的整合方式

- `scheduler.make_plan(tasks, availability, previous_plan, now)` 回傳 `{"plan": [...], "new_alerts": [...]}`，不是單純的清單。`plan_bridge.normalize_plan_result()` 負責擷取排程並補上 `user_id`。
- `storage.load_json()`、`storage.update_json()` 共用 `data/` 資料路徑與檔案鎖。LINE 筆記使用 `storage.save_feedback()` 去重。
- LINE 補筆記流程只在使用者提供讀書分鐘數、Deadline 並選定時段後才建立任務；Worker 於排定時段開始時才整理並傳送已同意 AI 的來源筆記。
- `line_bot.py` 已有星期／時段／課名／筆記的文字式流程。真正的 LINE 推送、HTTPS Webhook、API 金鑰仍須實際部署測試。

## 本機啟動與測試

使用 Python 3.11 以上。安裝依賴後，以 `python -m streamlit run app.py` 啟動介面，使用 `python -m pytest -q` 執行離線測試。LINE Webhook 與常駐 Worker 的執行方式見主 [README](README.md)。

AI API 是 MVP 的可選整合介面，但不要求每次展示都連上外部模型。需設定私有 `OPENAI_API_KEY`、`OPENAI_MODEL`，並由使用者明確同意；只在關聯任務的讀書時段開始時呼叫。未設定金鑰仍可以 Markdown 匯出或測試替身（Mock）驗證介面；不能把 Mock 當成真正的 API 回應。

## Git 協作慣例

1. 先同步最新 `main`：`git switch main`、`git pull origin main`。
2. 建立 `feature/...` 或 `chore/...` 分支，不直接修改 `main`。
3. 提交前測試；Commit 訊息以**繁體中文**寫明具體變更，如 `修正：避免 LINE 提醒重送時覆蓋資料`。
4. Push 分支並建立 Pull Request，審查後才合併。

## 限制

目前採單一測試使用者 `demo_user_001`，不是正式多人帳號服務。單機 JSON 檔案鎖不保證跨機一致性。真正 LINE、AI API、長時間 Worker 運作仍須部署驗收。
