"""
The routes merged from origin/main (#48: datalakes, faces, image full analysis)
under IAM (spec 0014 §4.4, CA1, CA12), in every IAM_MODE, `enforce` included.

Semantics are the ones main shipped: owner only; missing and someone else's are the
same 404 with the route's own detail ("Conexão não encontrada", "Job não
encontrado", "Full Analysis não encontrada"); bootstrap reads no one else's data;
an API key acts as its owner (0014 §2: key behaviour is unchanged until 0015).
"""

import logging
from datetime import datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import datalake_routes, deps, face_routes, image_routes
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.datalake import service
from shared.datalake.secrets import seal
from shared.models import (DatalakeConnection, ImageAnalysisRun, Job, JobDatalakeExport, JobStatus, Page,
                           User)

ALICE, BOB, ROOT = "user-alice", "user-bob", "user-root"
MODES = ("off", "shadow", "enforce")
CREDS = {"access_key": "test-key", "secret_key": "test-secret"}
NOT_FOUND_DL = (404, "Conexão não encontrada")
NOT_FOUND_JOB = (404, deps.JOB_NOT_FOUND_DETAIL)
NOT_FOUND_RUN = (404, "Full Analysis não encontrada")
# A request is a session or an API key; the key acts as its owner in this slice.
CREDENTIALS = ({}, {"x-api-key": "k"})


def connection(cid, owner, **kw):
    return DatalakeConnection(id=cid, user_id=owner, name=cid, provider="s3",
                              config={"buckets": ["allowed"], **kw.pop("config", {})},
                              credentials_encrypted=seal(owner, cid, CREDS), **kw)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id=ALICE, email="a@example.com", username="alice", hashed_password="x", is_active=True),
        User(id=BOB, email="b@example.com", username="bob", hashed_password="x", is_active=True),
        # Bootstrap reads no one else's data (0014 §4.4): root is denied like bob.
        User(id=ROOT, email="r@example.com", username="root", hashed_password="x", is_active=True,
             is_admin=True),
    ])
    session.flush()
    session.add_all([connection("dl-a", ALICE), connection("dl-b", BOB), connection("dl-a-used", ALICE)])
    for job_id, owner in (("img-a", ALICE), ("img-a-done", ALICE), ("img-b", BOB), ("doc-a", ALICE)):
        session.add(Job(id=job_id, user_id=owner, name=job_id, filename=f"{job_id}.png",
                        status=JobStatus.COMPLETED if job_id != "img-a" else JobStatus.PROCESSING,
                        job_type="MAIN", source_type="image", created_at=datetime(2026, 1, 1)))
    session.flush()
    for job_id, status in (("img-a", "processing"), ("img-a-done", "completed"), ("img-b", "processing")):
        session.add(ImageAnalysisRun(job_id=job_id, options={}, source_path=f"images/{job_id}/source",
                                     deadline_at=datetime(2030, 1, 1), status=status))
    # A child job of alice's (no row of its own): authorized through its MAIN job,
    # still no Full Analysis of its own.
    session.add(Page(job_id="img-a", page_number=1, page_job_id="img-a-p1", status="completed"))
    session.add(JobDatalakeExport(job_id="img-a-done", connection_id="dl-a-used", bucket="allowed",
                                  status="failed", attempts=5))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(params=MODES)
def mode(request, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "iam_mode", request.param)
    monkeypatch.setattr(s, "admin_user_ids", "")
    return request.param


@pytest.fixture
def no_shadow_noise(caplog, mode):
    """In shadow the new path is evaluated and swallowed: it must neither raise nor diverge."""
    caplog.set_level(logging.WARNING, logger="shared.iam")
    caplog.set_level(logging.WARNING, logger="api.iam_deps")
    yield
    if mode == "shadow":
        noise = [r.getMessage() for r in caplog.records
                 if r.getMessage().startswith(("iam_shadow_divergence", "iam_shadow_error"))]
        assert not noise, noise


class StubAdapter:
    def buckets(self):
        return ["allowed"]

    def bucket_exists(self, name):
        return name == "allowed"

    def objects(self, bucket, prefix, limit):
        return [{"key": f"{prefix}x.json"}]


@pytest.fixture
def client(db, mode, no_shadow_noise, monkeypatch):
    adapter = StubAdapter()
    monkeypatch.setattr(service, "adapter_for", lambda c: adapter)
    monkeypatch.setattr(datalake_routes, "adapter_for", lambda c: adapter)
    monkeypatch.setattr(service, "enqueue_export", lambda job_id, session_factory=None: None)
    monkeypatch.setattr(deps, "_redis_owner_matches", lambda job_id, user_id: False)
    monkeypatch.setattr(deps, "_redis_job_status", lambda job_id: None)
    app = FastAPI()
    app.include_router(face_routes.router)
    app.include_router(datalake_routes.router)
    app.include_router(datalake_routes.job_router)
    app.include_router(image_routes.router)

    def current_user(request: Request):
        # The real get_current_user marks API-key requests on request.state.
        request.state.api_key = object() if request.headers.get("x-api-key") else None
        return db.get(User, app.state.user)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = current_user
    tc = TestClient(app)

    def as_user(uid):
        app.state.user = uid
        return tc

    return as_user


def _detail(response):
    return response.status_code, response.json().get("detail")


# -- datalake connections by id ------------------------------------------------------


@pytest.mark.parametrize("method,path,body", [
    ("get", "/datalakes/dl-a/buckets", None),
    ("get", "/datalakes/dl-a/objects?bucket=allowed", None),
    ("post", "/datalakes/dl-a/test", {}),
    ("patch", "/datalakes/dl-a", {"name": "renamed"}),
    ("delete", "/datalakes/dl-a", None),
])
@pytest.mark.parametrize("headers", CREDENTIALS)
def test_connection_routes_are_owner_only_with_the_legacy_404(client, db, method, path, body, headers):
    kw = {"headers": headers, **({"json": body} if body is not None else {})}
    for uid in (BOB, ROOT):
        assert _detail(getattr(client(uid), method)(path, **kw)) == NOT_FOUND_DL, (uid, path)
    missing = path.replace("dl-a", "no-such-connection")
    assert _detail(getattr(client(ALICE), method)(missing, **kw)) == NOT_FOUND_DL
    db.expire_all()
    assert db.get(DatalakeConnection, "dl-a").name == "dl-a"  # untouched by the denied calls

    r = getattr(client(ALICE), method)(path, **kw)
    assert r.status_code in (200, 204), r.text


def test_owner_results_are_the_legacy_ones(client, db):
    alice = client(ALICE)
    assert alice.get("/datalakes/dl-a/buckets").json() == {"buckets": ["allowed"], "configured": True}
    assert alice.post("/datalakes/dl-a/test", json={"bucket": "allowed"}).json() == {"ok": True, "bucket": "allowed"}
    r = alice.patch("/datalakes/dl-a", json={"name": "Renamed", "credentials": {"access_key": "n", "secret_key": "s"}})
    assert r.status_code == 200 and r.json()["name"] == "Renamed"
    # Re-sealed to the owner: the connection still opens (unseal checks the binding).
    from shared.datalake.secrets import unseal
    db.expire_all()
    assert unseal(db.get(DatalakeConnection, "dl-a")) == {"access_key": "n", "secret_key": "s"}
    # A connection referenced by a job cannot be deleted, as before.
    assert alice.delete("/datalakes/dl-a-used").status_code == 409
    assert alice.delete("/datalakes/dl-a").status_code == 204
    assert db.get(DatalakeConnection, "dl-a") is None


@pytest.mark.parametrize("path,body", [
    ("/datalakes/discover", {"provider": "s3", "connection_id": "dl-a"}),
    ("/datalakes/partition-preview", {"connection_id": "dl-a"}),
    ("/datalakes/buckets", {"provider": "s3", "connection_id": "dl-a", "bucket": "new-bucket"}),
])
def test_body_referenced_connections_are_owner_only(client, path, body):
    """The draft routes are self-service, but a connection they name is still the caller's only."""
    for uid in (BOB, ROOT):
        assert _detail(client(uid).post(path, json=body)) == NOT_FOUND_DL, (uid, path)
    assert client(ALICE).post(path, json=body).status_code not in (401, 403, 404)


# -- job deliveries ----------------------------------------------------------------


@pytest.mark.parametrize("headers", CREDENTIALS)
def test_job_delivery_routes_are_owner_only(client, db, headers):
    for uid in (BOB, ROOT):
        assert _detail(client(uid).get("/jobs/img-a-done/datalake", headers=headers)) == NOT_FOUND_JOB
        assert _detail(client(uid).post("/jobs/img-a-done/datalake/retry", headers=headers)) == NOT_FOUND_JOB
    assert _detail(client(ALICE).get("/jobs/missing/datalake", headers=headers)) == NOT_FOUND_JOB

    alice = client(ALICE)
    assert alice.get("/jobs/img-a-done/datalake", headers=headers).json()["destination"]["status"] == "failed"
    assert alice.get("/jobs/doc-a/datalake", headers=headers).json() == {"destination": None}
    r = alice.post("/jobs/img-a-done/datalake/retry", headers=headers)
    assert r.status_code == 202 and r.json()["destination"]["status"] == "pending", r.text
    # The owner's job with no destination, and an unfinished one: the route's own answers.
    assert _detail(alice.post("/jobs/doc-a/datalake/retry", headers=headers)) == (404, "Destino não encontrado")
    assert alice.post("/jobs/img-a/datalake/retry", headers=headers).status_code == 409


# -- image full analysis cancel ----------------------------------------------------


@pytest.mark.parametrize("headers", CREDENTIALS)
def test_image_cancel_is_owner_only_with_its_own_404(client, db, headers):
    for uid in (BOB, ROOT):
        assert _detail(client(uid).post("/images/img-a/cancel", headers=headers)) == NOT_FOUND_RUN
    alice = client(ALICE)
    for job_id in ("missing", "img-b", "doc-a", "img-a-p1"):  # missing, bob's, no run, a child job
        assert _detail(alice.post(f"/images/{job_id}/cancel", headers=headers)) == NOT_FOUND_RUN, job_id
    db.expire_all()
    assert not db.get(ImageAnalysisRun, "img-b").cancel_requested

    r = alice.post("/images/img-a/cancel", headers=headers)
    assert r.status_code == 202 and r.json() == {"job_id": "img-a", "status": "processing", "cancel_requested": True}
    r = alice.post("/images/img-a-done/cancel", headers=headers)
    assert r.status_code == 200 and r.json()["cancel_requested"] is False


# -- self-service `require(...)` -----------------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("post", "/images/analyze"),             # images.analyze
    ("post", "/images/analyze/upload"),      # images.analyze
    ("post", "/images/faces"),               # images.analyze
    ("post", "/images/faces/upload"),        # images.analyze
    ("get", "/images/faces/capabilities"),   # images.analyze
    ("post", "/datalakes"),                  # datalakes.create
    ("post", "/datalakes/discover"),         # datalakes.create
    ("post", "/datalakes/buckets"),          # datalakes.create
    ("post", "/datalakes/partition-preview"),  # datalakes.create
])
@pytest.mark.parametrize("headers", CREDENTIALS)
def test_self_service_routes_admit_every_active_user(client, method, path, headers):
    # Decided before the body is validated: never 401/403 for an active user.
    for uid in (BOB, ROOT):
        r = getattr(client(uid), method)(path, headers=headers)
        assert r.status_code not in (401, 403), (uid, path, r.text)


def test_create_connection_belongs_to_the_caller(client, db):
    r = client(BOB).post("/datalakes", json={"name": "mine", "provider": "s3", "credentials": CREDS},
                         headers={"x-api-key": "k"})
    assert r.status_code == 201, r.text
    assert db.get(DatalakeConnection, r.json()["id"]).user_id == BOB
