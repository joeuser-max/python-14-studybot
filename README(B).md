# ClassPulse（莊育哲負責模組）

本專案包含規格書中的讀書排程、讀書／課後提醒 Worker，以及 LINE Webhook／補筆記功能。

## 安裝

```powershell
python -m pip install -r requirements.txt
```

程式不會自動載入 `.env`；要使用 LINE 請在啟動 Webhook／Worker 的 PowerShell 視窗設定環境變數，參考整合版 [README.md](README.md)。

## 執行

```powershell
# LINE Webhook
python -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000

# 常駐提醒 Worker
python reminder_worker.py
```

設定 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET` 與 `LINE_BINDING_CODE` 後可測試真實 LINE。未設定 Token 時只輸出模擬訊息，提醒維持未成功狀態，不會宣稱已實際送達。詳見整合版 [README.md](README.md)。

## 主要 B 模組

- `scheduler.py`：`make_plan`、任務狀態、課後／讀書提醒到期判斷
- `reminder_worker.py`：常駐檢查、LINE Push、retry key 與送出狀態
- `line_bot.py`：簽章驗證、Webhook 去重、課次定位與筆記保存

Webhook 會將通過簽章驗證的綁定碼訊息對應到 A 端固定測試使用者 `demo_user_001`；Streamlit 可調整課後／讀書提醒開關。
