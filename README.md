# ClassPulse — 第14組

主動式學習回饋與讀書排程專題。A 蕭博軒（Onlynotonly）負責 Streamlit、JSON、追蹤、Markdown 與 AI；B 莊育哲（joeuser-max）負責排程、LINE Webhook 與 Worker。詳見 README(A).md 和 README(B).md。

## 安裝與運行

需要 Python 3.11+。先執行 python -m venv .venv，啟用虛擬環境，再執行 python -m pip install -r requirements.txt。

分三個終端執行：

- python -m streamlit run app.py
- python -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000
- python reminder_worker.py

測試：python -m pytest -q。真實 LINE Webhook 必須有公開可連線的 HTTPS /webhook URL，且驗證 X-Line-Signature。

## LINE 帳號綁定及補筆記

在私有環境設定 LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN、LINE_BIND_CODE（自己產生的長隨機字串）。不要把任何金鑰提交到 GitHub。專案不會自動讀取 .env。

向 LINE Bot 傳送「綁定 <綁定碼>」，經有效 LINE Webhook 驗簽後為單一 Demo 帳號 demo_user_001 綁定 LINE ID。已綁定其他人時不允許覆蓋。

先在 Streamlit 建立課表，再向 LINE Bot 傳送「補筆記」→ 選星期數字 → 選上課時段數字 → 同時段多門課時選課名數字 → 輸入筆記。10 分鐘內完成；任一階段傳「取消」退出。

無 LINE Access Token 的本地模擬不代表 LINE Push 已送達，不能算作已發送提醒。

## 產品 AI

ai_assistant.py 透過 OpenAI Responses API 的 Structured Outputs 分析筆記，產生有來源 feedback ID 的待確認複習任務。額外設定 OPENAI_API_KEY 和 OPENAI_MODEL；只有在 UI 勾選同意並主動分析才連外，使用者確認後才加入 tasks.json。沒有金鑰仍可下載 Markdown。原始規格書是早期 MVP 文件，其「不使用內建 LLM」已不符合目前程式。

## 驗證限制與協作

尚未驗證真實 LINE API、HTTPS Tunnel、OpenAI API 和 Worker 長時間運作。JSON 方案僅支援低併發 Demo，跨程序多檔案操作沒有完整交易性。

Git 工作流程：先同步 main → feature branch 開發 → 測試 → push feature branch → PR 審查 → 合併。不要直接 Push main。
