import base64
import hashlib
import hmac
from datetime import datetime
from zoneinfo import ZoneInfo

from line_bot import resolve_class_slot, verify_line_signature


TZ = ZoneInfo("Asia/Taipei")


def test_valid_line_signature():
    body = b'{"events":[]}'
    secret = "test-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    assert verify_line_signature(body, signature, secret)


def test_invalid_line_signature():
    assert not verify_line_signature(b'{"events":[]}', "wrong", "test-secret")
