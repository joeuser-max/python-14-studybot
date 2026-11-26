# ClassPulse｜學習助理控制台

ClassPulse 將課後筆記、AI 建議、讀書任務和時間安排連成一條流程。**LINE 是日常互動入口；AI Model API 負責筆記分析；Streamlit 是設定與管理控制台；Google／Apple Calendar 用於手機查看。**

這是第 14 組 Python 課程的可執行 MVP，不是正式上線的多人 SaaS。

## 正確啟動網頁：始終使用最新已合併的 main

**版本與網址是兩回事。** GitHub 的 main 才是已合併的正式版本；功能分支／PR 尚未合併的版本不會自動出現在 main。本機 Streamlit 也不會因為 GitHub 更新而自行同步。**舊的 localhost:8501 可能還有舊程序在執行，因此我們統一使用 http://localhost:8502。**

新版啟動器會先執行 GitHub main 的安全更新（git fetch → git switch main → git pull --ff-only），再檢查 Python、安裝套件、顯示「分支及 Commit」，最後在固定的 8502 Port 開啟。遇到網路失敗、無法安全更新或 Port 已占用就會停下來，**不會偷偷改成別的 Port、強制刪除本機修改或啟動舊版**。

### macOS：第一次安裝（整段複製）

在 Terminal 貼上：

~~~bash
git clone https://github.com/joeuser-max/python-14-studybot.git ~/ClassPulse-Demo
bash ~/ClassPulse-Demo/start_mac.sh
~~~

如果顯示「destination path already exists」，不用再次 Clone。用下面的已安裝流程。

### macOS：已經有資料夾，以後這樣開（整段複製）

~~~bash
cd ~/ClassPulse-Demo
git fetch origin main
git switch main
git pull --ff-only origin main
bash ./start_mac.sh
~~~

如果專案不在 ~/ClassPulse-Demo，先開 Finder，將專案資料夾拖到 Terminal 的 cd 後面，再執行後三行。新版啟動器日後會自動更新 main；上面額外的 Git 步驟是為了讓舊版啟動器也確實升級。

### Windows PowerShell：第一次使用或已安裝皆可（整段複製）

~~~powershell
$project = Join-Path $HOME "ClassPulse-Demo"
if (-not (Test-Path (Join-Path $project ".git"))) {
    if (Test-Path $project) { throw "資料夾已存在但不是 Git 專案；請先檢查位置" }
    git clone https://github.com/joeuser-max/python-14-studybot.git $project
    if ($LASTEXITCODE -ne 0) { throw "Git Clone 失敗" }
}
Set-Location $project
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw "Git fetch 失敗" }
git switch main
if ($LASTEXITCODE -ne 0) { throw "無法安全切換 main" }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw "無法安全更新 main" }
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_windows.ps1
~~~

之後可以直接執行最後一行，新版 Windows 啟動器會自行更新主線，使用專案內的 .venv\Scripts\python.exe，不需要 Activate.ps1。

### 我如何確認不是舊版本？

啟動後的 Terminal／PowerShell 應同時顯示以下三個資訊：

- **ClassPulse：main / [Git Commit 短碼]**
- **專案資料夾：...**（實際執行的原始碼目錄）
- **網站網址：http://localhost:8502**

在網頁左側 ClassPulse 標題下，會再顯示「目前程式：main · [相同短碼]」。展開「查看執行目錄及版本」，檢查是不是同一個資料夾。**短碼會隨每次新的合併而改變，請勿把以前的 SHA 當成永久正確版本。**

需要查本機狀態可以用：

~~~bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --show-toplevel
~~~

### 常見情況

| 現象 | 正確處理 |
| --- | --- |
| 開到舊介面或原本的四個水平 Tab | 你可能開了舊的 localhost:8501；請關閉舊 Terminal 程序（Control/Ctrl + C），改用 8502 和新版啟動器 |
| requirements.txt 找不到 | 目前不在專案根目錄；啟動器會自行切換目錄。用 git rev-parse --show-toplevel 檢查 |
| No module named streamlit | 先讓啟動器完成安裝步驟，不要只執行 python -m streamlit run app.py |
| Port 8502 已被使用 | 先關閉原先啟動 8502 的 Terminal，然後重跑啟動器；不要開另一個 Port 猜版本 |
| 無法切換分支／拉取更新 | 請先 git status 檢查是否有本機修改；不會自動 git reset --hard 或刪除工作 |
| 網頁版本正確但展示資料還是舊的 | 既有 .classpulse-demo-data 是持久資料。若想還原最新示範內容，可在側欄按「還原展示資料」；**會覆寫展示期間的修改** |

需要 Git 與 Python 3.11 以上版本。localhost 網址只能從啟動網站的電腦直接存取；沒有自動上線成公共網址。

## 網頁首次使用：從設定到完成一天

第一次開網站會看到 **5 個逐步引導**；每一步只要做當前那件事，就可以往下一步。沒有課表、還沒接 LINE 或 AI，都能跳過：

1. **先認識流程**：網站負責設定／控制、LINE 負責課後筆記、AI 負責提建議、Scheduler 依規則排時間。想試用範例，先切換側欄「展示模式」。
2. **新增課程**：在表單輸入課名、星期、上課時間。上傳截圖目前只會顯示圖片，**不會自動辨識**；已新增課程稍後可從「時間規劃」修改。
3. **了解 LINE／AI**：按「LINE 一日展示」可看固定三選一互動。真正連接 LINE 需部署 Bot 和 Webhook；AI 建議須由本人確認後才建立任務。
4. **建立任務與可用時間**：至少新增一項待辦與一個空檔。完成設定後到「時間規劃」的 Timesheet，可將待排方塊拖入日／週時間格、拉長或縮短，確認才儲存。
5. **行事曆匯出**：按下載 .ics，將目前的已排時段帶到 Google／Apple Calendar。這只是一次性匯入，之後在網站修改時不會自動同步。

完成後，側欄可以看到「總覽／我的任務／時間規劃／學習回饋／AI 助理／連接與匯出／LINE 一日展示／首次設定」。首頁能看待辦及日週月完成曲線；點任務卡片可直接改名、調整完成百分比或刪除。所有設定均可在日後繼續編輯。

**要確認自己的版本：**看側欄「目前程式：main · Commit 短碼」。舊版若沒有這項資訊，應先確認是否開錯 localhost Port 或還沒更新程式。

## 附加展示：LINE 從 08:00 到 21:00 的一天

側欄「LINE 一日展示」不需要 LINE API Key、Webhook 或 OpenAI API Key。它有 **13 個依時間排序的場景**，每個場景提供 **3 個預設訊息選項**，按下後立即顯示相應的 LINE 虛擬回覆，不必輸入文字。可逐段繼續、一鍵播放完整一天，或重播。

包含：08:00 早晨規劃 → 課前提醒 → 課程 → 課後理解度 → 補筆記 → Mock AI 分析 → 使用者確認任務 → 規則式排程 → 無法排入提醒 → 手機行事曆 → 19:00 讀書提醒 → 任務完成度 → 21:00 當日回顧。

虛擬引擎追蹤當天的理解度、筆記、是否接受 AI 任務、排程選項及進度，以免拒絕任務後卻顯示已完成安排。**這些都是模擬選擇；絕不對外發送 LINE、不呼叫模型、不覆寫正式任務或資料。**

## 展示模式資料

這版展示課表依使用者提供的「1151 學期 A4 課表」截圖，整理 **14 個每週課次**（包含不同星期的同名課程）。只保存課名、星期、上課時間及教室，**不寫入截圖上的姓名或學號**。

展示總覽另增加 **8 項已完成任務**及相對應的範例完成事件，分布在近一天、一週及一個月，讓 `1D / 1W / 1M` 可以切換看到不同成果。這些數據僅在展示模式中，並非真實讀書紀錄。也會提供「✦ AI 建議」待辦，方便辨認不同來源。

與固定課程發生重疊時，**拖曳／拉長後立即跳出「確認時段調整」視窗**：顯示被覆蓋的課程與時間，先選擇「不覆蓋」或「覆蓋」，後者必須提供「請假／翹課／停課」原因，才會寫入真正的排程。這不會向學校提出請假。

**升級既有本機展示資料：** 因為展示 JSON 預設保留使用者調整，更新程式不會自動覆寫已建立的展示資料。請進入側欄「展示模式」後按 **「還原展示資料」**，才會完整載入新版課表與完成紀錄。這個操作會清除之前在展示模式做的修改，正式資料不受影響。

## 外部行事曆

- 下載 **classpulse.ics**：包含接下來 12 週的固定課程，以及已排入、未完成的讀書任務。Google 或 Apple Calendar 可匯入檔案。
- 點擊排程卡片的「新增到 Google Calendar」：在 Google Calendar 預填事件，使用者自行確認後才新增。
- **目前是單向匯出**，不是 OAuth 授權或雙向同步。日後修改任務必須重新匯入，避免對使用者宣稱自動更新。

## 視覺化時間規劃（正式可操作功能）

「時間規劃」頁面顯示以 FullCalendar 建立的週／日 Timesheet：

1. 紅色固定課程不可拖動；已過去、已開始的讀書時間無法變更。
2. 未排程任務以灰色／紫色方塊放在日曆上方的「全天」待排列，拖入時間格即可提出安排。紫色 ✦ AI 代表「由 AI 建議且使用者已確認加入」的任務，不表示 AI 自行決定排程。
3. 未來的藍／紫色讀書方塊可以再拖動或拉長／縮短，時間以 15 分鐘為格。放開滑鼠後會顯示確認區；**只有按「確認並儲存」才會寫入 JSON**。可將方塊移回待排區，觸控／手機提供備用表單。
4. 與另一項讀書任務重疊會拒絕；若與每週課程重疊，必須選擇「請假」「翹課」「停課」才能繼續。該選擇只記錄本人原因，不會通知學校或更改課表。
5. 手動固定任務優先，再使用原有的 Deadline → 預估時間 → Best Fit 規則處理其餘任務。**自動排程不再允許與固定課表衝突**。若可用時段部分與課程重疊，目前保守排除整段；可改用手動拖曳選擇空出的部分。尚未支援將一項任務拆成多段自動排程。
6. 時間表中的淺綠「可用時間」背景來自使用者資料，不是演算法憑空產生的時段。

**資料持久性：** 手動拖放會更新任務的估時、固定時段與 plan.json；讀書提醒 Worker 及 ICS 匯出繼續使用同一組排程。單機 JSON 的跨檔案更新沒有完整資料庫交易保證，不適合直接當成多人上線服務。

## 日／週／月學習成果

Dashboard 的「學習成果」可切換 1D、1W、1M，從 progress_events.json 計算**已透過任務編輯保存的完成事件**。呈現完成數、完成任務的預估分鐘與累積完成曲線。**不計算真實計時工時**，也不假造導入功能前的完成時間。

新展示模式會放入一筆標示為 demo_seed 的完成範例，用來說明圖表；一般模式絕不匯入展示成績。若已有展示資料，須在側欄按「還原展示資料」才會載入新增範例。重設會覆蓋展示資料，請先確認。

## 校園資源

側欄低調提供 [中央大學圖書館空間預約](https://mwa.lib.ncu.edu.tw/pwaspace/) 和 [中央大學 ee-class](https://ncueeclass.ncu.edu.tw/)。ClassPulse 不替學生訂位，也不自動讀取學校帳戶資料。

## 真正的 LINE／AI 模組

要測試真實 LINE：在私有環境設定 LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN、LINE_BINDING_CODE，並提供安全、公開的 HTTPS Webhook URL；在另外兩個終端執行：

    python -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000
    python reminder_worker.py

AI API 使用 OPENAI_API_KEY 與 OPENAI_MODEL；可使用正式 Responses API 及 JSON Schema 解析結果。沒有金鑰時可以驗證 Mock 測試，但**Mock 不等於真實 API 呼叫成功**。密鑰、真實課表與個人筆記不應提交 GitHub。

## 測試與 Git 協作

    python -m pytest -q

GitHub Actions 另做 Python 語法檢查、Streamlit HTTP 啟動檢查和 Streamlit AppTest。HTTP 啟動成功不代表每個 UI 互動都已經由真人逐項驗收。

分工以 **README(A).md**、**README(B).md** 及 GitHub Commit 歷史為準。莊育哲負責的 Scheduler 與原始 LINE 功能仍保留原作者；蕭博軒的管理介面、資料整合、行事曆匯出、LINE 一日虛擬展示及測試使用 Onlynotonly 提交。遵循最新 main → 獨立 feature branch → 測試 → PR → 審查後合併，不直接推送 main。
