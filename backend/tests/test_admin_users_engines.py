"""
GET /admin/users/{user_id}: engines bindings (spec 0018) are shown as
GET /admin/iam/bindings shows them — only to a login session with engines
authority, and only while the 0009 decision holds them active (parent chain).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import admin_users_routes
from shared.access import contracts as C
from shared.access import policy
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.iam.models import IamBinding
from shared.models import User
from tests.test_execution_profiles import HEADERS, constraints, grant, world  # noqa: F401


@pytest.fixture
def api(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "iam_mode", "enforce")
    app = FastAPI()
    app.include_router(admin_users_routes.router)

    def db_override():
        with world() as db:
            yield db

    def user_override():
        with world() as db:
            return db.get(User, "bootstrap")

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = user_override
    with TestClient(app) as http:
        yield lambda headers=HEADERS: http.get("/admin/users/observer", headers=headers)


def _roles(r):
    assert r.status_code == 200, r.text
    return [(b["family"], b["role"]) for b in r.json()["iam_bindings"]]


def test_login_session_sees_an_active_engines_binding(world, api):  # noqa: F811
    with world() as db:
        grant(db, actor="observer", role="observer")
    assert _roles(api()) == [("engines", "observer")]


def test_api_key_never_sees_engines_bindings(world, api):  # noqa: F811
    with world() as db:
        grant(db, actor="observer", role="observer")
    assert _roles(api({**HEADERS, "X-API-Key": "k"})) == []


def test_binding_whose_parent_delegation_was_revoked_is_left_out(world, api):  # noqa: F811
    with world() as db:
        envelope = C.Delegation(permissions=sorted(policy.ROLES["observer"]), constraints=constraints(),
                                max_grant_seconds=1800)
        parent = grant(db, actor="delegate", role="access_admin", delegation=envelope)
        grant(db, actor="observer", role="observer", creator="delegate",
              expires=datetime.now(timezone.utc) + timedelta(minutes=10))
    assert _roles(api()) == [("engines", "observer")]
    with world() as db:
        row = db.get(IamBinding, parent["id"])
        row.revoked_at = datetime.utcnow()
        db.commit()
    assert _roles(api()) == []


def test_reading_with_engines_authority_writes_and_locks_nothing(world, api):  # noqa: F811
    from sqlalchemy import event

    with world() as db:
        grant(db, actor="observer", role="observer")
        engine = db.get_bind()
    seen = []
    listener = lambda conn, cursor, statement, *a: seen.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert _roles(api()) == [("engines", "observer")]
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert seen, "the route ran no SQL at all"
    writes = [s for s in seen if s.lstrip().split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
    assert not writes and not [s for s in seen if "FOR UPDATE" in s.upper()]
