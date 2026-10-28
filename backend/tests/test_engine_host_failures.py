"""
scripts/engine_host_failures.py: what the host agent reports when an operation fails.

The operation's error carries the API's refusal code (ACCESS_REVOKED, ...), or
HTTP_<status>, not "HTTP Error 403: Forbidden", so the admin sees why the host's
call was refused.
"""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def failures():
    if not (SCRIPTS / "engine_host_failures.py").exists():
        pytest.skip("scripts not mounted")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import engine_host_failures

    return engine_host_failures


def _http(status, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError("https://api/x", status, "Forbidden", {}, io.BytesIO(raw))


@pytest.mark.parametrize("code", ["ACCESS_REVOKED", "ACCESS_DENIED", "HOST_IDENTITY_REQUIRED"])
def test_an_api_refusal_reports_its_code(failures, code):
    assert failures.failure_code(_http(403, {"detail": {"code": code, "message": "x"}})) == code


@pytest.mark.parametrize("body", [{"detail": "Forbidden"}, {"error": "x"}, b"<html>proxy</html>", b""],
                         ids=["text-detail", "no-detail", "not-json", "empty"])
def test_an_http_error_without_a_code_reports_its_status(failures, body):
    assert failures.failure_code(_http(403, body)) == "HTTP_403"


def test_any_other_failure_keeps_its_message(failures):
    assert failures.failure_code(RuntimeError("HOST_COMMAND_FAILED:1")) == "HOST_COMMAND_FAILED:1"
    assert len(failures.failure_code(RuntimeError("x" * 500))) == 200


def test_the_agent_reports_through_it(failures):
    """The agent's result path and the journal line use this module, not a copy."""
    import engine_host_agent

    assert engine_host_agent.failure_code is failures.failure_code
    assert engine_host_agent.describe_failure is failures.describe_failure
