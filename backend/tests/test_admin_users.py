"""
GET /admin/users and GET /admin/users/{user_id}: the read-only user directory for
platform administrators.

The real router is mounted on a small app over SQLite; authentication is replaced
as in test_iam_admin_routes.py (the user comes from X-Test-User; X-API-Key marks
an API-key request).
"""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import admin_users_routes
from shared import admin_users
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.i18n import LanguageMiddleware
from shared.iam.models import IamBinding
from shared.models import ROOT_SLOT, AdminAudit, APIKey, Folder, Job, JobStatus, Project, User

JWT = {"authorization": "Bearer t"}
KEY = {"x-api-key": "k"}
NOW = datetime.utcnow()
SECRET_HASH = "f" * 64


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_user_ids", "")
    monkeypatch.setattr(s, "iam_mode", "enforce")
    return s


def _user(db, name, *, is_admin=False, root=False, active=True, created=None):
    u = User(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"user/{name}")), email=f"{name}@example.com", username=name,
             hashed_password="x", is_active=active, is_admin=is_admin, root_slot=ROOT_SLOT if root else None,
             created_at=created or NOW)
    db.add(u)
    db.commit()
    return u


def _bind(db, user, role, granted_by):
    db.add(IamBinding(subject_type="user", subject_id=user.id, role=role, scope_type="platform",
                      granted_by=granted_by.id, expires_at=NOW + timedelta(days=30), version=0))
    db.commit()


def _job(db, user, status=JobStatus.COMPLETED, *, size=0, pages=None, source="file", project=None,
         created=None, parent=None, job_type="MAIN"):
    job = Job(id=str(uuid.uuid4()), user_id=user.id if user else None, job_type=job_type, status=status,
              file_size_bytes=size, total_pages=pages, source_type=source, created_at=created or NOW,
              project_id=project.id if project else None, parent_job_id=parent)
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def people(db, settings):
    """root (root user), admin/op/aud: one platform binding each, alice: nothing."""
    root = _user(db, "root", is_admin=True, root=True, created=NOW - timedelta(days=400))
    people = SimpleNamespace(root=root, alice=_user(db, "alice", created=NOW - timedelta(days=10)))
    for name, role in (("admin", "platform_admin"), ("op", "platform_operator"), ("aud", "platform_auditor")):
        user = _user(db, name, created=NOW - timedelta(days=5))
        _bind(db, user, role, granted_by=root)
        setattr(people, name, user)
    return people


@pytest.fixture
def client(db):
    app = FastAPI()
    app.add_middleware(LanguageMiddleware)

    def current_user(request: Request):
        if "x-test-user" not in request.headers:
            raise HTTPException(status_code=401, detail="Not authenticated")
        request.state.api_key = object() if request.headers.get("x-api-key") else None
        return db.get(User, request.headers["x-test-user"])

    app.dependency_overrides[get_current_active_user] = current_user
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(admin_users_routes.router)
    return TestClient(app)


def call(client, path, user, headers=JWT, **kw):
    return client.get(path, headers={"x-test-user": user.id, **headers}, **kw)


# -- who may read (CA1) ----------------------------------------------------------------


@pytest.mark.parametrize("who", ["root", "admin"])
@pytest.mark.parametrize("path", ["/admin/users", "/admin/users/{alice}"])
def test_root_and_platform_admin_read(people, client, who, path):
    r = call(client, path.format(alice=people.alice.id), getattr(people, who))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("who", ["op", "aud", "alice"])
@pytest.mark.parametrize("path", ["/admin/users", "/admin/users/{alice}"])
def test_operator_auditor_and_plain_users_are_refused(people, client, who, path):
    r = call(client, path.format(alice=people.alice.id), getattr(people, who))
    assert (r.status_code, r.json()["detail"]["code"]) == (403, "ADMIN_REQUIRED")


def test_unauthenticated_is_401(people, client):
    assert client.get("/admin/users").status_code == 401


def test_api_key_of_an_admin_is_accepted(people, client):
    assert call(client, "/admin/users", people.root, headers=KEY).status_code == 200


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_outside_enforce_only_bootstrap_reads(people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    assert call(client, "/admin/users", people.root).status_code == 200
    assert call(client, "/admin/users", people.admin).status_code == 403


# -- the list (CA2, CA4, CA7) ------------------------------------------------------------


@pytest.fixture
def usage(db, people):
    alice = people.alice
    project = Project(id="p-1", user_id=alice.id, name="Docs", name_key="docs")
    db.add(project)
    db.add_all([Folder(id=f"f-{i}", project_id="p-1", user_id=alice.id, name=f"F{i}", name_key=f"f{i}")
                for i in range(3)])
    db.commit()
    main = _job(db, alice, size=1000, pages=10, project=project, created=NOW - timedelta(days=1))
    _job(db, alice, JobStatus.FAILED, size=500, source="url", created=NOW - timedelta(days=40))
    _job(db, alice, size=999_999, pages=99, parent=main.id, job_type="PAGE")  # a child: never counted
    _job(db, alice, size=888_888, job_type=None)  # not a MAIN job: GET /jobs does not count it either
    _job(db, None, size=7)  # owner deleted
    db.add_all([
        APIKey(id="k-live", user_id=alice.id, key_hash=SECRET_HASH, name="ci", is_active=True,
               last_used_at=NOW - timedelta(hours=1), project_id="p-1"),
        APIKey(id="k-off", user_id=alice.id, key_hash="e" * 64, name="old", is_active=False),
        APIKey(id="k-exp", user_id=alice.id, key_hash="d" * 64, name="exp", is_active=True,
               expires_at=NOW - timedelta(days=1)),
    ])
    db.commit()
    return people


def _items(r):
    return {i["username"]: i for i in r.json()["items"]}


def test_list_summarises_every_user(usage, client):
    r = call(client, "/admin/users", usage.root)
    body = r.json()
    assert body["total"] == 5 and body["orphan_jobs"] == 1
    alice = _items(r)["alice"]
    assert alice["jobs_total"] == 2  # the PAGE child and the non-MAIN row do not count
    assert alice["jobs_by_status"] == {"completed": 1, "failed": 1}
    assert (alice["bytes_uploaded"], alice["pages_total"]) == (1500, 10)
    assert alice["api_keys_active"] == 1  # the inactive and the expired key do not count
    assert alice["projects_total"] == 1
    assert alice["last_api_key_used_at"] is not None
    root = _items(r)["root"]
    assert (root["is_root"], root["is_admin"], root["jobs_total"], root["last_job_at"]) == (True, True, 0, None)
    assert _items(r)["admin"]["is_admin"] is False  # a binding is not the bootstrap flag


def test_inactive_users_are_listed(db, usage, client):
    _user(db, "gone", active=False)
    assert _items(call(client, "/admin/users", usage.root))["gone"]["is_active"] is False


def test_search_by_email_or_username(usage, client):
    r = call(client, "/admin/users?q=ALI", usage.root)
    assert set(_items(r)) == {"alice"}
    assert (r.json()["total"], r.json()["orphan_jobs"]) == (1, 0)
    assert _items(r)["alice"]["jobs_total"] == 2  # the narrowed aggregates are the same numbers
    assert set(_items(call(client, "/admin/users?q=aud@example", usage.root))) == {"aud"}


@pytest.mark.parametrize("needle", ["%", "_", "a_ice"])
def test_search_wildcards_are_literal(db, usage, client, needle):
    assert _items(call(client, "/admin/users", usage.root, params={"q": needle})) == {}
    _user(db, "a_ice")
    if needle != "%":
        assert set(_items(call(client, "/admin/users", usage.root, params={"q": needle}))) == {"a_ice"}


def test_statuses_use_the_api_names(db, usage, client):
    _job(db, usage.alice, JobStatus.PENDING)
    assert _items(call(client, "/admin/users", usage.root))["alice"]["jobs_by_status"] == {
        "completed": 1, "failed": 1, "queued": 1,
    }


def test_sort_orders_values_breaks_ties_by_id_and_puts_missing_last(db, usage, client):
    for name in ("op", "aud"):
        _job(db, getattr(usage, name), created=NOW - timedelta(days=3))
    ids = sorted([usage.op.id, usage.aud.id])
    r = call(client, "/admin/users?sort=last_job_at&order=desc", usage.root)
    names = [i["username"] for i in r.json()["items"]]
    assert names[0] == "alice"  # 1 day ago, newest
    tied = [i["id"] for i in r.json()["items"][1:3]]
    assert tied == ids[::-1]  # equal values: by id, in the same direction
    assert set(names[3:]) == {"root", "admin"}  # no job: last
    r = call(client, "/admin/users?sort=last_job_at&order=asc", usage.root)
    assert [i["id"] for i in r.json()["items"][:2]] == ids
    assert set(i["username"] for i in r.json()["items"][3:]) == {"root", "admin"}


def test_sort_puts_users_without_the_field_last(usage, client):
    r = call(client, "/admin/users?sort=last_job_at&order=asc", usage.root)
    assert [i["username"] for i in r.json()["items"]][0] == "alice"
    r = call(client, "/admin/users?sort=created_at&order=asc", usage.root)
    assert [i["username"] for i in r.json()["items"]][:2] == ["root", "alice"]
    r = call(client, "/admin/users?sort=jobs_total", usage.root)
    assert r.json()["items"][0]["username"] == "alice"


def test_pagination_keeps_the_total(usage, client):
    r = call(client, "/admin/users?sort=created_at&order=asc&limit=2&offset=1", usage.root)
    items = r.json()["items"]
    assert r.json()["total"] == 5
    assert len(items) == 2 and items[0]["username"] == "alice"


@pytest.mark.parametrize("query", ["sort=email", "order=up", "limit=0", "limit=201", "offset=-1"])
def test_invalid_query_is_422(usage, client, query):
    assert call(client, f"/admin/users?{query}", usage.root).status_code == 422


# -- the detail (CA5, CA6) ---------------------------------------------------------------


def test_detail_has_keys_projects_usage_and_bindings(usage, client):
    r = call(client, f"/admin/users/{usage.alice.id}", usage.root)
    body = r.json()
    keys = {k["id"]: k for k in body["api_keys"]}
    assert set(keys) == {"k-live", "k-off", "k-exp"}
    assert (keys["k-live"]["project_id"], keys["k-exp"]["expired"], keys["k-off"]["is_active"]) == ("p-1", True, False)
    assert body["projects"] == [{**body["projects"][0], "id": "p-1", "folder_count": 3, "jobs_total": 1}]
    assert body["usage"]["by_source_type"] == {"file": 1, "url": 1}
    assert body["usage"]["last_30_days"] == {"jobs": 1, "bytes": 1000, "pages": 10}
    assert body["iam_bindings"] == []

    aud = call(client, f"/admin/users/{usage.aud.id}", usage.root).json()
    assert [b["role"] for b in aud["iam_bindings"]] == ["platform_auditor"]


def test_detail_never_carries_a_key_hash(usage, client):
    text = json.dumps(call(client, f"/admin/users/{usage.alice.id}", usage.root).json())
    assert SECRET_HASH not in text and "key_hash" not in text


def test_unknown_user_is_404(people, client):
    r = call(client, "/admin/users/nobody", people.root)
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "USER_NOT_FOUND")


# -- fixed query count and no writes (CA3, CA8) ------------------------------------------


def _statements(engine):
    seen = []
    event.listen(engine, "before_cursor_execute", lambda *a: seen.append(a[2].lstrip().split()[0].upper()))
    return seen


def test_the_list_runs_a_fixed_number_of_queries(engine, db, people):
    seen = _statements(engine)
    admin_users.list_users(db)
    few = len(seen)
    for i in range(5):
        other = _user(db, f"extra{i}")
        _job(db, other)
    seen.clear()
    admin_users.list_users(db)
    assert len(seen) == few


def test_reading_writes_nothing(engine, usage, db, client):
    before = (db.query(AdminAudit).count(), db.get(APIKey, "k-live").last_used_at)
    seen = _statements(engine)
    call(client, "/admin/users", usage.root)
    call(client, f"/admin/users/{usage.alice.id}", usage.root)
    assert not [s for s in seen if s in ("INSERT", "UPDATE", "DELETE")]
    db.expire_all()
    assert (db.query(AdminAudit).count(), db.get(APIKey, "k-live").last_used_at) == before
