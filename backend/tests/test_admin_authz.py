"""Admin endpoints must only be reachable by users listed in ADMIN_USER_IDS."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import admin_routes

USER = SimpleNamespace(id="11111111-1111-1111-1111-111111111111", email="user@example.com")


@pytest.fixture
def admin_ids(monkeypatch):
    def set_ids(value):
        monkeypatch.setattr(admin_routes.settings, "admin_user_ids", value)
    return set_ids


@pytest.mark.parametrize(
    "configured",
    ["", "   ", "22222222-2222-2222-2222-222222222222", USER.id + "0"],
    ids=["empty", "blank", "other-user", "prefix-only"],
)
def test_non_admin_is_forbidden(admin_ids, configured):
    admin_ids(configured)
    with pytest.raises(HTTPException) as exc:
        admin_routes.require_admin(USER)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "configured",
    [USER.id, f" 22222222-2222-2222-2222-222222222222 , {USER.id} "],
    ids=["single", "list-with-spaces"],
)
def test_admin_is_allowed(admin_ids, configured):
    admin_ids(configured)
    assert admin_routes.require_admin(USER) is USER
