"""
Spec 0018 CA5 on InnoDB: the global lock order (§4.3) epoch -> users ->
iam_bindings/access_role_grants holds with both binding families in one table.

Opt-in like the other InnoDB gates: set ENGINE_CONTROL_TEST_DATABASE_URL to a
disposable database named engine_control_test_*. The four interleavings of §7:

1. revocation x effect admission (the 0009 gates in
   test_execution_profiles_migration.py, now over iam_bindings);
2. parent revocation x child creation through `_delegator` (and x a revocation
   by the delegate);
3. parent revocation x the child's effect admission;
4. the child's effect admission x a 0014 grant to the parent's owner, no deadlock.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from shared.access import contracts as C, policy, service
from shared.access.models import EffectAdmission
from shared.engine_control import service as control
from shared.engine_control.contracts import PlanRequest
from shared.iam import bindings
from shared.iam import models as iam_models
from shared.iam.decide import Decider
from shared.iam.models import IamBinding
from shared.models import Engine, User
from tests.test_execution_profiles import constraints, grant, published, world  # noqa: F401
from tests.test_execution_profiles_migration import mysql_world  # noqa: F401


def _soon(minutes=10):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _delegated(db):
    """A `delegate` access_admin parent and the operator's child engine_operator."""
    p = published(db)
    service.bind(
        db,
        db.get(Engine, "engine-a"),
        C.Bind(version=0, feature="transcription", revision_id=p["latest_published_revision_id"]),
        "bootstrap",
    )
    parent = grant(
        db,
        actor="delegate",
        role="access_admin",
        delegation=C.Delegation(
            permissions=sorted(policy.ROLES["engine_operator"]),
            constraints=constraints(),
            max_grant_seconds=1800,
        ),
    )
    child = grant(db, actor="operator", role="engine_operator", creator="delegate", expires=_soon())
    assert child["parent_id"] == parent["id"]
    return parent, child


def _claimed(db, actor="operator"):
    plan = control.create_plan(
        db, db.get(Engine, "engine-a"), PlanRequest(type="scale", engine_version=1, max_usd="0.10"), actor
    )
    op = control.enqueue(db, plan["plan_id"], plan["plan_hash"], "once", actor, True)
    return op["operation_id"], control.claim(db, op["operation_id"], "executor")


def _admit(factory, op_id, gen, step, started=None, commit=True):
    with factory() as db:
        # Hold an old identity snapshot before waiting on the SQL epoch.
        assert db.get(User, "operator").is_active
        if started is not None:
            started.set()
        try:
            control.admit_effect(db, op_id, gen, step)
            if commit:
                db.commit()
            return "admitted"
        except control.ControlError as exc:
            db.rollback()
            return exc.code


def test_innodb_parent_revocation_before_child_creation_refuses_the_child(mysql_world):  # noqa: F811
    with mysql_world() as db:
        parent, _ = _delegated(db)
        revision = db.get(IamBinding, parent["id"]).condition_ref
    started = Event()
    with mysql_world() as revoker, ThreadPoolExecutor(max_workers=1) as pool:
        policy.epoch(revoker, True)

        def create():
            with mysql_world() as db:
                # The delegate's grants are read before waiting on the epoch.
                assert db.get(IamBinding, parent["id"]).revoked_at is None
                started.set()
                try:
                    return service.create_grant(
                        db,
                        C.GrantCreate(
                            user_id="observer",
                            role="engine_operator",
                            policy_revision_id=revision,
                            expires_at=_soon(),
                        ),
                        "delegate",
                    )["id"]
                except policy.ControlError as exc:
                    db.rollback()
                    return exc.code

        future = pool.submit(create)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        service.revoke(revoker, parent["id"], 0, "bootstrap")
        assert future.result(timeout=5) in {"ACCESS_DENIED", "DELEGATION_EXCEEDED"}
    with mysql_world() as db:
        assert db.query(IamBinding).filter_by(subject_id="observer").count() == 0


def test_innodb_parent_revocation_before_a_delegated_revoke_refuses_it(mysql_world):  # noqa: F811
    """A delegate whose access_admin is revoked first no longer revokes through it."""
    with mysql_world() as db:
        parent, child = _delegated(db)
    started = Event()
    with mysql_world() as revoker, ThreadPoolExecutor(max_workers=1) as pool:
        policy.epoch(revoker, True)

        def revoke_child():
            with mysql_world() as db:
                assert db.get(IamBinding, parent["id"]).revoked_at is None
                started.set()
                try:
                    return service.revoke(db, child["id"], 0, "delegate")["revoked_at"]
                except policy.ControlError as exc:
                    db.rollback()
                    return exc.code

        future = pool.submit(revoke_child)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        service.revoke(revoker, parent["id"], 0, "bootstrap")
        assert future.result(timeout=5) in {"ACCESS_DENIED", "DELEGATION_EXCEEDED"}
    with mysql_world() as db:
        assert db.get(IamBinding, child["id"]).revoked_at is None


def test_innodb_child_created_before_parent_revocation_dies_with_it(mysql_world):  # noqa: F811
    with mysql_world() as db:
        parent, _ = _delegated(db)
        revision = db.get(IamBinding, parent["id"]).condition_ref
    started = Event()
    with mysql_world() as creator, ThreadPoolExecutor(max_workers=1) as pool:
        # The child's creation holds the epoch until it commits.
        policy.epoch(creator, True)

        def revoke():
            with mysql_world() as db:
                started.set()
                return service.revoke(db, parent["id"], 0, "bootstrap")["revoked_at"]

        future = pool.submit(revoke)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        child = service.create_grant(
            creator,
            C.GrantCreate(
                user_id="observer", role="engine_operator", policy_revision_id=revision, expires_at=_soon()
            ),
            "delegate",
        )
        assert child["parent_id"] == parent["id"]
        assert future.result(timeout=5) is not None
    with mysql_world() as db:
        assert not policy.allowed(db, "observer", "engines.read", engine=db.get(Engine, "engine-a"))


def test_innodb_parent_revocation_before_child_admission_denies_the_child(mysql_world):  # noqa: F811
    with mysql_world() as db:
        parent, _ = _delegated(db)
        op_id, gen = _claimed(db)
    started = Event()
    with mysql_world() as revoker, ThreadPoolExecutor(max_workers=1) as pool:
        policy.epoch(revoker, True)
        future = pool.submit(_admit, mysql_world, op_id, gen, "sdk:after-parent-revoke", started)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        service.revoke(revoker, parent["id"], 0, "bootstrap")
        assert future.result(timeout=5) == "ACCESS_DENIED"
    with mysql_world() as db:
        assert db.query(EffectAdmission).count() == 0


def test_innodb_child_admission_before_parent_revocation_is_durable(mysql_world):  # noqa: F811
    with mysql_world() as db:
        parent, _ = _delegated(db)
        op_id, gen = _claimed(db)
    started = Event()
    with mysql_world() as executor, ThreadPoolExecutor(max_workers=1) as pool:
        control.admit_effect(executor, op_id, gen, "sdk:before-parent-revoke")

        def revoke():
            with mysql_world() as db:
                started.set()
                return service.revoke(db, parent["id"], 0, "bootstrap")

        future = pool.submit(revoke)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        executor.commit()
        assert future.result(timeout=5)["revoked_at"] is not None
    with mysql_world() as db:
        assert db.query(EffectAdmission).one().state == "uncertain"
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            control.admit_effect(db, op_id, gen, "sdk:next")


def _platform_grant(factory, subject_locked=None, go=None):
    """A 0014 grant to the parent's owner, optionally paused once it holds the users row."""
    with factory() as db:
        try:
            b = bindings.grant(
                db, db.get(User, "bootstrap"), subject_type="user", subject_id="delegate",
                role="platform_auditor", expires_at=datetime.utcnow() + timedelta(days=1),
                decider=Decider(db),
            )
            return b.id
        except Exception as exc:  # a deadlock surfaces here as OperationalError 1213
            db.rollback()
            return repr(exc)


@pytest.mark.parametrize("first", ["platform_grant", "admission"])
def test_innodb_child_admission_and_a_platform_grant_to_the_parent_owner_never_deadlock(
    mysql_world, monkeypatch, first  # noqa: F811
):
    """
    CA5: the admission locks epoch -> users(operator) -> the operator's bindings ->
    users(delegate) -> the parent binding; the 0014 grant locks users(delegate) ->
    the (delegate, platform_auditor) index range -> inserts. Both orders finish.
    """
    with mysql_world() as db:
        parent, _ = _delegated(db)
        op_id, gen = _claimed(db)
    # The new binding sorts after the delegate's access_admin in every iam_bindings
    # index, so its insert lands in the gap just before the operator's rows: the
    # gap a range lock on the operator's bindings would hold (random ids hit it
    # about half the time).
    monkeypatch.setattr(iam_models, "uuid4", lambda: "ffffffff-ffff-4fff-bfff-ffffffffffff")

    locked, go = Event(), Event()
    original = bindings._lock_subject

    def paused(db, subject_type, subject_id):
        found = original(db, subject_type, subject_id)
        locked.set()
        assert go.wait(5)
        return found

    with ThreadPoolExecutor(max_workers=2) as pool:
        if first == "platform_grant":
            # The grant holds users(delegate) before the admission reaches it: the
            # admission waits there, holding the operator's bindings, while the
            # grant reads and inserts its own index range.
            monkeypatch.setattr(bindings, "_lock_subject", paused)
            granted = pool.submit(_platform_grant, mysql_world)
            assert locked.wait(5)
            admitted = pool.submit(_admit, mysql_world, op_id, gen, "sdk:during-platform-grant")
            with pytest.raises(TimeoutError):
                admitted.result(timeout=0.3)
            go.set()
        else:
            # The admission holds the whole chain, uncommitted, when the grant starts.
            started = Event()
            with mysql_world() as executor:
                control.admit_effect(executor, op_id, gen, "sdk:before-platform-grant")
                started.set()
                granted = pool.submit(_platform_grant, mysql_world)
                with pytest.raises(TimeoutError):
                    granted.result(timeout=0.3)
                executor.commit()
            admitted = None
        grant_id = granted.result(timeout=10)
        outcome = admitted.result(timeout=10) if admitted is not None else "admitted"

    assert outcome == "admitted", outcome
    with mysql_world() as db:
        b = db.get(IamBinding, grant_id)
        assert b is not None and b.role == "platform_auditor" and b.subject_id == "delegate"
        assert db.query(EffectAdmission).count() == 1
        # The platform binding never reaches the engines family.
        assert policy.navigation(db, db.get(User, "delegate"))["permissions"]
        assert parent["id"] in {g.id for g in policy.grants(db, "delegate")}
