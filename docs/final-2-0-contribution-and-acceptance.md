# ClassPulse Final 2.0 — Engineering contribution and acceptance record

日期：2026-11-28（Asia/Taipei）  
貢獻者：@Onlynotonly（蕭博軒；實機操作、產品需求、除錯驗證、AI 輔助實作與文件整理）  
範圍：內部展示版（最多兩個自動註冊帳號），不宣稱 production-ready。  
PR：[Draft #20](https://github.com/joeuser-max/python-14-studybot/pull/20)；head feature/line-friend-demo，base feature/rich-demo-fixtures。  
**Final 2.0 Golden Baseline（程式快照）：[0e0c0bde73e149c63f4266e6c12a9575484f1fc6](https://github.com/joeuser-max/python-14-studybot/commit/0e0c0bde73e149c63f4266e6c12a9575484f1fc6)**。  
保留原 V2 Golden Baseline PR #16 head be687f7b96019744bdf10b9e6a4ce（短 SHA），Final 1.1 10b5fc5；不修改 main，不宣稱已 merge。詳見 [累積開發紀錄](line-friend-demo-progress.md)、[Final 1.1 audit](final-1-1-note-task-audit.md)、[V2 architecture](architecture-v2.md)。

## 1. 需求與設計演進

初始目標：將原本單人、共用 Demo 與本機 LINE Bot，轉為加入 ClassPulse 官方好友即可有獨立的虛構課表、筆記、讀書任務、AI 問題候選及紫色 30 分鐘任務；可拖曳排程，不要求輸入綁定碼、User ID 或額外共用密碼。使用者身份不能由 URL 任意指定。保留原有 V2/Final 1.1 功能，不直接操作 main 或覆寫原本資料。

| 階段 | 工程成果與實際驗收 |
|---|---|
| 12 | macOS Git、venv、Flask、ngrok、LINE OA Messaging API 串接；註冊 helper 與個人 ID。原本 ngrok localhost 403 改 127.0.0.1 後 Verify 成功；IPv4/IPv6 或埠綁定是合理推論，非已證明精確原因。 |
| 13 | 預設關閉的 signed follow registration；防重複、保留 legacy 綁定、pending gate；本機 20 tests，CI 46062648073。 |
| 14 | 獨立 synthetic seed：14 courses、15 tasks（含紫色 30 分鐘任務）、7 availability、3 plan、5 notes、3 external events；穩定 IDs、逐檔鎖與重試；非跨檔交易；CI 46063100830。 |
| 15 | owner-scoped storage、calendar、board、scheduler、plan bridge、worker、LINE group context；CI 曾 143 pass/1 fail，追查 owner-qualified map 卻以 bare ID 查詢造成 check-in 遺漏，修正並新增正向測試；146 passed、CI 46063747162。 |
| 16 | LINE Login code flow、state/browser binding、nonce、PKCE S256、官方 ID-token verify、server-side opaque session、cookie Secure/HttpOnly/SameSite、登出撤銷；161 passed、CI #250 46064083802；不是 LIFF SDK。 |
| 17 | 獨立 detached worktree、venv、data、.env；Flask 5001 / Streamlit 8502 / Caddy 18080 / Cloudflare HTTPS；初次 Protected Quick Tunnel 發生 refresh bug，改 Caddy Basic Auth；6/6 實機驗收。 |
| 17.7 | Railway/Docker/Gunicorn/Caddy/Persistent Volume 配置及 fail-closed tests；使用者決定先暫緩雲端，未開通、未實際 build/deploy、未產生已知雲端費用。 |
| 18.1 | 真實瀏覽器第二分頁共用登入、登出撤銷、無痕需登入、重新登入修改保留；5/5。 |
| 18.2 | 雙帳號實機驗收使用者決定暫緩；已有離線 owner tests，不能代替 live cross-account acceptance。 |
| 18.3 | 獨立 tester OA、同 Provider、簽章 POST-only endpoint、空白 friend-e2e 資料目錄；179 passed / CI #257；401/200/404/401；真實 Follow、seed、回覆網址、LINE Login、re-follow 不覆寫、開啟網頁 recovery 全通過（使用者回報）。 |
| 19 | Internal mode opt-in；取消手動 user ID 白名單與 Caddy Basic Auth，兩個先到先得名額（含既有帳號）；直接 /auth/line/start?openExternalBrowser=1，有效 Session 略過 OAuth；182 tests 預期、CI #261 通過；4/4 實機回報。 |
| 20 | Original OA Bridge :5002；驗證原 OA HMAC 後分流 signed follow / 個人「開啟網頁」至 friend-e2e，其他事件 re-sign 後送原 :5000；既有好友可從開啟網頁 seed。兩個 OA 原始憑證分開，tester 路徑不變；186/186 本機回報、CI #264；5/5 實機回報。 |

## 2. 重要除錯案例：Cloudflare refresh / authentication / CORS

**症狀**：第一個 Protected Quick Tunnel（allowed-mail）進入網頁後刷新重新要求 Email 驗證，卡在 completing authentication，部分 Streamlit 功能出現 CORS error。LINE Login 初次顯示與外層 session 行為混在一起。

**隔離實驗**：直接存取 Flask 的 /health（不經 Streamlit UI、不需 OAuth/個人資料），約 15 秒後刷新也重新要求 Email 驗證。因問題可在簡單 health endpoint 重現，故不能只歸因於 Streamlit callback、拖曳元件或 LINE OAuth。外層 Cloudflare access/session 是主要懷疑對象。

**處理**：保留同 origin、HTTPS、CORS/XSRF、OAuth 與 app 核心程式；將 Protected Quick Tunnel 改普通 Quick Tunnel，私人存取控制移至 Caddy bcrypt Basic Auth。第一次 Caddy validate 出現 base64-decoding password: illegal base64 data at input byte 7，推測 hash/placeholder 格式不正確（未取得原檔，不能確證）。重新生成 hash、保護 Caddyfile，驗證路由後啟動。新的臨時網域需同步 LINE callback 與 staging origin；第一次用 Python heredoc + input() 出現 EOFError，原因是 stdin 已供程式碼，改直接指定已知網址（不重建資料）解決。

**證據**：
- 本機五項 HTTP：未授權 Flask 401、已授權 200、未授權 Streamlit 401、已授權 200、Webhook 404。
- 外部 HTTPS：未授權 401、授權 200（Cloudflare → Caddy → Flask）。
- 實機 6/6：密碼、LINE Login、個人課表、紫色任務拖曳、30 秒後 refresh 保留登入、原 CORS error 消失。
- [Step 17.6 record](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228301271)

**結論的邊界**：更換外層驗證後症狀消失，支持外層驗證/session 層是問題所在；未分析 Cloudflare server logs 或 Cookie trace，不能斷言其內部實作 bug 或 CORS error 的精確觸發點。此為實機系統隔離與 workaround 貢獻，不是 Cloudflare 官方 bug 修復。

## 3. Follow Event 除錯與真實驗收

初次 LINE 收到的是 OA 內建 Greeting message，而非 Python 回覆。Verify 只驗證 signed 空 events，不能證明 follow registration。區分三層：是否收到事件、是否符合 allowlist、是否 seed 後 Reply API 成功。使用唯讀 Bot info / webhook endpoint / profile API 與 users/events/tasks/processed_webhooks 計數定位；具體哪項配置改動使回覆成功未在對話中留下輸出，因此不推定精確原因。使用者後續回報收到連結及 E2E 全通過。初次 Basic Auth 401 後第二次 200；GET webhook 404；無簽章 POST 401 由 Flask 而非 Caddy 回傳，證明正確穿過 proxy 並拒絕無簽章。

## 4. 最終本機架構與貢獻界線

```
LINE ClassPulse OA -> HTTPS /webhook/classpulse -> Caddy :18080
    -> Official Bridge :5002 (原 OA HMAC / own reply token)
       -> follow/open: friend-e2e synthetic store
       -> other events: original Flask :5000 (legacy store)
LINE tester OA -> /webhook -> Flask :5001 -> friend-e2e
Browser -> same HTTPS origin -> /auth/line/* :5001
                             -> Streamlit :8502 -> friend-e2e
Original reminder worker (if running) -> legacy store
```

- Original OA、ngrok、Flask、原 .env 與資料不搬遷；原 OA webhook URL 於 Step 20 切到 Bridge，原 URL 保留作回復。
- 這是入口整合而非資料合併。新網頁課表/任務與舊 LINE 筆記/推播的資料集仍獨立。網頁 personal staging 使用 mock AI，reminder controls disabled；seeded_pending_auth 帳號被 legacy bot/worker gate 阻擋；不能宣稱新登入者已完成真正跨端筆記/排程/推播閉環。
- Official Bridge 改變 follow/open routing；原有普通訊息按原 legacy handler；實機驗收者回報原筆記功能仍正常。Bridge tests 驗證分流、簽章、空 Verify、重放、group routing，非真實 LINE API 或新帳號筆記同步測試。
- 內部展示採先到先得兩名額，不是真正組員 allowlist；外部網址可達、LINE OAuth 仍必須有效。不得廣泛分享 QR code。雙帳號 live isolation、正式營運硬化、持久雲端、LIFF、實際外部 AI/worker 對新 demo owner 的驗收未完成。
- 開發/測試仍依賴 Mac、原 :5000 與暫時 Tunnel；重啟需重新確認 origin/callback/webhooks。Terminal 4 不需保持運行。不要把憑證、真實 User ID、session、原始筆記或可用臨時 URL 寫入 GitHub。未建立一鍵啟動腳本。

## 5. 驗收證據索引

| 項目 | Evidence |
|---|---|
| Step 17.6 HTTPS/refresh/CORS | [6/6](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228301271) |
| Step 18.1 Session | [5/5](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228360598) |
| Step 18.3 signed follow | [E2E](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228659281) / [CI #257](https://github.com/joeuser-max/python-14-studybot/actions/runs/46070640856) |
| Step 19 internal UX | [4/4](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228763264) / [CI #261](https://github.com/joeuser-max/python-14-studybot/actions/runs/46072112988) |
| Step 20 official integration | [5/5](https://github.com/joeuser-max/python-14-studybot/pull/20#issuecomment-7228880141) / [CI #264](https://github.com/joeuser-max/python-14-studybot/actions/runs/46072701471) |

CI conclusion verified through GitHub; local 179 count observed in supplied terminal log, 186 and mobile acceptance are user-reported, not independently observed by assistant. Contribution count should cite commits, decisions, test evidence and user-performed troubleshooting, rather than equating lines changed with effort. Original V2/Final 1.1 and teammate work are not claimed as new contributions here.

## 6. 下一階段

See [Step 21 LINE interaction audit](step21-line-interaction-audit.md). Freeze this code SHA before adapting any teammate changes. Do not wholesale merge main or cherry-pick conflicting monolithic commit. Preserve the V2/Final 1.1 UI, owner identity and data; test synthetic notes with explicit consent before any actual model call or outbound reminder. Scope: one internal user, real LINE two-way interaction against the same personal data; no new public deployment or two-account live acceptance requested.
