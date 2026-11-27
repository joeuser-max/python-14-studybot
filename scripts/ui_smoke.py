"""瀏覽器端 smoke test：確認真正顯示 7 × 16，並能手動拖入與一鍵填滿。

只在 CI 安裝 playwright；不影響使用者執行 app.py 的依賴。
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8511"


def wait_for_server():
    for _ in range(60):
        try:
            with urllib.request.urlopen(URL + "/_stcore/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Streamlit 未在預期時間內啟動")


def main():
    log_path = Path("/tmp/classpulse-ui-smoke-server.log")
    with log_path.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.headless=true", "--server.port=8511",
             "--server.fileWatcherType=none"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            wait_for_server()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                try:
                    page.goto(URL, wait_until="domcontentloaded")
                    # The 16×7 matrix must exist in the browser, not merely in Python data.
                    expect(page.locator(".matrix .cell")).to_have_count(112, timeout=25000)
                    expect(page.locator(".matrix .period")).to_have_count(16)
                    expect(page.locator(".matrix .hdr")).to_have_count(8)

                    # The previous day/week/month views must remain usable.
                    switch = page.locator('[data-testid="stSegmentedControl"]')
                    expect(switch).to_have_count(1, timeout=25000)
                    for label, css in [
                        ("週", ".fc-timegrid"),
                        ("月", ".fc-daygrid"),
                        ("日", ".fc-timegrid"),
                    ]:
                        switch.get_by_text(label, exact=True).click()
                        expect(page.locator(css)).to_be_visible(timeout=25000)
                    switch.get_by_text("七日拖排", exact=True).click()
                    expect(page.locator(".matrix .cell")).to_have_count(112, timeout=25000)

                    # The guided route and LINE mock must be discoverable as tabs.
                    page.get_by_role("tab", name="操作引導").click()
                    expect(page.get_by_text("引導式操作｜從課表到 AI 建議")).to_be_visible()
                    page.get_by_role("tab", name="行事曆與拖排").click()

                    # Demo data must start with two pending items, NOT pre-filled.
                    page.get_by_text("展示模式（使用獨立的範例資料）", exact=False).click()
                    expect(page.locator(".cards .card")).to_have_count(2, timeout=25000)

                    # Resize a pending card by dragging its right-hand handle.
                    grip = page.locator(".cards .card").first.locator(".grip")
                    bounds = grip.bounding_box()
                    assert bounds is not None
                    center_x = bounds["x"] + bounds["width"] / 2
                    center_y = bounds["y"] + bounds["height"] / 2
                    page.mouse.move(center_x, center_y)
                    page.mouse.down()
                    page.mouse.move(center_x + 39, center_y, steps=6)
                    page.mouse.up()
                    expect(page.locator(".cards .card").first).to_contain_text(
                        "2 節", timeout=25000)

                    # Drag exactly ONE task to tomorrow 08:00; the other stays pending.
                    page.locator(".cards .card").first.drag_to(page.locator(".matrix .cell").nth(1))
                    expect(page.locator(".cards .card")).to_have_count(1, timeout=25000)
                    expect(page.locator(".event.study")).to_have_count(1)

                    # Only the explicit button may schedule the other task.
                    page.get_by_role("button", name="一鍵填滿剩餘任務").click()
                    expect(page.locator(".cards .card")).to_have_count(0, timeout=25000)
                    expect(page.locator(".event.study")).to_have_count(2)

                    # LINE Mock must be independently visible, with a daily timeline
                    # and an interactive note form, without any real LINE token.
                    page.get_by_role("tab", name="LINE 一日 Mock").click()
                    expect(page.get_by_text("LINE 一日 Mock｜一整天的提醒、互動與回饋")).to_be_visible()
                    expect(page.get_by_text("選擇模擬日期")).to_be_visible()
                    expect(page.get_by_text("模擬 LINE 課後提醒與補筆記")).to_be_visible()
                    expect(page.get_by_role("button", name="模擬回覆並存入展示資料")).to_be_visible()

                    assert not errors, "JavaScript errors: " + "; ".join(errors)
                    print("通過：日週月檢視、五步引導、LINE 一日 Mock、七日拖排與一鍵填滿")
                except Exception:
                    page.screenshot(path="/tmp/classpulse-ui-smoke-failure.png", full_page=True)
                    raise
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            if log_path.exists() and server.returncode not in (0, -15):
                print(log_path.read_text(encoding="utf-8")[-10000:])


if __name__ == "__main__":
    main()
