import hashlib
import hmac
import base64
import json
import os

import pytest
from filelock import FileLock

from deploy import local_service_manager as manager


@pytest.fixture
def configured(tmp_path, monkeypatch):
    data = tmp_path / "data" / "friend-e2e"
    data.mkdir(parents=True)
    runtime = tmp_path / "data" / "local-launcher"
    runtime.mkdir()
    monkeypatch.setattr(manager, "ROOT", tmp_path)
    monkeypatch.setattr(manager, "DATA", data)
    monkeypatch.setattr(manager, "RUNTIME", runtime)
    monkeypatch.setattr(manager, "STATE", runtime / "state.json")
    for name, label in (("friend-e2e.env", "tester"), ("official-bridge.env", "official")):
        path = tmp_path / "data" / name
        path.write_text(f"CLASSPULSE_DATA_DIR={data}\n"
                        "CLASSPULSE_WEB_ORIGIN=https://example.trycloudflare.com\n"
                        f"LINE_CHANNEL_SECRET={label}-secret\n"
                        f"LINE_CHANNEL_ACCESS_TOKEN={label}-token\n"
                        "LINE_LOGIN_CHANNEL_ID=123\nLINE_LOGIN_CHANNEL_SECRET=login-secret\n"
                        "AI_PROVIDER=gemini\nGEMINI_API_KEY=fake-key\n"
                        "CLASSPULSE_FRIEND_AI_SYNC=1\n")
        path.chmod(0o600)
    return data, runtime


@pytest.mark.skipif(os.name == "nt", reason="macOS local supervisor requires POSIX mode 0600; Windows offline demo uses Streamlit directly")
def test_configs_and_role_env_are_isolated(configured, monkeypatch):
    data, _ = configured
    tester, official = manager.load_configs()
    monkeypatch.setenv("CLASSPULSE_STAGING_TEST_USERS", "stale")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "inherited")
    for role in ("tester", "bridge", "web", "worker", "caddy", "tunnel"):
        env = manager.child_env(official if role in ("bridge", "worker") else tester,
                                "https://new.trycloudflare.com", role, "run")
        assert env["CLASSPULSE_DATA_DIR"] == str(data)
        assert env["CLASSPULSE_WEB_ORIGIN"] == "https://new.trycloudflare.com"
        assert "CLASSPULSE_STAGING_TEST_USERS" not in env
        assert env["CLASSPULSE_PUBLIC_WEB"] == "0"
        assert env["CLASSPULSE_FRIEND_AUTO_PUSH"] == ("1" if role in ("bridge", "worker") else "0")
        assert env["GEMINI_API_KEY"] == ("fake-key" if role == "bridge" else "")
        assert env["LINE_CHANNEL_ACCESS_TOKEN"] == (
            "official-token" if role in ("bridge", "worker") else "tester-token" if role == "tester" else "")
        if role in ("caddy", "tunnel"):
            assert not env["LINE_LOGIN_CHANNEL_SECRET"]


@pytest.mark.skipif(os.name == "nt", reason="macOS local supervisor requires POSIX mode 0600; Windows offline demo uses Streamlit directly")
def test_rejects_duplicate_credentials_and_loose_permissions(configured):
    path = manager.ROOT / "data" / "official-bridge.env"
    original = path.read_text()
    path.write_text(original.replace("official-token", "tester-token"))
    with pytest.raises(ValueError, match="must differ"):
        manager.load_configs()
    path.write_text(original)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="mode 600"):
        manager.load_configs()


def test_signed_empty_probe_never_follows_redirects(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True}
    def fake(url, **kwargs):
        assert kwargs["data"] == b'{"events":[]}'
        assert kwargs["allow_redirects"] is False
        expected = base64.b64encode(hmac.new(b"fake", kwargs["data"], hashlib.sha256).digest()).decode()
        assert kwargs["headers"]["X-Line-Signature"] == expected
        assert kwargs["verify"] is True
        return Response()
    monkeypatch.setattr(manager.requests, "post", fake)
    assert manager.signed_probe("https://example.trycloudflare.com/webhook", "fake")


def test_controls_are_run_specific_and_do_not_signal_pids(configured):
    _, runtime = configured
    run = "a" * 32
    manager.atomic_write(manager.STATE, json.dumps({"id": run, "phase": "awaiting_console"}))
    with pytest.raises(RuntimeError, match="No active"):
        manager.command_marker("stop")
    with FileLock(str(runtime / "supervisor.lock")):
        manager.command_marker("activate")
        assert manager.marker("activate", run)
        assert not manager.marker("activate", "b" * 32)
        manager.command_marker("stop")
        assert manager.marker("stop", run)
    assert not manager.locked()


def test_occupied_ports_are_refused_without_terminating_process(monkeypatch):
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setattr(manager, "PORTS", (port,))
        assert manager.free_ports() == [port]
        assert listener.fileno() >= 0
