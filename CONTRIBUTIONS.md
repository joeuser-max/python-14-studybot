# ClassPulse｜第 14 組個人貢獻與工程證據

> 此頁面供課程評分、期末展示及組員審查。按功能責任與實際工程成果歸屬，而非將提交數量直接換算成個人分數。更新日期：2026-11-28（臺灣時間）。

## 組員與責任

| 組員 | GitHub | 主要責任 |
|---|---|---|
| **蕭博軒（A）** | [@Onlynotonly](https://github.com/Onlynotonly) | 資料管理與 Streamlit、產品流程與 UI/UX、排程引擎與 AI 任務整合、LINE 個人化身份及跨端同步、自動提醒與本機服務管理、跨分支整合、測試與實機除錯 |
| 莊育哲（B） | [@joeuser-max](https://github.com/joeuser-max) | 原始 LINE Webhook／帳號綁定、課後補筆記、提醒 Worker 與排程／進度回報、附件擷取、課後 AI 與讀書提醒等後端功能；其版本的前端與排程改善亦保留在原始提交 |

**蕭博軒的核心貢獻不是單一前端頁面，而是將原有 A/B 模組整合成可驗證的個人學習閉環：LINE 取得課後回饋 → AI 整理疑問 → 使用者確認任務 → 網頁安排讀書時段 → LINE 自動提醒及進度回報 → 局部重排。** 原始 LINE 與後端功能沿用及適配之處，不宣稱為本人獨立發明。

## 蕭博軒個人貢獻明細

| 工作項目 | 本人新增、主導整合或修正的具體成果 | 程式與證據 |
|---|---|---|
| A 模組基礎 | 資料管理、Streamlit 介面、Markdown/AI 分析，與 B 模組進行資料契約整合 | [PR #1](https://github.com/joeuser-max/python-14-studybot/pull/1)、[PR #2](https://github.com/joeuser-max/python-14-studybot/pull/2)、storage.py、app.py、exporter.py、ai_assistant.py |
| 可靠性與整合 | Reminder retry key 保留、鎖內更新與狀態回寫、綁定防覆蓋、合併 btesting 並保留組員原作者歷史、CI compileall/HTTP health、macOS 啟動說明 | [PR #3](https://github.com/joeuser-max/python-14-studybot/pull/3)、[PR #4](https://github.com/joeuser-max/python-14-studybot/pull/4)、[PR #5](https://github.com/joeuser-max/python-14-studybot/pull/5) |
| 使用者體驗 | 引導式控制台、任務與時段卡片、LINE 一日互動 Mock、虛構展示資料隔離、日週月檢視、課程衝突提示、任務進度統計、版本與啟動除錯 | [PR #6](https://github.com/joeuser-max/python-14-studybot/pull/6)–[PR #13](https://github.com/joeuser-max/python-14-studybot/pull/13)、app.py、demo_data.py、mock_day.py、line_mock_chat.py |
| V2 排程 | 七日十六節視覺板、單任務拖放與伸縮、手排固定與一鍵填滿分離、Deadline/合法區間與課程衝突、ICS 匯入匯出、外部事件衝突警告 | [PR #14](https://github.com/joeuser-max/python-14-studybot/pull/14)、[PR #15](https://github.com/joeuser-max/python-14-studybot/pull/15)、[PR #16](https://github.com/joeuser-max/python-14-studybot/pull/16)、week_board.py、week_planner.py、calendar_sync.py、calendar_views.py |
| 排程最佳化與 AI Coach | 綠色偏好是軟目標而非硬限制，兼顧跨日負荷，保留固定任務；匿名小組 JSON 模板、Gemini Coach 候選方案及本地合法性驗證 | [PR #14](https://github.com/joeuser-max/python-14-studybot/pull/14)、[PR #17](https://github.com/joeuser-max/python-14-studybot/pull/17)、schedule_preferences.py、study_coach.py、peer_exchange.py |
| LINE 文件與 V2 整合 | 適配組員原始 TXT/DOCX/PDF 擷取、PDF 附件、課後 AI/讀書提醒及進度回報；本人新增未分類快速筆記、正文搜尋、局部重排及 V2 固定時段保護 | [PR #17](https://github.com/joeuser-max/python-14-studybot/pull/17)、line_note_files.py、note_attachments.py、line_study_ai.py、[來源與適配紀錄](docs/final-integration-1-audit.md) |
| Final 1.1 AI 任務 | 筆記一對多疑問、來源 ID 去重、逐題確認、紫色 30 分鐘任務、下一次課程開始前 Deadline、半小時排程與伸縮、課程／週次筆記庫 | [PR #18](https://github.com/joeuser-max/python-14-studybot/pull/18)、note_tasks.py、week_planner.py、[審核紀錄](docs/final-1-1-note-task-audit.md) |
| Final 2.0 身份與資料隔離 | LINE follow/idempotent 個人註冊、獨立 seed、跨模組 owner-scoped 讀寫、LINE Login authorization code/state/nonce/PKCE、伺服端 Session、登出撤銷、原 OA bridge、保留原始服務 | [PR #19](https://github.com/joeuser-max/python-14-studybot/pull/19)、[PR #20](https://github.com/joeuser-max/python-14-studybot/pull/20)、line_demo_registration.py、line_demo_seed.py、line_web_auth.py、line_friend_e2e.py、line_official_bridge.py |
| Final 3.0 真實學習閉環 | 修正 LINE 與網頁雙資料來源；Gemini provider 適配、逐次同意及真實 API、逐題確認、讀書開始快取摘要、讀書結束回報與單項重排、指定課次直接回饋 | [PR #20](https://github.com/joeuser-max/python-14-studybot/pull/20) 後續提交、[PR #21](https://github.com/joeuser-max/python-14-studybot/pull/21)、ai_assistant.py、line_official_bridge.py、line_personal_study_worker.py、line_personal_progress.py、line_personal_class_worker.py |
| 自動化與維運 | 單一常駐 Worker、個人提醒 opt-in/out、持久 Retry Key 去重、啟用與關閉授權；一鍵啟動／健康檢查／簽章探測／日誌／安全停止與重啟，保留舊服務和資料 | [PR #21](https://github.com/joeuser-max/python-14-studybot/pull/21)、line_personal_auto_worker.py、classpulse.sh、deploy/local_service_manager.py、[操作手冊](docs/local-launcher.md) |
| QA 與部署實機除錯 | 逐階段 regression、Chromium UI 回歸、Webhook 簽章與權限負面測試、實際 LINE/Gemini 測試、HTTPS session/refresh 故障隔離、Python SSL 憑證與 CLI 錯誤修復、版本封存、維運手冊 | tests/、scripts/ui_smoke.py、[Final 2.0](docs/final-2-0-contribution-and-acceptance.md)、[Final 3.0](docs/final-3-0-contribution-and-acceptance.md) |

## 組員原始貢獻與共同整合邊界

- B 原始 LINE 綁定、Webhook、課後補筆記、課後 AI、提醒及進度回報等在 btesting/main 提交中已有實作。A 於 PR #5 以雙親 merge 保留原始提交；後續 PR #17/#18 以來源可追溯方式適配。
- 組員在 [main 參考 commit 1ef63c8](https://github.com/joeuser-max/python-14-studybot/commit/1ef63c8e7d98d344bc7297ac744706f2a59608ec) 另實作課程進度／複習範圍、使用者指定時間與時段、LINE 文件、提醒和重排等流程。這些原始功能與 A 的產品改進有所重疊，但不應將 B 的不同需求設計直接稱為錯誤。詳見 [Step 21 來源比較](docs/step21-line-interaction-audit.md)。
- A 的新增價值包括 V2 排程契約、獨立問題任務、owner 隔離與身份驗證、真實 LINE/網頁同一資料集、Gemini 明確同意流程、實際雙向閉環、自動化與維運；並非將原有 B 模組全部重寫後據為己有。
- 此紀錄將 AI 輔助開發列為方法之一；蕭博軒負責產品決策、需求、工程整合、GitHub 操作授權、本機服務配置、實機操作與驗收。不能將 AI 生成的每行程式碼表述為完全手寫。

## 可量化的 GitHub 與驗收證據

截至建立 Main Integration 分支前，GitHub API 實際列出 PR #1–#21 共 21 個由 Onlynotonly 建立，20 個歷史上已合併，#21 為草稿。已合併不等於目前 main 含有所有歷史功能；main 已與功能分支分岔。組員直接提交和 btesting 歷史不能由 PR 計數推定。不得將 21/21 PR 或 ahead 264/behind 1 當作個人完成百分比。

| 驗收里程碑 | 結果與證據 |
|---|---|
| A/B 整合 | PR #5 記錄 43 tests、compileall、Streamlit HTTP 檢查 |
| Final 2.0 | 186 tests；原 OA bridge 5/5 實機回報；[CI #264](https://github.com/joeuser-max/python-14-studybot/actions/runs/46072701471) |
| Gemini API 與紫色任務 | 199 tests；[CI #275](https://github.com/joeuser-max/python-14-studybot/actions/runs/46076031734)；[8/8](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7229369179) |
| LINE 進度閉環 | 修正 SyntaxError 後 209 tests；[8/8](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7229568888) |
| 自動提醒 | 218 tests；[8/8](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7229779416) |
| 本機 Service Manager | 實際 terminal 輸出 223 passed in 2.04s；[啟動證據](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7229865932)、[10/10](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7229889884) |

手機驗收為使用者回報；離線測試使用替身與暫存資料，不是 223 次真實 LINE API 呼叫。最新封存 SHA 的 CI 未獨立確認；Main Integration 仍須重跑測試。未宣稱雙帳號實機、雲端部署、永久公開網址、跨檔資料交易或 production-ready。

## 版本與追溯

- V2：[`be687f7b`](https://github.com/joeuser-max/python-14-studybot/commit/be687f7b96019744bdf10b9e6a4cecd0df562ab5)
- Final 1.1：[`10b5fc5c`](https://github.com/joeuser-max/python-14-studybot/commit/10b5fc5c87bc6bbc5fe6f08a4e3b61a04d55f52b)
- Final 2.0：[`0e0c0bde`](https://github.com/joeuser-max/python-14-studybot/commit/0e0c0bde73e149c63f4266e6c12a9575484f1fc6)
- Final 3.0：[`e835140e`](https://github.com/joeuser-max/python-14-studybot/commit/e835140e0658717e1fdda14ab7ec07c7d8554ed3)、[封存分支](https://github.com/joeuser-max/python-14-studybot/tree/archive/final-3.0)
- Main Integration：`integrate/final-3.0-main`，保留兩位組員歷史；不直接覆寫 main，合併前需審查、解決衝突及重新驗收。

**評分建議：** 依上述模組責任、原始 PR、程式碼、真實測試及實機成果分別評價，而非以 LOC 或 Git 提交次數自動換算分數。個人比例若需填入課程正式表單，應由組員確認評分口徑及共同工作分攤。
