# ClassPulse｜第 14 組 — 主動式學習回饋與規劃助手

> **Final 3.0：已完成本機內部展示驗收；支援離線展示及本機 LINE 服務。**

## 產品功能

LINE 課後回饋 → Gemini 分析 → 逐題確認紫色任務 → 七日拖排 → LINE 自動提醒 → 進度回報及局部重排。個人資料由 LINE Login 身份映射；不需每次手動啟動提醒任務。

## 團隊與版本

第 14 組：蕭博軒、莊育哲。原始分工為 A 模組（資料管理、網頁與 AI 分析）及 B 模組（LINE 互動、排程與提醒），最終共同整合為 ClassPulse。

## 主要程式檔案

| 檔案 | 用途 |
| --- | --- |
| `app.py`、`week_board.py` | 網頁控制台、行事曆、任務拖排 |
| `storage.py` | JSON 資料讀寫、驗證與保存 |
| `scheduler.py`、`week_planner.py` | 讀書排程、時間及衝突限制 |
| `line_bot.py`、`line_official_bridge.py` | LINE 訊息接收、筆記與進度回報 |
| `line_web_auth.py` | LINE 登入與個人身份驗證 |
| `ai_assistant.py`、`note_tasks.py` | 筆記分析、疑問及複習任務候選 |
| `reminder_worker.py`、`line_personal_auto_worker.py` | 定期提醒與進度確認 |
| `exporter.py`、`tracker.py` | Markdown 匯出及學習回饋統計 |
| `classpulse.sh`、`deploy/local_service_manager.py` | 本機服務管理 |

## 安裝與離線展示（不需 API 金鑰）

Python 3.11 以上，在專案根目錄執行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

開啟 Streamlit 網頁，啟用「展示模式」即可操作虛構課表、任務拖排與 LINE Mock。展示模式不發送真實 LINE 或呼叫外部 AI。

### Windows（PowerShell）

建議使用全新 clone，避免覆寫既有資料。安裝 Python 3.11 及 Git 後，在專案根目錄執行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

開啟 http://localhost:8501，啟用展示模式，再按「重設展示資料」（只還原虛構展示資料）。不需要啟用 PowerShell script execution policy、LINE Token、Gemini API Key、Caddy 或 Tunnel。按 Ctrl+C 停止本機網頁。

- [跨平台 Demo 操作手冊](docs/demo-quickstart.md)
- Windows CI 執行離線測試、Chromium UI 測試及本機 HTTP health check；POSIX 權限相關的 macOS launcher 測試在 Windows 明確略過。完整真實 LINE 服務管理仍為 macOS 內部環境，不宣稱 Windows 原生支援。

## AI 使用說明

開發過程使用 AI 協助規格、程式、除錯與文件，實際採用內容經人工判斷及測試；過程見 [AI 協作紀錄](docs/ai-log.md)。產品內建 AI 用於筆記整理與疑問候選，須使用者同意才連外；任務與排程由使用者確認，合法性由程式規則檢查。

- [本機一鍵啟動與維運](docs/local-launcher.md)
- [主線整合與驗收規則](docs/main-integration-plan.md)

### 啟動已設定好的 macOS 內部展示服務

```bash
bash classpulse.sh start
```

既有 staging 環境、原始 Flask 5000 及現有 HTTPS Tunnel 為前置條件。另一個 Terminal 可使用 `bash classpulse.sh status`、`bash classpulse.sh logs worker`、`bash classpulse.sh stop`。第一次設定請閱讀維運手冊；不要將 Token、環境檔或個人資料提交至 GitHub。公開部署、雙帳號實機及新 Tunnel 模式尚未驗收。

---

## 專案文件

- [專題規格書](spec_第14組.md)
- [AI 協作紀錄](docs/ai-log.md)
- [系統架構](docs/architecture-v2.md)
- [服務管理](docs/local-launcher.md)

## 自動化測試

    python -m pytest -q

測試使用隔離資料與外部服務替身，不需要真實 API 金鑰。
