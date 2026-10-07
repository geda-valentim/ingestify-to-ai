"""
Spec 0018 CA4: the 0009 decisions over `iam_bindings` equal those of a frozen copy
of the pre-0018 reader over `access_role_grants`.

The legacy state is built with the 0009 service itself (grants, delegation,
revocation), then migrated with `upgrade_0018`, then both stores are compared by
`shared.iam.engine_equivalence.run` over its default request matrix.
"""

import ast
import inspect as pyinspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from shared.access import contracts as C, policy, service
from shared.access.models import AuthorizationEpoch, RoleGrant
from shared.engine_control import service as control
from shared.iam import engine_bindings, engine_equivalence, migration
from shared.iam.models import IamBinding
from shared.models import Engine, User
from tests.test_execution_profiles import constraints, grant, world  # noqa: F401

EXTRA_USERS = [
    "delegate2", "child2", "delegate3", "child3", "delegate4", "child4", "ghost", "cycler",
]


def _users(db, ids):
    for uid in ids:
        db.add(User(id=uid, username=uid, email=uid + "@example.test",
                    hashed_password="unused", is_admin=False, is_active=True))
    db.commit()


def _soon(minutes=10):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _envelope():
    return C.Delegation(
        permissions=sorted(policy.ROLES["observer"]),
        constraints=constraints(),
        max_grant_seconds=1800,
    )


def _delegated(db, delegate, child):
    parent = grant(db, actor=delegate, role="access_admin", delegation=_envelope())
    kid = grant(db, actor=child, role="observer", creator=delegate, expires=_soon())
    assert kid["parent_id"] == parent["id"]
    return parent, kid


def drop_engine_bindings(db, ids=None):
    """
    Back to the pre-0018 store: the grants live only in access_role_grants.

    The 0009 service writes engines bindings (mirrored into access_role_grants)
    since 0018 slice 2; the migration under test starts from the old store.
    """
    q = db.query(IamBinding).filter(IamBinding.role.in_(list(policy.ROLES)))
    if ids is not None:
        q = q.filter(IamBinding.id.in_(list(ids)))
    q.update({IamBinding.parent_id: None}, synchronize_session=False)
    q.delete(synchronize_session=False)
    db.commit()


def legacy_grant(db, **kw):
    """A grant as the pre-0018 code wrote it: only in access_role_grants."""
    g = grant(db, **kw)
    drop_engine_bindings(db, [g["id"]])
    return g


def legacy_revoke(db, grant_id, actor):
    """A revocation as the pre-0018 `service.revoke` made it: access_role_grants only."""
    g = db.get(RoleGrant, grant_id)
    g.revoked_at = datetime.utcnow()
    g.version += 1
    db.get(AuthorizationEpoch, 1).version += 1
    policy.audit(db, actor, "access.revoked", grant_id)
    db.commit()


def legacy_state(db):
    """Every CA4 fixture, written through the 0009 code into access_role_grants."""
    _users(db, EXTRA_USERS)
    ids = {}
    # Several grants of the same role for one user, with distinct permission subsets
    # and distinct conditions.
    ids["op_plan"] = grant(db, actor="operator", role="engine_operator",
                           permissions=sorted(policy.READ | {"engine_operations.plan"}))["id"]
    ids["op_b"] = grant(db, actor="operator", role="engine_operator",
                        scope=constraints(engine_ids=["engine-b"]))["id"]
    ids["editor"] = grant(db, actor="editor", role="profile_editor")["id"]
    # Revoked, expired.
    ids["revoked"] = grant(db, actor="outsider", role="observer")["id"]
    service.revoke(db, ids["revoked"], 0, "bootstrap")
    ids["expired"] = grant(db, actor="outsider", role="runtime_configurator")["id"]
    db.get(RoleGrant, ids["expired"]).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    # Delegated and active.
    ids["parent"], ids["child"] = (g["id"] for g in _delegated(db, "delegate", "observer"))
    # Parent revoked.
    ids["parent2"], ids["child2"] = (g["id"] for g in _delegated(db, "delegate2", "child2"))
    service.revoke(db, ids["parent2"], 0, "bootstrap")
    # Parent expired.
    ids["parent3"], ids["child3"] = (g["id"] for g in _delegated(db, "delegate3", "child3"))
    db.get(RoleGrant, ids["parent3"]).expires_at = datetime.utcnow() - timedelta(seconds=1)
    # Owner of the parent inactive.
    ids["parent4"], ids["child4"] = (g["id"] for g in _delegated(db, "delegate4", "child4"))
    db.get(User, "delegate4").is_active = False
    db.commit()
    # Owner of the grant inactive.
    ids["ghost"] = grant(db, actor="ghost", role="observer")["id"]
    db.get(User, "ghost").is_active = False
    db.commit()
    # A parent_id cycle, reachable only through UPDATEs.
    a = grant(db, actor="cycler", role="observer")["id"]
    b = grant(db, actor="cycler", role="observer")["id"]
    db.get(RoleGrant, a).parent_id = b
    db.get(RoleGrant, b).parent_id = a
    db.commit()
    ids["cycle_a"], ids["cycle_b"] = a, b
    drop_engine_bindings(db)
    return ids


def _engine(world):  # noqa: F811
    return world.kw["bind"]


@pytest.fixture
def migrated(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
    migration.upgrade_0018(_engine(world))
    return world, ids


def test_iam_store_decides_exactly_like_the_legacy_store(migrated):
    factory, ids = migrated
    report = engine_equivalence.run(factory, engine_bindings.grants)
    assert report.decisions > 1000
    assert report.clean, "\n".join(map(str, report.divergences[:20]))


def test_the_fixtures_exercise_both_outcomes(migrated):
    factory, ids = migrated
    with factory() as db:
        held = {g.id for u in ("operator", "editor", "observer", "delegate") for g in engine_bindings.grants(db, u)}
        assert {ids["op_plan"], ids["op_b"], ids["editor"], ids["parent"], ids["child"]} <= held
        for uid in ("outsider", "child2", "child3", "child4", "delegate4", "ghost", "cycler"):
            assert engine_bindings.grants(db, uid) == [], uid
            assert engine_equivalence.legacy_grants(db, uid) == [], uid
        engine_a = db.get(Engine, "engine-a")
        with _swap(engine_bindings.grants):
            assert policy.allowed(db, "observer", "engines.read", engine=engine_a)
            assert policy.allowed(db, "editor", "execution_profiles.read")


def test_a_restriction_made_only_in_iam_bindings_is_reported(migrated):
    """The harness is not vacuous: a one-sided revocation is a divergence."""
    factory, ids = migrated
    with factory() as db:
        db.get(IamBinding, ids["op_plan"]).revoked_at = datetime.utcnow()
        db.commit()
    report = engine_equivalence.run(factory, engine_bindings.grants, user_ids=["operator"])
    assert not report.clean
    assert {d.actor for d in report.divergences} == {"operator"}


def test_a_legacy_revocation_reconciled_is_denied_by_the_iam_store(migrated):
    """The pre-0018 code revokes during a rollback; reconciliation brings it back."""
    factory, ids = migrated
    with factory() as db:
        legacy_revoke(db, ids["child"], "bootstrap")  # writes access_role_grants only
        epoch = db.get(AuthorizationEpoch, 1).version
    with _engine(factory).begin() as conn:
        assert migration.reconcile_engine_grants(conn) == {"copied": 0, "restricted": 1}
    with factory() as db:
        b = db.get(IamBinding, ids["child"])
        assert b.revoked_at is not None and b.revoked_by == "bootstrap" and b.version == 1
        assert db.get(AuthorizationEpoch, 1).version == epoch + 1
        assert engine_bindings.grants(db, "observer") == []
    assert engine_equivalence.run(factory, engine_bindings.grants, user_ids=["observer", "delegate"]).clean


@pytest.mark.parametrize("corruption", ["null", "dangling", "empty_permissions", "service_principal"])
def test_a_malformed_engines_binding_contributes_nothing(migrated, corruption):
    """0018 §4.1: a missing condition is never read as unrestricted."""
    factory, ids = migrated
    with factory() as db:
        engine_a = db.get(Engine, "engine-a")
        with _swap(engine_bindings.grants):
            # The allow baseline on the iam side, so the denials below are the corruption's.
            assert policy.allowed(db, "editor", "execution_profiles.read")
            assert policy.navigation(db, db.get(User, "editor"))["permissions"]
        db.execute(text("PRAGMA foreign_keys=OFF"))
        b = db.get(IamBinding, ids["editor"])
        if corruption == "null":
            b.condition_ref = None
        elif corruption == "dangling":
            b.condition_ref = "no-such-revision"
        elif corruption == "empty_permissions":
            b.permissions = []
        else:
            b.subject_type = "service_principal"
        db.commit()
        assert engine_bindings.grants(db, "editor") == []
        with _swap(engine_bindings.grants):
            assert not policy.allowed(db, "editor", "execution_profiles.read")
            assert not policy.allowed(db, "editor", "engines.read", engine=engine_a)
            assert policy.navigation(db, db.get(User, "editor"))["permissions"] == []


def _swap(reader):
    """The decision code over `reader` (what slice 2 wires permanently)."""
    return engine_equivalence._source(reader)


def test_a_child_whose_parent_binding_is_revoked_is_denied(migrated):
    factory, ids = migrated
    with factory() as db:
        assert [g.id for g in engine_bindings.grants(db, "observer")] == [ids["child"]]
        db.get(IamBinding, ids["parent"]).revoked_at = datetime.utcnow()
        db.commit()
        assert engine_bindings.grants(db, "observer") == []


def test_only_the_frozen_copy_reads_the_legacy_store():
    """CA4: the frozen copy does not import the code it is compared with, and the
    IAM reader never touches access_role_grants."""
    tree = ast.parse(pyinspect.getsource(engine_equivalence))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert "shared.iam.engine_bindings" in imported  # only inside main(), lazily
    top = {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
    assert "shared.iam.engine_bindings" not in top
    reader = ast.parse(pyinspect.getsource(engine_bindings))
    names = {n.id for n in ast.walk(reader) if isinstance(n, ast.Name)}
    names |= {a.name for n in ast.walk(reader) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "RoleGrant" not in names


def test_errors_of_the_decision_code_are_outcomes_too():
    assert engine_equivalence._outcome(lambda: 1) == ("allow", 1)
    assert engine_equivalence._outcome(
        lambda: (_ for _ in ()).throw(control.ControlError("ACCESS_DENIED", 403))
    ) == ("deny", "ACCESS_DENIED", 403)
    assert engine_equivalence._outcome(lambda: {}["x"]) == ("error", "KeyError")
