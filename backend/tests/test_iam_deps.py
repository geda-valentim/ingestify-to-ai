"""
IAM route dependencies (spec 0014 §8 item 2): require / authorized / visible /
engine_access under IAM_MODE off, shadow and enforce.

A small app mounts the dependencies; authentication is replaced (the user comes
from the X-Test-User header) and the database is SQLite. Redis is never consulted.
"""

import logging
from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api import deps
from api.iam_deps import (
    PLATFORM_DENIED_DETAIL,
    SESSION_REQUIRED_DETAIL,
    Scope,
    authorized,
    declaration_of,
    engine_access,
    request_decider,
    require,
    visible,
)
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.iam.models import IamBinding
from shared.models import AdminAudit, Folder, Job, Page, Project, User


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    monkeypatch.setattr(deps, "_redis_job_status", lambda job_id: None)
    monkeypatch.setattr(deps, "_redis_owner_matches", lambda job_id, user_id: False)


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_user_ids", "")
    monkeypatch.setattr(s, "iam_mode", "off")
    return s


def _user(db, name, *, is_admin=False):
    u = User(id=f"user-{name}", email=f"{name}@example.com", username=name,
             hashed_password="x", is_active=True, is_admin=is_admin)
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def people(db, settings):
    root = _user(db, "root", is_admin=True)
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    db.add_all([
        Job(id="main", user_id=alice.id, job_type="MAIN"),
        Page(id="p1", job_id="main", page_number=1, page_job_id="page-1"),
        Job(id="bobs", user_id=bob.id, job_type="MAIN"),
        Project(id="proj", user_id=alice.id, name="P", name_key="p"),
        Folder(id="fold", user_id=alice.id, project_id="proj", name="F", name_key="f"),
    ])
    db.commit()
    return root, alice, bob


def _bind(db, user, role, granted_by):
    b = IamBinding(subject_type="user", subject_id=user.id, role=role, scope_type="platform",
                   granted_by=granted_by.id, expires_at=datetime.utcnow() + timedelta(days=30))
    db.add(b)
    db.commit()
    return b


@pytest.fixture
def client(db):
    app = FastAPI()

    def current_user(request: Request):
        user = db.get(User, request.headers["x-test-user"])
        # The real get_current_user marks API-key requests on request.state.
        request.state.api_key = object() if request.headers.get("x-api-key") else None
        return user

    app.dependency_overrides[get_current_active_user] = current_user
    app.dependency_overrides[get_db] = lambda: db

    @app.get("/stats")
    def stats(user=Depends(require("platform.stats.read"))):
        return {"user": user.id}

    @app.patch("/settings")
    def settings_update(user=Depends(require("platform.settings.update", session=True))):
        return {"user": user.id}

    @app.post("/recover")
    def recover(user=Depends(require("platform.jobs.recover"))):
        return {"user": user.id}

    @app.post("/convert")
    def convert(user=Depends(require("documents.convert"))):
        return {"user": user.id}

    @app.get("/jobs/{job_id}")
    def job(request: Request, job=Depends(authorized(Job, "jobs.read")), decider=Depends(request_decider)):
        assert request.state.iam_decider is decider
        return {"row": job.id if job is not None else None}

    @app.get("/projects/{project_id}")
    def project(project=Depends(authorized(Project, "projects.read"))):
        return {"row": project.id}

    @app.get("/folders/{folder_id}")
    def folder(folder=Depends(authorized(Folder, "folders.read"))):
        return {"row": folder.id}

    @app.get("/jobs")
    def jobs(scope: Scope = Depends(visible(Job, "jobs.read"))):
        return sorted(j.id for j in db.query(Job).filter(scope.predicate))

    @app.get("/engines", dependencies=[Depends(engine_access())])
    def engines():
        return []

    return TestClient(app)


def _get(client, path, user, **headers):
    return client.get(path, headers={"x-test-user": user.id, **headers})


JWT = {"authorization": "Bearer t"}


# -- declarations --------------------------------------------------------------------


def test_each_dependency_declares_its_kind_and_permission():
    assert declaration_of(require("platform.stats.read")).kind == "require"
    assert declaration_of(require("platform.settings.update", session=True)).session
    decl = declaration_of(authorized(Job, "jobs.read"))
    assert (decl.kind, decl.model, decl.permission) == ("authorized", Job, "jobs.read")
    assert declaration_of(visible(Project, "projects.read")).kind == "visible"
    assert declaration_of(engine_access()).kind == "engine_access"
    assert declaration_of(get_current_active_user) is None


@pytest.mark.parametrize("bad", [
    lambda: require("engines.read"),             # 0009: engine_access()
    lambda: require("jobs.read"),                # needs a resource
    lambda: require("platform.nope"),            # outside the catalog
    lambda: authorized(Job, "platform.stats.read"),
    lambda: authorized(Job, "projects.read"),    # wrong family
    lambda: authorized(Page, "jobs.read"),       # no loader
    lambda: visible(Job, "folders.read"),
    lambda: visible(User, "jobs.read"),
])
def test_wrong_declarations_fail_at_import_time(bad):
    with pytest.raises((ValueError, KeyError)):
        bad()


# -- require -------------------------------------------------------------------------


def test_off_is_the_legacy_admin_rule_and_bindings_are_inert(db, people, client, settings):
    root, alice, bob = people
    _bind(db, alice, "platform_operator", granted_by=root)
    assert _get(client, "/stats", root).status_code == 200
    r = _get(client, "/stats", alice)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)
    assert _get(client, "/stats", bob).status_code == 403


def test_off_honours_admin_user_ids(db, people, client, settings, monkeypatch):
    _, alice, _ = people
    monkeypatch.setattr(settings, "admin_user_ids", alice.id)
    assert _get(client, "/stats", alice).status_code == 200


def test_enforce_answers_with_bindings(db, people, client, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "enforce")
    root, alice, bob = people
    binding = _bind(db, alice, "platform_operator", granted_by=root)
    assert _get(client, "/stats", alice).status_code == 200
    assert _get(client, "/stats", root).status_code == 200  # bootstrap
    r = _get(client, "/stats", bob)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)
    # The operator role does not hold settings.update.
    r = client.patch("/settings", headers={"x-test-user": alice.id, **JWT})
    assert r.status_code == 403

    # Revocation takes effect on the next request (no cache across requests).
    binding.revoked_at = datetime.utcnow()
    binding.revoked_by = root.id
    db.commit()
    assert _get(client, "/stats", alice).status_code == 403


def test_shadow_answers_legacy_and_logs_the_divergence(db, people, client, settings, monkeypatch, caplog):
    monkeypatch.setattr(settings, "iam_mode", "shadow")
    root, alice, bob = people
    _bind(db, alice, "platform_operator", granted_by=root)
    with caplog.at_level(logging.WARNING, logger="shared.iam.decide"):
        assert _get(client, "/stats", alice).status_code == 403  # legacy answers
        assert _get(client, "/stats", root).status_code == 200
        assert _get(client, "/stats", bob).status_code == 403
    divergences = [r for r in caplog.records if r.getMessage().startswith("iam_shadow_divergence")]
    assert len(divergences) == 1  # only alice: root and bob agree
    # The fields are in the message: the API's log format prints only %(message)s.
    formatted = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s").format(divergences[0])
    assert formatted.endswith(
        f"iam_shadow_divergence route=GET /stats permission=platform.stats.read "
        f"subject={alice.id} legacy=False iam=True"
    )
    d = divergences[0]
    assert (d.permission, d.route, d.subject, d.legacy, d.iam) == (
        "platform.stats.read", "GET /stats", alice.id, False, True
    )


def test_shadow_survives_a_failing_new_decision(db, people, client, settings, monkeypatch, caplog):
    monkeypatch.setattr(settings, "iam_mode", "shadow")
    root, alice, bob = people
    from shared.iam.decide import Decider

    def broken(self, *a, **k):
        raise RuntimeError("iam_bindings does not exist")

    monkeypatch.setattr(Decider, "decide", broken)
    with caplog.at_level(logging.ERROR, logger="api.iam_deps"):
        assert _get(client, "/stats", root).status_code == 200
        assert _get(client, "/stats", bob).status_code == 403
        assert _get(client, "/jobs/main", alice).json() == {"row": "main"}
        assert _get(client, "/jobs/main", bob).status_code == 404
    errors = [r.getMessage() for r in caplog.records if r.getMessage().startswith("iam_shadow_error")]
    assert errors == [
        "iam_shadow_error route=GET /stats permission=platform.stats.read",
        "iam_shadow_error route=GET /stats permission=platform.stats.read",
        "iam_shadow_error route=GET /jobs/{job_id} permission=jobs.read",
        "iam_shadow_error route=GET /jobs/{job_id} permission=jobs.read",
    ]


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_session_is_required_after_the_permission(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    root, _, bob = people
    ok = client.patch("/settings", headers={"x-test-user": root.id, **JWT})
    assert ok.status_code == 200
    key = client.patch("/settings", headers={"x-test-user": root.id, "x-api-key": "k", **JWT})
    assert (key.status_code, key.json()["detail"]) == (403, SESSION_REQUIRED_DETAIL)
    # Without the permission the answer is the permission 403, as require_admin_session.
    denied = client.patch("/settings", headers={"x-test-user": bob.id, "x-api-key": "k"})
    assert (denied.status_code, denied.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_bootstrap_mutation_is_audited_once_per_request(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    root, _, _ = people
    assert client.patch("/settings", headers={"x-test-user": root.id, **JWT}).status_code == 200
    assert _get(client, "/stats", root).status_code == 200  # reads are not audited
    rows = db.query(AdminAudit).filter(AdminAudit.action == "iam.bootstrap.use").all()
    assert [(r.actor_user_id, r.target_id) for r in rows] == [(root.id, "platform.settings.update")]


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
@pytest.mark.parametrize("headers,credential", [(JWT, "session"), ({"x-api-key": "k"}, "api_key")])
def test_bootstrap_audit_records_the_real_credential(db, people, client, settings, monkeypatch, mode, headers, credential):
    monkeypatch.setattr(settings, "iam_mode", mode)
    root, _, _ = people
    # A mutation without session=True: an API key passes, and is audited as such.
    assert client.post("/recover", headers={"x-test-user": root.id, **headers}).status_code == 200
    [row] = db.query(AdminAudit).filter(AdminAudit.action == "iam.bootstrap.use").all()
    # audit_auth_method is jwt|cli (unchanged); the exact credential is in `after`.
    assert (row.auth_method, row.after["credential"]) == ("jwt", credential)


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_self_service_permission_is_open_to_every_active_user(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    _, alice, _ = people
    r = client.post("/convert", headers={"x-test-user": alice.id})
    assert (r.status_code, r.json()) == (200, {"user": alice.id})


# -- authorized ----------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_authorized_job_is_owner_only_and_returns_the_legacy_row(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    root, alice, bob = people
    assert _get(client, "/jobs/main", alice).json() == {"row": "main"}
    # A child job resolves to the MAIN row that authorized it.
    assert _get(client, "/jobs/page-1", alice).json() == {"row": "main"}
    for user, job_id in ((bob, "main"), (alice, "bobs"), (alice, "missing"), (root, "main")):
        r = _get(client, f"/jobs/{job_id}", user)
        assert (r.status_code, r.json()["detail"]) == (404, deps.JOB_NOT_FOUND_DETAIL), (user.id, job_id)


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
@pytest.mark.parametrize("path,code", [("/projects", "PROJECT_NOT_FOUND"), ("/folders", "FOLDER_NOT_FOUND")])
def test_authorized_project_and_folder_keep_the_legacy_404(db, people, client, settings, monkeypatch, mode, path, code):
    monkeypatch.setattr(settings, "iam_mode", mode)
    _, alice, bob = people
    rid = "proj" if path == "/projects" else "fold"
    assert _get(client, f"{path}/{rid}", alice).json() == {"row": rid}
    captured = []
    real = deps.LocationError

    def spy(*a):
        captured.append(a[1])
        return real(*a)

    monkeypatch.setattr(deps, "LocationError", spy)
    for user, target in ((bob, rid), (alice, "missing")):
        assert _get(client, f"{path}/{target}", user).status_code == 404
    assert captured == [code, code]


def test_shadow_authorized_answers_legacy_and_logs(db, people, client, settings, monkeypatch, caplog):
    monkeypatch.setattr(settings, "iam_mode", "shadow")
    _, alice, _ = people
    # Make the legacy path deny what IAM allows, to observe a divergence.
    def legacy_denies(db, job_id, user):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=deps.JOB_NOT_FOUND_DETAIL)

    monkeypatch.setattr(deps, "resolve_owned_job", legacy_denies)
    with caplog.at_level(logging.WARNING, logger="shared.iam.decide"):
        assert _get(client, "/jobs/main", alice).status_code == 404
    [d] = [r for r in caplog.records if r.getMessage().startswith("iam_shadow_divergence")]
    assert d.getMessage() == (
        f"iam_shadow_divergence route=GET /jobs/{{job_id}} permission=jobs.read "
        f"subject={alice.id} legacy=False iam=True"
    )


def test_enforce_authorized_does_not_call_the_legacy_path(db, people, client, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "enforce")
    _, alice, _ = people
    monkeypatch.setattr(deps, "resolve_owned_job", lambda *a: pytest.fail("legacy called in enforce"))
    assert _get(client, "/jobs/main", alice).json() == {"row": "main"}


# -- visible -------------------------------------------------------------------------


def _sql(clause):
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_visible_predicate_is_exactly_the_owner_filter(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    _, alice, bob = people
    assert _get(client, "/jobs", alice).json() == ["main"]
    assert _get(client, "/jobs", bob).json() == ["bobs"]


def test_visible_scope_is_model_user_id_equals_me():
    import asyncio

    alice = User(id="user-alice")
    for model, perm in ((Job, "jobs.read"), (Project, "projects.read"), (Folder, "folders.read")):
        dep = visible(model, perm)
        scope = asyncio.run(dep(user=alice))
        assert _sql(scope.predicate) == _sql(model.user_id == "user-alice")
        assert (scope.user, scope.permission) == (alice, perm)


# -- engine_access -------------------------------------------------------------------


def test_engine_access_decides_nothing(db, people, client, settings):
    _, _, bob = people
    assert _get(client, "/engines", bob).status_code == 200
