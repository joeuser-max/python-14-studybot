# ClassPulse｜跨平台期末 Demo

## 準備

依 [README](../README.md) 安裝 Python 3.11、依賴，執行 pytest，再啟動 Streamlit。Windows 使用 PowerShell 的 .venv\Scripts\python.exe；macOS/Linux 使用 .venv/bin/python。建議全新 clone，不複製其他人的 .env 或 data/。

1. 開啟 http://localhost:8501。
2. 開啟「展示模式（使用獨立的範例資料）」。
3. 按「重設展示資料」。此操作只還原獨立的虛構展示資料，不清除正式或 LINE 個人資料。
4. 確認七日板顯示 14 門課、8 張待排任務、3 項已排任務及 3 筆外部活動。

## 主要 Demo（無金鑰、無外部 API）

| 順序 | 操作 | 驗收重點 |
| --- | --- | --- |
| 1 | 行事曆與拖排：切換七日、日、週、月 | 同一份課表與任務資料 |
| 2 | LINE 一日 Mock：補筆記 → 星期一 → 固態物理 09:00–11:00 → 3 → 輸入「費米能階為何隨溫度改變？」 → 傳送筆記 → 只保留筆記 | 筆記保存；清楚標示 Mock AI |
| 3 | 總覽與回饋：查看筆記庫；任務管理：檢視疑問候選，確認一題 | 紫色待排卡、30 分鐘、來源課程及下次上課前期限；不自動覆寫排程 |
| 4 | 七日拖排：拖一張待排卡至未佔用的格子，再伸縮卡片 | 手排只改單一任務；非法重疊被拒絕 |
| 5 | 點「一鍵安排：標記綠色偏好」，畫綠後按「確認偏好並一鍵安排」 | 保留手排，優先使用綠色但可用其他合法空格 |
| 6 | 匯入 examples/demo_external_calendar.ics（預覽確認）；切換日週月 | 外部活動與排程共存，僅本機副本 |
| 7 | 總覽與回饋：查看完成率、回覆率、筆記及 Mock Coach（選用） | AI 候選需驗證與人工確認，不把模擬當真實模型 |
| 8 | Markdown 與 AI：下載學習資料；行事曆匯出 ICS | 資料可匯出，不自動上傳 |

可重設展示資料後重複操作。若 LINE Mock 沒有星期一選項，選任一有課的日期與課程。若候選無法安排，檢查來源課程、Deadline 和空白格。日期相對於當前日期，不固定使用截圖時間。

## 真實整合（另行展示）

只有已設定的 macOS 內部服務才使用 LINE Login、Gemini API、常駐提醒及進度回報。Windows 離線展示不需要取得其他組員金鑰或使用其 LINE 帳號。完整服務部署參考 [local-launcher.md](local-launcher.md)。

## 測試結果

GitHub Actions 對 Linux 與 Windows 執行 Python 回歸、Chromium 瀏覽器 smoke test 和 Streamlit HTTP 檢查。POSIX 權限相關測試在 Windows 略過；不能將離線 CI 等同真實 LINE/Gemini 服務驗收。若執行失敗，記錄 pytest 結果及畫面，不要提交私人資料或 .env。
