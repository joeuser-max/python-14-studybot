#!/bin/bash
# ClassPulse — always launch the latest merged main (macOS).
# Finds its own project folder, never force-overwrites local edits,
# and refuses to silently switch ports if the desired port is occupied.
set -euo pipefail

cd -- "$(dirname -- "$0")"
printf '\n=== ClassPulse｜最新已合併版本啟動器（macOS）===\n'
printf '專案資料夾：%s\n' "$PWD"

if [[ ! -f app.py || ! -f requirements.txt || ! -d .git ]]; then
  echo "錯誤：啟動器必須放在 ClassPulse Git 專案根目錄。" >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "錯誤：找不到 Git。請先安裝 Git。" >&2
  exit 1
fi

echo "[1/4] 取得 GitHub 最新 main..."
if ! git fetch origin main; then
  echo "無法連接 GitHub。為避免誤開舊版，本次不啟動。" >&2
  exit 1
fi
if ! git switch main; then
  echo "無法切換 main。可能有尚未提交的本機修改；不會刪除或覆蓋。" >&2
  echo "請執行 git status 檢查，處理修改後再試。" >&2
  exit 1
fi
if ! git pull --ff-only origin main; then
  echo "無法安全更新 main，已停止啟動，沒有強制覆寫本機檔案。" >&2
  echo "請執行 git status 與 git log -3 --oneline 檢查。" >&2
  exit 1
fi
branch="$(git branch --show-current)"
sha="$(git rev-parse --short HEAD)"
printf '已選版本：%s · %s\n' "$branch" "$sha"

echo "[2/4] 檢查 Python 環境..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "錯誤：找不到 Python 3。請先安裝 Python 3.11 以上版本。" >&2
  exit 1
fi
if ! python3 -c 'import sys;sys.exit(sys.version_info < (3,11))'; then
  python3 --version
  echo "錯誤：需要 Python 3.11 以上版本。" >&2
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

echo "[3/4] 確保依賴符合目前版本..."
.venv/bin/python -m pip install -r requirements.txt

port=8502
echo "[4/4] 檢查專用 Port $port..."
if ! .venv/bin/python -c 'import socket,sys;s=socket.socket();result=s.connect_ex(("127.0.0.1",int(sys.argv[1])));s.close();sys.exit(result==0)' "$port"; then
  echo "Port $port 已被其他服務使用。可能是先前的 ClassPulse。" >&2
  echo "請回到先前啟動網站的 Terminal 按 Control + C，再重新執行此啟動器。" >&2
  echo "不會自行改用其他 Port，避免你開錯版本。" >&2
  exit 1
fi

printf '\n====================================================\n'
printf 'ClassPulse：main / %s\n' "$sha"
printf '網站網址：http://localhost:%s\n' "$port"
printf '只開這個網址，舊的 http://localhost:8501 請關閉。\n'
printf '停止：按 Control + C。\n'
printf '====================================================\n\n'
exec .venv/bin/python -m streamlit run app.py --server.port "$port" --server.address 127.0.0.1
