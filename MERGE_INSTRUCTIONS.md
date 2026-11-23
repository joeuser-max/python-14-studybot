# 正確 Repo 整合操作說明

目標：`joeuser-max/python-14-studybot`。本 ZIP **僅含蕭博軒（A）的模組及兩人共用設定合併稿**，不包含 B 已存在的 `scheduler.py`、`line_bot.py`、`reminder_worker.py`、`README(B).md`、原 `docs/ai-log.md` 或 B 的測試。

1. 在正確 Repo clone 後由自己的 feature branch 提交。勿複製至名稱相似的 `Onlynotonly/pyhton-14-studybot`。
2. 將本套件內容合併至 Repo 根目錄；`storage.py` 為 A 的強化版，保留與 B 所用 `load_json`、`save_json` 同名介面，但 B 多程序更新應改用 `update_json`。
3. `requirements.txt`、`.env.example`、`.gitignore` 已合併 B 原有內容與 A 的依賴。`.env`、資料 JSON 不可提交。
4. 既有 `README.md`、`docs/ai-log.md` 不覆寫；A 的說明分別存為 `README(A).md`、`docs/ai-log-A.md`。
5. `app.py` 現可接受 B 的 `make_plan` dict 輸出，並在儲存時補入 `user_id`。
6. 執行 `python -m unittest discover -s tests -v`；再由 B 修正 `docs/B_INTEGRATION.md` 所列的 Webhook 與 Worker 整合缺口。
7. LINE 真實通知、外部 AI、完整整合尚未執行端到端驗證。
