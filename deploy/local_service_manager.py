"""Local internal demo supervisor; legacy Flask and external tunnel remain external."""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

from dotenv import dotenv_values
from filelock import FileLock, Timeout
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "friend-e2e"
RUNTIME = ROOT / "data" / "local-launcher"
STATE = RUNTIME / "state.json"
PORTS = (5001, 5002, 8502, 18080)
ORIGIN_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SERVICES = ("tester", "bridge", "web", "caddy", "tunnel", "worker")
KEYS = ("LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN", "LINE_LOGIN_CHANNEL_ID",
        "LINE_LOGIN_CHANNEL_SECRET", "CLASSPULSE_WEB_ORIGIN", "CLASSPULSE_DATA_DIR",
        "AI_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
BODY = b'{"events":[]}'


def config(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing local configuration: {path.name}")
    if path.stat().st_mode & 0o077:
        raise ValueError(f"Restrict {path.name} to mode 600 before starting")
    values = dotenv_values(path, interpolate=False)
    if Path(values.get("CLASSPULSE_DATA_DIR") or "/").resolve() != DATA.resolve():
        raise ValueError("Configuration does not select the isolated friend-e2e store")
    for key in KEYS[:4]:
        if not values.get(key):
            raise ValueError(f"Missing {key} in {path.name}")
    if not ORIGIN_RE.fullmatch(values.get("CLASSPULSE_WEB_ORIGIN") or ""):
        raise ValueError(f"Expected existing Quick Tunnel HTTPS origin in {path.name}")
    return values


def load_configs():
    if not DATA.is_dir() or DATA.is_symlink():
        raise ValueError("Existing isolated friend-e2e data directory required")
    tester = config(ROOT / "data" / "friend-e2e.env")
    official = config(ROOT / "data" / "official-bridge.env")
    for key in ("LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"):
        if tester[key] == official[key]:
            raise ValueError("Tester and official OA credentials must differ")
    for key in ("LINE_LOGIN_CHANNEL_ID", "LINE_LOGIN_CHANNEL_SECRET"):
        if tester[key] != official[key]:
            raise ValueError("LINE Login configuration differs between environments")
    if tester["CLASSPULSE_WEB_ORIGIN"] != official["CLASSPULSE_WEB_ORIGIN"]:
        raise ValueError("Configured tester/official HTTPS origins differ")
    return tester, official


def child_env(values, origin, role, launch_id):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLASSPULSE_", "LINE_", "OPENAI_", "GEMINI_"))
           and k not in ("AI_PROVIDER", "PYTHONPATH", "PYTHONHOME")}
    env.update({k: str(values.get(k) or "") for k in KEYS if k not in
                ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")})
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if values.get(key):
            env[key] = values[key]
    env.update(CLASSPULSE_DATA_DIR=str(DATA), CLASSPULSE_WEB_ORIGIN=origin,
               CLASSPULSE_LAUNCH_ID=launch_id, CLASSPULSE_PUBLIC_WEB="0",
               CLASSPULSE_LINE_WEB_STAGING="1", CLASSPULSE_FRIEND_INTERNAL="1",
               CLASSPULSE_FRIEND_E2E="1", LINE_FRIEND_DEMO_ENABLED="0",
               LINE_FRIEND_DEMO_SEED_ENABLED="0", LINE_BINDING_CODE="",
               CLASSPULSE_OFFICIAL_BRIDGE="0", CLASSPULSE_FRIEND_NOTE_SYNC="0",
               CLASSPULSE_FRIEND_AI_SYNC="0", CLASSPULSE_FRIEND_PROGRESS_SYNC="0",
               CLASSPULSE_FRIEND_STUDY_PUSH="0", CLASSPULSE_FRIEND_CLASS_PUSH="0",
               CLASSPULSE_FRIEND_AUTO_PUSH="0", PYTHONUNBUFFERED="1")
    if role in ("bridge", "worker"):
        env.update(CLASSPULSE_OFFICIAL_BRIDGE="1", CLASSPULSE_FRIEND_NOTE_SYNC="1",
                   CLASSPULSE_FRIEND_PROGRESS_SYNC="1", CLASSPULSE_FRIEND_AUTO_PUSH="1",
                   CLASSPULSE_FRIEND_STUDY_PUSH="1", CLASSPULSE_FRIEND_CLASS_PUSH="1")
        env["CLASSPULSE_FRIEND_AI_SYNC"] = "1" if values.get("CLASSPULSE_FRIEND_AI_SYNC") == "1" else "0"
    if role != "bridge":
        env.update(GEMINI_API_KEY="", OPENAI_API_KEY="")
    if role in ("web", "caddy", "tunnel"):
        env.update(LINE_CHANNEL_SECRET="", LINE_CHANNEL_ACCESS_TOKEN="")
    if role in ("caddy", "tunnel"):
        env.update(LINE_LOGIN_CHANNEL_ID="", LINE_LOGIN_CHANNEL_SECRET="")
    return env


def signed_probe(url, secret, *, verify=True):
    signature = base64.b64encode(hmac.new(secret.encode(), BODY, hashlib.sha256).digest()).decode()
    try:
        response = requests.post(url, data=BODY, headers={
            "Content-Type": "application/json", "X-Line-Signature": signature},
            allow_redirects=False, timeout=5, verify=verify)
        return response.status_code == 200 and response.json().get("ok") is True
    except (requests.RequestException, ValueError, AttributeError):
        return False


def free_ports():
    busy = []
    for port in PORTS:
        with socket.socket() as sock:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                busy.append(port)
    return busy


def atomic_write(path, value):
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8") as f:
        f.write(value)
    os.replace(temp, path)


def read_state():
    try:
        value = json.loads(STATE.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def locked():
    lock = FileLock(str(RUNTIME / "supervisor.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return True
    lock.release()
    return False


def marker(name, launch_id):
    try:
        return (RUNTIME / name).read_text().strip() == launch_id
    except OSError:
        return False


def ready(url, expected=None, verify=True):
    try:
        r = requests.get(url, timeout=3, allow_redirects=False, verify=verify)
        return r.status_code == 200 and (expected is None or r.text.strip() == expected)
    except requests.RequestException:
        return False


def flask_cmd(module, port):
    return [sys.executable, "-c",
            f'import logging; from {module} import create_app; '
            'logging.getLogger("werkzeug").setLevel(logging.ERROR); '
            f'create_app().run(host="127.0.0.1", port={port}, debug=False, use_reloader=False)']


def start(new_tunnel=False):
    lock = FileLock(str(RUNTIME / "supervisor.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise RuntimeError("Launcher already active")
    children = {}
    launch_id = uuid4().hex
    state = {"id": launch_id, "phase": "preflight", "origin": "", "services": {},
             "tunnel": "managed" if new_tunnel else "external", "legacy": "external"}
    logdir = RUNTIME / launch_id
    logdir.mkdir(mode=0o700)

    def write_state(phase):
        state["phase"] = phase
        state["services"] = {n: "running" if p.poll() is None else "exited"
                             for n, p in children.items()}
        atomic_write(STATE, json.dumps(state))

    def check():
        if marker("stop", launch_id):
            raise KeyboardInterrupt
        if any(p.poll() is not None for p in children.values()):
            raise RuntimeError("Managed service exited; inspect logs")

    def spawn(name, args, env):
        with (logdir / (name + ".log")).open("ab") as log:
            children[name] = subprocess.Popen(args, cwd=ROOT, env=env,
                                               stdin=subprocess.DEVNULL,
                                               stdout=log, stderr=subprocess.STDOUT)
        write_state(state["phase"])

    def wait_until(predicate, label, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            check()
            if predicate():
                return
            time.sleep(0.5)
        raise RuntimeError(f"Readiness failed: {label}")

    def stop_signal(_sig, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_signal)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, stop_signal)
    try:
        write_state("preflight")
        tester, official = load_configs()
        busy = free_ports()
        if busy:
            raise RuntimeError(f"Ports occupied: {busy}. Stop only old staging services manually.")
        caddy = shutil.which("caddy")
        if not caddy:
            raise RuntimeError("caddy not found on PATH")
        worker_lock = FileLock(str(DATA / ".personal-auto-worker.lock"))
        try:
            worker_lock.acquire(timeout=0)
        except Timeout:
            raise RuntimeError("Stop the old automatic worker before launching")
        worker_lock.release()
        if not signed_probe("http://127.0.0.1:5000/webhook", official["LINE_CHANNEL_SECRET"]):
            raise RuntimeError("Existing legacy Flask 5000 failed signed empty probe; leave it external")
        origin = official["CLASSPULSE_WEB_ORIGIN"]
        verify = official.get("SSL_CERT_FILE") or True
        if new_tunnel:
            tunnel = shutil.which("cloudflared")
            if not tunnel:
                raise RuntimeError("cloudflared not found on PATH")
            spawn("tunnel", [tunnel, "tunnel", "--url", "http://127.0.0.1:18080"],
                  child_env(tester, origin, "tunnel", launch_id))
            found = []
            def find_origin():
                match = ORIGIN_RE.search((logdir / "tunnel.log").read_text(errors="replace"))
                if match:
                    found.append(match.group())
                    return True
                return False
            wait_until(find_origin, "Quick Tunnel URL", 90)
            origin = found[0]
        state["origin"] = origin
        write_state("starting")
        proxy_env = child_env(tester, origin, "caddy", launch_id)
        caddy_args = ["--config", str(ROOT / "deploy" / "Caddyfile.local"), "--adapter", "caddyfile"]
        with (logdir / "caddy.log").open("ab") as log:
            subprocess.run([caddy, "validate", *caddy_args], cwd=ROOT, env=proxy_env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=20)
        spawn("tester", flask_cmd("line_friend_e2e", 5001), child_env(tester, origin, "tester", launch_id))
        spawn("bridge", flask_cmd("line_official_bridge", 5002), child_env(official, origin, "bridge", launch_id))
        spawn("web", [sys.executable, "-m", "streamlit", "run", "app.py",
                      "--server.address", "127.0.0.1", "--server.port", "8502",
                      "--server.headless", "true", "--server.enableCORS", "true",
                      "--server.enableXsrfProtection", "true", "--browser.gatherUsageStats", "false"],
              child_env(tester, origin, "web", launch_id))
        wait_until(lambda: ready("http://127.0.0.1:5001/health"), "tester")
        wait_until(lambda: ready("http://127.0.0.1:5002/health"), "bridge")
        wait_until(lambda: ready("http://127.0.0.1:8502/_stcore/health"), "web")
        spawn("caddy", [caddy, "run", *caddy_args], proxy_env)
        wait_until(lambda: ready("http://127.0.0.1:18080/readyz", launch_id), "local proxy")
        wait_until(lambda: ready(origin + "/readyz", launch_id, verify), "public tunnel", 90)
        if not signed_probe(origin + "/webhook", tester["LINE_CHANNEL_SECRET"], verify=verify):
            raise RuntimeError("Public tester webhook probe failed")
        if not signed_probe(origin + "/webhook/classpulse", official["LINE_CHANNEL_SECRET"], verify=verify):
            raise RuntimeError("Public official webhook probe failed")
        print(f"Web origin: {origin}", flush=True)
        if new_tunnel:
            write_state("awaiting_console")
            print("Update LINE Console before starting automatic worker:", flush=True)
            print(f"Tester webhook: {origin}/webhook\nOfficial webhook: {origin}/webhook/classpulse\n"
                  f"Login callback: {origin}/auth/line/callback", flush=True)
            print("After console Verify and login checks, run: bash classpulse.sh activate", flush=True)
            while not marker("activate", launch_id):
                check()
                time.sleep(1)
        spawn("worker", [sys.executable, "line_personal_auto_worker.py"],
              child_env(official, origin, "worker", launch_id))
        time.sleep(1)
        check()
        write_state("running")
        print("Managed services running. Ctrl+C or bash classpulse.sh stop stops only these children.", flush=True)
        while True:
            check()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping managed services...", flush=True)
    finally:
        # Never signal a PID from disk, or any independently launched service.
        for name in reversed(list(children)):
            p = children[name]
            if p.poll() is None:
                p.terminate()
        for p in children.values():
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        write_state("stopped")
        lock.release()


def status():
    state = read_state()
    if not locked():
        print("Launcher stopped (legacy Flask and independently started tunnel are not managed).")
        return
    print("Phase:", state.get("phase", "starting"))
    print("Origin:", state.get("origin") or "pending")
    print("Legacy Flask: external; tunnel:", state.get("tunnel"))
    for name, value in state.get("services", {}).items():
        print(f"{name}: {value}")
    for name, url in (("legacy", "http://127.0.0.1:5000/health"),
                      ("tester", "http://127.0.0.1:5001/health"),
                      ("bridge", "http://127.0.0.1:5002/health"),
                      ("web", "http://127.0.0.1:8502/_stcore/health")):
        print(f"{name} HTTP: {'ready' if ready(url) else 'unavailable'}")
    if state.get("id"):
        print("local proxy HTTP:", "ready" if ready("http://127.0.0.1:18080/readyz", state["id"]) else "unavailable")


def command_marker(name):
    if not locked():
        raise RuntimeError("No active launcher")
    state = read_state()
    if not re.fullmatch(r"[0-9a-f]{32}", state.get("id", "")):
        raise RuntimeError("Launcher state unavailable")
    if name == "activate" and state.get("phase") != "awaiting_console":
        raise RuntimeError("Launcher is not waiting for LINE Console confirmation")
    atomic_write(RUNTIME / name, state["id"])
    print("Requested:", name)


def logs(service=None):
    state = read_state()
    if not re.fullmatch(r"[0-9a-f]{32}", state.get("id", "")):
        raise RuntimeError("No launcher logs")
    for name in ([service] if service else SERVICES):
        path = RUNTIME / state["id"] / (name + ".log")
        if path.is_file():
            print(f"\n--- {name} (last 20 lines; local only) ---")
            print("\n".join(path.read_text(errors="replace").splitlines()[-20:]))


def main():
    os.umask(0o077)
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    launch = sub.add_parser("start")
    launch.add_argument("--new-tunnel", action="store_true")
    for name in ("stop", "status", "activate"):
        sub.add_parser(name)
    log = sub.add_parser("logs")
    log.add_argument("service", nargs="?", choices=SERVICES)
    args = parser.parse_args()
    if args.command == "start":
        start(args.new_tunnel)
    elif args.command == "status":
        status()
    elif args.command == "logs":
        logs(args.service)
    else:
        command_marker(args.command)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Launcher: {exc}", file=sys.stderr)
        sys.exit(1)
