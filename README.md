# ClassPulse｜A／B 整合版操作手冊

這份手冊從第一次安裝開始，帶你測試課表、讀書排程、進度／Markdown 匯出，以及選擇性 LINE 整合。

- **A 功能**：Streamlit 介面、JSON 資料、安全儲存、回覆統計、Markdown 匯出、可選 AI 建議。
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

通過時會看到所有測試皆通過（目前 17 項；數量可能隨後續更新增加）。測試使用暫存資料，不會呼叫真實 LINE Push 或 OpenAI API。

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
4. 在「新增可用讀書時段」選一個**未來日期**、開始時間及可用分鐘，再按「新增時段」。同一人的可用時段不可重疊。
5. 課表或時段輸入錯誤時，可點行事曆中的項目，修改區會帶入該筆資料；也能直接從下拉選單選擇。修改可用時段後，舊讀書計畫會清除，請重新產生計畫。
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

要測完成狀態：在任務清單下方選任務，將狀態改為 `completed`，按「更新狀態」後重新產生計畫。完成的任務不會再被排讀書時段。

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

### 5.1 設定 Webhook 與 Worker 使用的環境變數

在一個新的 PowerShell 視窗切到專案資料夾，設定自己的值（不要把真實值貼到程式碼或提交 Git）：

```powershell
Set-Location 'C:\Users\yuzhe\Desktop\程式設計-python期末專案作業\python-14-studybot'
$env:LINE_CHANNEL_SECRET = '你的 Channel Secret'
$env:LINE_CHANNEL_ACCESS_TOKEN = '你的 Channel Access Token'
$env:LINE_BINDING_CODE = '自己設定一組測試綁定碼'
```

環境變數只作用於這個 PowerShell 視窗及其子程序；**Webhook 和 Worker 各自使用不同視窗時，兩邊都要設定一次**。`.env.example` 只有假值，而且程式不會自動讀取 `.env`。

### 5.2 啟動 Webhook

在已設定上面三個環境變數的視窗執行：

```powershell
.\.venv\Scripts\python.exe -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000
```

瀏覽器開啟 `http://127.0.0.1:5000/health`，應看到：

```json
{"ok":true}
```

再使用你信任且允許的 HTTPS Tunnel／部署主機，將外部 HTTPS 請求轉到本機 `5000` 埠。在 LINE Developers Console：

1. 將 Webhook URL 設為 `https://你的公開網址/webhook`。
2. 啟用 **Use webhook**。
3. 按 **Verify**；驗證失敗時先確認 Tunnel 正在執行、網址路徑是 `/webhook`，且 Channel Secret 正確。

Webhook 只接受有效 LINE 簽章。不要為了測試而關閉簽章驗證，也不要把測試 Tunnel 公開給不可信任的人。

### 5.3 用 LINE 綁定測試使用者

在 LINE 對你的官方帳號傳送：

```text
綁定 你設定的測試綁定碼
```

成功後，Webhook 會將該 LINE 帳號綁定至 `demo_user_001`。回到 Streamlit 重新整理，在「課表與時段」的 LINE 提醒設定確認已綁定，並打開想測試的提醒。綁定碼錯誤時，確認 Webhook 視窗有設定相同的 `LINE_BINDING_CODE`。

### 5.4 啟動常駐提醒 Worker

另開一個 PowerShell 視窗，切到專案資料夾並**重新設定相同的三個環境變數**，然後執行：

```powershell
.\.venv\Scripts\python.exe reminder_worker.py
```

保持視窗開啟。Worker 每分鐘檢查課後提醒、讀書時段提醒及尚未送出的未排入警示。要停止 Worker，在該視窗按 `Ctrl+C`。

若沒設定 `LINE_CHANNEL_ACCESS_TOKEN`，Worker 只輸出「未實際推送」的模擬訊息，不會把提醒標記為 `sent`。`sent` 只代表 LINE API 接受請求，不代表使用者已讀。

### 5.5 實際測一次讀書時段提醒

1. 確認 LINE 已綁定，並在 Streamlit 打開「接收讀書時段開始提醒」。
2. 新增一個開始時間在未來幾分鐘內的可用時段，分鐘數要足以容納任務。
3. 新增 Deadline 晚於該時段的任務，預估分鐘數不要大於時段長度。
4. 按「產生／重新安排計畫」，確認任務已排在該時段。
5. 在排程開始前先啟動 Worker 並保持執行；時段開始後等候最多約一分鐘。
6. 確認 LINE 收到任務提醒；`data\reminders.json` 中該筆提醒應為 `study_session`，成功時狀態為 `sent`。同一任務／時段不會重複送出。

要測未排入警示，可建立預估時間超過所有可用時段的任務、重新排程，確認頁面顯示原因並等待 Worker 發送警示。

### 5.6 實際測一次課後提醒與補筆記

1. 確認 Worker 正在執行、LINE 已綁定，而且「接收課後提醒與未排入警示」已打開。
2. 在 Streamlit 新增一門課，星期選今天、下課時間設為幾分鐘後，提醒偏移設 `0`。開始時間必須早於下課時間。
3. 保持 Worker 執行。課程結束後約一分鐘內，LINE 應收到課後提醒；首次觸發需在排定提醒時間後 5 分鐘內。
4. 在 LINE **輸入** `補筆記`，依序選星期、回覆課表清單上的編號，再輸入至少兩個字的筆記或疑問。
5. LINE 回覆「筆記已儲存」後，回到 Streamlit「回饋與進度」查看紀錄及統計。
6. 如果手動補登的課次沒有成功送出的課後提醒，筆記仍會保存，但不會計入提醒回覆率。

筆記日期只會定位最近 7 天內已結束的同星期課次。輸入 `取消` 可中止流程；選課後 10 分鐘沒有完成時，狀態會逾時清除。Webhook 狀態和筆記分別可在 `data\processed_webhooks.json`、`data\feedback.json` 查看。

## 6. 可選：啟用頁面內 AI 分析

AI 分析不是執行排程或下載 Markdown 的必要條件。若要使用，先在**啟動 Streamlit 的同一個 PowerShell 視窗**設定可用的 OpenAI API Key 與支援 Structured Outputs 的模型名稱：

```powershell
$env:OPENAI_API_KEY = '你的私有 API Key'
$env:OPENAI_MODEL = '你可使用的模型名稱'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

在「Markdown 與 AI」勾選同意後按「分析學習紀錄」。只有按下按鈕才會把遮蔽後的資料送至外部 API。建議必須由你確認後才會新增任務；不會自動修改排程。不要把 API Key 放進 `.env.example`、README、截圖或 Git。

## 7. 常用資料檔與重置

| 檔案 | 用途 |
|---|---|
| `data\events.json` | 課表 |
| `data\tasks.json` | 任務與完成狀態 |
| `data\availability.json` | 可用讀書時段 |
| `data\plan.json` | 最近一次排程及未排入狀態 |
| `data\users.json` | 測試使用者 LINE 綁定與提醒開關 |
| `data\reminders.json` | 推送類型、狀態、時間及 retry key |
| `data\feedback.json` | LINE 補筆記紀錄 |
| `data\pending_notes.json` | 暫存中的補筆記流程 |
| `data\processed_webhooks.json` | 已處理的 Webhook ID |

開始前可備份 `data\`。要清空測試資料時，請先停止 Streamlit、Webhook、Worker，再將上述 JSON 檔內容逐一改成 `[]`；不要刪除或覆寫有用的正式資料。`CLASSPULSE_DATA_DIR` 可將資料指定到另一個本機資料目錄。

## 8. 常見問題

- **`py -3.11` 找不到**：安裝 64 位 Python 3.11，再重做虛擬環境。Windows 32 位 Python 可能沒有 Streamlit 所需套件的安裝檔。
- **`localhost:8501` 無法開啟**：確認 Streamlit 視窗沒有錯誤並仍在執行；若提示埠號已使用，先關閉舊程序或改用 `--server.port 8502`。
- **LINE Verify 失敗／Webhook 401**：核對 Channel Secret、公開 HTTPS URL、`/webhook` 路徑和簽章設定；不可將 `LINE_CHANNEL_SECRET` 誤填成 Access Token。
- **LINE 沒收到提醒**：確認 Worker 還在執行、Access Token 正確、使用者已綁定，Streamlit 的對應提醒開關已啟用；讀書任務需是 pending 且目前排程仍指向該時段。
- **排程顯示未排入**：確認時段日期在未來、Deadline 不早於時段結束、時段長度足夠且沒有重疊；頁面會列出原因。
- **補筆記沒有對到課程**：確認使用者已綁定、星期與課表一致，且該課在最近 7 天內已結束。
- **JSON 資料格式錯誤**：程式會停止寫入以避免覆蓋壞檔；先備份並修復該 JSON，確認它是有效陣列後再重啟。

## 9. 安全與部署限制

`data\` 可能含個人筆記與 LINE User ID；不要提交、公開或放進不可信任的雲端。真實 Token／Secret 只放在本機或部署環境變數，不要提交 `.env`。檔案鎖只適用共享的本機檔案系統；不支援跨機器交易、正式多人帳號或高併發部署。
