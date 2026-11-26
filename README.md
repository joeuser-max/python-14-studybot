# ClassPulse｜A／B 整合版操作手冊

這份手冊從第一次安裝開始，帶你測試課表、讀書排程、進度／Markdown 匯出，以及選擇性 LINE 整合。

- **A 功能**：Streamlit 介面、JSON 資料、安全儲存、回覆統計、Markdown 匯出、經同意後的 AI 筆記整理。
- **B 功能**：固定／自動讀書排程、LINE Webhook 補筆記、課後與讀書時段提醒 Worker。
- **目前限制**：單一測試使用者 `demo_user_001`、本機 JSON 資料；不是正式多人服務。

## 1. 準備環境

以下步驟以 Windows PowerShell 為例。建議使用 **64 位元 Python 3.11**；若已安裝 Python Launcher，先確認：

```powershell
py -3.11 --version
```

切換到專案資料夾（若你的資料夾位置不同，請修改路徑）：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot'
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

### 3.1 建立課表與可用讀書時段

在 **「課表與時段」** 分頁最上方會看到整合行事曆：

1. 預設是週檢視；右上角可切換月檢視或日檢視，使用「今天／上一個／下一個」瀏覽日期。
2. **紅色**代表每週重複的課程；**綠色**代表指定日期的可用讀書時段；**藍色**代表已排定的讀書任務。
3. 每週課程依星期重複顯示；可用讀書時段只在實際設定日期出現。
4. 在行事曆下方可新增課程與可用時段；也可點選行事曆項目，或在修改區的下拉選單選取資料，調整後按「儲存課程修改」或「儲存時段修改」。

新增資料的方式：

1. 在「設定每週課表」填課名、星期、上課／下課時間。
2. 要測課後提醒時，把提醒偏移設為 `0`；單純試介面時可用任何分鐘數。
3. 按「新增課程」。
4. 在「新增可用讀書時段」選一個**未來日期**，再勾選有空的半小時區塊並按「新增時段」；連續區塊會自動合併為一段時段。已過去、與課程衝突或已設定為可用的區塊會停用。
5. 課表或時段輸入錯誤時，可點行事曆中的項目，修改區會帶入該筆資料；也能直接從下拉選單選擇。修改時段會清除舊讀書計畫；刪除時段前先勾選確認，若有任務固定在該時段，會解除固定。修改或刪除後請重新產生計畫。
6. 在「LINE 提醒設定」可先打開或關閉課後／未排入提醒、讀書時段開始提醒。尚未綁定 LINE 時，設定可以保存，但不會實際推送。

星期使用 ISO 格式：1＝週一、2＝週二、…、7＝週日。

### 3.2 建立任務並產生計畫

切到 **「讀書任務與排程」**：

1. 填科目、任務名稱、Deadline、預估分鐘數。
2. 「指定固定時段」留在「自動安排」表示交給排程器安排；也可以選一個可用時段固定任務。
3. 按「新增任務」。
4. 按「產生／重新安排計畫」查看結果。
5. 回到「課表與時段」分頁，行事曆會以藍色顯示已排定任務的科目、任務名稱及讀書起訖時間；未排入與已完成任務不會顯示為讀書事件。

排程會先保留有效的固定時段，再依 Deadline（相同 Deadline 時較長任務優先）安排其他任務；自動安排會挑選足夠且剩餘時間最少的時段。沒有可排時，結果會顯示「尚未排入」與原因。固定時段無效或衝突時不會自動偷偷換到別的時段。

要測無法排入：建立一個預估分鐘數大於所有可用時段的任務，再重新產生計畫。

要修改任務名稱、期限或狀態：在任務清單下方的「修改任務名稱、狀態與期限」選擇任務，調整任務名稱、Deadline 或狀態後按「儲存任務修改」。修改會清除目前測試使用者的舊計畫，請再按「產生／重新安排計畫」；標記為 `completed` 的任務不會再被安排。

### 3.3 查看回饋、統計與下載

切到 **「回饋與進度」** 查看已送出課後提醒、已回覆課次、回覆率及任務完成數。沒有成功送出的課後提醒時，回覆率會顯示「尚無資料」。

切到 **「Markdown 與 AI」**：

- 按「下載 classpulse_learning_export.md」下載目前測試使用者的學習資料。
- 匯出會讀取當下 JSON，不會自動上傳外部 AI；下載後可自行檢查內容。
- 若要使用頁面內「分析學習紀錄」，見下方「可選：AI 分析」。不設定 AI 時，其他功能及 Markdown 下載仍可使用。

## 4. 不連 LINE 也能先驗證

在專案資料夾執行測試：

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

這會驗證排程、固定時段衝突、簽章驗證、LINE 測試流程、提醒防重複與失敗重試。即使沒有 LINE 帳號或 Token，也可以先完成網站操作和 Markdown 匯出。

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
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot'
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
3. 到 ngrok Dashboard 取得 **ngrok Authtoken**，在 PowerShell 設定一次：

   ```powershell
   $ngrokToken = Read-Host '請輸入 ngrok Dashboard 的 Authtoken'
   & $ngrok config add-authtoken $ngrokToken
   $ngrokToken = $null
   ```

   提示出現後才貼上 Authtoken 並按 Enter。Authtoken 是 ngrok 憑證，不是 LINE Channel Access Token；只在本機輸入，不要放進 README 或提交 Git。

4. 在另一個 PowerShell 視窗啟動 Tunnel：

   ```powershell
   $ngrok = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe'
   & $ngrok http 5000
   ```

   保持視窗開啟，複製輸出中 `Forwarding https://company-record-valuables.ngrok-free.dev` 的 HTTPS 網址。

5. 在 LINE Developers Console 依序選擇 Provider → 對應的 **Messaging API Channel** → **Messaging API** 分頁 → **Webhook settings**：

   - Webhook URL 填入剛才的 HTTPS 網址並加上 `/webhook`，格式為 `https://company-record-valuables.ngrok-free.dev/webhook`。
   - 開啟 **Use webhook**，再按 **Verify**。

**Use webhook** 開啟後，LINE 才會把訊息事件送到 Flask。Webhook 只接受有效 LINE 簽章；不要為了測試而關閉簽章驗證。ngrok 網址是公開連線入口，不要公開分享；停止 Tunnel 請在該視窗按 `Ctrl+C`。Tunnel 重啟後若網址改變，需更新 Webhook URL 並再次 Verify。

### 5.4 用 LINE 綁定測試使用者

先用自己的 LINE 加入官方帳號好友，然後在聊天室傳送 `綁定 studybot-test-2026-7391`。例如若你設定的碼是 `my-test-code-1234`，就傳送 `綁定 my-test-code-1234`；`<...>` 和文件中的佔位文字不要照抄。

成功後，Webhook 會將該 LINE 帳號綁定至 `demo_user_001`。回到 Streamlit 重新整理，在「課表與時段」的 LINE 提醒設定確認已綁定，並打開想測試的提醒。綁定碼錯誤時，確認 Flask 啟動前設定的 `LINE_BINDING_CODE` 與傳送內容完全相同。

### 5.5 啟動常駐提醒 Worker

另開一個 PowerShell 視窗，切到專案資料夾並啟動 Worker。Worker 會自動讀取相同的 `.env`，不必再貼一次 Token：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot'
.\.venv\Scripts\python.exe reminder_worker.py
```

保持視窗開啟。Worker 每分鐘檢查課後提醒、讀書時段提醒及尚未送出的未排入警示。要停止 Worker，在該視窗按 `Ctrl+C`。

若沒設定 `LINE_CHANNEL_ACCESS_TOKEN`，Worker 只輸出「未實際推送」的模擬訊息，不會把提醒標記為 `sent`。`sent` 只代表 LINE API 接受請求，不代表使用者已讀。

### 5.6 實際測一次讀書時段提醒

1. 確認 LINE 已綁定，並在 Streamlit 打開「接收讀書時段開始提醒」。
2. 新增一個開始時間在未來幾分鐘內的可用時段，分鐘數要足以容納任務。
3. 新增 Deadline 晚於該時段的任務，預估分鐘數不要大於時段長度。
4. 按「產生／重新安排計畫」，確認任務已排在該時段。
5. 在排程開始前先啟動 Worker 並保持執行；時段開始後等候最多約一分鐘。
6. 確認 LINE 收到任務提醒；`data\reminders.json` 中該筆提醒應為 `study_session`，成功時狀態為 `sent`。同一任務／時段不會重複送出。

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
