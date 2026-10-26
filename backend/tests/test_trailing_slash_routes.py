"""
No route may answer a URL the frontend builds with a 307.

FastAPI's `redirect_slashes` turns `POST /api-keys` into a 307 to `/api-keys/`
when only the slashed path is registered. Behind the dev tunnel the app runs
with `root_path="/api"` and the redirect's Location drops that prefix, so the
browser lands on a Next.js page: POST got 405 and GET got HTML, while the same
calls worked on the API port directly. Three layers keep it from coming back:

  1. the API-key collection answers both spellings, with and without a session;
  2. every registered route ending in "/" also has its bare twin, for the same
     methods (the OpenAPI keeps only the slashed one, so the pins don't move);
  3. every URL `frontend/lib/api.ts` builds matches a registered route with the
     trailing slash exactly as written - `test_frontend_api_contract` matches
     paths with the slashes stripped, which is why it stayed green.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import apikey_routes
from shared.auth import get_current_active_user
from shared.database import Base, get_db
from shared.models import User
from tests.test_frontend_api_contract import API_CLIENT, _client_paths

ALICE = "user-alice"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _client(db, signed_in):
    # root_path as behind the tunnel: a 307 there loses the prefix.
    app = FastAPI(root_path="/api")
    app.include_router(apikey_routes.router, prefix="/api-keys")
    app.dependency_overrides[get_db] = lambda: db
    if signed_in:
        app.dependency_overrides[get_current_active_user] = lambda: db.get(User, ALICE)
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", ["/api-keys", "/api-keys/"])
def test_api_key_collection_answers_both_spellings(db, path):
    client = _client(db, signed_in=True)

    created = client.post(path, json={"name": f"robo {path}"})
    assert created.status_code == 201, created.text
    listed = client.get(path)
    assert listed.status_code == 200, listed.text
    assert f"robo {path}" in {k["name"] for k in listed.json()}


@pytest.mark.parametrize("path", ["/api-keys", "/api-keys/"])
def test_api_key_collection_without_a_session_is_401_not_a_redirect(db, path):
    client = _client(db, signed_in=False)

    assert client.post(path, json={"name": "robo"}).status_code == 401
    assert client.get(path).status_code == 401


def _methods_by_path():
    from api.main import app

    found = {}
    for route in app.routes:
        found.setdefault(route.path, set()).update(getattr(route, "methods", None) or ())
    return found


def test_every_slashed_route_has_its_bare_twin():
    routes = _methods_by_path()
    missing = sorted(
        f"{path} ({', '.join(sorted(methods - routes.get(path.rstrip('/'), set())))})"
        for path, methods in routes.items()
        if path != "/" and path.endswith("/") and methods - routes.get(path.rstrip("/"), set())
    )
    assert not missing, (
        "These routes only exist with a trailing slash, so the bare path answers 307 "
        "and behind root_path the redirect leaves the API: " + ", ".join(missing)
        + ". Stack a hidden twin: @router.<verb>(\"\", ..., include_in_schema=False)."
    )


def _segments_match(client_path, route_path):
    client, route = client_path.split("/"), route_path.split("/")
    return len(client) == len(route) and all(
        c == r or (c == "{}" and r.startswith("{") and r.endswith("}"))
        for c, r in zip(client, route)
    )


def test_every_url_the_client_builds_matches_a_route_slash_for_slash():
    if not API_CLIENT.exists():
        pytest.skip("frontend not present in this checkout")

    routes = list(_methods_by_path())
    redirected = sorted(
        path for path in _client_paths()
        if not any(_segments_match(path, route) for route in routes)
        and any(_segments_match(path.rstrip("/") if path.endswith("/") else path + "/", route) for route in routes)
    )
    assert not redirected, (
        "frontend/lib/api.ts builds URLs that only match a route with the trailing slash "
        "flipped, so FastAPI answers 307: " + ", ".join(redirected)
    )
