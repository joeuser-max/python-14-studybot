# Final 3.0 → main 整合規則

## 目標與基準

將兩位組員的 Git 歷史整合至主線，保留已驗收的 Final 3.0 個人學習閉環及原始 B 模組來源，並審查 B 最新版本的獨立改進。不是 force-push、reset main、整批 ours/theirs 或把來源作者改為 A。

| Ref | 整合開始時的固定 SHA |
|---|---|
| main | 1ef63c8e7d98d344bc7297ac744706f2a59608ec |
| 共同祖先 | a7ff1138133ba4485d8135ed15d8ce48154be845 |
| Final 3.0 驗收程式 | e835140e0658717e1fdda14ab7ec07c7d8554ed3 |
| 功能分支含封存紀錄 | 37b61625a005daf11618752788e7d218dde63678 |
| V2 整合分支 | 97fbba82fb7d5c83a8211e4724d293b1e640527b |

整合候選：integrate/final-3.0-main。先保留 Final 3.0 程式碼與功能分支的 PR 歷史，再做 main 真正的三方合併。archive/final-3.0 不修改。原本 staging worktree、LINE Console、環境檔、資料與執行程序一律不操作。

## 待核對的功能重疊

這是從 GitHub main 變更清單與歷史稽核所得的審查清單；不是已完成的衝突解決結果。須取得實際 Git merge 衝突與 diff。

| 區域 | 保留 Final 3.0 的契約 | 審查 main 的獨立改進 |
|---|---|---|
| app.py | V2 七日板、日週月、30 分鐘伸縮、身份映射、筆記庫、授權提示 | B 的課程進度、複習範圍、附件／資料編輯等操作，檢查哪些尚未涵蓋；避免用舊 UI 替換 V2 |
| line_bot.py | 原始簽章與綁定、個人／legacy 分流、逐題 AI 確認、局部重排 | B 的課程進度、指定分鐘／deadline／選時段、附件流程；不能讓不同狀態機同時搶同一事件 |
| scheduler.py / reminder_worker.py | owner 範圍、既有固定時段、retry key、個人自動提醒去重 | B 的 60 分鐘課後補發、15 分鐘讀書提醒、時段更動識別；若改規格需明文說明及測試，不重複推播 |
| storage.py / exporter.py | 原始記錄保留、owner scope、檔案鎖、穩定 IDs、來源欄位 | B 新增附件／課程進度／資料刪除等能力；審查資料契約，禁止跨 owner 或破壞現有 JSON |
| tests / requirements / pytest.ini | 223 項 Final 3.0 regression 基準、現行依賴及 CI | B 獨立新增的測試與依賴；測試預期不同時寫明功能規格，不直接刪掉失敗測試 |
| README、spec、.gitignore、歷史重複目錄 | 貢獻可追溯、資料／金鑰不入 Git、現行操作手冊 | 合併 B 原始分工、功能敘述；重複目錄與刪除須檢查追蹤狀況，不能刪本機運行資料 |

如某個 B 功能的產品規格與 Final 3.0 互斥，不得無聲捨棄；記錄選擇、原因、測試影響，提交組員審查。

## 合併程序

1. 確認本機乾淨的獨立 worktree 指向 integrate/final-3.0-main，原 staging 不改動。
2. fetch origin；確認 main SHA。對候選分支執行 git merge --no-ff --no-commit origin/main。
3. 檢查 git status --short、git diff --name-only --diff-filter=U 和未衝突的自動合併差異；逐檔解決，保留兩位作者歷史。不得 force-push。
4. git diff --check、Python 語法、完整 pytest、Playwright UI 與 CI。223 是已驗收來源的測試基準，不是合併後預定總數；B 新增測試可能使總數提高。
5. 在隔離環境驗收核心路徑、LINE 及 Gemini（若有授權）。不對原本運作的 bot 做未經同意的切換。
6. 提交具雙親的 merge commit，push 到候選分支，檢查 PR 相對 main 的 diff、CI、作者與貢獻紀錄。組員審查後以一般 merge commit 合併 main；不 squash 或 rebase 掉作者與整合歷史。
7. 合併後確認 main 包含雙方歷史與 README/CONTRIBUTIONS，紀錄 main SHA。之後再決定正式版本標籤、預設分支保護與歷史 PR 整理。

## 不等於完成

Final 3.0 的本機測試與實機驗收只適用於封存 SHA，不能直接當成合併後的驗收。此次整合不能擴張成公開部署或完整多用戶安全驗證。Main Integration PR 未通過所有檢查之前保持 Draft。
