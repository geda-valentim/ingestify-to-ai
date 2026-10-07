"""
IAM decision core (spec 0014 §8 item 1): catalog, bindings, decide() and the
binding service.

Unit tests on SQLite; Redis is never consulted (the parent-link fallback is
replaced explicitly where a test needs it).
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from shared.access.models import ServicePrincipal
from shared.access.policy import PERMISSIONS as ENGINE_PERMISSIONS
from shared.config import get_settings
from shared.database import Base
from shared.iam import bindings, catalog, migration, ownership
from shared.iam.decide import (
    PLATFORM,
    Decider,
    DelegatedPermission,
    JobRef,
    UnknownPermission,
    can,
    decide,
    principal_for_service,
    principal_for_user,
)
from shared.iam.models import IamBinding
from shared.models import AdminAudit, Job, Page, Project, User

NOW = datetime(2026, 10, 6, 12, 0, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    monkeypatch.setattr(ownership, "redis_job_status", lambda job_id: None)
    monkeypatch.setattr(ownership, "redis_owner_matches", lambda job_id, user_id: False)
    # The defaults were bound at definition time; rebind them through the module.
    real = ownership.job_access

    def job_access(db, job_id, user_id, **kw):
        kw.setdefault("redis_status", lambda j: None)
        kw.setdefault("owner_matches", lambda j, u: False)
        return real(db, job_id, user_id, **kw)

    monkeypatch.setattr(ownership, "job_access", job_access)


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_user_ids", "")
    monkeypatch.setattr(s, "iam_mode", "off")
    return s


def _user(db, name, *, is_admin=False, active=True):
    u = User(id=f"user-{name}", email=f"{name}@example.com", username=name,
             hashed_password="x", is_active=active, is_admin=is_admin)
    db.add(u)
    db.commit()
    return u


def _bind(db, user, role, *, granted_by, expires_at=None, revoked_at=None, subject_type="user"):
    b = IamBinding(subject_type=subject_type, subject_id=user if isinstance(user, str) else user.id,
                   role=role, scope_type="platform", granted_by=granted_by.id,
                   expires_at=expires_at or NOW + timedelta(days=30), revoked_at=revoked_at,
                   created_at=NOW - timedelta(days=1))
    db.add(b)
    db.commit()
    return b


def _decider(db, **kw):
    return Decider(db, now=NOW, **kw)


@pytest.fixture
def people(db, settings):
    root = _user(db, "root", is_admin=True)
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    return root, alice, bob


# -- catalog -----------------------------------------------------------------------

EXPECTED_ROLES = {
    "platform_admin": {
        "platform.stats.read", "platform.jobs.read", "platform.jobs.recover",
        "platform.jobs.cleanup", "platform.monitoring.read", "platform.broker.requeue",
        "platform.settings.read", "platform.settings.update", "platform.routing.read",
        "platform.routing.update", "platform.audit.read", "engines.remote.use",
        "iam.bindings.read", "iam.bindings.manage",
    },
    "platform_operator": {
        "platform.stats.read", "platform.jobs.read", "platform.jobs.recover",
        "platform.monitoring.read", "platform.broker.requeue", "platform.routing.read",
    },
    "platform_auditor": {
        "platform.stats.read", "platform.jobs.read", "platform.monitoring.read",
        "platform.settings.read", "platform.routing.read", "platform.audit.read",
        "iam.bindings.read",
    },
    "remote_engine_user": {"engines.remote.use"},
}


def test_managed_roles_are_exactly_the_spec_table():
    assert {k: set(r.permissions) for k, r in catalog.ROLES.items()} == EXPECTED_ROLES


def test_cleanup_belongs_only_to_platform_admin():
    assert catalog.roles_granting("platform.jobs.cleanup") == ("platform_admin",)


def test_catalog_is_closed_and_disjoint_from_0009():
    assert not set(catalog.PERMISSIONS) & ENGINE_PERMISSIONS
    assert catalog.PLATFORM_PERMISSIONS == EXPECTED_ROLES["platform_admin"]
    assert catalog.DATA_PERMISSIONS.isdisjoint(catalog.PLATFORM_PERMISSIONS)
    described = catalog.describe()
    assert {p["name"] for p in described["permissions"]} == set(catalog.PERMISSIONS)
    assert {r["key"] for r in described["roles"]} == set(EXPECTED_ROLES)


def test_auditor_holds_no_mutation():
    for name in catalog.ROLES["platform_auditor"].permissions:
        assert not catalog.permission(name).mutation, name


# -- decide: platform ----------------------------------------------------------------

@pytest.mark.parametrize("role", sorted(EXPECTED_ROLES))
@pytest.mark.parametrize("permission", sorted(catalog.PLATFORM_PERMISSIONS))
def test_role_by_permission_matrix(db, people, role, permission):
    root, alice, _ = people
    b = _bind(db, alice, role, granted_by=root)
    d = decide(db, alice, permission, decider=_decider(db))
    if permission in EXPECTED_ROLES[role]:
        assert (d.allow, d.status, d.via, d.binding_id) == (True, 200, "binding", b.id)
    else:
        assert (d.allow, d.status) == (False, 403)


def test_no_binding_is_403_for_platform(db, people):
    _, alice, _ = people
    for permission in catalog.PLATFORM_PERMISSIONS:
        d = decide(db, alice, permission, decider=_decider(db))
        assert (d.allow, d.status, d.via) == (False, 403, "no_binding")


def test_null_actor_is_401_and_never_admin(db, people):
    for permission in ["platform.stats.read", "iam.bindings.manage", "jobs.read", "jobs.create"]:
        d = decide(db, None, permission)
        assert (d.allow, d.status) == (False, 401)
    assert principal_for_user(None) is None


def test_inactive_user_is_403_even_if_admin_or_bound(db, people):
    root, _, _ = people
    ghost = _user(db, "ghost", is_admin=True, active=False)
    _bind(db, ghost, "platform_admin", granted_by=root)
    assert decide(db, ghost, "platform.stats.read", decider=_decider(db)).status == 403
    assert decide(db, ghost, "jobs.create").status == 403


def test_expired_binding_denies_using_utc(db, people):
    root, alice, bob = people
    _bind(db, alice, "platform_operator", granted_by=root, expires_at=NOW)  # boundary: expired
    _bind(db, bob, "platform_operator", granted_by=root, expires_at=NOW + timedelta(seconds=1))
    assert not decide(db, alice, "platform.stats.read", decider=_decider(db)).allow
    assert decide(db, bob, "platform.stats.read", decider=_decider(db)).allow


def test_revoked_binding_denies(db, people):
    root, alice, _ = people
    _bind(db, alice, "platform_operator", granted_by=root, revoked_at=NOW - timedelta(minutes=1))
    assert not decide(db, alice, "platform.stats.read", decider=_decider(db)).allow


def test_unknown_role_key_in_table_grants_nothing(db, people):
    root, alice, _ = people
    _bind(db, alice, "superuser", granted_by=root)
    assert not decide(db, alice, "platform.stats.read", decider=_decider(db)).allow


def test_bootstrap_by_column_and_by_env_holds_every_platform_permission(db, people, settings, monkeypatch):
    root, alice, _ = people
    monkeypatch.setattr(settings, "admin_user_ids", f" {alice.id} ,other")
    for user in (root, alice):
        for permission in catalog.PLATFORM_PERMISSIONS:
            d = decide(db, user, permission, decider=_decider(db))
            assert (d.allow, d.via) == (True, "bootstrap"), (user.id, permission)
        assert _decider(db).platform_permissions(user) == catalog.PLATFORM_PERMISSIONS
        assert _decider(db).platform_roles(user) == []


def test_bootstrap_mutation_is_audited_once_per_request_and_reads_are_not(db, people):
    root, _, _ = people
    decider = _decider(db)
    decider.decide(root, "platform.stats.read")
    decider.decide(root, "platform.settings.update")
    decider.decide(root, "platform.settings.update")
    db.commit()
    rows = db.query(AdminAudit).filter_by(action="iam.bootstrap.use").all()
    assert len(rows) == 1
    assert rows[0].actor_user_id == root.id
    assert rows[0].auth_method == "jwt"
    assert rows[0].target_id == "platform.settings.update"
    assert rows[0].after == {"permission": "platform.settings.update", "via": "bootstrap",
                             "credential": "session"}
    _decider(db).decide(principal_for_user(root, credential="api_key"), "platform.jobs.cleanup")
    db.commit()
    assert db.query(AdminAudit).filter_by(action="iam.bootstrap.use").count() == 2


def test_binding_use_is_not_bootstrap_audited(db, people):
    root, alice, _ = people
    _bind(db, alice, "platform_admin", granted_by=root)
    assert decide(db, alice, "platform.settings.update", decider=_decider(db)).via == "binding"
    db.commit()
    assert db.query(AdminAudit).count() == 0


def test_engine_and_unknown_permissions_are_refused(db, people):
    root, _, _ = people
    with pytest.raises(DelegatedPermission):
        decide(db, root, "engines.read")
    with pytest.raises(UnknownPermission):
        decide(db, root, "platform.everything")


def test_bindings_are_read_once_per_request_and_never_across(db, people):
    root, alice, _ = people
    b = _bind(db, alice, "platform_operator", granted_by=root)
    request = _decider(db)
    assert request.decide(alice, "platform.stats.read").allow
    b.revoked_at = NOW
    db.commit()
    # Same request: memoized. Next request: revoked.
    assert request.decide(alice, "platform.jobs.read").allow
    assert not _decider(db).decide(alice, "platform.stats.read").allow


def test_service_principal_binding(db, people):
    root, _, _ = people
    db.add(ServicePrincipal(id="sp-1", purpose="ops", active=True))
    db.commit()
    _bind(db, "sp-1", "platform_operator", granted_by=root, subject_type="service_principal")
    sp = principal_for_service(db, "sp-1")
    assert decide(db, sp, "platform.jobs.recover", decider=_decider(db)).allow
    assert decide(db, sp, "jobs.create").status == 404  # owns no data
    assert principal_for_service(db, "missing") is None


# -- decide: data ------------------------------------------------------------------

def test_data_is_owner_only_and_bootstrap_reads_nothing_else(db, people):
    root, alice, bob = people
    db.add_all([
        Job(id="main", user_id=alice.id, job_type="MAIN"),
        Page(id="p1", job_id="main", page_number=1, page_job_id="page-1"),
        Project(id="proj", user_id=alice.id, name="P", name_key="p"),
        Job(id="orphan", user_id=None, job_type="MAIN"),
    ])
    db.commit()
    for resource in [JobRef("main"), JobRef("page-1"), db.get(Job, "main"), db.get(Project, "proj")]:
        ok = decide(db, alice, "jobs.read", resource)
        assert (ok.allow, ok.via) == (True, "owner")
        for other in (bob, root):
            d = decide(db, other, "jobs.read", resource)
            assert (d.allow, d.status) == (False, 404)
    assert decide(db, alice, "jobs.read", JobRef("page-1")).target.id == "main"
    for user in (alice, bob, root):
        assert decide(db, user, "jobs.delete", JobRef("orphan")).status == 404
        assert decide(db, user, "jobs.read", JobRef("nope")).status == 404


def test_self_service_needs_no_resource_other_data_permissions_do(db, people):
    _, alice, _ = people
    assert decide(db, alice, "jobs.create").via == "self_service"
    assert decide(db, alice, "documents.convert", PLATFORM).allow
    assert decide(db, alice, "jobs.read").status == 404
    assert decide(db, alice, "projects.delete", None).status == 404


@pytest.mark.parametrize("permission", sorted(catalog.DATA_PERMISSIONS))
def test_missing_resource_is_404_for_every_data_permission(db, people, permission):
    # A scoped lookup that found nothing must never fall through to self_service.
    root, alice, _ = people
    for user in (alice, root):
        d = decide(db, user, permission, None)
        assert (d.allow, d.status) == (False, 404)


def test_redis_fallback_still_needs_a_positive_owner_match(db, people):
    _, alice, bob = people
    decider = _decider(db, job_access=lambda d, j, u: ownership.job_access(
        d, j, u, redis_status=lambda _: None, owner_matches=lambda jj, uu: uu == alice.id))
    assert decider.decide(alice, "jobs.read", JobRef("redis-only")).allow
    assert not decider.decide(bob, "jobs.read", JobRef("redis-only")).allow


# -- can(): IAM_MODE ------------------------------------------------------------------

def test_mode_off_leaves_bindings_inert(db, people, settings):
    root, alice, _ = people
    _bind(db, alice, "remote_engine_user", granted_by=root)
    assert not can(db, alice, "engines.remote.use", decider=_decider(db))
    assert can(db, root, "engines.remote.use")


def test_mode_enforce_honours_bindings_and_revocation(db, people, settings, monkeypatch):
    monkeypatch.setattr(settings, "iam_mode", "enforce")
    root, alice, bob = people
    b = _bind(db, alice, "remote_engine_user", granted_by=root)
    assert can(db, alice, "engines.remote.use", decider=_decider(db))
    assert not can(db, bob, "engines.remote.use", decider=_decider(db))
    assert can(db, root, "engines.remote.use", decider=_decider(db))
    assert not can(db, None, "engines.remote.use")
    bindings.revoke(db, root, b.id, version=0, decider=_decider(db))
    assert not can(db, alice, "engines.remote.use", decider=_decider(db))


def test_mode_shadow_answers_legacy_and_logs_divergence(db, people, settings, monkeypatch, caplog):
    monkeypatch.setattr(settings, "iam_mode", "shadow")
    root, alice, _ = people
    _bind(db, alice, "platform_operator", granted_by=root)
    with caplog.at_level(logging.WARNING, logger="shared.iam.decide"):
        assert not can(db, alice, "platform.stats.read", decider=_decider(db))
    assert any(r.getMessage().startswith("iam_shadow_divergence ") for r in caplog.records)


def test_mode_off_is_exactly_legacy_for_an_inactive_admin(db, people, settings):
    # Workers read is_effective_admin off the job owner with no is_active check.
    ghost = _user(db, "ghost", is_admin=True, active=False)
    assert can(db, ghost, "engines.remote.use", mode="off")
    assert not can(db, ghost, "engines.remote.use", mode="enforce", decider=_decider(db))
    assert not can(db, ghost, "jobs.create", mode="off")


def test_mode_off_still_audits_bootstrap_mutations(db, people, settings):
    root, _, _ = people
    assert can(db, root, "platform.settings.update", mode="off", decider=_decider(db))
    assert can(db, root, "platform.stats.read", mode="off", decider=_decider(db))
    db.commit()
    rows = db.query(AdminAudit).filter_by(action="iam.bootstrap.use").all()
    assert [r.target_id for r in rows] == ["platform.settings.update"]


def test_mode_shadow_resolves_data_ownership_once(db, people, settings, monkeypatch):
    _, alice, _ = people
    db.add(Job(id="j1", user_id=alice.id, job_type="MAIN"))
    db.commit()
    calls = []
    real = ownership.job_access
    decider = _decider(db, job_access=lambda d, j, u: calls.append(j) or real(d, j, u))
    assert can(db, alice, "jobs.read", JobRef("j1"), mode="shadow", decider=decider)
    assert calls == ["j1"]


# -- binding service -----------------------------------------------------------------

def _grant(db, actor, subject, role="platform_operator", expires_at=None, **kw):
    return bindings.grant(
        db, actor, subject_type=kw.pop("subject_type", "user"),
        subject_id=subject if isinstance(subject, str) else subject.id,
        role=role, expires_at=expires_at or NOW + timedelta(days=90),
        decider=_decider(db), **kw,
    )


def _refused(code, status, fn, *a, **kw):
    with pytest.raises(bindings.IamError) as e:
        fn(*a, **kw)
    assert (e.value.code, e.value.status) == (code, status)


def test_bootstrap_grants_and_it_is_audited(db, people):
    root, alice, _ = people
    b = _grant(db, root, alice, ip="10.0.0.1")
    assert (b.granted_by, b.version, b.scope_type, b.scope_id) == (root.id, 0, "platform", None)
    audit = db.query(AdminAudit).filter_by(action="iam.binding.grant").one()
    assert (audit.target_type, audit.target_id, audit.ip) == ("iam_binding", b.id, "10.0.0.1")
    assert audit.after["role"] == "platform_operator"
    assert decide(db, alice, "platform.jobs.recover", decider=_decider(db)).allow


def test_nobody_grants_to_themselves(db, people):
    root, alice, _ = people
    _refused("SELF_GRANT", 422, _grant, db, root, root, role="remote_engine_user")
    _bind(db, alice, "platform_admin", granted_by=root)
    _refused("SELF_GRANT", 422, _grant, db, alice, alice, role="remote_engine_user")


def test_nobody_grants_a_role_above_their_own(db, people, monkeypatch):
    root, alice, bob = people
    monkeypatch.setitem(catalog.ROLES, "bindings_manager", catalog.Role(
        "bindings_manager", frozenset({"iam.bindings.manage", "iam.bindings.read"}), "test"))
    _bind(db, alice, "bindings_manager", granted_by=root)
    _refused("ROLE_ABOVE_GRANTOR", 422, _grant, db, alice, bob, role="platform_operator")
    _bind(db, alice, "platform_operator", granted_by=root)
    assert _grant(db, alice, bob, role="platform_operator").granted_by == alice.id
    _refused("ROLE_ABOVE_GRANTOR", 422, _grant, db, alice, bob, role="platform_admin")


def test_only_managers_grant(db, people):
    root, alice, bob = people
    _refused("ACCESS_DENIED", 401, _grant, db, None, bob)
    _refused("ACCESS_DENIED", 403, _grant, db, alice, bob)
    _bind(db, alice, "platform_auditor", granted_by=root)
    _refused("ACCESS_DENIED", 403, _grant, db, alice, bob)


def test_expires_at_is_required_future_and_at_most_365_days(db, people):
    root, alice, _ = people
    for bad in [None, "not-a-date", NOW, NOW - timedelta(days=1), NOW + timedelta(days=365, seconds=1)]:
        with pytest.raises(bindings.IamError) as e:
            bindings.grant(db, root, subject_type="user", subject_id=alice.id,
                           role="platform_operator", expires_at=bad, decider=_decider(db))
        assert (e.value.code, e.value.status) == ("INVALID_EXPIRES_AT", 422), bad
    b = _grant(db, root, alice, expires_at=NOW + timedelta(days=365))
    assert b.expires_at == NOW + timedelta(days=365)


def test_expires_at_is_normalized_to_utc(db, people):
    root, alice, bob = people
    brt = timezone(timedelta(hours=-3))
    local = datetime(2026, 10, 7, 9, 0, tzinfo=brt)
    assert _grant(db, root, alice, expires_at=local).expires_at == datetime(2026, 10, 7, 12, 0)
    assert _grant(db, root, bob, expires_at="2026-10-07T12:00:00Z").expires_at == datetime(2026, 10, 7, 12, 0)
    # Aware past in another zone is still past.
    _refused("INVALID_EXPIRES_AT", 422, _grant, db, root, alice, role="remote_engine_user",
             expires_at=datetime(2026, 10, 6, 11, 0, tzinfo=timezone(timedelta(hours=2))))


def test_grant_validates_role_and_subject(db, people):
    root, alice, _ = people
    _refused("UNKNOWN_ROLE", 422, _grant, db, root, alice, role="owner")
    _refused("INVALID_SUBJECT", 422, _grant, db, root, alice, subject_type="group")
    _refused("SUBJECT_NOT_FOUND", 422, _grant, db, root, "user-nobody")
    _refused("SUBJECT_NOT_FOUND", 422, _grant, db, root, "sp-x", subject_type="service_principal")
    _grant(db, root, alice)
    _refused("BINDING_EXISTS", 409, _grant, db, root, alice)


def test_revoke_with_version_and_audit(db, people):
    root, alice, _ = people
    b = _grant(db, root, alice)
    _refused("VERSION_CONFLICT", 409, bindings.revoke, db, root, b.id, version=7, decider=_decider(db))
    _refused("ACCESS_DENIED", 403, bindings.revoke, db, alice, b.id, version=0, decider=_decider(db))
    _refused("BINDING_NOT_FOUND", 404, bindings.revoke, db, root, "nope", version=0, decider=_decider(db))
    revoked = bindings.revoke(db, root, b.id, version=0, ip="10.0.0.2", decider=_decider(db))
    assert (revoked.version, revoked.revoked_by, revoked.revoked_at) == (1, root.id, NOW)
    _refused("ALREADY_REVOKED", 409, bindings.revoke, db, root, b.id, version=1, decider=_decider(db))
    audit = db.query(AdminAudit).filter_by(action="iam.binding.revoke").one()
    assert audit.before["active"] is True and audit.after["active"] is False
    assert not decide(db, alice, "platform.stats.read", decider=_decider(db)).allow
    # A revoked role can be granted again.
    assert _grant(db, root, alice).id != b.id


def test_list_bindings_requires_read(db, people):
    root, alice, bob = people
    _grant(db, root, alice)
    _refused("ACCESS_DENIED", 403, bindings.list_bindings, db, bob, decider=_decider(db))
    _bind(db, bob, "platform_auditor", granted_by=root)
    listed = bindings.list_bindings(db, bob, decider=_decider(db))
    assert {(x["subject_id"], x["role"]) for x in listed} == {
        (alice.id, "platform_operator"), (bob.id, "platform_auditor")}


# -- migration ---------------------------------------------------------------------

def test_migration_is_additive_idempotent_and_marked(settings, monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('kept')"))
    migration.upgrade(engine)
    with engine.begin() as conn:
        migration.upgrade(conn)
    migration.validate_schema(engine)
    tables = set(inspect(engine).get_table_names())
    assert tables == {"users", "app_migrations", "iam_bindings"}
    indexes = {i["name"] for i in inspect(engine).get_indexes("iam_bindings")}
    assert {"ix_iam_bindings_subject", "ix_iam_bindings_scope"} <= indexes
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM app_migrations")).scalars().all() == [migration.MARKER]
        assert conn.execute(text("SELECT id FROM users")).scalars().all() == ["kept"]

    monkeypatch.setattr(settings, "iam_mode", "enforce")
    with pytest.raises(RuntimeError):
        migration.downgrade(engine)
    monkeypatch.setattr(settings, "iam_mode", "off")
    migration.downgrade(engine)
    assert "iam_bindings" not in inspect(engine).get_table_names()
    with pytest.raises(RuntimeError):
        migration.validate_schema(engine)
    engine.dispose()


def test_migration_refuses_without_base_schema():
    engine = create_engine("sqlite://")
    with pytest.raises(RuntimeError):
        migration.upgrade(engine)
    engine.dispose()


def test_a_service_principal_never_writes_bindings(db, people):
    root, alice, bob = people
    db.add(ServicePrincipal(id="sp-1", purpose="ops", active=True))
    db.commit()
    b = _grant(db, root, "sp-1", role="platform_admin", subject_type="service_principal")
    sp = principal_for_service(db, "sp-1")
    # It may read bindings, but granted_by/revoked_by are users.id FKs.
    assert bindings.list_bindings(db, sp, decider=_decider(db))
    _refused("ACCESS_DENIED", 403, _grant, db, sp, alice)
    other = _grant(db, root, bob)
    _refused("ACCESS_DENIED", 403, bindings.revoke, db, sp, other.id, version=0, decider=_decider(db))
    assert db.get(IamBinding, other.id).revoked_at is None
    assert b.granted_by == root.id
