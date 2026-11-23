# ClassPulse（莊育哲負責模組）

本專案包含規格書中的讀書排程、讀書／課後提醒 Worker，以及 LINE Webhook／補筆記功能。

## 安裝

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## 執行

```powershell
# LINE Webhook
python -m flask --app line_bot:create_app run --host 0.0.0.0 --port 5000

# 常駐提醒 Worker
python reminder_worker.py
```

可用 `LINE_CHANNEL_ACCESS_TOKEN` 與 `LINE_CHANNEL_SECRET` 測試真實 LINE；未設定 token 時 worker 使用模擬輸出，不會宣稱已實際送達。

## 主要 B 模組

- `scheduler.py`：`make_plan`、任務狀態、課後／讀書提醒到期判斷
- `reminder_worker.py`：常駐檢查、LINE Push、retry key 與送出狀態
- `line_bot.py`：簽章驗證、Webhook 去重、課次定位與筆記保存
