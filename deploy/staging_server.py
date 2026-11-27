"""Railway private staging launcher. Never start the unauthenticated legacy UI."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import time
from urllib.request import urlopen


def configure(env):
    # Do not import storage until the isolated directory and flags are established.
    mount = env.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    if mount != "/data":
        raise ValueError("A Railway persistent volume at /data is required")
    port = env.get("PORT", "8080")
    if not port.isdigit() or not 1024 <= int(port) <= 65535 or int(port) in (5001, 8502):
        raise ValueError("Invalid public PORT")
    host = env.get("RAILWAY_PUBLIC_DOMAIN", "")
    if not re.fullmatch(r"[a-z0-9-]+\.up\.railway\.app", host):
        raise ValueError("Generate a Railway HTTPS domain first")
    if env.get("CLASSPULSE_WEB_ORIGIN") != "https://" + host:
        raise ValueError("Set CLASSPULSE_WEB_ORIGIN to the exact Railway HTTPS origin")
    password = env.get("CLASSPULSE_STAGING_PASSWORD_HASH", "")
    if not re.fullmatch(r"\$2[aby]\$(?:0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{53}", password):
        raise ValueError("Set a bcrypt hash, not a plaintext staging password")
    if not re.fullmatch(r"[0-9]+", env.get("LINE_LOGIN_CHANNEL_ID", "")):
        raise ValueError("Set the LINE Login Channel ID")
    if not env.get("LINE_LOGIN_CHANNEL_SECRET"):
        raise ValueError("Set the LINE Login Channel secret")
    subjects = [v.strip() for v in env.get("CLASSPULSE_STAGING_TEST_USERS", "").split(",") if v.strip()]
    if not subjects or len(set(subjects)) != len(subjects) or len(subjects) > 5 or any(
        not re.fullmatch(r"U[0-9a-f]{32}", s) for s in subjects
    ):
        raise ValueError("Set 1 to 5 unique tester LINE user IDs")
    env.update(
        PORT=port, CLASSPULSE_DATA_DIR="/data/classpulse",
        CLASSPULSE_PUBLIC_WEB="0", CLASSPULSE_LINE_WEB_STAGING="1",
        LINE_FRIEND_DEMO_ENABLED="0", LINE_FRIEND_DEMO_SEED_ENABLED="0",
        LINE_CHANNEL_SECRET="", LINE_CHANNEL_ACCESS_TOKEN="",
        OPENAI_API_KEY="", GEMINI_API_KEY="",
    )
    return subjects


def wait_ready(url, children, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in children):
            raise RuntimeError("A staging backend exited before readiness")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Staging backend readiness timeout")


def run():
    subjects = configure(os.environ)
    # Runtime-only mount, not the image layer. Linux mountinfo handles bind mounts.
    if not any(line.split()[4] == "/data" for line in Path("/proc/self/mountinfo").read_text().splitlines()):
        raise ValueError("Persistent volume is not mounted")
    directory = Path(os.environ["CLASSPULSE_DATA_DIR"])
    os.umask(0o077)
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Invalid staging data directory")
    # Startup privileges only for preparing the volume. All app processes run unprivileged.
    if os.getuid() == 0:
        account = pwd.getpwnam("classpulse")
        os.chown(directory, account.pw_uid, account.pw_gid)
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    directory.chmod(0o700)

    from line_web_auth import config
    from line_demo_registration import get_or_create_line_user
    from line_demo_seed import seed_line_user
    config()
    for subject in subjects:
        user, _ = get_or_create_line_user(subject)
        seed_line_user(user["user_id"])
    print("Private staging test accounts initialized; no live LINE or AI calls.", flush=True)
    children = []
    def stop(_signum, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Validate outer password guard BEFORE opening a network listener.
        subprocess.run(["caddy", "validate", "--config", "/app/deploy/Caddyfile",
                        "--adapter", "caddyfile"], check=True)
        children.append(subprocess.Popen([
            sys.executable, "-m", "gunicorn", "--bind", "127.0.0.1:5001",
            "--workers", "1", "--threads", "4", "--error-logfile", "-",
            "line_bot:app"
        ]))
        children.append(subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address", "127.0.0.1", "--server.port", "8502",
            "--server.headless", "true", "--server.enableCORS", "true",
            "--server.enableXsrfProtection", "true", "--browser.gatherUsageStats", "false",
            "--browser.serverAddress", os.environ["RAILWAY_PUBLIC_DOMAIN"],
        ]))
        wait_ready("http://127.0.0.1:5001/health", children)
        wait_ready("http://127.0.0.1:8502/_stcore/health", children)
        children.append(subprocess.Popen([
            "caddy", "run", "--config", "/app/deploy/Caddyfile", "--adapter", "caddyfile"
        ]))
        while True:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A staging process exited")
            time.sleep(1)
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
        for p in children:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if __name__ == "__main__":
    run()
