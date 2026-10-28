"""Opt-in of the local idle cooldown and the actor of its automatic operations (spec 0007 §4.6).

The idle policy has no identity of its own: its cooldown/start run as the admin who applied the
revision with idle_cooldown=true. So the opt-in is refused unless that admin may plan, cool down
and start the engine, and only local transcription/vision qualify; the automatic operations carry
their trigger in the plan, the operation view and the audit.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.access.models import EngineAttributes
from shared.database import Base
from shared.engine_control import idle_opt_in, service
from shared.engine_control.contracts import PlanRequest, TriggeredPlanRequest
from shared.engine_control.models import EngineOperation, OperationPlan, RuntimeProfile
from shared.models import AdminAudit, Engine
from tests.test_engine_control import prepared, profile  # noqa: F401
from tests.test_engine_control import world as control_world  # noqa: F401  (fixture)
from tests.test_execution_profiles import constraints, grant
from tests.test_execution_profiles import world as iam_world  # noqa: F401  (fixture)

LOCAL = SimpleNamespace(id="l", adapter_type="local")
REMOTE = SimpleNamespace(id="m", adapter_type="modal")


# --- which engines and features qualify (no IAM involved) ------------------------------------

@pytest.mark.parametrize("engine,feature", [(REMOTE, "transcription"), (LOCAL, "document_conversion")])
def test_opt_in_off_a_local_transcription_or_vision_engine_is_refused(engine, feature, monkeypatch):
    monkeypatch.setattr("shared.access.policy.enabled", lambda: False)
    with pytest.raises(service.ControlError) as e:
        idle_opt_in.require(None, engine, feature, {"idle_cooldown": True}, "admin", [])
    assert (e.value.code, e.value.status) == ("IDLE_COOLDOWN_NOT_SUPPORTED", 422)


@pytest.mark.parametrize("profile_", [{}, {"idle_cooldown": False}, None])
def test_without_the_opt_in_nothing_is_checked(profile_):
    idle_opt_in.require(None, REMOTE, "document_conversion", profile_, "anyone", [])


@pytest.mark.parametrize("feature", ["transcription", "vision"])
def test_local_transcription_and_vision_qualify_with_iam_off(feature, monkeypatch):
    monkeypatch.setattr("shared.access.policy.enabled", lambda: False)
    idle_opt_in.require(None, LOCAL, feature, {"idle_cooldown": True}, "admin", [])


# --- the actor must be able to run the automatic operations (real IAM) -----------------------

def _local_engine(db):
    db.add(Engine(id="engine-l", slug="engine-l", display_name="Local", adapter_type="local",
                  config={"features": {}}, deployments={}, version=0, limit_usd=10, min_remaining_usd=0))
    db.add(EngineAttributes(engine_id="engine-l", environment="development"))
    db.commit()
    return db.get(Engine, "engine-l")


def _scope():
    # an envelope on the local engine (any model; the default CPU/memory/replica limits)
    return constraints(engine_ids=["engine-l"], adapters=["local"], model_ids=None)


RUNTIME = {"idle_cooldown": True, "max_replicas": 1, "memory_mb": 512, "binding": {"workers": 1, "cpu": 1}}


def test_an_operator_who_can_plan_cool_down_and_start_may_opt_in(iam_world):  # noqa: F811
    with iam_world() as db:
        engine = _local_engine(db)
        grant(db, scope=_scope())
        idle_opt_in.require(db, engine, "transcription", RUNTIME, "operator", [])


@pytest.mark.parametrize("permissions", [
    ["engine_operations.plan", "engine_operations.execute.cooldown"],  # no start
    ["engine_operations.plan", "engine_operations.execute.start"],  # no cooldown
    ["engine_operations.execute.cooldown", "engine_operations.execute.start"],  # no plan
])
def test_an_actor_missing_one_of_the_three_permissions_cannot_opt_in(iam_world, permissions):  # noqa: F811
    with iam_world() as db:
        engine = _local_engine(db)
        grant(db, scope=_scope(), permissions=permissions)
        with pytest.raises(service.ControlError) as e:
            idle_opt_in.require(db, engine, "transcription", RUNTIME, "operator", [])
        assert (e.value.code, e.value.status) == ("IDLE_COOLDOWN_PERMISSION_REQUIRED", 403)


def test_an_actor_without_any_grant_cannot_opt_in(iam_world):  # noqa: F811
    with iam_world() as db:
        engine = _local_engine(db)
        with pytest.raises(service.ControlError) as e:
            idle_opt_in.require(db, engine, "transcription", RUNTIME, "outsider", [])
        assert e.value.code == "IDLE_COOLDOWN_PERMISSION_REQUIRED"


def test_a_grant_scoped_to_the_source_profile_counts_when_the_profile_is_passed(iam_world):  # noqa: F811
    with iam_world() as db:
        engine = _local_engine(db)
        source = SimpleNamespace(id="profile-1", adapter_type="local", feature="transcription",
                                 environment="development")
        grant(db, scope=constraints(engine_ids=["engine-l"], adapters=["local"], model_ids=None,
                                    profile_ids=["profile-1"]))
        idle_opt_in.require(db, engine, "transcription", RUNTIME, "operator", [], profile=source)


def test_a_grant_on_another_engine_does_not_count(iam_world):  # noqa: F811
    with iam_world() as db:
        engine = _local_engine(db)
        grant(db)  # scoped to engine-a only
        with pytest.raises(service.ControlError) as e:
            idle_opt_in.require(db, engine, "transcription", RUNTIME, "operator", [])
        assert e.value.code == "IDLE_COOLDOWN_PERMISSION_REQUIRED"


# --- the actor the automatic operations run as -------------------------------------------------

@pytest.fixture
def db():
    sql = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(sql)
    with sessionmaker(bind=sql)() as session:
        yield session
    sql.dispose()


T0 = datetime(2026, 10, 27, 12, 0)


def _revision(db, revision, idle, applied_at=T0):
    row = RuntimeProfile(engine_id="l", feature="transcription", revision=revision,
                         profile={"idle_cooldown": idle}, applied_at=applied_at)
    db.add(row)
    db.flush()
    return row


def _operation(db, revision_row, type_, actor, state="succeeded", finished=T0):
    plan = OperationPlan(engine_id="l", actor_id=actor, engine_version=0, profile_id=revision_row.id,
                         body={"type": type_, "feature": "transcription"}, hash="h", expires_at=T0)
    db.add(plan)
    db.flush()
    db.add(EngineOperation(engine_id="l", actor_id=actor, plan_id=plan.id, idempotency_key=plan.id,
                           request_hash="r", state=state, deadline=T0, finished_at=finished))
    db.flush()


def test_the_actor_is_whoever_applied_the_opted_in_revision(db):
    rev = _revision(db, 1, idle=True)
    _operation(db, rev, "apply_profile", "admin-a")
    # a later cooldown by someone else does not take over the policy
    _operation(db, rev, "cooldown", "admin-b", finished=T0 + timedelta(minutes=5))
    assert idle_opt_in.opt_in(db, "l", "transcription") == ("admin-a", 1)


def test_the_latest_apply_of_the_revision_wins(db):
    rev = _revision(db, 1, idle=True)
    _operation(db, rev, "apply_profile", "admin-a")
    _operation(db, rev, "apply_profile", "admin-b", finished=T0 + timedelta(minutes=5))
    assert idle_opt_in.opt_in(db, "l", "transcription") == ("admin-b", 1)


def test_no_actor_without_the_opt_in_or_without_a_successful_apply(db):
    off = _revision(db, 1, idle=False)
    _operation(db, off, "apply_profile", "admin-a")
    assert idle_opt_in.opt_in(db, "l", "transcription") is None
    on = _revision(db, 2, idle=True, applied_at=T0 + timedelta(minutes=1))
    _operation(db, on, "apply_profile", "admin-a", state="failed")
    _operation(db, on, "start", "admin-a", finished=T0 + timedelta(minutes=2))  # applied, not by apply_profile
    assert idle_opt_in.opt_in(db, "l", "transcription") is None


def test_no_actor_before_any_revision_was_applied(db):
    db.add(RuntimeProfile(engine_id="l", feature="transcription", revision=1, profile={"idle_cooldown": True}))
    db.flush()
    assert idle_opt_in.opt_in(db, "l", "transcription") is None


# --- saving / applying the opt-in goes through the check; the trigger is visible --------------

def test_saving_the_opt_in_on_a_remote_engine_is_refused(control_world):  # noqa: F811
    with control_world() as s:
        with pytest.raises(service.ControlError) as e:
            service.save_profile(s, s.get(Engine, "e"), "transcription", dict(profile(), idle_cooldown=True), 0, "admin")
        assert e.value.code == "IDLE_COOLDOWN_NOT_SUPPORTED"


def test_an_automatic_operation_carries_its_trigger_to_the_view_and_the_audit(control_world):  # noqa: F811
    p = prepared(control_world)
    with control_world() as s:
        e = s.get(Engine, "e")
        plan = service.create_plan(s, e, TriggeredPlanRequest(type="scale", engine_version=e.version,
                                                              profile_revision=1, max_usd="0.1",
                                                              trigger="idle_policy"), "admin")
        assert plan["trigger"] == "idle_policy"
        op = service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        assert op["trigger"] == "idle_policy"
        audit = s.query(AdminAudit).filter_by(action="engine.operation_created").one()
        assert audit.after["trigger"] == "idle_policy"
    assert p  # the human plan of `prepared` has no trigger
    with control_world() as s:
        human = s.get(OperationPlan, p["plan_id"])
        assert "trigger" not in human.body


def test_an_unknown_trigger_is_refused():
    with pytest.raises(ValueError):
        TriggeredPlanRequest(type="cooldown", engine_version=0, trigger="cron")


def test_a_client_cannot_claim_to_be_the_idle_policy():
    # the HTTP route takes PlanRequest (closed): a forged trigger is a 422, not a false audit
    with pytest.raises(ValueError):
        PlanRequest(type="cooldown", engine_version=0, trigger="idle_policy")


def test_the_opt_in_is_checked_again_when_its_apply_profile_is_planned(control_world, monkeypatch):  # noqa: F811
    from shared.engine_control import registry

    prepared(control_world)
    monkeypatch.setitem(registry.descriptor("test-vm"), "actions", ["scale", "drain_stop", "apply_profile"])
    with control_world() as s:
        row = s.query(RuntimeProfile).filter_by(engine_id="e").one()
        row.profile = dict(row.profile, idle_cooldown=True)  # as if saved where it qualified
        s.commit()
        e = s.get(Engine, "e")
        with pytest.raises(service.ControlError) as err:
            service.create_plan(s, e, PlanRequest(type="apply_profile", engine_version=e.version,
                                                  profile_revision=1, max_usd="0.1"), "admin")
        assert err.value.code == "IDLE_COOLDOWN_NOT_SUPPORTED"
