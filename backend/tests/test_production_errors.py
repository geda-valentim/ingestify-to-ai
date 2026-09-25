"""Production must not leak exception details to clients."""
import asyncio
import json

import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import main
from shared.config import Settings


def test_environment_defaults_to_production(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert Settings(_env_file=None).environment == "production"


def test_sql_echo_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SQL_ECHO", raising=False)
    assert Settings(_env_file=None).sql_echo is False


@pytest.mark.parametrize("environment, leaks", [("production", False), ("development", True)])
def test_unhandled_errors_hide_details_in_production(monkeypatch, environment, leaks):
    monkeypatch.setattr(main.settings, "environment", environment)
    secret = "mysql+pymysql://root:hunter2@db/ingestify unreachable"
    response = asyncio.run(main.global_exception_handler(None, RuntimeError(secret)))
    body = json.loads(response.body)
    assert response.status_code == 500
    assert (secret in json.dumps(body)) is leaks
