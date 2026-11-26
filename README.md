# ClassPulse｜學習助理控制台

ClassPulse 將課後筆記、AI 建議、讀書任務和時間安排連成一條流程。**LINE 是日常互動入口；AI Model API 負責筆記分析；Streamlit 是設定與管理控制台；Google／Apple Calendar 用於手機查看。**

這是第 14 組 Python 課程的可執行 MVP，不是正式上線的多人 SaaS。

## 快速啟動網站

**先確認 Terminal 位於專案目錄！** 如果畫面顯示 `~ %`，代表你在 Mac 使用者主目錄，直接輸入 `pip install -r requirements.txt` 會找不到檔案。只有 `cd` 到包含 `app.py`、`requirements.txt` 的專案資料夾，才能正確啟動。

### macOS：第一次下載與啟動（推薦）

開啟 Terminal，整段貼上：

```bash
git clone https://github.com/joeuser-max/python-14-studybot.git ~/ClassPulse-Demo
bash ~/ClassPulse-Demo/start_mac.sh
```

`start_mac.sh` 會自動切換到專案根目錄、建立專案專用 `.venv`、必要時安裝套件，然後啟動 Streamlit。Mac 瀏覽器開啟 **http://localhost:8501**。不用預先安裝 LINE 或 OpenAI 憑證就可以體驗展示模式。

**以後再次開啟：**只需執行 `bash ~/ClassPulse-Demo/start_mac.sh`；如果要取得新版本，先 `cd ~/ClassPulse-Demo && git pull --ff-only`。停止網站按 `Control + C`。

如果顯示 `fatal: destination path ... already exists`，代表已下載過，直接執行上面「再次開啟」的指令即可。如果你已經將專案放在另一個資料夾，也可以從 Finder 將該資料夾拖曳到 Terminal 的 `cd ` 後面，或先 `pwd` 和 `ls` 確認資料夾位置。

### macOS／Linux：手動啟動

```bash
# 先到你已經 Clone 的專案根目錄
cd ~/ClassPulse-Demo
ls app.py requirements.txt
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### Windows PowerShell

```powershell
git clone https://github.com/joeuser-max/python-14-studybot.git
cd python-14-studybot
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### 常見錯誤

| 錯誤訊息 | 原因與修復 |
| --- | --- |
| `No such file or directory: requirements.txt` | 沒有進入專案根目錄。先 `pwd`、`ls`，再 `cd ~/ClassPulse-Demo`。 |
| `No module named streamlit` | 安裝先前失敗或用錯 Python 環境。執行 `source .venv/bin/activate`、`python -m pip install -r requirements.txt`。 |
| `cd: no such file or directory: python-14-studybot` | 專案尚未 Clone，或已在專案內。用 `pwd` 確認後再 Clone。 |
| 網址打不開 | 確認 Streamlit 的 Terminal 視窗仍在執行；`localhost` 只能在啟動網站的同一台電腦開啟。 |

需要 **Python 3.11 以上**。如果下載後已有本機修改，先不要強制 `git pull` 或覆蓋檔案。

## 使用者流程

1. **首次引導**：認識產品 → 新增課程／課表截圖預覽 → LINE 說明 → 新增任務與可用時段 → 外部行事曆。每一步可略過，完成後才出現全部側欄。
2. **總覽**：顯示待辦、課程數及已排入任務。避免一次展示所有表單。
3. **我的任務**：直接點擊卡片編輯名稱、期限、預估時間、0–100% 進度或完成勾選，也可刪除。
4. **時間規劃**：點課程或可用時段卡片直接修改。Scheduler 依 Deadline、時段容量及衝突規則排程。
5. **學習回饋**：相同 (課程 ID, 課程日期) 的多則筆記合併顯示；原始筆記與 ID 保留。
6. **AI 助理**：只有在使用者明確同意後才嘗試呼叫 OpenAI；AI 建議需要再次確認才寫入任務。
7. **連接與匯出**：調整 LINE 提醒偏好，下載 .ics 和 Markdown，或為單一任務開啟 Google Calendar 新增事件畫面。

## 附加展示：LINE 從 08:00 到 21:00 的一天

側欄「LINE 一日展示」不需要 LINE API Key、Webhook 或 OpenAI API Key。它有 **13 個依時間排序的場景**，每個場景提供 **3 個預設訊息選項**，按下後立即顯示相應的 LINE 虛擬回覆，不必輸入文字。可逐段繼續、一鍵播放完整一天，或重播。

包含：08:00 早晨規劃 → 課前提醒 → 課程 → 課後理解度 → 補筆記 → Mock AI 分析 → 使用者確認任務 → 規則式排程 → 無法排入提醒 → 手機行事曆 → 19:00 讀書提醒 → 任務完成度 → 21:00 當日回顧。

虛擬引擎追蹤當天的理解度、筆記、是否接受 AI 任務、排程選項及進度，以免拒絕任務後卻顯示已完成安排。**這些都是模擬選擇；絕不對外發送 LINE、不呼叫模型、不覆寫正式任務或資料。**

## 展示模式資料

在側欄打開「展示模式」會載入獨立資料夾 .classpulse-demo-data/，包含**虛構範例課表**、任務、回饋與進度。可直接修改或按「還原展示資料」。切回一般模式不受影響。使用者實際課表需收到資料後再手動替換，**目前不宣稱已完成 OCR 辨識**。

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
