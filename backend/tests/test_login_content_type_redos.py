"""A pathological Content-Type must not stall /auth/login (CVE-2024-24762, python-multipart ReDoS)."""
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api import auth_routes
from api.main import app
from shared.database import get_db

# Shape of the advisory's PoC: an unterminated quoted parameter followed by many backslashes.
EVIL_CONTENT_TYPE = 'application/x-www-form-urlencoded; !="\\' + "\\" * 5000
MAX_SECONDS = 5.0  # the vulnerable 0.0.6 parser needs minutes for this input


def test_login_with_pathological_content_type_returns_promptly(monkeypatch):
    # No Redis, no database: the rate limiter and the credential check are stubbed out.
    monkeypatch.setattr(auth_routes, "_lockout_identity", lambda db, login: "acct")
    monkeypatch.setattr(auth_routes.rate_limit, "hit", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes.rate_limit, "check_failures", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes.rate_limit, "record_failure", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "authenticate_user", lambda db, username, password: None)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        started = time.monotonic()
        response = TestClient(app).post(
            "/auth/login",
            content=b"username=a&password=b",
            headers={"Content-Type": EVIL_CONTENT_TYPE},
        )
        elapsed = time.monotonic() - started
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert elapsed < MAX_SECONDS
    # The header still parses as a urlencoded form, so the request reaches the credential check.
    assert response.status_code == 401


def test_python_multipart_parses_pathological_header_in_bounded_time():
    from python_multipart.multipart import parse_options_header

    started = time.monotonic()
    parse_options_header(EVIL_CONTENT_TYPE)
    assert time.monotonic() - started < MAX_SECONDS
