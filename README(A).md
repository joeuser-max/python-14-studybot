# ClassPulse｜蕭博軒（A）負責功能

主動學習回饋／進度追蹤工具的 **A 組員程式**。此套件不冒充已完成的 LINE Bot 或排程器。LINE Webhook、主動提醒與排程由 B（莊育哲）負責。

## A 已完成的模組

| 檔案 | 功能 |
|---|---|
| `app.py` | Streamlit 課表、讀書時段、任務、狀態、回饋、Markdown 下載與 AI 建議確認畫面 |
| `storage.py` | JSON 驗證、安全讀寫、檔案鎖、筆記去重（同檔原子更新） |
| `tracker.py` | 課後提醒回覆率、明確任務完成數的計算 |
| `exporter.py` | 將課程、任務、排程、筆記、時間戳記匯出為 UTF-8 Markdown；基本個資遮蔽 |
| `ai_assistant.py` | 透過 OpenAI Responses API 把學習筆記轉成有來源 ID 的待確認複習建議 |
| `tests/` | 可離線執行的自動測試 |

## 本機執行

需要 Python 3.11 以上。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**不設定 OpenAI API Key**，仍可使用課表、任務、統計與 Markdown 匯出；只有真正按下「分析學習紀錄」才會呼叫外部模型。模型無法連線時會顯示錯誤，不修改資料。

要啟用 AI 分析，請在自己的電腦設定 `OPENAI_API_KEY` 與 `OPENAI_MODEL` 環境變數（`.env.example` 只提供範本，程式不會自行載入 `.env`），使用支援 Structured Outputs 的模型。勿把真正的 Key 放進程式、截圖或 GitHub。

```bash
# PowerShell 示例（填自己的值；不要提交）
$env:OPENAI_API_KEY="你的私有金鑰"
$env:OPENAI_MODEL="你可使用的支援結構化輸出模型名稱"
streamlit run app.py
```

## A 與 B 整合介面

B 端新增以下檔案，不要在 A 的 `app.py` 中複製另一份排程邏輯：

- `scheduler.py`：提供 `make_plan(tasks, availability, previous_plan, now) -> list[dict]`；或回傳 `(list[dict], alert_list)`，其中每筆 plan 至少包含 `user_id`、`task_id`、`availability_id`、`status`、`source`、`reason`。
- `reminder_worker.py`：獨立常駐執行，更新 `data/reminders.json`。提醒狀態 `sent` 僅代表 API 接受，不代表已讀。
- `line_bot.py`：驗證 LINE Webhook 後，將完整筆記 dict 傳給 `storage.save_feedback(feedback)`。B 必須將已綁定的 LINE 使用者對應到本期固定 `demo_user_001`。`webhook_event_id` 必填，同一 ID 的重送會返回 `False`，不增加第二筆。
- `app.py` 不會在網頁開啟時自動發送 LINE，避免重新整理造成重複訊息。

**提醒：** 只要 Streamlit、Webhook、Worker 共用同一個檔案系統，`storage.py` 的 `filelock` 可以保護同檔案讀改寫；若程式部署在不同機器或雲端無共享檔案系統，不能使用此 JSON 方案保證跨機一致性，需改用資料庫或集中儲存服務。

## Git 協作與提交建議

建議在自己的功能分支執行（範例分支名稱 `feature/hsiao-data-ai`）：

```bash
git clone https://github.com/joeuser-max/python-14-studybot.git
cd python-14-studybot
git switch -c feature/hsiao-data-ai
# 複製此套件檔案到 repo；請確認並保留 B 已修改的檔案
git status
git add storage.py tracker.py tests/test_storage.py
git commit -m "feat: add safe JSON storage and learning statistics"
git add exporter.py tests/test_tracker_exporter_ai.py
git commit -m "feat: export structured learning records with tests"
git add ai_assistant.py
git commit -m "feat: extract AI review tasks with source validation"
git add app.py README(A).md requirements.txt .gitignore .env.example docs/ai-log.md
git commit -m "feat: add Streamlit UI and integration documentation"
git push -u origin feature/hsiao-data-ai
```

推送後以 Pull Request 併回 `main`。**若你沒有該 Repository 的寫入權限，push 會失敗**，請由 repo 擁有者邀請你的 GitHub 帳號作為 collaborator，或連結具有權限的 GitHub 帳號。

## 測試

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py storage.py tracker.py exporter.py ai_assistant.py
```

目前測試不呼叫 LINE，也不發送真實的 AI API 請求；AI 的結構化輸出解析與來源 ID 驗證可離線測試。

## 本版限制

- 單一測試使用者 `demo_user_001`，**未提供多使用者登入**；不宜暴露至公網給陌生使用者。
- AI 外部分析需使用者同意，且僅作來源可追溯的複習建議，必須人工確認才新增任務。
- Email／手機遮蔽是基本保護，不能保證辨識所有個資。
- 完整 LINE 補筆記流程、實際 Push、獨立 worker、規則式排程，須待 B 的程式整合才能端到端驗收。
