# ClassPulse｜歷史整合紀錄與後續協作

這份文件原本是 A 組員將 ZIP 程式碼合併至正確 Repository 的操作說明。**該次程式整合已完成**，不需要再複製 ZIP，亦不應再次覆蓋 B 組員檔案。

## Repository 與原始分工

- 正確位置：`joeuser-max/python-14-studybot`。
- 蕭博軒（A）：Streamlit、JSON、Markdown、AI Model API 介面。
- 莊育哲（B）：Scheduler、LINE Webhook、提醒 Worker。
- 已合併的功能請以主 [README](README.md) 與最新 `main` 程式為準。

## 目前開發流程

1. 先在本機同步 `main`，確認最新版可執行。
2. 建立功能分支，不直接 Push `main`。
3. 調整與驗證模組介面，再以**繁體中文、具體描述**的 Commit 訊息提交。
4. Push 至 Branch，經 Pull Request 與 CI 測試後由組員合併。

## 歷史備註

先前出現的 `123`、`12345` 為測試 Commit 訊息。它們已進入共用歷史，不安全地重寫歷史會造成合作者分支不同步。因此採用新的修正 Commit，而不是對 `main` 執行 force push。`123` 誤加入的重複子模組已於清理 PR 中移除；A 模組程式內容仍保留。

實際 LINE API、公開 HTTPS、AI API 使用與常駐部署是否可用，必須另外驗證，不能以離線測試代替。
