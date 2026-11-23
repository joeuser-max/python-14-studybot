# A／B 整合紀錄

目前 A／B 整合工作在 `ab-integration` 分支進行。A 的 Streamlit／資料介面與 B 的排程／LINE 模組共用 `storage.py` 的資料路徑及檔案鎖定更新函式。

## 已整合

- Streamlit 產生排程時呼叫 `scheduler.make_plan()`，由 `plan_bridge.normalize_plan_result()` 補上固定測試使用者 ID，並以鎖定更新方式替換該使用者計畫。
- Streamlit 提供 LINE 綁定狀態及課後／讀書提醒開關；Webhook 經簽章驗證後可用綁定碼綁定 `demo_user_001`。
- LINE「補筆記」依序選星期、課表編號與文字；儲存時使用 A 的 `storage.save_feedback()` 驗證及 Webhook ID 去重。
- Worker 改用 A 的 `data_path()` 與 `update_json()`，推送狀態不會覆蓋其他程序的最新 JSON；推送失敗使用相同 retry key 重試。
- `tests/test_ab_integration.py` 覆蓋 Streamlit 排程介面至 Worker、失敗重試、LINE 簽章與補筆記流程。

## 尚需真實服務設定

實際 LINE 端到端測試仍需 LINE OA Channel Secret／Access Token、綁定碼，以及 LINE 可存取的 HTTPS Webhook URL。無 Token 的 Worker 模擬輸出不會記為已送達。詳見 [README.md](README.md)。

## 驗證指令

```powershell
python -m pytest -v
python -m compileall -q app.py scheduler.py storage.py line_bot.py reminder_worker.py plan_bridge.py
```
