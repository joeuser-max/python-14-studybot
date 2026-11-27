# ClassPulse｜A／B 整合版操作手冊

**V2 架構與驗收邊界：**[七日規劃板／AI 教練／匿名訓練模板設計說明](docs/architecture-v2.md)。

**三分鐘期末 Demo：**[實際操作腳本、範例 ICS 與 Mock AI 驗收](docs/demo-v2.md)。


這份手冊從第一次安裝開始，帶你測試課表、讀書排程、進度／Markdown 匯出，以及選擇性 LINE 整合。

- **A 功能**：Streamlit 介面、JSON 資料、安全儲存、回覆統計、Markdown 匯出、經同意後的 AI 筆記整理。
- **B 功能**：固定／自動讀書排程、LINE Webhook 補筆記、課後與讀書時段提醒 Worker。
- **目前限制**：單一測試使用者 `demo_user_001`、本機 JSON 資料；不是正式多人服務。

## 行事曆操作：七日拖排不取代日／週／月

ClassPulse 有六個主頁籤：

- **行事曆與拖排**：上方切換「七日拖排／日／週／月」。七日拖排顯示 T+0 ～ T+6、每日固定 16 節與待排任務盒，支援拉長卡片、只拖入單一任務、一鍵填滿剩餘任務。日／週／月可以往前往後切換，純顯示課程、已排讀書和 ICS 外部行程；不會因切換視圖自動重新排程。取消舊式 All-day Standby 時段。
- **操作引導**：五步引導「建立課程 → 新增待排任務 → 手動拖排 → 一鍵填滿 → LINE Mock／AI」；前兩步可以直接建立資料，第四步才會在按鈕確認時自動填滿。
- **LINE 一日 Mock**：需先開啟展示模式。選擇當天，依時間順序模擬上課、課後提醒、讀書開始與時段結束回報；仍可填寫 1–5 自評與課堂筆記儲存到隔離展示資料。**不傳送真實 LINE、也不呼叫 AI**。
- **任務管理／總覽與回饋／Markdown 與 AI**：保留 V2 已有的任務、個人學習指標、匿名訓練模板及模型 API 介面。

如果進入頁面後只看到七日板，請在「行事曆與拖排」上方點選「日／週／月」，不需要切換 Git 分支或額外安裝另一個網頁。

## 展示模式（不需要 LINE 或 AI 金鑰）

在 Streamlit 頂部開啟「展示模式（使用獨立的範例資料）」後，系統會載入**虛構、日期相對的完整教學情境**：14 門每週課程、8 張仍可拖動的待排任務、3 項已排任務（手排與自動混合）、3 項已完成任務、5 則課後回饋及 3 筆外部活動。LINE 一日 Mock 預設選擇事件較多的一天，讓展示時能連續看到上課、提醒與回報。**這些課名與時間不是任何人的正式選課紀錄或真實 LINE 活動。**

- **獨立資料：**展示資料儲存在本機 `.classpulse-demo-data/`，與正常模式的 `data/` 完全分開；切換模式不覆寫原本資料。此目錄已加入 `.gitignore`。
- **修改既有課程：**在「七日規劃板」頁面點選課程或使用修改選單，更改課名、星期、時間或提醒設定。修改展示資料後切換分頁不會被自動重設。
- **課表截圖：**「設定每週課表 → 上傳課表截圖（預覽展示）」可選 PNG、JPG、WebP，顯示圖片與檔名；**目前不會自動 OCR、解析時段或建立課程**，要修改仍使用表單。圖片不會傳至 AI API。
- **模擬 LINE：**可調整提醒設定、選一門示範課、查看模擬通知、以 1–5 分及文字輸入模擬筆記。操作只寫入展示 JSON，**不會推送 LINE**。
- **模擬 AI：**切到「Markdown 與 AI」，按「展示 AI 建議（Mock，不呼叫 API）」可生成一筆引用展示筆記 ID 的固定規則建議。按「確認並新增至讀書任務」後，可在任務與排程分頁確認結果；**不是模型實際產生的回答**。
- **還原：**按頂部「重設展示資料」可把展示課程、任務、回饋與提醒開關還原成初始虛構範例，不影響一般模式資料。 以前已開啟過展示模式的電腦，更新程式後需**主動按一次「重設展示資料」**才能把舊版三門課資料替換為豐富情境；一般網頁刷新不會覆寫你的 Demo 編輯。

關閉展示開關即可返回一般模式。正常模式仍使用原本的 Streamlit、LINE Webhook、OpenAI API 與規則式 Scheduler。

## macOS／Linux 快速啟動

專案已有 Streamlit 網頁，無須另外建立 HTML 網站。安裝 Python 3.11 以上後，在專案根目錄執行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

開啟 `http://localhost:8501`，即可使用課表、讀書排程、行事曆及 Markdown 匯出。若尚未設定 LINE 與 AI API，核心網頁功能仍可操作；真正 LINE/Webhook 需額外啟動 Flask 和提醒 Worker。以下 Windows 操作手冊提供完整的服務設定示範。

**API MVP 驗收界線：**`ai_assistant.py` 有真實 OpenAI Responses API 的 HTTP 請求、JSON Schema 驗證與錯誤處理；測試以 Mock Response 證明資料流，不代表已有真實付費 API 成功回應。

## 1. 準備環境

以下步驟以 Windows PowerShell 為例。建議使用 **64 位元 Python 3.11**；若已安裝 Python Launcher，先確認：

```powershell
py -3.11 --version
```

切換到專案資料夾（若你的資料夾位置不同，請修改路徑）：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot\python-14-studybot'
```

建立虛擬環境並安裝套件：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本手冊後續都使用 `.\.venv\Scripts\python.exe`，因此不必啟用 PowerShell 執行原則或啟用虛擬環境。

## 2. 先跑自動測試

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

通過時會看到所有測試皆通過。測試使用暫存資料，不會呼叫真實 LINE Push 或 OpenAI API。

## 3. 啟動網站並試用 A／B 功能

在專案資料夾執行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

瀏覽器通常會自動開啟 `http://localhost:8501`。若沒有自動開啟，手動輸入該網址。要停止網站，在執行它的 PowerShell 視窗按 `Ctrl+C`。

第一次啟動時，`data\` 裡的 JSON 檔是空陣列 `[]`，介面會顯示尚無資料。

### 3.1 七日十六節規劃板

開啟 **「七日規劃板」**。介面固定顯示今天（T+0）到六天後（T+6），七天各 16 格，無須上下滾動日曆本身。過去日期不會顯示，今天已經過去的節次呈灰色並禁止新增。

- 節次依序：`1 2 3 4 Z 5 6 7 8 9 A B C D E F`。每格代表整點開始的 60 分鐘規劃單位。`1–4、Z、5–9、A–D` 對照中央大學常用課表；**`E/F`（22:00／23:00）為 ClassPulse 延伸時間，不宣稱是校方正式上課節次**。
- **左側待排任務盒**：卡片右側虛線把手可水平拉伸、縮短（1–4 節）。直接拖到右側任一未佔用格；也可以先點選任務，再點目標格。
- **手動與自動完全分開**：拖入 A 只會寫入 A，B/C 不動；重新整理也不會自動排其他任務。想讓其餘任務依 Deadline → 同期限較長優先、並避開固定課和外部行程時，才點 **「一鍵填滿剩餘任務」**。
- 日曆上藍色讀書卡片可按 `×` 移回待排區；修改某一任務只影響該任務。
- **可用時段預設涵蓋七天全部未來節次**，不再需要另外填寫「指定固定時段」或勾選幾十個半小時區塊。若有外部約會或課程，就視為不可排入。

### 3.2 新增任務與外部行事曆

在 **「任務管理」** 輸入科目、任務名稱及 Deadline。新增時預設為一節 60 分鐘；不要在表單輸入數字工時或指定時間，在七日規劃板以卡片把手操作。任務完成後，可在任務管理變更狀態；完成率、Focus XP 等指標會在 **「總覽與回饋」** 更新。

在七日規劃板展開 **「外部行事曆」**，可匯入 Google、Outlook 或 Apple 匯出的 `.ics`。支援最近七天內的循環事件展開；同一事件不重複匯入，勾選覆寫才更新重複來源。點黃色外部事件，修改前會彈出確認視窗。**只修改 ClassPulse 的本機副本**，不會直接寫回 Google／Outlook；修改後可按「匯出七日行事曆（ICS）」由使用者自行重新匯入原平台。

### 3.2.1 AI 教練與匿名訓練菜單

在 **「總覽與回饋」** 查看三項回饋：任務完成率、LINE 回報完成率、Focus XP。這些是行為紀錄，**不是防作弊的學力測驗或 Elo 排名**。可選三種示範訓練型態，或使用 **匯出／匯入匿名訓練模板 JSON**，由使用者自願與同學交換粗粒度的學習節奏，不傳送學號、課名或完整行事曆。

若選擇使用 Gemini API 教練，需在本機 `.env` 或環境變數設定 `GEMINI_API_KEY`，預設模型 `gemini-2.5-flash-lite`。**使用者每次必須明確同意**，才會將必要任務／時段和彙總指標傳給 Gemini。模型提出的方案再次由本地 Deadline、衝突檢查驗證，使用者確認個別建議後才排入。沒有 API 金鑰不會假裝 AI 已完成；可使用內建訓練模板。

目前匿名模板交換是離線 Prototype，**不是真實的 NCU 多人服務或已驗證的校內排行榜**。正式團隊排行榜需要登入／群組同意、可稽核的活動紀錄及防濫用政策。

### 3.3 查看回饋、統計與下載

切到 **「回饋與進度」** 查看已送出課後提醒、已回覆課次、回覆率及任務完成數。筆記庫可依課程、課次日期與主題標籤搜尋；每筆筆記都可手動新增、修改或移除標籤。沒有成功送出的課後提醒時，回覆率會顯示「尚無資料」。

切到 **「Markdown 與 AI」**：

- 按「下載 classpulse_learning_export.md」下載目前測試使用者的學習資料。
- 匯出會讀取當下 JSON，不會自動上傳外部 AI；下載後可自行檢查內容。
- 若要使用頁面內「分析學習紀錄」，見下方「可選：AI 分析」。不設定 AI 時，其他功能及 Markdown 下載仍可使用。

## 4. 不連 LINE 也能先驗證

在專案資料夾執行測試：

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

這會驗證排程、剩餘進度重排、筆記庫篩選、固定時段衝突、簽章驗證、LINE 測試流程、提醒防重複與失敗重試。即使沒有 LINE 帳號或 Token，也可以先完成網站操作和 Markdown 匯出。

## 5. 選擇性設定真實 LINE

要收到真實 LINE 訊息，需要 LINE Official Account、Messaging API Channel、Channel Secret、Channel Access Token，以及一個 LINE 能從公網連到的 **HTTPS Webhook URL**。本機的 `localhost`／`127.0.0.1` 不能直接讓 LINE 呼叫。

### 5.1 準備 LINE Channel 憑證與綁定碼

先在 LINE Developers Console 選取正確的 Messaging API Channel：

- **Channel Secret**：在 **Basic settings** 頁面取得，供 Webhook 驗證 LINE 簽章。
- **Channel Access Token**：在 **Messaging API** 頁面簽發，供 Webhook 回覆訊息及 Worker 推播。
- **綁定碼**：自己設定的一組測試文字，並非 LINE 提供的 Token。不要使用本文件中的佔位文字。

Webhook 啟動前要設定 Channel Secret、Channel Access Token 和綁定碼；Worker 也會使用同一份 Channel Access Token。程式會自動讀取專案根目錄的 `.env`，Flask、Worker 和 Streamlit 不需要每個視窗重貼憑證。

第一次設定時，在專案資料夾的 PowerShell 執行以下命令，複製範例檔並用記事本編輯：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot\python-14-studybot'
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
notepad .env
```

在 `.env` 填入 LINE Developers 中目前有效的值，不要加 PowerShell 的 `$env:` 前綴或把等號右側留空：

```text
LINE_CHANNEL_SECRET=貼上你的ChannelSecret
LINE_CHANNEL_ACCESS_TOKEN=貼上你的ChannelAccessToken
LINE_BINDING_CODE=設定一組不易猜測的測試綁定碼
```

`.env` 也可選填 `OPENAI_API_KEY` 和 `OPENAI_MODEL` 以啟用課後 AI。存檔後重新啟動 Flask、Worker 和 Streamlit，讓各程序載入新設定。`.env` 已加入 `.gitignore`，不會被 Git 提交；仍是未加密的本機檔案，請勿放在共用／同步資料夾、截圖或分享。`.env.example` 只包含空白欄位，不要把真實憑證放進範例檔。若憑證曾曝光，請先在服務端重新簽發，再把新值存入 `.env`。

### 5.2 啟動 Webhook

在專案資料夾啟動 Flask；程式會自動讀取 `.env`：

```powershell
.\.venv\Scripts\python.exe -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000
```

瀏覽器開啟 `http://127.0.0.1:5000/health`，應看到：

```json
{"ok":true}
```

確認顯示 `{"ok":true}` 後，保持 Flask 視窗開啟。

### 5.3 啟動 HTTPS Tunnel 並設定 LINE Webhook

LINE 不能直接連到 `localhost`，需用 HTTPS Tunnel 將公網請求轉到本機 `5000` 埠。以下以 ngrok 為例：

1. 安裝 ngrok CLI：可從 [ngrok 官方下載頁](https://ngrok.com/download) 下載 Windows 版本，或使用：

   ```powershell
   winget install --id Ngrok.Ngrok --exact --source winget
   ```

2. 安裝後重新開啟 PowerShell。先設定 ngrok 執行檔路徑；若使用 winget 安裝，可執行：

   ```powershell
   $ngrok = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe'
   ```

   若你使用其他方式安裝，將路徑改成 `ngrok.exe` 的實際位置。若 ngrok 提示版本太舊，執行 `& $ngrok update`，再用 `& $ngrok version` 確認版本符合錯誤訊息要求。若 PowerShell 已能辨識 `ngrok`，也可直接使用 `ngrok` 命令。
3. 到 ngrok Dashboard 取得 **ngrok Authtoken**，在 PowerShell 設定一次。`config add-authtoken` 成功後會將 Authtoken 保存到 ngrok 自己的本機設定檔；之後啟動 Tunnel 不必再次輸入，也不需要把它放進專案 `.env`：

   ```powershell
   $ngrokToken = Read-Host '請輸入 ngrok Dashboard 的 Authtoken'
   & $ngrok config add-authtoken $ngrokToken
   $ngrokToken = $null
   & $ngrok config check
   ```

   提示出現後才貼上 Authtoken 並按 Enter。`config check` 可確認 ngrok 設定檔位置與設定是否有效，不要開啟或分享包含憑證的設定檔。Authtoken 是 ngrok 憑證，不是 LINE Channel Access Token；不要放進 README、專案 `.env` 或提交 Git。若 Authtoken 曾曝光，請在 ngrok Dashboard 撤銷並重新產生。

4. 在另一個 PowerShell 視窗啟動 Tunnel：

   ```powershell
   $ngrok = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe'
   & $ngrok http 5000
   ```

   保持視窗開啟，複製輸出中 `Forwarding https://your-ngrok-subdomain.ngrok-free.dev` 的 HTTPS 網址。

5. 在 LINE Developers Console 依序選擇 Provider → 對應的 **Messaging API Channel** → **Messaging API** 分頁 → **Webhook settings**：

   - Webhook URL 填入剛才的 HTTPS 網址並加上 `/webhook`，格式為 `https://your-ngrok-subdomain.ngrok-free.dev/webhook`。
   - 開啟 **Use webhook**，再按 **Verify**。

**Use webhook** 開啟後，LINE 才會把訊息事件送到 Flask。Webhook 只接受有效 LINE 簽章；不要為了測試而關閉簽章驗證。ngrok 網址是公開連線入口，不要公開分享；停止 Tunnel 請在該視窗按 `Ctrl+C`。Tunnel 重啟後若網址改變，需更新 Webhook URL 並再次 Verify。

### 5.4 用 LINE 綁定測試使用者

先確認專案根目錄 `.env` 的 `LINE_BINDING_CODE` 已填入你自行設定的綁定碼，不能留空或保留佔位文字；修改 `.env` 後，先停止並重新啟動 Flask，讓新設定載入。接著用自己的 LINE 加入官方帳號好友，並在聊天室傳送 `綁定 ` 加上 `.env` 中完全相同的綁定碼。例如，若 `.env` 設為 `LINE_BINDING_CODE=my-test-code-1234`，就傳送 `綁定 my-test-code-1234`。不要照抄本文件的示範碼，也不要把真實綁定碼貼到聊天或截圖。

成功時 LINE 會回覆「LINE 帳號已綁定 ClassPulse，可以開始接收提醒」。回到 Streamlit 重新整理，在「七日規劃板」的 LINE 提醒設定確認已綁定，並打開想測試的提醒。若回覆「綁定碼不正確或尚未設定」，請檢查 `.env` 的值非空、訊息和它完全相同，並確認 Flask 已在修改後重新啟動。

### 5.5 啟動常駐提醒 Worker

另開一個 PowerShell 視窗，切到專案資料夾並啟動 Worker。Worker 會自動讀取相同的 `.env`，不必再貼一次 Token：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot\python-14-studybot'
.\.venv\Scripts\python.exe reminder_worker.py
```

保持視窗開啟。Worker 每分鐘檢查課後提醒、讀書開始／結束進度確認及尚未送出的未排入警示。要停止 Worker，在該視窗按 `Ctrl+C`。

若沒設定 `LINE_CHANNEL_ACCESS_TOKEN`，Worker 只輸出「未實際推送」的模擬訊息，不會把提醒標記為 `sent`。`sent` 只代表 LINE API 接受請求，不代表使用者已讀。

### 5.6 實際測一次讀書時段提醒

1. 確認 LINE 已綁定，並在 Streamlit 打開「接收讀書開始提醒與結束進度確認」。
2. 新增一個開始時間在未來幾分鐘內的可用時段，分鐘數要足以容納任務。
3. 新增 Deadline 晚於該時段的任務，預估分鐘數不要大於時段長度。
4. 按「產生／重新安排計畫」，確認任務已排在該時段。
5. 開始提醒會同時顯示科目與任務名稱，例如「讀書時段開始囉！任務：科目「英文」，ch2，請開始完成。」
5. 在排程開始前先啟動 Worker 並保持執行；時段開始後等候最多約一分鐘。
6. 確認 LINE 收到任務提醒；`data\reminders.json` 中該筆提醒應為 `study_session`，成功時狀態為 `sent`。同一任務／時段不會重複送出。
7. 任務預估時長結束時，LINE 會詢問進度。依訊息回覆「完成 任務代碼」或「未完成 任務代碼」；未完成時再輸入剩餘分鐘數，Webhook 會以剩餘時間重新安排。若只有一筆待確認任務，也可直接回覆「完成」或「未完成」。沒有回覆不會標記完成；可在任務修改區手動更新剩餘分鐘，再按「產生／重新安排計畫」。

要測未排入警示，可建立預估時間超過所有可用時段的任務、重新排程，確認頁面顯示原因並等待 Worker 發送警示。

### 5.7 實際測一次課後提醒與補筆記

1. 確認 Worker 正在執行、LINE 已綁定，而且「接收課後提醒與未排入警示」已打開。
2. 在 Streamlit 新增一門課，星期選今天、下課時間設為幾分鐘後，提醒偏移設 `0`。開始時間必須早於下課時間。
3. 保持 Worker 執行。課程結束後約一分鐘內，LINE 應收到課後提醒；首次觸發需在排定提醒時間後 5 分鐘內。
4. 在 LINE **輸入** `補筆記`，依序選星期、回覆課表清單上的編號、回報理解進度 `1` 至 `5`，再輸入上課重點或疑問。
5. 已在 Streamlit 啟用 AI 同意且 Flask 設定 OpenAI API 時，LINE 會回傳整理摘要、課堂重點、待釐清問題與一項複習任務建議。回覆「加入讀書任務」後才會建立任務並依可用時段排程；回覆「先不用」只保留筆記。未啟用 AI 時，筆記與進度仍會照常保存。
6. 如果手動補登的課次沒有成功送出的課後提醒，筆記仍會保存，但不會計入提醒回覆率。

筆記日期只會定位最近 7 天內已結束的同星期課次。輸入 `取消` 可中止流程；選課後 10 分鐘沒有完成時，狀態會逾時清除。Webhook 狀態和筆記分別可在 `data\processed_webhooks.json`、`data\feedback.json` 查看。

## 6. 可選：啟用內建 AI 課後整理

AI 整理不是記錄課後回饋或手動排程的必要條件。若要讓 LINE 回饋後自動整理筆記，請在 `.env` 填入 OpenAI API Key 和支援 Structured Outputs 的模型名稱，然後重新啟動 Flask 與 Streamlit。

在 Streamlit「LINE 提醒設定」勾選並儲存「同意使用 AI 整理課後筆記並建議複習任務」。每次回饋只會把課程名稱、筆記文字及使用者自評進度送至 OpenAI，不會傳送 LINE User ID 或資料 ID。OpenAI API 可能依帳戶方案計費。AI 建議的複習任務必須先由使用者在 LINE 確認；確認後才新增，接著由既有規則式 scheduler 依期限、已固定任務與可用時段安排，不是讓模型直接改動行事曆。預設 Deadline 為課後 7 天，可在 Streamlit 修改。

若未同意或 API 尚未設定，筆記與進度仍會保存，但不會送往 AI。API 失敗時也會保留原始回饋。舊的「Markdown 與 AI」頁面仍可在使用者另行同意後，手動分析匯出的學習資料。不要把 API Key 放進 `.env.example`、README、截圖或 Git。

## 7. 常用資料檔與重置

| 檔案 | 用途 |
|---|---|
| `data\events.json` | 課表 |
| `data\tasks.json` | 任務與完成狀態 |
| `data\availability.json` | 可用讀書時段 |
| `data\plan.json` | 最近一次排程及未排入狀態 |
| `data\users.json` | LINE 綁定、提醒開關及課後 AI 同意設定 |
| `data\reminders.json` | 推送類型、狀態、時間及 retry key |
| `data\feedback.json` | LINE 筆記、自評進度及可選 AI 整理結果 |
| `data\pending_notes.json` | 暫存中的補筆記／AI 任務確認流程 |
| `data\processed_webhooks.json` | 已處理的 Webhook ID |

開始前可備份 `data\`。要清空測試資料時，請先停止 Streamlit、Webhook、Worker，再將上述 JSON 檔內容逐一改成 `[]`；不要刪除或覆寫有用的正式資料。`CLASSPULSE_DATA_DIR` 可將資料指定到另一個本機資料目錄。

## 8. 常見問題

- **`py -3.11` 找不到**：安裝 64 位 Python 3.11，再重做虛擬環境。Windows 32 位 Python 可能沒有 Streamlit 所需套件的安裝檔。
- **`localhost:8501` 無法開啟**：確認 Streamlit 視窗沒有錯誤並仍在執行；若提示埠號已使用，先關閉舊程序或改用 `--server.port 8502`。
- **`ngrok` 無法辨識**：安裝後重新開啟 PowerShell／VS Code，讓 PATH 更新；確認 Flask 正在 `5000` 埠，並以 `ngrok http 5000` 啟動 Tunnel。
- **ngrok 顯示 `ERR_NGROK_121` 或版本過舊**：執行 `ngrok update`，再執行 `ngrok version` 確認已更新。ngrok Authtoken 無效時，從 ngrok Dashboard 重新取得並執行 `ngrok config add-authtoken`；不要使用 LINE Token 代替。
- **Flask 日誌顯示 `POST /Webhook 404`**：路徑大小寫不同。程式只註冊小寫 `/webhook`；請在 LINE Developers 將 Webhook URL 改成 `https://你的-ngrok-網址/webhook`（全小寫）後再按 **Verify**。此時請求尚未進入簽章驗證；若改好後變成 401，再依下方檢查 Channel Secret。
- **LINE Verify 顯示 401**：代表請求已到 Flask，但簽章驗證失敗。確認 `LINE_CHANNEL_SECRET` 是同一個 Messaging API Channel 的 **Basic settings → Channel secret**，不是 Channel Access Token；設定環境變數後必須重新啟動 Flask，因程式在啟動時讀取 Secret。確認 URL 使用目前 Tunnel 網址並以 `/webhook` 結尾。
- **LINE 沒收到提醒**：確認 Worker 還在執行、Access Token 正確、使用者已綁定，Streamlit 的對應提醒開關已啟用；讀書任務需是 pending 且目前排程仍指向該時段。
- **排程顯示未排入**：確認時段日期在未來、Deadline 不早於時段結束、時段長度足夠且沒有重疊；頁面會列出原因。
- **補筆記沒有對到課程**：確認使用者已綁定、星期與課表一致，且該課在最近 7 天內已結束。
- **JSON 資料格式錯誤**：程式會停止寫入以避免覆蓋壞檔；先備份並修復該 JSON，確認它是有效陣列後再重啟。

## 9. 安全與部署限制

`data\` 可能含個人筆記與 LINE User ID；不要提交、公開或放進不可信任的雲端。真實 Token／Secret 只放在本機或部署環境變數，不要提交 `.env`，也不要貼到聊天、截圖或 README。若憑證曾貼出或提交，請立即在對應服務撤銷／重新簽發；只從文件刪除並不足以讓舊憑證失效。檔案鎖只適用共享的本機檔案系統；不支援跨機器交易、正式多人帳號或高併發部署。
