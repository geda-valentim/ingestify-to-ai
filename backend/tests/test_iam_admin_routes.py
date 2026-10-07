"""
Administrative routes under IAM (spec 0014 §8 item 3, §4.7, §4.9; CA5-CA8, CA12).

The real routers (`/admin/*`, `/admin/routing`, `/admin/iam/*`, `/iam/*`,
`/auth/me` and the 0009 `/admin/access/*`) are mounted on a small app.
Authentication is replaced (the user comes from the X-Test-User header; an
X-API-Key header marks the request as an API-key request, as the real
`get_current_user` does), the database is SQLite, and the handlers' outside
world (Celery, Redis, the broker) is stubbed, so a permission that passes
reaches a real 200.

Every role test sets IAM_MODE explicitly: bindings only count under `enforce`.
"""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import admin_routes, auth_routes, deps, iam_routes, routing_admin_routes
from api import access_routes, engine_admin_routes
from api.iam_deps import PLATFORM_DENIED_DETAIL
from shared import broker_unacked
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.iam import catalog
from shared.iam.models import IamBinding
from shared.models import AdminAudit, User

JWT = {"authorization": "Bearer t"}
KEY = {"x-api-key": "k"}
ORPHAN_TAG = "7"


# -- fixtures --------------------------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_user_ids", "")
    monkeypatch.setattr(s, "iam_mode", "enforce")
    monkeypatch.setattr(s, "engine_access_enabled", True)
    return s


@pytest.fixture(autouse=True)
def outside_world(monkeypatch):
    """Celery, Redis and the broker answer instantly; nothing here is under test."""
    monkeypatch.setattr(deps, "_redis_job_status", lambda job_id: None)
    monkeypatch.setattr(deps, "_redis_owner_matches", lambda job_id, user_id: False)

    report = json.dumps({"orphans": [{"delivery_tag": ORPHAN_TAG, "task_id": "t-1", "job_id": "j-1"}]})
    redis = SimpleNamespace(client=SimpleNamespace(info=lambda: {}, get=lambda key: report))
    monkeypatch.setattr(admin_routes, "get_redis_client", lambda: redis)
    monkeypatch.setattr(admin_routes, "get_system_stats", lambda: {"jobs": {}})
    monkeypatch.setattr(admin_routes, "get_stuck_jobs", lambda **kw: [])
    monkeypatch.setattr(admin_routes, "get_stuck_pages", lambda **kw: [])
    monkeypatch.setattr(admin_routes, "detect_stuck_jobs", lambda: {})
    monkeypatch.setattr(admin_routes, "cleanup_old_jobs", lambda: {})
    monkeypatch.setattr(admin_routes, "get_job_with_pages", lambda job_id: (SimpleNamespace(id=job_id), []))

    inspector = SimpleNamespace(scheduled=lambda: {}, active=lambda: {}, registered=lambda: {})
    monkeypatch.setattr(workers.celery_app.celery_app.control, "inspect", lambda **kw: inspector)
    monkeypatch.setattr(broker_unacked, "broker_client", lambda: None)
    monkeypatch.setattr(broker_unacked, "list_unacked", lambda client: [])
    monkeypatch.setattr(broker_unacked, "live_task_ids", lambda inspect: set())
    monkeypatch.setattr(broker_unacked, "requeue", lambda client, tag: True)

    monkeypatch.setattr(routing_admin_routes, "_alive_by_feature", lambda: {})
    monkeypatch.setattr(routing_admin_routes, "_remote_worker_view", lambda: None)


def _user(db, name, *, is_admin=False):
    # /auth/me serializes the id as a UUID.
    u = User(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"user/{name}")), email=f"{name}@example.com", username=name,
             hashed_password="x", is_active=True, is_admin=is_admin)
    db.add(u)
    db.commit()
    return u


def _bind(db, user, role, granted_by, *, days=30):
    b = IamBinding(subject_type="user", subject_id=user.id, role=role, scope_type="platform",
                   granted_by=granted_by.id, expires_at=datetime.utcnow() + timedelta(days=days), version=0)
    db.add(b)
    db.commit()
    return b


@pytest.fixture
def people(db, settings):
    """root: bootstrap; admin/op/aud: one binding each; alice: nothing."""
    root = _user(db, "root", is_admin=True)
    people = SimpleNamespace(root=root, alice=_user(db, "alice"))
    for name, role in (("admin", "platform_admin"), ("op", "platform_operator"), ("aud", "platform_auditor")):
        user = _user(db, name)
        _bind(db, user, role, granted_by=root)
        setattr(people, name, user)
    return people


@pytest.fixture
def client(db):
    app = FastAPI()

    def current_user(request: Request):
        if "x-test-user" not in request.headers:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user = db.get(User, request.headers["x-test-user"])
        request.state.api_key = object() if request.headers.get("x-api-key") else None
        return user

    app.dependency_overrides[get_current_active_user] = current_user
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(auth_routes.router, prefix="/auth")
    app.include_router(admin_routes.router)
    app.include_router(routing_admin_routes.router)
    app.include_router(engine_admin_routes.router)
    app.include_router(access_routes.router)
    app.include_router(iam_routes.router)
    return TestClient(app)


def call(client, method, path, user, headers=JWT, **kw):
    return client.request(method, path, headers={"x-test-user": user.id, **headers}, **kw)


# -- the §4.7 matrix (CA5, CA6) ---------------------------------------------------------

READS = [
    ("GET", "/admin/stats"),
    ("GET", "/admin/jobs/stuck"),
    ("GET", "/admin/health/monitoring"),
    ("GET", "/admin/broker/unacked"),
    ("GET", "/admin/routing"),
    ("GET", "/admin/engines/status"),
]
OPERATOR_MUTATIONS = [
    ("POST", "/admin/jobs/recover-stuck", None),
    ("POST", "/admin/jobs/job-1/retry-all-failed", None),
    ("POST", f"/admin/broker/unacked/{ORPHAN_TAG}/requeue", None),
]
ADMIN_ONLY_MUTATIONS = [
    ("PUT", "/admin/routing/transcription", {"steps": []}),
    ("DELETE", "/admin/routing/transcription", None),
    ("POST", "/admin/cleanup", None),
    ("POST", "/admin/iam/bindings",
     {"subject_id": "someone", "role": "remote_engine_user", "expires_at": "2099-01-01T00:00:00Z"}),
    ("POST", "/admin/iam/bindings/b-1/revoke", {"version": 0}),
]


@pytest.mark.parametrize("method,path", READS)
def test_operator_reads_the_platform(people, client, method, path):
    r = call(client, method, path, people.op)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path,body", OPERATOR_MUTATIONS)
def test_operator_recovers_stuck_work(people, client, method, path, body):
    r = call(client, method, path, people.op, json=body)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY_MUTATIONS + [(None, "/admin/iam/bindings", None)])
def test_operator_is_refused_settings_routing_cleanup_and_iam(people, client, method, path, body):
    r = call(client, method or "GET", path, people.op, json=body)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)


@pytest.mark.parametrize("method,path", READS + [("GET", "/admin/iam/bindings")])
def test_auditor_reads_everything_including_bindings(people, client, method, path):
    r = call(client, method, path, people.aud)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path,body", OPERATOR_MUTATIONS + ADMIN_ONLY_MUTATIONS)
def test_auditor_mutates_nothing(people, client, method, path, body):
    r = call(client, method, path, people.aud, json=body)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)


@pytest.mark.parametrize("method,path", READS + [("GET", "/admin/iam/bindings")])
@pytest.mark.parametrize("who", ["alice", "remote"])
def test_no_platform_role_no_admin_route(db, people, client, method, path, who):
    user = people.alice
    if who == "remote":
        # engines.remote.use is a platform permission, but opens no admin route.
        _bind(db, user, "remote_engine_user", granted_by=people.root)
    r = call(client, method, path, user)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)


@pytest.mark.parametrize("who", ["root", "admin"])
@pytest.mark.parametrize("method,path,body", OPERATOR_MUTATIONS + [ADMIN_ONLY_MUTATIONS[2]])
def test_platform_admin_and_bootstrap_hold_every_admin_route(people, client, who, method, path, body):
    r = call(client, method, path, getattr(people, who), json=body)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path", [("PUT", "/admin/routing/transcription"), ("DELETE", "/admin/routing/transcription")])
def test_routing_changes_still_need_a_login_session(people, client, method, path):
    r = call(client, method, path, people.root, headers=KEY, json={"steps": []} if method == "PUT" else None)
    assert r.status_code == 403
    assert "login session" in r.json()["detail"]


def test_off_mode_keeps_the_legacy_admin_rule(people, client, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "off")
    assert call(client, "GET", "/admin/stats", people.root).status_code == 200
    # Bindings are inert: rollback to off only ever reduces access.
    for user in (people.admin, people.op, people.aud):
        assert call(client, "GET", "/admin/stats", user).status_code == 403
    assert call(client, "GET", "/admin/iam/bindings", people.admin).status_code == 403


# -- 0009 is untouched (§4.9, CA13) -----------------------------------------------------


@pytest.mark.parametrize("who", ["op", "aud", "admin"])
def test_a_platform_binding_does_not_open_the_0009_routes(people, client, who):
    user = getattr(people, who)
    # access_session reads only the 0009 grants.
    r = call(client, "GET", "/admin/access/me", user)
    assert (r.status_code, r.json()["detail"]) == (403, {"code": "ACCESS_DENIED"})
    # require_admin (0009 engine routes) is still the bootstrap rule.
    assert call(client, "GET", "/admin/gpus", user).status_code == 403


def test_bootstrap_still_opens_the_0009_routes(people, client):
    assert call(client, "GET", "/admin/access/me", people.root).status_code == 200


# -- /admin/iam/bindings (CA7) ----------------------------------------------------------


def _grant(client, actor, subject, role="platform_operator", days=30, headers=JWT, expires_at="default"):
    if expires_at == "default":
        expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
    body = {"subject_type": "user", "subject_id": subject.id, "role": role, "expires_at": expires_at}
    return call(client, "POST", "/admin/iam/bindings", actor, headers=headers, json=body)


@pytest.mark.parametrize("who", ["root", "admin"])
def test_grant_list_and_revoke_take_effect_on_the_next_request(db, people, client, who):
    actor = getattr(people, who)
    assert call(client, "GET", "/admin/stats", people.alice).status_code == 403

    r = _grant(client, actor, people.alice)
    assert r.status_code == 201, r.text
    granted = r.json()
    assert (granted["role"], granted["granted_by"], granted["version"], granted["active"]) == (
        "platform_operator", actor.id, 0, True)
    assert call(client, "GET", "/admin/stats", people.alice).status_code == 200

    listed = call(client, "GET", "/admin/iam/bindings", people.aud).json()["bindings"]
    assert granted["id"] in {b["id"] for b in listed}

    r = call(client, "POST", f"/admin/iam/bindings/{granted['id']}/revoke", actor, json={"version": 0})
    assert r.status_code == 200, r.text
    assert (r.json()["version"], r.json()["active"]) == (1, False)
    assert call(client, "GET", "/admin/stats", people.alice).status_code == 403

    listed = call(client, "GET", "/admin/iam/bindings", people.aud).json()["bindings"]
    assert granted["id"] not in {b["id"] for b in listed}
    everything = call(client, "GET", "/admin/iam/bindings?include_inactive=true", people.aud).json()["bindings"]
    assert granted["id"] in {b["id"] for b in everything}

    actions = sorted(a.action for a in db.query(AdminAudit).filter(AdminAudit.target_type == "iam_binding"))
    assert actions == ["iam.binding.grant", "iam.binding.revoke"]


@pytest.mark.parametrize("kwargs,status,code", [
    (dict(role="platform_wizard"), 422, "UNKNOWN_ROLE"),
    (dict(days=365), 201, None),
    (dict(days=366), 422, "INVALID_EXPIRES_AT"),
    (dict(days=-1), 422, "INVALID_EXPIRES_AT"),
    (dict(expires_at=None), 422, "INVALID_EXPIRES_AT"),
    (dict(expires_at="tomorrow"), 422, "INVALID_EXPIRES_AT"),
])
def test_grant_validation(people, client, kwargs, status, code):
    r = _grant(client, people.admin, people.alice, **kwargs)
    assert (r.status_code, r.json()["detail"]["code"] if code else None) == (status, code), r.text


def test_grant_to_a_subject_that_does_not_exist(db, people, client):
    ghost = SimpleNamespace(id="no-such-user")
    r = _grant(client, people.admin, ghost)
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "SUBJECT_NOT_FOUND")
    assert db.query(IamBinding).filter(IamBinding.subject_id == ghost.id).count() == 0


@pytest.mark.parametrize("method,path", [
    ("GET", "/iam/permissions"),
    ("POST", "/iam/check"),
    ("GET", "/admin/iam/bindings"),
    ("POST", "/admin/iam/bindings"),
    ("POST", "/admin/iam/bindings/b-1/revoke"),
])
def test_iam_routes_need_a_session(people, client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_nobody_grants_to_themselves(people, client):
    r = _grant(client, people.admin, people.admin, role="remote_engine_user")
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "SELF_GRANT")


def test_a_second_active_binding_of_the_same_role_conflicts(people, client):
    r = _grant(client, people.admin, people.op)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "BINDING_EXISTS")


def test_grant_with_an_api_key_is_refused(db, people, client):
    r = _grant(client, people.root, people.alice, headers=KEY)
    assert r.status_code == 403
    assert "login session" in r.json()["detail"]
    assert db.query(IamBinding).filter(IamBinding.subject_id == people.alice.id).count() == 0


def test_revoke_checks_the_version_and_the_binding(people, client):
    granted = _grant(client, people.admin, people.alice).json()
    path = f"/admin/iam/bindings/{granted['id']}/revoke"
    r = call(client, "POST", path, people.admin, json={"version": 3})
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "VERSION_CONFLICT")
    assert call(client, "POST", path, people.admin, json={"version": 0}).status_code == 200
    r = call(client, "POST", path, people.admin, json={"version": 1})
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "ALREADY_REVOKED")
    r = call(client, "POST", "/admin/iam/bindings/nope/revoke", people.admin, json={"version": 0})
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "BINDING_NOT_FOUND")


def test_an_expired_binding_grants_nothing(db, people, client):
    b = _bind(db, people.alice, "platform_operator", granted_by=people.root)
    b.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert call(client, "GET", "/admin/stats", people.alice).status_code == 403


# -- bootstrap (CA8) --------------------------------------------------------------------


def _bootstrap_uses(db):
    # The handlers share this session: drop whatever was only added or flushed,
    # so only rows that were committed count (production closes without commit).
    db.rollback()
    rows = db.query(AdminAudit).filter(AdminAudit.action == "iam.bootstrap.use").all()
    return [(r.actor_user_id, r.auth_method, r.target_id, r.after["permission"]) for r in rows]


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
def test_bootstrap_mutations_are_audited_and_reads_are_not(db, people, client, settings, monkeypatch, mode):
    monkeypatch.setattr(settings, "iam_mode", mode)
    root = people.root
    assert call(client, "GET", "/admin/stats", root).status_code == 200
    assert call(client, "GET", "/admin/routing", root).status_code == 200
    assert _bootstrap_uses(db) == []

    assert call(client, "POST", "/admin/cleanup", root).status_code == 200
    assert call(client, "POST", "/admin/jobs/recover-stuck", root).status_code == 200
    # These handlers never touch the DB: only the dependency's commit keeps the row.
    assert sorted(_bootstrap_uses(db)) == sorted([
        (root.id, "jwt", "platform.jobs.cleanup", "platform.jobs.cleanup"),
        (root.id, "jwt", "platform.jobs.recover", "platform.jobs.recover"),
    ])
    # Recorded before the handler runs, so even a failing change leaves its trace.
    assert call(client, "DELETE", "/admin/routing/transcription", root).status_code == 404
    assert _grant(client, root, people.alice, role="remote_engine_user").status_code == 201

    assert sorted(_bootstrap_uses(db)) == sorted([
        (root.id, "jwt", "platform.jobs.cleanup", "platform.jobs.cleanup"),
        (root.id, "jwt", "platform.jobs.recover", "platform.jobs.recover"),
        (root.id, "jwt", "platform.routing.update", "platform.routing.update"),
        (root.id, "jwt", "iam.bindings.manage", "iam.bindings.manage"),
    ])


def test_bootstrap_use_survives_a_handler_that_rolls_back(db, people, client):
    r = _grant(client, people.root, people.alice, role="platform_wizard")
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "UNKNOWN_ROLE")
    assert _bootstrap_uses(db) == [(people.root.id, "jwt", "iam.bindings.manage", "iam.bindings.manage")]


def test_a_binding_holder_is_not_audited_as_bootstrap(db, people, client):
    assert call(client, "POST", "/admin/cleanup", people.admin).status_code == 200
    assert _bootstrap_uses(db) == []


# -- /auth/me (CA8, CA12) ---------------------------------------------------------------


def _me(client, user):
    r = call(client, "GET", "/auth/me", user)
    assert r.status_code == 200, r.text
    return r.json()


def test_me_reports_bootstrap_and_every_platform_permission(people, client):
    me = _me(client, people.root)
    assert (me["is_admin"], me["bootstrap"], me["platform_roles"]) == (True, True, [])
    assert isinstance(me["permissions"], list) and me["permissions"] == sorted(me["permissions"])
    assert catalog.PLATFORM_PERMISSIONS <= set(me["permissions"])
    assert "engines.read" in me["permissions"]  # the 0009 ones stay


def test_me_reports_the_roles_and_permissions_of_a_binding(people, client):
    me = _me(client, people.op)
    assert (me["is_admin"], me["bootstrap"], me["platform_roles"]) == (False, False, ["platform_operator"])
    assert set(me["permissions"]) == catalog.ROLES["platform_operator"].permissions


def test_me_without_platform_access_only_gains_empty_fields(people, client):
    me = _me(client, people.alice)
    assert (me["bootstrap"], me["platform_roles"], me["permissions"]) == (False, [], [])
    assert {"id", "email", "username", "is_active", "created_at", "is_admin", "engine_access_enabled"} <= set(me)


def test_me_hides_inert_bindings_outside_enforce(people, client, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "off")
    me = _me(client, people.op)
    assert (me["platform_roles"], me["permissions"]) == ([], [])
    assert catalog.PLATFORM_PERMISSIONS <= set(_me(client, people.root)["permissions"])


def test_me_does_not_audit(db, people, client):
    _me(client, people.root)
    assert _bootstrap_uses(db) == []


# -- /iam/permissions, /iam/check -------------------------------------------------------


def test_permissions_catalog_is_served_to_any_session(people, client):
    body = call(client, "GET", "/iam/permissions", people.alice).json()
    assert {p["name"] for p in body["permissions"]} == set(catalog.PERMISSIONS)
    # Spec 0018: the engines family is described too, apart (`family`).
    assert {r["key"] for r in body["roles"] if r["family"] == "platform"} == set(catalog.ROLES)
    assert body["mode"] == "enforce"


@pytest.mark.parametrize("who,expected", [
    ("op", [True, False, False]),
    ("aud", [True, False, True]),
    ("root", [True, True, True]),
    ("alice", [False, False, False]),
])
def test_check_answers_for_the_caller(db, people, client, who, expected):
    checks = [{"permission": p} for p in ("platform.stats.read", "platform.settings.update", "iam.bindings.read")]
    r = call(client, "POST", "/iam/check", getattr(people, who), json=checks)
    assert r.status_code == 200, r.text
    assert [c["allowed"] for c in r.json()] == expected
    assert [c["permission"] for c in r.json()] == [c["permission"] for c in checks]
    assert _bootstrap_uses(db) == []  # asking is not exercising


@pytest.mark.parametrize("permission", ["jobs.read", "engines.read", "platform.nope"])
def test_check_is_for_platform_permissions_only(people, client, permission):
    r = call(client, "POST", "/iam/check", people.op, json=[{"permission": permission}])
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "UNSUPPORTED_PERMISSION")


def test_check_follows_the_mode(people, client, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "off")
    r = call(client, "POST", "/iam/check", people.op, json=[{"permission": "platform.stats.read"}])
    assert r.json() == [{"permission": "platform.stats.read", "allowed": False}]
