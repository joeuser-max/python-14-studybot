"""從正在執行的程式目錄取得 Git 版本，避免網頁與啟動目錄對不上。"""
from __future__ import annotations

from pathlib import Path
import subprocess


APP_ROOT = Path(__file__).resolve().parent


def _git(*args: str, root: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root or APP_ROOT,
            capture_output=True, text=True, timeout=3, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def get_version_info(root: Path | None = None) -> dict[str, str]:
    """只查本機檔案，不用網路；沒有 .git 的雲端部署也可安全顯示。"""
    directory = (root or APP_ROOT).resolve()
    branch = _git("branch", "--show-current", root=directory) or "未取得 Git 分支"
    sha = _git("rev-parse", "--short", "HEAD", root=directory) or "無 Git Commit"
    return {"branch": branch, "sha": sha, "directory": str(directory)}
