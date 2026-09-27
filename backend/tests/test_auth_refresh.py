"""POST /auth/refresh: the frontend's session heartbeat."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import auth_routes
from shared.auth import create_access_token, verify_token
from shared.database import Base, get_db
from shared.models import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id="u1", email="a@example.com", username="a", hashed_password="x", is_active=True),
        User(id="u2", email="b@example.com", username="b", hashed_password="x", is_active=False),
    ])
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_gets_a_new_one_for_the_same_user(client):
    response = client.post("/auth/refresh", headers=bearer(create_access_token({"sub": "u1"})))
    assert response.status_code == 200
    assert verify_token(response.json()["access_token"]) == "u1"


def test_expired_token_is_401(client):
    expired = create_access_token({"sub": "u1"}, expires_delta=timedelta(seconds=-1))
    assert client.post("/auth/refresh", headers=bearer(expired)).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-jwt"}, {"X-API-Key": "doc2md_sk_x"}])
def test_missing_or_invalid_credentials_are_401(client, headers):
    assert client.post("/auth/refresh", headers=headers).status_code == 401


def test_inactive_user_cannot_refresh(client):
    assert client.post("/auth/refresh", headers=bearer(create_access_token({"sub": "u2"}))).status_code == 401


def test_unknown_user_cannot_refresh(client):
    assert client.post("/auth/refresh", headers=bearer(create_access_token({"sub": "ghost"}))).status_code == 401
