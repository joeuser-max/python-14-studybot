"""新版啟動流程與分階段 onboarding 的回歸測試。"""
from pathlib import Path

import storage
from streamlit.testing.v1 import AppTest

import version_info

ROOT = Path(__file__).resolve().parents[1]


def test_version_info_reads_running_repository_root():
    version = version_info.get_version_info(ROOT)
    assert version["directory"] == str(ROOT)
    assert version["sha"]
    assert version["branch"]
    assert version_info.get_version_info(ROOT / "not-a-git-repo")["sha"] == "無 Git Commit"


def test_mac_launcher_explicitly_updates_main_and_avoids_old_port():
    script = (ROOT / "start_mac.sh").read_text(encoding="utf-8")
    assert "git fetch origin main" in script
    assert "git switch main" in script
    assert "git pull --ff-only origin main" in script
    assert "git rev-parse --short HEAD" in script
    assert 'port=8502' in script
    assert "--server.port" in script
    assert "git reset --hard" not in script


def test_windows_launcher_explicitly_updates_main_and_reports_version():
    script = (ROOT / "start_windows.ps1").read_text(encoding="utf-8")
    for instruction in ("git fetch origin main", "git switch main",
                        "git pull --ff-only origin main", "git rev-parse --short HEAD",
                        "streamlit run app.py", "8502"):
        assert instruction in script
    assert "git reset --hard" not in script


def test_onboarding_explains_each_stage_and_shows_git_version(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "normal")
    monkeypatch.setattr(storage, "DEMO_DATA_DIR", tmp_path / "demo")
    storage.select_demo_storage(False)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=25)
    assert not app.exception, [str(e) for e in app.exception]
    assert any("目前程式：" in item.value for item in app.sidebar.caption)
    assert any("先認識 ClassPulse" in title.value for title in app.title)

    expected = (
        "建立你的每週課表",
        "了解 LINE 與 AI 的角色",
        "加入任務與可以讀書的時間",
        "將安排帶到手機，完成設定",
    )
    for heading in expected:
        next_btn = next(button for button in app.button
                        if button.label == "繼續下一步")
        next_btn.click().run(timeout=25)
        assert not app.exception, (heading, [str(e) for e in app.exception])
        assert any(heading in title.value for title in app.title)
    finish = next(button for button in app.button
                  if button.label == "完成並進入 Dashboard")
    finish.click().run(timeout=25)
    assert not app.exception, [str(e) for e in app.exception]
    assert app.sidebar.radio[0].value == "總覽"
