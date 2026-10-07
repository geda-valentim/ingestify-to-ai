"""
Spec 0018 slice 3: `/admin/iam/bindings*` serve both role families.

- CA6: each family keeps its own authority and rules, which never cross;
- CA12: grants and revocations of both families audit on `iam_binding`;
- CA13: `/auth/me` and `/admin/access/me` read engine permissions from one store,
  `policy.navigation`;
- CA16: `IAM_MODE=off` + engines on, a delegate administers engines bindings here
  and sees no platform binding; under `enforce` a platform-only holder sees no
  engines binding;
- CA17: revoking an engines binding takes the epoch lock first and has the strict
  codes (ALREADY_REVOKED, VERSION_CONFLICT, BINDING_NOT_FOUND).

The world (users, engines, epoch) is the 0009 one of `test_execution_profiles`;
the real routers are mounted, authentication is replaced by the `actor` dict.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import access_routes, auth_routes, iam_routes
from api.iam_deps import PLATFORM_DENIED_DETAIL
from shared.access import contracts as C, policy, service
from shared.access.models import AuthorizationEpoch, RoleGrant
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.iam import bindings
from shared.iam.models import IamBinding
from shared.models import AdminAudit, User
from tests.test_execution_profiles import HEADERS, constraints, grant, world  # noqa: F401

BASE = "/admin/iam/bindings"


@pytest.fixture
def api(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "iam_mode", "enforce")
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/auth")
    app.include_router(access_routes.router)
    app.include_router(iam_routes.router)
    actor = {"id": "bootstrap"}

    def db_override():
        with world() as db:
            yield db

    def user_override():
        with world() as db:
            return db.get(User, actor["id"])

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = user_override
    with TestClient(app) as http:

        def call(who, method, path, json=None, headers=HEADERS):
            actor["id"] = who
            return http.request(method, path, headers=headers, json=json)

        yield call


def _later(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _revision(world):  # noqa: F811
    with world() as db:
        p = service.create_policy(db, C.PolicyCreate(name="Unified", constraints=constraints()), "bootstrap")
    return p["revisions"][0]["id"]


def _platform(world, subject, role="platform_admin"):  # noqa: F811
    with world() as db:
        b = IamBinding(subject_type="user", subject_id=subject, role=role, scope_type="platform",
                       granted_by="bootstrap", expires_at=datetime.utcnow() + timedelta(days=30), version=0)
        db.add(b)
        db.commit()
        return b.id


def _delegate(world):  # noqa: F811
    """`delegate` holds access_admin with an envelope of the observer role (30 min)."""
    with world() as db:
        envelope = C.Delegation(permissions=sorted(policy.ROLES["observer"]), constraints=constraints(),
                                max_grant_seconds=1800)
        return grant(db, actor="delegate", role="access_admin", delegation=envelope)


def _member(world, name):  # noqa: F811
    """A user /auth/me can serialize (its `id` is a UUID there)."""
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"user/{name}"))
    with world() as db:
        db.add(User(id=uid, username=name, email=f"{name}@example.test", hashed_password="unused",
                    is_admin=False, is_active=True))
        db.commit()
    return uid


def _engines_body(revision, subject="observer", role="observer", **kw):
    return {"subject_id": subject, "role": role, "condition_ref": revision, "expires_at": _later(minutes=10), **kw}


def _code(r):
    return r.status_code, r.json()["detail"]["code"]


def _epoch(world):  # noqa: F811
    with world() as db:
        return db.get(AuthorizationEpoch, 1).version


# -- CA6: grant, per family -------------------------------------------------------------


def test_bootstrap_grants_an_engines_role_with_its_condition(world, api):  # noqa: F811
    revision = _revision(world)
    before = _epoch(world)
    r = api("bootstrap", "POST", BASE, _engines_body(revision))
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["family"], b["subject_id"], b["role"], b["condition_ref"], b["parent_id"], b["active"]) == (
        "engines", "observer", "observer", revision, None, True)
    # Materialized: an action later added to the role never widens this binding.
    assert b["permissions"] == sorted(policy.ROLES["observer"])
    assert _epoch(world) == before + 1
    with world() as db:
        mirrored = db.execute(
            RoleGrant.__table__.select().where(RoleGrant.__table__.c.id == b["id"])
        ).mappings().first()
        assert (mirrored["user_id"], mirrored["policy_revision_id"]) == ("observer", revision)
        audit = db.query(AdminAudit).filter_by(target_type="iam_binding", target_id=b["id"]).one()
        assert (audit.action, audit.after["condition_ref"], audit.after["subject_id"]) == (
            bindings.GRANT_AUDIT_ACTION, revision, "observer")


def test_two_bindings_of_one_engines_role_with_distinct_subsets(world, api):  # noqa: F811
    revision = _revision(world)
    for subset in (["engines.read"], ["engine_operations.read"]):
        r = api("bootstrap", "POST", BASE, _engines_body(revision, "operator", "engine_operator", permissions=subset))
        assert r.status_code == 201, r.text
        assert r.json()["permissions"] == subset


@pytest.mark.parametrize("change,expected", [
    (dict(role="wizard"), (422, "UNKNOWN_ROLE")),
    (dict(condition_ref=None), (404, "GRANT_TARGET_NOT_FOUND")),
    (dict(condition_ref="no-such-revision"), (404, "GRANT_TARGET_NOT_FOUND")),
    (dict(subject_id="nobody"), (404, "GRANT_TARGET_NOT_FOUND")),
    (dict(subject_type="service_principal"), (422, "INVALID_SUBJECT")),
    (dict(subject_id="bootstrap"), (422, "SELF_GRANT")),
    (dict(permissions=["access.grants.manage"]), (422, "PERMISSIONS_OUTSIDE_ROLE")),
    (dict(permissions=[]), (422, "PERMISSIONS_OUTSIDE_ROLE")),
    (dict(expires_at=None), (422, "GRANT_EXPIRY_INVALID")),
    (dict(expires_at="tomorrow"), (422, "GRANT_EXPIRY_INVALID")),
    (dict(expires_at=_later(days=366)), (422, "GRANT_EXPIRY_INVALID")),
    (dict(parent_id="x"), (422, "FIELD_NOT_ALLOWED_FOR_ROLE")),
    (dict(delegation={"permissions": ["engines.read"], "constraints": None, "max_grant_seconds": 60}), None),
])
def test_engines_grant_validation(world, api, change, expected):  # noqa: F811
    revision = _revision(world)
    body = _engines_body(revision, **change)
    if expected is None:
        # A delegation on a role other than access_admin
        body["delegation"]["constraints"] = constraints().model_dump(mode="json")
        expected = (422, "DELEGATION_INVALID")
    r = api("bootstrap", "POST", BASE, body)
    assert _code(r) == expected, r.text
    assert set(r.json()["detail"]) == {"code", "message"}
    with world() as db:
        assert db.query(IamBinding).filter(IamBinding.role.in_(["observer", "wizard"])).count() == 0


def test_engines_grant_with_engine_access_off_is_503(world, api, monkeypatch):  # noqa: F811
    revision = _revision(world)
    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    assert _code(api("bootstrap", "POST", BASE, _engines_body(revision))) == (503, "ACCESS_NOT_ENABLED")


@pytest.mark.parametrize("field,value", [
    ("permissions", ["platform.stats.read"]),
    ("condition_ref", "rev"),
    ("delegation", {"permissions": [], "constraints": None, "max_grant_seconds": 60}),
    ("parent_id", "p"),
])
def test_a_platform_role_takes_no_engines_field(world, api, field, value):  # noqa: F811
    body = {"subject_id": "outsider", "role": "platform_auditor", "expires_at": _later(days=1), field: value}
    if field == "delegation":
        body[field]["constraints"] = constraints().model_dump(mode="json")
    assert _code(api("bootstrap", "POST", BASE, body)) == (422, "FIELD_NOT_ALLOWED_FOR_ROLE")


def test_a_platform_admin_neither_grants_nor_revokes_engines_roles(world, api):  # noqa: F811
    revision = _revision(world)
    _platform(world, "outsider")
    assert _code(api("outsider", "POST", BASE, _engines_body(revision))) == (403, "ACCESS_DENIED")
    target = api("bootstrap", "POST", BASE, _engines_body(revision)).json()
    r = api("outsider", "POST", f"{BASE}/{target['id']}/revoke", {"version": 0})
    assert _code(r) == (403, "ACCESS_DENIED")
    # The platform family is still theirs.
    r = api("outsider", "POST", BASE, {"subject_id": "editor", "role": "platform_auditor", "expires_at": _later(days=1)})
    assert r.status_code == 201, r.text


def test_a_delegate_neither_grants_nor_revokes_platform_roles(world, api):  # noqa: F811
    _delegate(world)
    platform_id = _platform(world, "editor", "platform_auditor")
    r = api("delegate", "POST", BASE, {"subject_id": "observer", "role": "platform_auditor", "expires_at": _later(days=1)})
    assert _code(r) == (403, "ACCESS_DENIED")
    assert _code(api("delegate", "POST", f"{BASE}/{platform_id}/revoke", {"version": 0})) == (403, "ACCESS_DENIED")


def test_without_either_administration_the_route_is_closed(world, api):  # noqa: F811
    for method, path, body in (("GET", BASE, None), ("POST", BASE, {"subject_id": "x", "role": "observer"}),
                               ("POST", f"{BASE}/x/revoke", {"version": 0})):
        r = api("outsider", method, path, body)
        assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)


def test_writes_of_both_families_need_a_login_session(world, api):  # noqa: F811
    _delegate(world)
    revision = _revision(world)
    for who, body in (("bootstrap", {"subject_id": "outsider", "role": "platform_auditor", "expires_at": _later(days=1)}),
                      ("delegate", _engines_body(revision, "editor"))):
        r = api(who, "POST", BASE, body, headers={**HEADERS, "X-API-Key": "k"})
        assert r.status_code == 403 and "login session" in r.json()["detail"], r.text


# -- CA7: delegation through the unified route --------------------------------------------


def test_a_delegate_grants_within_the_envelope_and_the_child_dies_with_the_parent(world, api):  # noqa: F811
    parent = _delegate(world)
    revision = parent["policy_revision_id"]
    member = _member(world, "member")
    r = api("delegate", "POST", BASE, _engines_body(revision, member))
    assert r.status_code == 201, r.text
    child = r.json()
    assert child["parent_id"] == parent["id"]
    assert _code(api("delegate", "POST", BASE, _engines_body(revision, member, "engine_operator"))) == (
        403, "DELEGATION_EXCEEDED")
    assert _code(api("delegate", "POST", BASE, _engines_body(revision, member, expires_at=_later(hours=1)))) == (
        403, "DELEGATION_EXCEEDED")

    assert api(member, "GET", "/admin/access/me").status_code == 200
    r = api("bootstrap", "POST", f"{BASE}/{parent['id']}/revoke", {"version": 0})
    assert r.status_code == 200, r.text

    # CA13: the child contributes nothing anywhere, from the one store.
    assert _code(api(member, "GET", "/admin/access/me")) == (403, "ACCESS_DENIED")
    me = api(member, "GET", "/auth/me").json()
    assert (me["permissions"], me["platform_roles"]) == ([], [])
    listed = {b["id"]: b for b in api("bootstrap", "GET", f"{BASE}?include_inactive=true").json()["bindings"]}
    assert listed[child["id"]]["active"] is False
    assert child["id"] not in {b["id"] for b in api("bootstrap", "GET", BASE).json()["bindings"]}


def test_auth_me_and_access_me_agree_on_engine_permissions(world, api):  # noqa: F811
    revision = _revision(world)
    member = _member(world, "member")
    api("bootstrap", "POST", BASE, _engines_body(revision, member, "engine_operator", permissions=["engines.read"]))
    _platform(world, member, "platform_auditor")
    me = api(member, "GET", "/auth/me").json()
    access_me = api(member, "GET", "/admin/access/me").json()
    assert access_me["permissions"] == ["engines.read"]
    assert me["platform_roles"] == ["platform_auditor"]
    engine_permissions = {p for p in me["permissions"] if p in policy.PERMISSIONS}
    assert engine_permissions == set(access_me["permissions"])


# -- CA17: revoke, per family -------------------------------------------------------------


def test_revoking_an_engines_binding(world, api, monkeypatch):  # noqa: F811
    revision = _revision(world)
    b = api("bootstrap", "POST", BASE, _engines_body(revision)).json()
    path = f"{BASE}/{b['id']}/revoke"
    assert _code(api("bootstrap", "POST", path, {"version": 3})) == (409, "VERSION_CONFLICT")

    seen = []
    real_epoch = policy.epoch

    def epoch(db, lock=False):
        if lock:
            # The epoch lock is the transaction's first statement (MySQL snapshot after it).
            seen.append(db.in_transaction())
        return real_epoch(db, lock)

    monkeypatch.setattr(policy, "epoch", epoch)
    before = _epoch(world)
    r = api("bootstrap", "POST", path, {"version": 0})
    assert r.status_code == 200, r.text
    assert seen and seen[0] is False
    assert (r.json()["version"], r.json()["active"], r.json()["revoked_by"]) == (1, False, "bootstrap")
    assert _epoch(world) == before + 1
    with world() as db:
        mirrored = db.execute(
            RoleGrant.__table__.select().where(RoleGrant.__table__.c.id == b["id"])
        ).mappings().first()
        assert (mirrored["revoked_at"] is not None, mirrored["version"]) == (True, 1)
        audit = db.query(AdminAudit).filter_by(target_type="iam_binding", target_id=b["id"],
                                               action=bindings.REVOKE_AUDIT_ACTION).one()
        assert (audit.before["active"], audit.after["active"]) == (True, False)

    assert _code(api("bootstrap", "POST", path, {"version": 1})) == (409, "ALREADY_REVOKED")
    assert _code(api("bootstrap", "POST", f"{BASE}/nope/revoke", {"version": 0})) == (404, "BINDING_NOT_FOUND")


def test_a_delegate_revokes_only_what_the_envelope_covers(world, api):  # noqa: F811
    parent = _delegate(world)
    revision = parent["policy_revision_id"]
    mine = api("delegate", "POST", BASE, _engines_body(revision, "editor")).json()
    theirs = api("bootstrap", "POST", BASE, _engines_body(revision, "operator", "engine_operator")).json()
    assert _code(api("delegate", "POST", f"{BASE}/{theirs['id']}/revoke", {"version": 0})) == (
        403, "DELEGATION_EXCEEDED")
    assert api("delegate", "POST", f"{BASE}/{mine['id']}/revoke", {"version": 0}).status_code == 200


def test_engines_revoke_with_engine_access_off_is_503(world, api, monkeypatch):  # noqa: F811
    b = api("bootstrap", "POST", BASE, _engines_body(_revision(world))).json()
    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    assert _code(api("bootstrap", "POST", f"{BASE}/{b['id']}/revoke", {"version": 0})) == (503, "ACCESS_NOT_ENABLED")


def test_platform_writes_leave_the_epoch_alone(world, api):  # noqa: F811
    before = _epoch(world)
    b = api("bootstrap", "POST", BASE, {"subject_id": "outsider", "role": "platform_auditor",
                                        "expires_at": _later(days=1)}).json()
    assert b["family"] == "platform"
    assert all(b[k] is None for k in ("permissions", "condition_ref", "delegation", "parent_id"))
    assert api("bootstrap", "POST", f"{BASE}/{b['id']}/revoke", {"version": 0}).status_code == 200
    assert _epoch(world) == before


# -- listing (CA16) -------------------------------------------------------------------


def _listed(api, who, query=""):
    r = api(who, "GET", BASE + query)
    assert r.status_code == 200, r.text
    return r.json()["bindings"]


def test_bootstrap_lists_both_families(world, api):  # noqa: F811
    platform_id = _platform(world, "outsider", "platform_auditor")
    engines = api("bootstrap", "POST", BASE, _engines_body(_revision(world))).json()
    rows = {b["id"]: b["family"] for b in _listed(api, "bootstrap")}
    assert rows == {platform_id: "platform", engines["id"]: "engines"}


@pytest.mark.parametrize("mode", ["off", "enforce"])
def test_a_delegate_administers_engines_bindings_and_sees_no_platform_one(world, api, monkeypatch, mode):  # noqa: F811
    monkeypatch.setattr(get_settings(), "iam_mode", mode)
    parent = _delegate(world)
    _platform(world, "editor", "platform_auditor")
    revision = parent["policy_revision_id"]
    outside = api("bootstrap", "POST", BASE, _engines_body(revision, "operator", "engine_operator")).json()

    r = api("delegate", "POST", BASE, _engines_body(revision, "editor"))
    assert r.status_code == 201, r.text
    child = r.json()
    rows = _listed(api, "delegate", "?include_inactive=true")
    assert {b["family"] for b in rows} == {"engines"}
    assert child["id"] in {b["id"] for b in rows}
    assert outside["id"] not in {b["id"] for b in rows}
    assert api("delegate", "POST", f"{BASE}/{child['id']}/revoke", {"version": 0}).status_code == 200
    assert child["id"] not in {b["id"] for b in _listed(api, "delegate")}


def test_under_enforce_a_platform_only_holder_sees_no_engines_binding(world, api):  # noqa: F811
    _platform(world, "outsider", "platform_auditor")
    api("bootstrap", "POST", BASE, _engines_body(_revision(world)))
    rows = _listed(api, "outsider", "?include_inactive=true")
    assert rows and {b["family"] for b in rows} == {"platform"}


def test_engines_off_hides_engines_bindings_from_the_listing(world, api, monkeypatch):  # noqa: F811
    _delegate(world)
    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    # With the flag off policy.authorize answers "bootstrap" for anyone: never an opening.
    r = api("delegate", "GET", BASE)
    assert (r.status_code, r.json()["detail"]) == (403, PLATFORM_DENIED_DETAIL)
    assert {b["family"] for b in _listed(api, "bootstrap", "?include_inactive=true")} <= {"platform"}
