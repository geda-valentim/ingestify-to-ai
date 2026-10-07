"""
Data routes by id (spec 0014 §8 item 4): converted to `authorized(...)` /
`require(...)` with the legacy semantics — owner only, the same 404 (detail and
error_code) for missing and someone else's — under every IAM_MODE, `enforce`
included. The pre-existing route tests run in the default `off`; this file pins
that `enforce` answers identically.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import apikey_routes, deps, live_routes, projects_api, routes, tag_routes
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.models import APIKey, Folder, Job, JobStatus, LiveSession, Page, Project, User
from shared.tags import set_job_tags

ALICE, BOB, ROOT = "user-alice", "user-bob", "user-root"
KEY_A = str(uuid.uuid5(uuid.NAMESPACE_URL, "alice-key"))
KEY_B = str(uuid.uuid5(uuid.NAMESPACE_URL, "bob-key"))
MODES = ("off", "shadow", "enforce")


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
    session.add_all([
        Project(id="proj-a", user_id=ALICE, name="Projeto", name_key="projeto"),
        Project(id="proj-b", user_id=BOB, name="Projeto", name_key="projeto"),
    ])
    session.flush()
    session.add(Folder(id="fold-a", user_id=ALICE, project_id="proj-a", name="Pasta", name_key="pasta"))
    job = Job(id="job-a", user_id=ALICE, name="a", filename="a.pdf", status=JobStatus.COMPLETED,
              job_type="MAIN", project_id="proj-a", total_pages=1)
    session.add(job)
    set_job_tags(job, ["x"])
    session.add(Job(id="job-b", user_id=BOB, name="b", filename="b.pdf", status=JobStatus.COMPLETED,
                    job_type="MAIN", project_id="proj-b"))
    session.flush()
    session.add(Page(id="page-row", job_id="job-a", page_number=1, page_job_id="job-a-p1",
                     status="completed"))
    session.add(LiveSession(job_id="job-a", state="completed", backend="x", model="m", language="pt",
                            worker_id="w", generation=1))
    session.add_all([
        APIKey(id=KEY_A, user_id=ALICE, key_hash="ha", name="a"),
        APIKey(id=KEY_B, user_id=BOB, key_hash="hb", name="b"),
    ])
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
def client(db, fake_redis, monkeypatch, mode):
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(deps, "_redis_owner_matches", lambda job_id, user_id: False)
    monkeypatch.setattr(deps, "_redis_job_status", lambda job_id: None)
    app = FastAPI()
    app.include_router(apikey_routes.router, prefix="/api-keys")
    app.include_router(projects_api.router)
    app.include_router(tag_routes.router)
    app.include_router(routes.router)
    app.include_router(live_routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: db.get(User, app.state.user)
    tc = TestClient(app)

    def as_user(uid):
        app.state.user = uid
        return tc

    return as_user


def _detail(response):
    return response.status_code, response.json().get("detail")


# -- api keys ------------------------------------------------------------------------


def test_api_key_patch_and_delete_are_owner_only(client, db):
    for uid in (BOB, ROOT):
        assert _detail(client(uid).patch(f"/api-keys/{KEY_A}", json={"project_id": None})) == (404, "API key not found")
        assert _detail(client(uid).delete(f"/api-keys/{KEY_A}")) == (404, "API key not found")
    missing = str(uuid.uuid4())
    assert _detail(client(ALICE).delete(f"/api-keys/{missing}")) == (404, "API key not found")
    # A malformed id is still a 422 (the path parameter keeps its UUID type).
    assert client(ALICE).delete("/api-keys/not-a-uuid").status_code == 422
    assert db.get(APIKey, KEY_A) is not None

    r = client(ALICE).patch(f"/api-keys/{KEY_A}", json={"project_id": "proj-a"})
    assert r.status_code == 200 and r.json()["project"]["id"] == "proj-a"
    # Someone else's project is the project 404, as before.
    r = client(ALICE).patch(f"/api-keys/{KEY_A}", json={"project_id": "proj-b"})
    assert _detail(r) == (404, deps.PROJECT_NOT_FOUND_DETAIL)
    assert client(ALICE).delete(f"/api-keys/{KEY_A}").status_code == 204
    db.expire_all()
    assert db.get(APIKey, KEY_A) is None and db.get(APIKey, KEY_B) is not None


def test_api_key_create_is_open_to_every_active_user(client):
    r = client(BOB).post("/api-keys/", json={"name": "k"})
    assert r.status_code == 201, r.text


# -- jobs ----------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", [
    ("get", "/jobs/job-a", None),
    ("get", "/jobs/job-a-p1", None),          # a child job resolves to its MAIN owner
    ("get", "/jobs/job-a/pages", None),
    ("get", "/jobs/job-a/pages/1/status", None),
    ("put", "/jobs/job-a/tags", {"tags": ["y"]}),
    ("delete", "/jobs/job-a", None),
])
def test_job_routes_are_owner_only_with_the_legacy_404(client, method, path, body):
    for uid in (BOB, ROOT):
        r = getattr(client(uid), method)(path, **({"json": body} if body is not None else {}))
        assert _detail(r) == (404, deps.JOB_NOT_FOUND_DETAIL), (uid, path)
    r = getattr(client(ALICE), method)(path.replace("job-a", "missing"), **({"json": body} if body is not None else {}))
    assert r.status_code == 404


def test_owner_reads_and_tags_the_job(client, db):
    assert client(ALICE).get("/jobs/job-a/pages/1/status").status_code == 200
    r = client(ALICE).put("/jobs/job-a/tags", json={"tags": ["Novo"]})
    assert r.status_code == 200 and r.json()["tags"] == ["novo"]
    # A child job has no row to tag: still the legacy 404 after authorizing.
    assert _detail(client(ALICE).put("/jobs/job-a-p1/tags", json={"tags": []})) == (404, "Job não encontrado")


def test_page_retry_shares_one_authorization_with_its_page(client):
    # Someone else's page: 404 from the job authorization, never a page leak.
    assert _detail(client(BOB).post("/jobs/job-a/pages/1/retry")) == (404, deps.JOB_NOT_FOUND_DETAIL)


# -- projects / folders --------------------------------------------------------------


def test_folder_resolve_is_owner_only(client):
    r = client(ALICE).get("/projects/proj-a/folders/resolve", params={"name": "pasta"})
    assert r.status_code == 200 and r.json()["match"]["id"] == "fold-a"
    for uid in (BOB, ROOT):
        r = client(uid).get("/projects/proj-a/folders/resolve", params={"name": "pasta"})
        assert _detail(r) == (404, deps.PROJECT_NOT_FOUND_DETAIL)


# -- live sessions -------------------------------------------------------------------


def test_live_session_status_and_cancel_are_owner_only(client):
    assert client(ALICE).get("/transcribe/live/sessions/job-a").json()["state"] == "completed"
    for uid in (BOB, ROOT):
        assert _detail(client(uid).get("/transcribe/live/sessions/job-a")) == (404, deps.JOB_NOT_FOUND_DETAIL)
        assert _detail(client(uid).delete("/transcribe/live/sessions/job-a")) == (404, deps.JOB_NOT_FOUND_DETAIL)
    # A job of the owner without a live session is the live 404, as before.
    assert _detail(client(BOB).get("/transcribe/live/sessions/job-b")) == (404, "Sessão não encontrada")


def test_ws_ticket_owner_check_is_the_legacy_rule(db):
    """The WS decides through shared.iam: the ticket's user must still own the job."""
    from shared.iam.decide import decide, principal_for_user

    job = db.get(Job, "job-a")
    alice, bob = db.get(User, ALICE), db.get(User, BOB)
    assert decide(db, principal_for_user(alice), "jobs.update", job).allow
    assert not decide(db, principal_for_user(bob), "jobs.update", job).allow
    alice.is_active = False
    assert not decide(db, principal_for_user(alice), "jobs.update", job).allow
    alice.is_active = True
    job.user_id = None  # owner deleted (SET NULL): nobody's
    assert not decide(db, principal_for_user(alice), "jobs.update", job).allow
    db.rollback()
