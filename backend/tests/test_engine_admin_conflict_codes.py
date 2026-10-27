"""The engine admin routes answer a control-guard refusal with the guard's own code (spec 0007).

The guards raise store.VersionConflict with a specific reason, and every route used to map it
to 409 VERSION_CONFLICT: a client could not tell "re-read and retry" from "this engine is
managed, go through a runtime profile and a plan". The status stays 409; `code` is the reason.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import engine_admin_routes
from shared.database import get_db
from shared.engine_control import service
from shared.engine_control.models import ControlResource, EngineOperation
from shared.engines import store
from shared.models import Engine
from tests.test_engine_control import prepared, world  # noqa: F401  (fixture)


@pytest.fixture
def client(world, monkeypatch):  # noqa: F811
    # the credentials routes also check the password and the IAM scope: not what is tested here
    monkeypatch.setattr(engine_admin_routes, "_require_password", lambda user, password: None)
    monkeypatch.setattr(engine_admin_routes, "scoped_engine", lambda db, engine_id, user_id: db.get(Engine, engine_id))
    app = FastAPI()
    app.include_router(engine_admin_routes.router)

    def db_override():
        with world() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    admin = lambda: SimpleNamespace(id="admin")  # noqa: E731
    app.dependency_overrides[engine_admin_routes.require_admin_session] = admin
    app.dependency_overrides[engine_admin_routes.access_session] = admin
    with TestClient(app) as c:
        yield c


def _version(world):  # noqa: F811
    with world() as db:
        return db.get(Engine, "e").version


def _delete_credentials(client, world):  # noqa: F811
    body = {"version": _version(world), "current_password": "x"}
    return client.request("DELETE", "/admin/engines/e/credentials", json=body)


def test_binding_put_on_a_managed_engine_is_runtime_operation_required(world, client):  # noqa: F811
    prepared(world)
    r = client.put("/admin/engines/e/features/transcription", json={"workers": 3, "version": _version(world)})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "RUNTIME_OPERATION_REQUIRED"


def test_a_resource_held_by_an_operation_is_operation_conflict(world, client):  # noqa: F811
    with world() as db:
        db.add(ControlResource(key="connection-test", owner_engine_id="e", operation_id="active-test"))
        db.commit()
    r = _delete_credentials(client, world)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "OPERATION_CONFLICT"


def test_reset_health_on_a_held_resource_is_a_409_not_a_500(world, client):  # noqa: F811
    with world() as db:
        db.add(ControlResource(key="connection-test", owner_engine_id="e", operation_id="active-test"))
        db.commit()
    r = client.post("/admin/engines/e/reset-health")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "OPERATION_CONFLICT"


def test_removing_the_only_cleanup_credential_is_cleanup_credential_required(world, client):  # noqa: F811
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        row = db.get(EngineOperation, op["operation_id"])
        row.state = "succeeded"
        row.handles = {"maintenance": {"cleanup_required": True}}
        db.get(ControlResource, p["resources"][0]).operation_id = None
        db.commit()
    r = _delete_credentials(client, world)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CLEANUP_CREDENTIAL_REQUIRED"


def test_a_stale_version_is_still_version_conflict(world, client):  # noqa: F811
    r = client.put("/admin/engines/e/features/transcription", json={"workers": 1, "version": _version(world) + 5})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "VERSION_CONFLICT"


def test_the_default_code_of_a_bare_version_conflict():
    assert store.VersionConflict("re-read").code == "VERSION_CONFLICT"


ROUTES = [
    ("put", "/admin/engines/e/features/transcription", {"workers": 1}),
    ("delete", "/admin/engines/e/features/transcription", None),
    ("put", "/admin/engines/l/gpus", {"gpus": []}),  # only the local engine declares GPUs
    ("post", "/admin/engines/e/activate", None),
    ("post", "/admin/engines/e/pause", None),
    ("post", "/admin/engines/e/reset-health", None),
    ("put", "/admin/engines/e/budget", {"limit_usd": "10"}),
    ("delete", "/admin/engines/e/credentials", {"current_password": "x"}),
]


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_a_guard_access_refusal_keeps_its_status_and_code_on_every_route(
    world, client, monkeypatch, method, path, body  # noqa: F811
):
    # the guard turns an IAM refusal into EngineStateError(403, code): some routes let it escape as a 500
    import shared.engine_control.guards as guards

    with world() as db:
        db.add(Engine(id="l", slug="local-test", display_name="Local", adapter_type="local",
                      config={"features": {}}, deployments={}, version=0))
        db.commit()

    def refuse(*a, **kw):
        raise store.EngineStateError("ACCESS_DENIED", 403, code="ACCESS_DENIED")

    monkeypatch.setattr(guards, "before_write", refuse)
    r = client.request(method.upper(), path, json=body)
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "ACCESS_DENIED"
