"""Registration policy is durable, enforced server-side, and editable only by admins."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401
from api import auth_routes, admin_routes, platform_settings_routes
from shared.auth import create_access_token, hash_password
from shared.database import Base, get_db
from shared.models import User
from shared.platform_settings import signup_enabled

USER_IDS = {"admin": "00000000-0000-0000-0000-000000000001", "member": "00000000-0000-0000-0000-000000000002", "inactive": "00000000-0000-0000-0000-000000000003"}


@pytest.fixture
def app_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        password = hash_password("test-password")
        db.add_all([
            User(id=USER_IDS["admin"], email="admin@example.com", username="admin", hashed_password=password, is_admin=True),
            User(id=USER_IDS["member"], email="member@example.com", username="member", hashed_password=password),
            User(id=USER_IDS["inactive"], email="inactive@example.com", username="inactive", hashed_password=password, is_admin=True, is_active=False),
        ])
        db.commit()
    monkeypatch.setattr(admin_routes.settings, "admin_user_ids", "")
    monkeypatch.setattr(auth_routes.rate_limit, "hit", lambda *a, **kw: None)
    monkeypatch.setattr(auth_routes.rate_limit, "check_failures", lambda *a, **kw: None)
    monkeypatch.setattr(auth_routes.rate_limit, "reset", lambda *a, **kw: None)
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    app.include_router(platform_settings_routes.router)

    def get_session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    yield app, sessions
    engine.dispose()


def bearer(user="admin"):
    return {"Authorization": f"Bearer {create_access_token({'sub': USER_IDS[user]})}"}


def test_default_policy_is_public_and_signup_is_open(app_db):
    app, sessions = app_db
    with TestClient(app) as client:
        response = client.get("/auth/registration-settings")
        assert response.json() == {"signup_enabled": True}
        assert response.headers["cache-control"] == "no-store"
        response = client.post("/auth/register", json={"username": "new-user", "email": "new@example.com", "password": "test-password"})
        assert response.status_code == 201
        assert response.json()["is_admin"] is False


def test_close_persists_blocks_direct_signup_and_reopens(app_db):
    app, sessions = app_db
    with TestClient(app) as client:
        response = client.patch("/admin/settings", headers=bearer(), json={"signup_enabled": False})
        assert response.status_code == 200
        assert response.json() == {"signup_enabled": False}
    # A new client/session observes the persisted value (no process-local flag).
    with sessions() as db:
        assert signup_enabled(db) is False
    with TestClient(app) as client:
        assert client.get("/admin/settings", headers=bearer()).json() == {"signup_enabled": False}
        assert client.get("/auth/registration-settings").json() == {"signup_enabled": False}
        payload = {"username": "blocked-user", "email": "blocked@example.com", "password": "test-password"}
        for headers in ({}, bearer()):
            assert client.post("/auth/register", json=payload, headers=headers).status_code == 403
        with sessions() as db:
            assert db.query(User).count() == 3
        # Existing accounts keep their login and session access.
        assert client.post("/auth/login", data={"username": "member", "password": "test-password"}).status_code == 200
        assert client.get("/auth/me", headers=bearer("member")).status_code == 200
        assert client.patch("/admin/settings", headers=bearer(), json={"signup_enabled": True}).status_code == 200
        assert client.post("/auth/register", json=payload).status_code == 201


@pytest.mark.parametrize("identity,expected", [(None, 401), ("member", 403), ("inactive", 400)])
def test_settings_require_active_admin(app_db, identity, expected):
    app, sessions = app_db
    with TestClient(app) as client:
        headers = bearer(identity) if identity else {}
        assert client.get("/admin/settings", headers=headers).status_code == expected
        assert client.patch("/admin/settings", headers=headers, json={"signup_enabled": False}).status_code == expected
        assert client.get("/auth/registration-settings").json() == {"signup_enabled": True}


def test_configured_admin_uses_existing_authorization(app_db, monkeypatch):
    app, sessions = app_db
    monkeypatch.setattr(admin_routes.settings, "admin_user_ids", USER_IDS["member"])
    with TestClient(app) as client:
        assert client.patch("/admin/settings", headers=bearer("member"), json={"signup_enabled": False}).status_code == 200


@pytest.mark.parametrize("payload", [{}, {"signup_enabled": "false"}, {"signup_enabled": None}, {"signup_enabled": 0}, {"signup_enabled": True, "is_admin": True}])
def test_invalid_policy_is_rejected(app_db, payload):
    app, sessions = app_db
    with TestClient(app) as client:
        assert client.patch("/admin/settings", headers=bearer(), json=payload).status_code == 422
        assert client.get("/auth/registration-settings").json() == {"signup_enabled": True}


def test_policy_store_failure_never_opens_registration(app_db, monkeypatch):
    app, sessions = app_db

    def unavailable(db):
        raise OperationalError("policy unavailable", None, Exception("unavailable"))

    monkeypatch.setattr(auth_routes, "signup_enabled", unavailable)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/auth/register", json={"username": "blocked-user", "email": "blocked@example.com", "password": "test-password"})
        assert response.status_code == 500
    with sessions() as db:
        assert db.query(User).count() == 3
