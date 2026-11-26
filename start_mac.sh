#!/bin/zsh
# ClassPulse macOS 快速啟動器，可從任意目前工作目錄呼叫。
set -e

cd -- "$(dirname -- "$0")"
echo "ClassPulse 專案位置：$PWD"
if [[ ! -f requirements.txt || ! -f app.py ]]; then
  echo "錯誤：找不到 requirements.txt 或 app.py；請確認啟動器位於專案根目錄。"
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "錯誤：找不到 python3，請先安裝 Python 3.11 以上版本。"
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "首次啟動：建立專案專用的 .venv..."
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import streamlit, flask, dotenv, filelock, streamlit_calendar" >/dev/null 2>&1; then
  echo "安裝 ClassPulse 依賴套件..."
  python -m pip install -r requirements.txt
fi

echo ""
echo "正在啟動 ClassPulse；瀏覽器網址：http://localhost:8501"
echo "停止網站：在這個 Terminal 按 Control + C。"
python -m streamlit run app.py
