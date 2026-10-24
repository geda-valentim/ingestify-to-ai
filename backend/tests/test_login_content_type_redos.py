"""A pathological Content-Type must not stall /auth/login (CVE-2024-24762, python-multipart ReDoS)."""
import time

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.main import app
from shared.database import get_db

# Shape of the advisory's PoC: an unterminated quoted parameter followed by many backslashes.
EVIL_CONTENT_TYPE = 'application/x-www-form-urlencoded; !="\\' + "\\" * 5000
MAX_SECONDS = 5.0  # the vulnerable 0.0.6 parser needs minutes for this input


def test_login_with_pathological_content_type_returns_promptly():
    app.dependency_overrides[get_db] = lambda: MagicMock()  # the form is rejected before any DB use
    try:
        client = TestClient(app, raise_server_exceptions=False)
        started = time.monotonic()
        response = client.post(
            "/auth/login",
            content=b"username=a&password=b",
            headers={"Content-Type": EVIL_CONTENT_TYPE},
        )
        elapsed = time.monotonic() - started
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert elapsed < MAX_SECONDS


def test_python_multipart_parses_pathological_header_in_bounded_time():
    from python_multipart.multipart import parse_options_header

    started = time.monotonic()
    parse_options_header(EVIL_CONTENT_TYPE)
    assert time.monotonic() - started < MAX_SECONDS
