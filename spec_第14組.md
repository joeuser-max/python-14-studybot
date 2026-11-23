## 1. 專案目標（一句話）

ClassPulse 透過主動式 LINE 互動蒐集學習回饋、規則式安排讀書任務，並將課程、筆記與進度匯出為 AI 可閱讀的 Markdown，降低大學生記錄、規劃及提供資料給外部 AI 分析的操作成本；以學習場景驗證可重用的「事件 → 觸發 → 回饋 → 資料整理 → 下一步行動」流程。

## 2. 問題與產品方向

### 問題陳述

大學生在多門課程與考試期限之間，可能因時間分配不佳而無法按預期完成讀書進度，考前才集中補讀；同時，課後學習重點與疑問也常需要靠自己記錄和追蹤。ClassPulse提供高效方法，讓學習成本降低，效率躍升，讓大學生活變的更加充裕、充實。

### 核心價值與可拓展性

- **主動式（Proactive）**：使用者設定一次課表，系統在指定時間主動發起 LINE 回饋請求，無須每次開啟網頁。
- **降低規劃成本（Low-friction）**：使用者可手動指定讀書時段；未指定的任務由程式依期限與所需時長安排，若排不進去主動向用戶警示。
- **助手（Assistant）**：提供「補筆記」互動，保存回饋與任務狀態，協助下次安排，而非僅發送單向通知；可由使用者一鍵匯出 AI 分析所需的資料。
- **可拓展性（Extensibility）**：將事件類型 `event_type` 與提醒模板分離。MVP 只處理課程（`class`），不實作其他生活場景；資料匯出流程不與 LINE 或特定 AI 平台綁定。
- **AI-ready 資料管線（MVP 必做）**：主動蒐集 → 結構化 JSON 儲存 → 產生具有日期、課程、任務期限、回饋內容及狀態的 Markdown → 使用者自行提供給外部 AI。產品內不呼叫 LLM，AI 分析結果也不自動回寫。

### 核心使用流程

```text
使用者在 Streamlit 設定課表、讀書任務、可用時段（可手動指定任務時段）
                         ↓
程式保留使用者指定安排，再依 Deadline 與所需時間安排其餘任務
            ├─ 無法安排 → 頁面警示／LINE 提醒
            ↓
讀書時段開始時 LINE 提醒使用者開始任務（可在設定中關閉）
            ↓
下課後 LINE 主動提醒；也可在 LINE 點選「補筆記」
                         ↓
使用者選擇星期與課表時段，輸入筆記／疑問
                         ↓
系統記錄對應課次、時間戳記及有效回覆狀態（JSON）
                         ↓
使用者在 Streamlit 查看進度並一鍵匯出 AI-ready Markdown
            ├─ 下載後可自行提供外部 AI 做複習／時間規劃
            ↓
使用者調整未完成任務並重新排程
```

## 3. MVP 功能表

| 編號／功能 | 使用者做什麼 | 程式要做什麼 | 驗收條件 |
|---|---|---|---|
| **F1｜設定課程、任務與可用時段** | 在 Streamlit 行事曆查看每週課程、指定日期的可用時段及已排定讀書任務；新增資料，或點選行事曆事件／使用下拉選單修改既有課程與時段。課程可改名稱、星期、起訖時間、提醒偏移及提醒開關；時段可改日期、開始時間及可用分鐘。另可輸入讀書任務、Deadline、預估分鐘數、指定固定時段，並開關讀書時段開始提醒 | 以週／月／日檢視呈現行事曆；紅色表示每週課程、綠色表示可用時段、藍色表示已排定讀書任務；點選課程／時段時選取相應編輯項目；驗證新增與修改資料，透過 JSON 安全更新 | 重新載入後資料存在；課程／時段修改保留原 ID 並更新行事曆；排程產生後以時段開始及任務預估分鐘數顯示讀書事件；未排入或已完成任務不顯示為排定事件；不合法輸入或時段重疊顯示錯誤且不寫入；修改可用時段後清除該使用者舊計畫並提示重新排程；提醒設定可保存並生效 |
| **F2｜產生及調整讀書計畫** | 按「產生／重新安排」，查看結果，回報任務完成／未完成 | 優先保留使用者指定時段；其餘按最早 Deadline、同期限較長任務優先排列；選擇長度足夠且不衝突的時段；無法排入時顯示原因並提醒 | 手動指定不被覆蓋；不重複佔用時段；顯示日期、時間、科目、任務；未排入可見且會提醒；已排定且未完成的任務在時段開始時收到一次提醒 |
| **F3｜主動回饋蒐集、追蹤與 AI-ready 匯出** | 綁定測試 LINE 帳號；可選擇接收讀書時段開始提醒；收下課提醒，或點「補筆記」→ 選星期 → 選上課時段 → 輸入文字；在 Streamlit 查看紀錄並按「匯出 AI 分析資料（.md）」下載 | 常駐觸發器依有效排程在讀書時段開始時送出 LINE 提醒；另依星期與課表時段定位課次；驗證 Webhook、防重送、保存回饋與統計；彙整課程、任務、期限、排程、時間戳記與回饋，生成結構化 Markdown | 啟用時能在讀書時段開始收到提醒；同一排程不重複推送，完成或已變更的排程不發過期提醒；回饋能正確歸類並統計；按鈕可下載 UTF-8 `.md`；匯出內容與 JSON 一致、含課程／日期／任務／期限／狀態／回饋，且不包含 LINE ID、金鑰等識別或機密資訊 |

### 3.1 讀書排程規則（優先級）

1. **使用者指定優先**：任務可指定 `preferred_availability_id`（固定時段）；先驗證該時段是否有效、長度足夠、未與其他安排重疊、結束時間不晚於 Deadline。有效者保留，不自動移動。若無效或與其他指定衝突，標示「尚未排入」及原因，要求使用者處理，不擅自替換。
2. **其餘任務排序**：排除已完成及有效固定安排的任務；依 Deadline 由近至遠排序；**相同 Deadline 時，預估分鐘數較長者優先**。不是單純依時間早晚先來先排。
3. **時段分配**：在尚未使用、足夠長、結束不晚於 Deadline、且與其他安排不重疊的時段中，選擇**剩餘分鐘數最少**的時段（Best Fit）；完全同分時，才用時段開始時間與 ID 作固定次序。每個時段最多安排一項任務，MVP 不拆分任務，也不把一個時段分給多項任務。
4. **無法排入通知**：若找不到可行時段，將任務列為 `unscheduled` 並附 `reason`；在 Streamlit 顯示警示，若 LINE 已綁定且使用者允許提醒，當任務**首次轉成尚未排入**時發送一則 LINE 告知。相同任務持續未排入，不因重新整理頁面重複推送；重新排入後再次變成未排入才可再提醒。
5. **邊界與限制**：Deadline 僅輸入日期，視為該日 23:59（臺北時間）；過去時段不可排入，可用讀書時段不得彼此重疊；若課表中出現同星期同時段的重複課程，留待 LINE 補筆記時由使用者再選課名。此方法是易於解釋的 Greedy 規則，不保證全域最佳排程。讀書任務是否完成由使用者在 Streamlit 明確回報，不由 LINE 筆記內容推測。

### 3.2 LINE「補筆記」與提醒規則

1. LINE 聊天選單／快速回覆提供「**補筆記**」；使用者依序選擇**星期幾**與**課表時段（開始～結束）**。系統從該 LINE 使用者綁定的 `events.json` 以 `user_id + weekday + start_time + end_time` 尋找課程。選單僅顯示已設定的候選課表，並可附課名供確認。
2. **日期判定**：對應的 `class_date` 採「最近一次已結束的同星期／同時段課次」（限最近 7 天、`Asia/Taipei`）。不提供任意歷史日期補登；若找不到已結束課次，顯示無可補登課次。若同星期、同時段仍有多門課，顯示課名請使用者再選，不自行猜測。
3. 選好課次後，將 `user_id`、`event_id`、`class_date` 暫存為**待輸入筆記狀態**，下一則文字才儲存；可取消或逾時（例如 10 分鐘）清除，避免把一般聊天誤存成筆記。
4. 若該課次已有成功送出之課後提醒，回饋關聯其 `reminder_id`；沒有提醒則以**手動補登**方式保存，`reminder_id` 留空。**只有與已送出課後提醒關聯的課次**計入提醒回覆率；純手動補登可計入筆記數，但不增加提醒分母或分子。
5. 排程器對同一 `user_id + event_id + class_date` 僅嘗試一個有效的課後提醒；未回覆不重複追問。課後回饋並不等於讀書任務完成或真的理解課程。
6. 每筆 LINE Webhook 先驗證簽章，依 `webhookEventId` 去重。LINE Push 的首次請求即使用並保存 UUID 格式的 `X-Line-Retry-Key`；網路失敗時以**同一 key**安全重試，不用新 key 重複送出。`sent` 代表 LINE API 接受，不代表使用者已讀或實際送達。
7. **回覆率**＝指定期間內「有至少一筆有效筆記、且關聯成功送出課後提醒」的**不同 `reminder_id` 數** ÷「成功送出課後提醒的不同 `reminder_id` 數」。不同類型的「無法排入」警示不列入。沒有成功送出的課後提醒時顯示「尚無資料」，不除以零。

### 3.2.1 讀書時段開始提醒

1. 使用者可在 Streamlit 設定中開啟或關閉讀書時段開始提醒；啟用且已綁定 LINE 時，系統在 `Asia/Taipei` 的排定日期與開始時間發送 LINE Push，提醒使用者開始該任務。
2. 僅提醒仍為 `pending`、目前排程狀態為 `scheduled`，且排程仍指向該可用時段的任務；已完成或已重新安排的舊時段不得發送提醒。過去時段不補發。
3. 同一 `user_id + task_id + availability_id` 最多成功送出一次讀書時段提醒；worker 重啟或重複檢查不得重複推送。Push 失敗依既有 retry key 規則以同一 key 重試。
4. 讀書時段提醒與課後回饋提醒、未排入警示是不同類型，不納入課後提醒回覆率。

### 3.3 AI-ready Markdown 匯出規則（MVP 必做）

1. **操作方式**：Streamlit 進度頁提供「匯出 AI 分析資料（.md）」按鈕，使用者自行下載 `.md` 檔，再自行決定是否提供給 ChatGPT、Copilot 或其他外部 AI；系統**不會自動上傳資料或呼叫外部模型**。
2. **資料來源**：由現有 `events.json`、`tasks.json`、`availability.json`、`plan.json`、`reminders.json`、`feedback.json` 產生。僅輸出目前測試使用者的資料，**不另建重複的匯出資料庫**。
3. **輸出結構**：固定依序包含 `# ClassPulse 學習資料`、匯出時間／時區、`## 課程與提醒設定`、`## 讀書任務與 Deadline`、`## 排程結果及未排入事項`、`## 課後回饋紀錄`、`## 回覆統計`。保留事件／任務識別碼、課次日期、時間戳記及資料來源，便於 AI 辨識脈絡；回饋按時間排序；未記錄的欄位寫「未提供」，**不猜測學習時數或理解程度**。
4. **安全與可讀性**：UTF-8 編碼；不匯出 `line_user_id`、Token、channel secret、Webhook 簽章、retry key 或其他部署秘密。筆記視為使用者自述，Markdown 清楚標明「回饋紀錄不等於已完成任務或已理解課程」。如無筆記或無排程資料，保留該小節並顯示「尚無資料」，仍可產生合法 `.md`。
5. **驗收**：用至少一筆課程、一筆有 Deadline 的任務及一筆 LINE 回饋進行匯出；檢查 Markdown 有正確關聯的科目、日期、筆記、任務與狀態；修改 JSON 後重新匯出會反映更新；空資料可匯出；不得包含機密或 LINE 帳號識別碼。此項為 **F3 驗收必要條件**，不是第二版功能。

### 3.4 不在 MVP 範圍內

- **產品內建** AI 語意理解、生成式 AI 建議、自動建立讀書任務或自動判斷是否學會；但 **AI-ready Markdown 匯出屬於本期 F3，不在排除範圍**。
- 自動匯入校務課表、作業與考試，或與 Google 日曆雙向同步。
- 懲罰機制、未回覆後持續追問、運動或其他生活情境、跨週任意日期補登。
- 多人正式帳號管理、跨裝置同步、正式商用部署及高併發資料服務。
- 保證 LINE 即時送達、保證找到最佳排程或保證使用者完成讀書。

## 4. 技術與限制

- 使用 Python 及 Streamlit 製作設定、讀書計畫、進度、筆記紀錄與 **Markdown 匯出介面（`st.download_button`）**；由 Python 字串及檔案處理產生 Markdown，不依賴 LLM API。
- 課表、可用時段與已排定讀書任務透過 `streamlit-calendar` 行事曆顯示；週／月／日檢視中以紅色表示每週重複課程、綠色表示指定日期時段、藍色表示排定任務。讀書事件依計畫的 `availability_id` 找到開始時段，並以任務 `estimated_minutes` 決定結束時間；未排入、已完成或已失效關聯的任務不顯示為排定事件。點選課程／時段可帶入對應編輯表單，也可用下拉選單選取；修改時沿用原資料 ID。可用時段修改成功後，須清除該使用者舊的 `plan.json` 計畫，避免顯示過期安排。
- 使用 LINE Official Account、Messaging API 及 Webhook 發送讀書時段開始提醒、課後提問與排程失敗警示，並接收使用者操作與回覆。
- 使用 Flask（或同等輕量框架）提供 Webhook；需可公開存取的 HTTPS URL。**獨立 `reminder_worker.py` 持續執行**，定期檢查課後提醒、讀書時段提醒及未排入警示並觸發 LINE Push，**不依賴使用者開啟 Streamlit**。MVP 在測試主機上常駐執行即可。
- 使用 JSON 檔存放課表、任務、時段、排程、提醒與回覆，不引入資料庫；限定單一測試使用者、低併發 Demo。檔案更新需先驗證、再安全寫入，避免失敗時覆蓋原資料；讀寫及 `.md` 下載一律使用 **UTF-8**。
- 核心排程與資料處理僅需變數、`if`、迴圈、函式、list、dict、檔案讀寫等基礎；介面與 LINE 整合才使用必要套件。主要註解與介面使用繁體中文。
- 時區固定 `Asia/Taipei`，完整時間戳記統一為含時區 ISO 8601。所有外部請求先驗證來源與輸入；Webhook 原始 body 驗證 LINE 簽章，再處理 `webhookEventId` 去重。
- Token 與 channel secret 放環境變數，**`.env.example` 只列出變數名稱與假值**，真實 `.env` 不提交 Git；`.gitignore` 排除 `.env` 與個人測試資料。
- 第 1 週優先驗證 LINE 推送、Webhook、HTTPS 與常駐 worker；若受外部服務限制，可使用清楚標示的模擬流程 Demo，不得宣稱已完成真實 LINE 整合。
- AI 協助設計／開發的提問、採用與修改理由，記錄在 `docs/ai-log.md`；規格書與 README 只寫已確認的實作情況。
- 不訓練 AI 模型、不串接生成式 AI API，也不將規則式排程稱為 AI 推論；**MVP 的 AI-ready 能力是資料整理與 Markdown 匯出，不是 AI 自動分析**。

### 架構概觀

```text
Streamlit（課表／指定時段／計畫／進度） ──► JSON 資料 ◄──► scheduler.py（規則式排程）
                                                     ▲
                                                     │
LINE Push ◄── reminder_worker.py（課後／讀書時段／未排入提醒） ─────┘
LINE 操作／回覆 ──► Flask Webhook（簽章／去重／選單狀態） ──► JSON 資料
Streamlit「匯出 AI 分析資料」 ◄── exporter.py（讀取 JSON → Markdown）
       └──► 使用者下載 .md ──► 由使用者自行提供外部 AI
```

`reminder_worker.py` 送出訊息；Webhook 接收訊息。兩者職責分開，避免只有開啟網頁時才能觸發提醒。`exporter.py` 僅負責把已儲存的 JSON 整理成 Markdown，不連外、也不修改原始資料。

## 5. 資料格式（JSON）

資料放在 `data/`，以下為 MVP 最小資料規格；範例皆為虛構測試資料。

### `data/events.json`：每週課程／通用事件

| 欄位 | 型別 | 說明 |
|---|---|---|
| `event_id` | string | 事件唯一 ID |
| `user_id` | string | 使用者 ID |
| `event_type` | string | MVP 固定為 `class`；保留未來其他事件類型 |
| `title` | string | 課程名稱 |
| `weekday` | integer | ISO 星期，1=週一、7=週日 |
| `start_time` | string | 開始時間，`HH:MM`；用於辨識 LINE 所選時段 |
| `end_time` | string | 下課時間，`HH:MM` |
| `offset_minutes` | integer | 下課後幾分鐘提醒，MVP 限 0–60 |
| `prompt_template` | string | MVP 為 `class_feedback`，保留模板擴展欄位 |
| `enabled` | boolean | 是否啟用自動提醒 |

```json
[
  {
    "event_id": "event_001",
    "user_id": "demo_user_001",
    "event_type": "class",
    "title": "Python 程式設計",
    "weekday": 5,
    "start_time": "13:00",
    "end_time": "15:00",
    "offset_minutes": 10,
    "prompt_template": "class_feedback",
    "enabled": true
  }
]
```

### `data/tasks.json`：讀書任務

每筆包含 `task_id`、`user_id`、`subject`、`title`、`deadline`（`YYYY-MM-DD`）、`estimated_minutes`（正整數）、`status`（`pending`／`completed`），及可選的 `preferred_availability_id`（使用者指定的時段；未指定時為空字串）。

### `data/availability.json`：可用讀書時段

每筆包含 `availability_id`、`user_id`、`date`（`YYYY-MM-DD`）、`start_time`（`HH:MM`）、`available_minutes`（正整數）。輸入時驗證同一使用者的時段不得互相重疊。

### `data/plan.json`：最近一次排程

每筆包含 `task_id`、`availability_id`（未排入時為空字串）、`status`（`scheduled`／`unscheduled`）、`source`（`manual`／`auto`）、`reason`（未排入原因）及 `unscheduled_alerted`（布林值）。重算時沿用尚未排入任務的已通知狀態；從排入變成未排入時重設通知狀態。

### `data/users.json`：測試使用者與 LINE 綁定

每筆包含 `user_id`、`line_user_id`、`reminders_enabled`（課後提醒與未排入警示）及 `study_reminders_enabled`（讀書時段開始提醒，布林值）。真實 LINE ID 只能經已驗證 Webhook 取得；不得用範例 ID 當作實際帳號。

### `data/reminders.json`：LINE 推送紀錄

每筆包含 `reminder_id`、`user_id`、`event_id`（非課後提醒可留空）、`task_id` 與 `availability_id`（讀書時段提醒必填，其他類型可留空）、`class_date`（課後提醒必填）、`kind`（`class_feedback`／`unscheduled_alert`／`study_session`）、`scheduled_at`、`sent_at`、`status`（`pending`／`sent`／`failed`）及 `retry_key`。課後提醒用 `user_id + event_id + class_date` 去重；讀書時段提醒用 `user_id + task_id + availability_id` 去重；`sent` 表示 LINE API 接受送出請求，不代表已讀。

### `data/feedback.json`：回饋／補筆記

每筆包含 `feedback_id`、`user_id`、`event_id`、`class_date`、`reminder_id`（純手動補登時可為空字串）、`received_at`、`content`、`source`（`selected`／`push`）及 `webhook_event_id`。去重後才儲存，回覆率以不同且有效的 `reminder_id` 計算。

### AI-ready 輸出檔：`classpulse_learning_export.md`

這是 **F3 即時產生的下載檔，不是需長期儲存的另一份資料**；資料取自上列 JSON。最小可閱讀輸出範例如下（虛構內容；僅展示格式）：

```markdown
# ClassPulse 學習資料
匯出時間：2026-11-20T13:00:00+08:00
時區：Asia/Taipei
> 以下筆記為使用者自述，不代表已完成任務或已驗證理解。

## 課程與提醒設定
- [event_001] Python 程式設計｜週五 13:00–15:00｜提醒：下課後 10 分鐘

## 讀書任務與 Deadline
- [task_001] Python 期末專題｜期限：2026-11-27｜預估：120 分鐘｜狀態：pending

## 排程結果及未排入事項
- [task_001] 2026-11-23 19:00｜排程來源：auto

## 課後回饋紀錄
- 2026-11-20｜Python 程式設計 [event_001]｜收到：2026-11-20T15:12:00+08:00
  - 筆記：學到 list 與 dict 的使用情境

## 回覆統計
- 已送出課後提醒：1；已回覆課次：1；回覆率：100%
```

### `data/pending_notes.json`、`data/processed_webhooks.json`：暫存互動狀態與防重送

- `pending_notes.json`：每使用者至多一筆 `user_id`、`event_id`、`class_date`、`expires_at`；「補筆記」選好課次後，供下一則文字對應，逾時或取消刪除。
- `processed_webhooks.json`：保存已成功處理的 LINE `webhook_event_id`；重送時跳過相同事件，避免重複補筆記或變更選單狀態。資料修改與事件 ID 記錄應在同一可靠流程完成，必要時安全重試。

## 6. 檔案結構

```text
classpulse-study/
├── spec.md
├── README.md                 # 如何安裝、設定與執行
├── requirements.txt          # Python 必要套件
├── .env.example              # 環境變數名稱與假值，不放真正金鑰
├── .gitignore                # 排除 .env 與個人測試資料
├── app.py                    # Streamlit 設定、計畫與紀錄頁面
├── calendar_events.py        # 將課程／可用時段／排程任務轉成行事曆事件
├── scheduler.py              # 讀書任務排程與提醒到期判斷
├── reminder_worker.py        # 常駐檢查到期事件及推送 LINE
├── storage.py                # JSON 驗證、載入與安全儲存
├── line_bot.py               # LINE Push、Webhook、補筆記選單
├── tracker.py                # 回覆率及進度統計
├── exporter.py               # 將 JSON 學習資料整理成 Markdown（MVP 必做）
├── tests/
│   ├── test_calendar_events.py   # 課程、可用時段及排程任務的行事曆轉換
│   └── test_storage_editing.py   # 課程／時段更新及衝突驗證
├── docs/
│   └── ai-log.md             # AI 協作歷程（提示詞／建議／人的判斷）
└── data/                     # Demo 測試資料；實際個人資料不提交 Git
    ├── events.json
    ├── tasks.json
    ├── availability.json
    ├── plan.json
    ├── users.json
    ├── reminders.json
    ├── feedback.json
    ├── pending_notes.json
    └── processed_webhooks.json
```

## 7. 函式清單與兩人分工

- **A：蕭博軒**（Streamlit、資料格式、驗證、統計、AI-ready Markdown 匯出）
- **B：莊育哲**（讀書排程、提醒觸發、LINE 整合）
- 兩人共同整合、測試與撰寫 README／AI 協作紀錄。以下分工為本次規劃，可依實作進度調整。

| 函式／模組 | 輸入 | 輸出 | 負責組員 |
|---|---|---|---|
| `load_json(path)` | JSON 路徑 | list；不存在回空 list，格式錯誤回報錯誤 | 蕭博軒 |
| `save_json(path, data)` | JSON 路徑、list | 儲存成功／明確錯誤，不覆寫損壞資料 | 蕭博軒 |
| `validate_event(event)` | 課程／事件 dict | 欄位、時間及衝突驗證結果 | 蕭博軒 |
| `update_event(event)` | 含既有 `event_id` 的課程 dict | 驗證並更新同一課程；找不到資料或欄位不合法時回報錯誤 | 蕭博軒 |
| `update_availability(slot)` | 含既有 `availability_id` 的時段 dict | 排除該筆自身後驗證時段衝突並更新；找不到資料或重疊時回報錯誤 | 蕭博軒 |
| `build_calendar_events(courses, availability, tasks, plan)` | 課程、可用時段、任務及排程 list | 產生 FullCalendar 所需事件；排定任務連結到時段，依任務預估分鐘數計算結束時間 | 蕭博軒 |
| `add_task(data, task)` | 任務資料、任務 dict | 更新後的任務資料或錯誤 | 蕭博軒 |
| `make_plan(tasks, availability, previous_plan, now)` | 任務、時段、上次計畫、現在時間 | 先固定使用者指定，再依期限／時長 Best Fit，含未排入原因與新警示清單 | 莊育哲 |
| `update_task_status(tasks, task_id, status)` | 任務清單、ID、新狀態 | 更新資料或錯誤 | 莊育哲 |
| `get_due_events(events, now, reminders)` | 課表、目前時間、提醒紀錄 | 到期且未送的課後提醒 list | 莊育哲 |
| `get_due_study_reminders(tasks, plan, availability, users, now, reminders)` | 任務、目前計畫、可用時段、使用者設定、目前時間、提醒紀錄 | 對已啟用提醒的使用者，回傳到期且仍有效、尚未送出的讀書時段提醒 list | 莊育哲 |
| `run_reminder_worker()` | 時間、課表、任務、計畫、可用時段、使用者設定及提醒紀錄 | 定期檢查、呼叫 LINE Push、寫入送出狀態 | 莊育哲 |
| `verify_line_signature(body, signature, secret)` | 原始 Webhook、簽章、secret | 有效／無效 | 莊育哲 |
| `resolve_class_slot(user_id, weekday, start_time, end_time, now)` | 使用者、星期、所選時段、現在時間 | 最近一次已結束課次之 `event_id + class_date`；模糊時回選項 | 莊育哲 |
| `save_feedback(feedback, path)` | 完整筆記 dict、路徑 | 去重及儲存結果／錯誤 | 莊育哲 |
| `calculate_response_rate(reminders, feedbacks)` | 課後提醒及筆記清單 | 已回覆課次、已送出課次、回覆率或無資料 | 蕭博軒 |
| `export_learning_markdown(records, now)` | 含課程、任務、時段、計畫、提醒、回饋等 list 的 dict；匯出時間 | 有標題、時間、關聯與狀態的 Markdown 字串；無資料時仍輸出有效格式 | 蕭博軒 |
| Streamlit `.md` 下載按鈕 | `export_learning_markdown()` 的文字 | 下載 UTF-8 `classpulse_learning_export.md`，不自動上傳 AI | 蕭博軒 |
| Streamlit／Flask 主流程 | 使用者操作、Webhook | 設定頁面、LINE 選單回覆、錯誤處理 | 兩人整合 |

## 8. 兩週開發計畫與風險

| 時程 | 工作 | 驗收交付 |
|---|---|---|
| 第 1 週前半 | 完成課表含 `event_type`／上課時段、任務與可用時間表單、簡單排程；確認 LINE Bot／Webhook／HTTPS 與常駐 worker 可運作 | 資料可寫入及重載；手動指定優先、Deadline／時長排序可測；至少完成一則 LINE 真實測試或確認備援方案 |
| 第 1 週後半 | 完成課後提醒、「補筆記」星期／時段選擇、Webhook 驗證與去重 | 相同課次不重複發送；選定時段能歸類至正確課次；LINE 回覆能保存 |
| 第 2 週前半 | 加入讀書時段開始提醒、未排入通知、回覆率統計、任務重新安排，**完成 JSON → Markdown 匯出**；補足測試 | 到排定讀書時間能收到一次 LINE 提醒；已完成或已重排任務不收到舊提醒；無法排入有頁面／LINE 告知、不重複催促；回覆率不把手動補登當成提醒；能下載含課程、任務、Deadline 與回饋的 `.md` |
| 第 2 週後半 | 修正、README、AI 協作紀錄與三分鐘 Demo | 完整示範：設定 → 排程 → LINE 互動／補筆記 → 追蹤 → **下載 Markdown 供外部 AI 使用**；外部服務失敗時標示模擬部分 |

**主要風險：**兩人、兩週內同時完成讀書排程、LINE Webhook／常駐推送及 Markdown 匯出有整合風險。Markdown 匯出應以純 Python 格式化 JSON 的最小實作完成，不增加模型 API。第 1 週先測通 HTTPS、Push 與 Webhook；若受阻，保留 F1、F2 真實運作，F3 清楚標示 LINE 哪些部分為模擬，不宣稱真實 LINE 整合； **JSON → Markdown 匯出仍須由真實執行的程式完成**，多使用者、交易式去重與可靠跨服務投遞留待後續版本。

## 9. 三分鐘 Demo 與驗收

1. 在 Streamlit 建立一門具有 `event_type=class` 的課、兩項讀書任務與可用時段；手動固定其中一項時段，並開啟讀書時段提醒。
2. 產生計畫：展示手動指定優先、其餘依 Deadline／時長處理；在一個測試排定時段開始時確認收到 LINE 提醒；刻意建立一個無法排入的任務，顯示原因及通知。
3. 模擬課後時間觸發 LINE 提醒；在 LINE 點「補筆記」，依序選星期與上課時段並提交一則文字筆記。
4. 在 Streamlit 檢視課次、時間戳記與回覆率；更新任務狀態後重新產生計畫。
5. 按「匯出 AI 分析資料（.md）」下載 Markdown，開啟檔案檢查課程、筆記、Deadline、進度與時間戳記；可說明使用者如何將檔案**自行交給外部 AI**，但不聲稱已完成 AI 分析。

| 測試 | 情境 | 預期結果 |
|---|---|---|
| 輸入驗證 | 必填欄位空白、時間非法、可用時段重疊 | 顯示錯誤，不儲存 |
| 課表行事曆修改 | 點選課程事件或從下拉選單選取，修改名稱、星期或時間並儲存 | 編輯表單帶入該筆課程；沿用原 `event_id` 儲存，行事曆顯示更新內容 |
| 排定任務行事曆 | 產生含已排定任務的計畫，並將任務標記完成或保留未排入 | 藍色事件顯示科目、任務名稱及起訖時間；未排入與已完成任務不顯示為讀書事件 |
| 可用時段修改 | 修改日期／開始時間／分鐘數並儲存；另測試修改後與其他時段重疊 | 合法修改更新原時段並清除該使用者舊計畫；重疊修改顯示錯誤且不寫入，其他使用者計畫不受影響 |
| 人工優先 | 指定任務與有效時段 | 排程保留指定，不自動移動 |
| 人工衝突 | 兩個固定任務指定同一時段、或超出期限 | 顯示衝突與未排入原因，不猜測更換 |
| Deadline 與時長 | 任務 A 30 分、B 60 分；時段各 30、60 分；同 Deadline | 較長任務先處理；兩者各分配合適時段，而非按最早時間浪費 60 分鐘槽 |
| 無法安排 | 無可行時段，或任務需求超過可用時長 | `unscheduled`＋原因；首次轉入時顯示／送出一次警示，不重複洗版 |
| 任務完成 | 標記 completed 後重算 | 完成任務不再排程 |
| 讀書時段提醒 | 開啟提醒；有一筆仍為 pending 且已排定的任務，到達排定開始時間 | Streamlit 關閉時 worker 仍向 LINE 發送一次提醒；重啟 worker 不重送 |
| 讀書提醒排程變更 | 提醒時間前將任務標記完成或重新排到其他時段 | 不發送已完成任務或舊時段的提醒；新時段開始時才提醒 |
| 讀書提醒關閉 | 關閉讀書時段提醒或未綁定 LINE | 不發送讀書時段提醒 |
| 課後自動提醒 | Streamlit 關閉，常駐 worker 運行且到課後提醒時間 | 仍可向 LINE 發送提醒；同課次重跑不重送 |
| 補筆記定位 | LINE 選星期五 + 13:00～15:00 | 對應本週最近一次已結束之 Python 課；存 `event_id`、`class_date` |
| 補筆記邊界 | 同時段有兩門課，或選擇尚未結束之課次 | 提示再選課名，或拒絕未發生課次；不猜測 |
| Webhook 去重 | 同一 `webhookEventId` 重送／簽章錯誤 | 不重複儲存；錯誤簽章拒絕 |
| 推送重試 | 首次 Push timeout，以同一 retry key 重送 | 不因重試而接受兩次相同推送請求 |
| 回覆率 | 5 筆成功課後提醒、其中 3 筆有有效回饋，另外 2 筆為純手動補登 | 回覆率 3/5＝60%；手動補登只增加筆記數 |
| 無提醒資料 | 成功送出課後提醒數＝0 | 顯示「尚無資料」，不除以零 |
| AI-ready 匯出 | 已有課程、筆記、任務、Deadline 與排程資料 | 下載 `.md` 含各資料段落、課程／日期關聯與正確狀態，且與 JSON 一致 |
| 匯出資料更新 | 改變任務完成狀態或增加一筆回饋，再次匯出 | 新檔反映更新，原始 JSON 不被匯出功能修改 |
| 匯出安全與空值 | 空回饋、未排入任務或含測試 LINE ID | 顯示「尚無資料」／未排入原因，不匯出 LINE ID、金鑰或秘密 |
| JSON 格式錯誤 | 任一資料檔損壞 | 顯示錯誤，不覆寫原檔 |

## 10. AI 定位與後續方向

- **本期 MVP 必做 AI-ready Data Architecture**：利用 LINE 主動蒐集筆記、以 JSON 結構化保存，並可一鍵匯出包含課程、回饋、任務、Deadline、安排結果與時間戳記的 Markdown，讓使用者直接提供給外部 AI 進行摘要、複習或規劃。這是產品資料交換能力，不是內建 AI 推論。
- 不自行訓練模型，也不把使用 Copilot 協助開發描述為產品內建 AI；**不自動將個人資料傳給任何 AI 平台**，匯出與分享由使用者決定。
- 第二版才考慮內建 LLM 摘要、自然語言任務輸入，或將外部 AI 的建議經使用者確認後寫回任務。**Markdown 匯出已屬 MVP，不得延後為第二版。**
- MVP 的 `event_type` 僅處理 `class`，`prompt_template` 僅處理 `class_feedback`；保留未來擴充運動、生活日誌及專案情境的資料結構，但本期不實作。
- `docs/ai-log.md` 紀錄 AI 協助發想、設計與除錯的提示詞、輸出、人的修正及反思；`.env.example` 是部署環境變數的無密碼範本，真實金鑰只放本地 `.env` 或部署環境設定。

