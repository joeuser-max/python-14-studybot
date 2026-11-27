import pytest

from deploy.staging_server import configure


def settings():
    return {
        "RAILWAY_VOLUME_MOUNT_PATH": "/data",
        "RAILWAY_PUBLIC_DOMAIN": "classpulse-test.up.railway.app",
        "CLASSPULSE_WEB_ORIGIN": "https://classpulse-test.up.railway.app",
        "CLASSPULSE_STAGING_PASSWORD_HASH": "$2a$14$" + "a" * 53,
        "LINE_LOGIN_CHANNEL_ID": "1234567890",
        "LINE_LOGIN_CHANNEL_SECRET": "fake",
        "CLASSPULSE_STAGING_TEST_USERS": "U" + "a" * 32,
        "LINE_CHANNEL_SECRET": "must-not-be-used",
        "OPENAI_API_KEY": "must-not-be-used",
        "CLASSPULSE_PUBLIC_WEB": "1",
    }


def test_cloud_config_forces_isolated_private_mode():
    env = settings()
    assert configure(env) == ["U" + "a" * 32]
    assert env["CLASSPULSE_DATA_DIR"] == "/data/classpulse"
    assert env["CLASSPULSE_LINE_WEB_STAGING"] == "1"
    assert env["CLASSPULSE_PUBLIC_WEB"] == "0"
    assert env["LINE_FRIEND_DEMO_ENABLED"] == "0"
    assert env["LINE_FRIEND_DEMO_SEED_ENABLED"] == "0"
    assert env["LINE_CHANNEL_SECRET"] == env["LINE_CHANNEL_ACCESS_TOKEN"] == ""
    assert env["OPENAI_API_KEY"] == env["GEMINI_API_KEY"] == ""


@pytest.mark.parametrize(("key", "value"), [
    ("RAILWAY_VOLUME_MOUNT_PATH", ""),
    ("RAILWAY_VOLUME_MOUNT_PATH", "/tmp"),
    ("PORT", "5001"),
    ("PORT", "invalid"),
    ("RAILWAY_PUBLIC_DOMAIN", "evil.example"),
    ("CLASSPULSE_WEB_ORIGIN", "http://classpulse-test.up.railway.app"),
    ("CLASSPULSE_STAGING_PASSWORD_HASH", "plaintext"),
    ("LINE_LOGIN_CHANNEL_ID", "not-numeric"),
    ("LINE_LOGIN_CHANNEL_SECRET", ""),
    ("CLASSPULSE_STAGING_TEST_USERS", ""),
    ("CLASSPULSE_STAGING_TEST_USERS", "U" + "a" * 32 + ",U" + "a" * 32),
])
def test_invalid_configuration_is_rejected(key, value):
    env = settings()
    env[key] = value
    with pytest.raises(ValueError):
        configure(env)
