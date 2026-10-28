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


def _operation(db, revision_row, type_, actor, state="succeeded", finished=T0, engine_id="l"):
    plan = OperationPlan(engine_id=engine_id, actor_id=actor, engine_version=0, profile_id=revision_row.id,
                         body={"type": type_, "feature": "transcription"}, hash="h", expires_at=T0)
    db.add(plan)
    db.flush()
    db.add(EngineOperation(engine_id=engine_id, actor_id=actor, plan_id=plan.id, idempotency_key=plan.id,
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


def test_reapplying_an_old_opted_in_revision_by_another_type_does_not_revive_it(db):
    # X (opt-in) applied by A; Y (no opt-in) applied later; B, who could only start, starts X
    x = _revision(db, 1, idle=True, applied_at=T0)
    _operation(db, x, "apply_profile", "admin-a", finished=T0)
    y = _revision(db, 2, idle=False, applied_at=T0 + timedelta(minutes=1))
    _operation(db, y, "apply_profile", "admin-a", finished=T0 + timedelta(minutes=1))
    x.applied_at = T0 + timedelta(minutes=2)
    _operation(db, x, "start", "operator-b", finished=T0 + timedelta(minutes=2))
    assert idle_opt_in.opt_in(db, "l", "transcription") is None


def test_a_newer_desired_revision_not_applied_does_not_change_the_opt_in(db):
    rev = _revision(db, 1, idle=True)
    _operation(db, rev, "apply_profile", "admin-a")
    db.add(RuntimeProfile(engine_id="l", feature="transcription", revision=2, profile={"idle_cooldown": False}))
    db.flush()
    assert idle_opt_in.opt_in(db, "l", "transcription") == ("admin-a", 1)


def test_tests_and_reconciles_of_the_feature_do_not_break_the_chain(db):
    rev = _revision(db, 1, idle=True)
    _operation(db, rev, "apply_profile", "admin-a")
    other = _revision(db, 2, idle=False, applied_at=None)
    _operation(db, other, "test", "admin-b", finished=T0 + timedelta(minutes=3))
    assert idle_opt_in.opt_in(db, "l", "transcription") == ("admin-a", 1)


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


def _local_opt_in(control_world, monkeypatch, actor="admin"):
    """The control-test engine as a local transcription engine whose applied revision 1 opted
    in through `actor`'s apply_profile (the test adapter stands in for the local one)."""
    from shared.engine_control import registry
    from shared.models import User

    d = dict(registry.descriptor("test-vm"), type="local", features=["transcription", "vision"],
             actions=["scale", "drain_stop", "cooldown", "start", "apply_profile"])
    monkeypatch.setitem(registry._registry, ("local", 1), (d, registry._registry[("test-vm", 1)][1]))
    prepared(control_world)
    with control_world() as s:
        s.get(Engine, "e").adapter_type = "local"
        s.add(User(id=actor, username=actor, email=actor + "@example.test", hashed_password="x",
                   is_admin=True, is_active=True))
        rev = s.query(RuntimeProfile).filter_by(engine_id="e", revision=1).one()
        rev.profile = dict(rev.profile, idle_cooldown=True)
        rev.applied_at = datetime.utcnow()
        _operation(s, rev, "apply_profile", actor, finished=datetime.utcnow(), engine_id="e")
        s.commit()


def _cooldown(s, actor="admin", revision=1, feature="transcription"):
    e = s.get(Engine, "e")
    return service.create_plan(s, e, TriggeredPlanRequest(
        type="cooldown", feature=feature, engine_version=e.version, profile_revision=revision,
        max_usd="0.1", trigger="idle_policy"), actor)


def test_an_automatic_cooldown_carries_its_trigger_to_the_view_and_the_audit(control_world, monkeypatch):  # noqa: F811
    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        plan = _cooldown(s)
        assert plan["trigger"] == "idle_policy"
        op = service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        assert op["trigger"] == "idle_policy"
        audit = s.query(AdminAudit).filter_by(action="engine.operation_created").one()
        assert audit.after["trigger"] == "idle_policy"


def test_an_automatic_plan_must_match_the_opt_in_it_claims(control_world, monkeypatch):  # noqa: F811
    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        rev1 = s.query(RuntimeProfile).filter_by(engine_id="e", revision=1).one()
        s.add(RuntimeProfile(engine_id="e", feature="transcription", revision=2, profile=rev1.profile))
        s.add(RuntimeProfile(engine_id="e", feature="vision", revision=1, profile=rev1.profile))
        s.commit()  # desired revisions exist, but only transcription revision 1 opted in (applied)
        for kwargs in ({"actor": "someone-else"}, {"revision": 2}, {"feature": "vision"}):
            with pytest.raises(service.ControlError) as e:
                _cooldown(s, **kwargs)
            assert e.value.code == "IDLE_POLICY_NOT_OPTED_IN", kwargs
        assert s.query(OperationPlan).filter(OperationPlan.body["trigger"].as_string() == "idle_policy").count() == 0


def test_with_iam_off_a_deactivated_opt_in_admin_no_longer_lends_their_identity(control_world, monkeypatch):  # noqa: F811
    from shared.models import User

    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        s.get(User, "admin").is_active = False
        s.commit()
        with pytest.raises(service.ControlError) as e:
            _cooldown(s)
        assert (e.value.code, e.value.status) == ("ACCESS_REVOKED", 403)


def test_with_iam_off_a_demotion_between_plan_and_enqueue_is_refused_at_enqueue(control_world, monkeypatch):  # noqa: F811
    from shared.models import User

    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        plan = _cooldown(s)
        s.get(User, "admin").is_admin = False
        s.commit()
        with pytest.raises(service.ControlError) as e:
            service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        assert e.value.code == "ACCESS_REVOKED"
        assert s.query(EngineOperation).filter_by(idempotency_key="idle:1").count() == 0


def test_an_automatic_plan_off_a_local_engine_is_refused(control_world, monkeypatch):  # noqa: F811
    from shared.engine_control import registry

    monkeypatch.setitem(registry.descriptor("test-vm"), "actions", ["scale", "drain_stop", "cooldown"])
    prepared(control_world)
    with control_world() as s:
        with pytest.raises(service.ControlError) as e:
            _cooldown(s)
        assert e.value.code == "IDLE_COOLDOWN_NOT_SUPPORTED"


@pytest.mark.parametrize("type_,trigger", [("scale", "idle_policy"), ("deploy", "wakeup"),
                                            ("start", "idle_policy"), ("cooldown", "wakeup")])
def test_the_borrowed_identity_only_cools_down_or_starts(type_, trigger):
    with pytest.raises(ValueError):
        TriggeredPlanRequest(type=type_, engine_version=0, trigger=trigger)


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


# --- the IAM-off rule equals authorize(force=True) -------------------------------------------
# With IAM off the automatic actor is checked by hand (authorize(force=True) needs the access
# schema, which an installation with IAM off may lack). Same matrix, both paths, same outcome:
# if either rule changes alone, this breaks.

ACTORS = {
    "admin": dict(is_admin=True, is_active=True),
    "inactive-admin": dict(is_admin=True, is_active=False),
    "demoted": dict(is_admin=False, is_active=True),
    "plain": dict(is_admin=False, is_active=True),
    "inactive-plain": dict(is_admin=False, is_active=False),
    "root": dict(is_admin=False, is_active=True, root_slot=1),
    "listed": dict(is_admin=False, is_active=True),  # admin by ADMIN_USER_IDS
}


def _outcome(call):
    try:
        call()
        return "pass"
    except service.ControlError as exc:
        return (exc.code, exc.status)


@pytest.mark.parametrize("actor", [*ACTORS, "missing"])
def test_the_iam_off_rule_matches_authorize_force(db, monkeypatch, actor):
    from shared.access import policy
    from shared.access.models import AuthorizationEpoch
    from shared.config import get_settings
    from shared.models import User

    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    monkeypatch.setattr(get_settings(), "admin_user_ids", "listed")
    db.add(AuthorizationEpoch(id=1, version=0))
    for uid, fields in ACTORS.items():
        db.add(User(id=uid, username=uid, email=uid + "@example.test", hashed_password="x", **fields))
    db.commit()
    permission = "engine_operations.execute.cooldown"

    manual = _outcome(lambda: idle_opt_in._authorize_actor(db, actor))
    forced = _outcome(lambda: policy.authorize(db, actor, permission, force=True))
    assert manual == forced, actor


def test_with_iam_on_a_profile_scoped_operator_runs_the_automatic_cooldown_end_to_end(iam_world, monkeypatch):  # noqa: F811
    """The operator's grant is scoped to the source profile (profile_ids): opt-in, apply and the
    automatic cooldown (plan and enqueue) all pass with the same grant."""
    from shared.access import contracts as C, service as access
    from shared.engine_control import registry
    from shared.engine_control.models import ControlResource
    from tests.test_execution_profiles import ADAPTER, draft, settings

    base = registry.descriptor(ADAPTER)
    d = dict(base, type="local", actions=["scale", "drain_stop", "cooldown", "start", "apply_profile"],
             model_profiles=[dict(m, adapters=["local"]) for m in base["model_profiles"]])
    monkeypatch.setitem(registry._registry, ("local", 1), (d, registry._registry[(ADAPTER, 1)][1]))
    with iam_world() as db:
        db.get(Engine, "engine-a").adapter_type = "local"
        db.commit()
        p = draft(db, adapter_type="local", settings=dict(settings(), idle_cooldown=True))
        p = access.publish(db, p["id"], C.Publish(version=p["version"], revision_id=p["revisions"][0]["id"]),
                           "bootstrap")
        scope = constraints(adapters=["local"], profile_ids=[p["id"]])
        grant(db, scope=scope)  # engine_operator: plan, cooldown, start, apply_profile...
        grant(db, role="runtime_configurator", scope=scope)  # ...and binding the profile
        access.bind(db, db.get(Engine, "engine-a"),
                    C.Bind(version=0, feature="transcription", revision_id=p["latest_published_revision_id"]),
                    "operator")
        e = db.get(Engine, "engine-a")
        plan = service.create_plan(db, e, PlanRequest(type="apply_profile", engine_version=e.version,
                                                      profile_revision=1, max_usd="0.10"), "operator")
        op = service.enqueue(db, plan["plan_id"], plan["plan_hash"], "apply", "operator", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.publish_applied(db, op["operation_id"], gen, {})
        service.finish(db, op["operation_id"], gen, "succeeded", {}, safe=True)
        assert idle_opt_in.opt_in(db, "engine-a", "transcription") == ("operator", 1)
        e = db.get(Engine, "engine-a")
        auto = service.create_plan(db, e, TriggeredPlanRequest(
            type="cooldown", engine_version=e.version, profile_revision=1, max_usd="0.10",
            trigger="idle_policy"), "operator")
        done = service.enqueue(db, auto["plan_id"], auto["plan_hash"], "idle:1", "operator", True)
        assert done["trigger"] == "idle_policy"
        assert db.query(ControlResource).filter(ControlResource.operation_id.isnot(None)).count() == 1


def test_a_published_but_unfinished_application_of_another_revision_breaks_the_chain(db):
    # Y was published (applied_at) but its operation never finished succeeded (needs_attention)
    x = _revision(db, 1, idle=True, applied_at=T0)
    _operation(db, x, "apply_profile", "admin-a", finished=T0)
    y = _revision(db, 2, idle=False, applied_at=T0 + timedelta(minutes=1))
    _operation(db, y, "apply_profile", "admin-a", state="needs_attention", finished=None)
    x.applied_at = T0 + timedelta(minutes=2)
    _operation(db, x, "start", "operator-b", finished=T0 + timedelta(minutes=2))
    assert idle_opt_in.opt_in(db, "l", "transcription") is None


def test_an_application_in_the_same_second_fails_closed(db):
    x = _revision(db, 1, idle=True, applied_at=T0)
    _operation(db, x, "apply_profile", "admin-a", finished=T0)
    _revision(db, 2, idle=False, applied_at=T0)  # same instant: cannot tell which came last
    x.applied_at = T0 + timedelta(seconds=1)
    db.flush()
    assert idle_opt_in.opt_in(db, "l", "transcription") is None


# --- the rule holds at every point from plan to effect (§4.6) --------------------------------

def _another_admin_applies_the_revision(s):
    """B re-applies revision 1 by apply_profile: the opt-in now belongs to B, not to A."""
    from shared.models import User

    s.add(User(id="admin-b", username="admin-b", email="b@example.test", hashed_password="x",
               is_admin=True, is_active=True))
    rev = s.query(RuntimeProfile).filter_by(engine_id="e", revision=1).one()
    _operation(s, rev, "apply_profile", "admin-b", finished=datetime.utcnow() + timedelta(seconds=5),
               engine_id="e")
    s.commit()


def test_enqueue_refuses_a_plan_whose_opt_in_changed_owner(control_world, monkeypatch):  # noqa: F811
    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        plan = _cooldown(s)
        _another_admin_applies_the_revision(s)
        with pytest.raises(service.ControlError) as e:
            service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        assert e.value.code == "IDLE_POLICY_NOT_OPTED_IN"


def test_claim_ends_without_effect_an_operation_whose_opt_in_changed_owner(control_world, monkeypatch):  # noqa: F811
    from shared.engine_control.models import ControlResource

    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        plan = _cooldown(s)
        op = service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        _another_admin_applies_the_revision(s)
        assert service.claim(s, op["operation_id"], "one") is None
        row = s.get(EngineOperation, op["operation_id"])
        assert (row.state, row.error["code"], row.effect_started) == ("failed", "IDLE_POLICY_NOT_OPTED_IN", False)
        assert s.query(ControlResource).filter(ControlResource.operation_id.isnot(None)).count() == 0


def test_with_iam_off_a_deactivation_after_claim_stops_the_effect(control_world, monkeypatch):  # noqa: F811
    from shared.models import User

    _local_opt_in(control_world, monkeypatch)
    with control_world() as s:
        plan = _cooldown(s)
        op = service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        gen = service.claim(s, op["operation_id"], "one")
        s.get(User, "admin").is_active = False
        s.commit()
        with pytest.raises(service.ControlError) as e:
            service.event(s, op["operation_id"], gen, "scaling", effect=True)  # the effect gate
        assert e.value.code == "ACCESS_REVOKED"
        s.rollback()
        assert s.get(EngineOperation, op["operation_id"]).effect_started is False


def test_human_operations_are_not_concerned_by_the_opt_in_rule(control_world):  # noqa: F811
    p = prepared(control_world)
    with control_world() as s:
        op = service.enqueue(s, p["plan_id"], p["plan_hash"], "human", "admin", True)
        gen = service.claim(s, op["operation_id"], "one")
        assert gen is not None
        service.event(s, op["operation_id"], gen, "scaling", effect=True)


# --- recovery of an automatic operation whose effect was admitted (§4.6, §4.8) ---------------

def _automatic_op_lost_mid_effect(control_world, monkeypatch, proof):
    """An automatic cooldown that admitted its effect, lost its executor (needs_attention), and
    whose opt-in actor was then deactivated; admin-b asks for the recovery."""
    from shared.engine_control import registry
    from shared.models import User
    from tests.test_engine_control import VMAdapter

    calls = []

    class Recoverable(VMAdapter):
        def apply(self, plan, ctx):
            calls.append("apply")
            raise AssertionError("an admitted effect is never replayed")

        def observe(self, engine, feature, p, ctx):
            calls.append("observe")
            return {"replicas_alive": 0, "ready_replicas": 0}

        def reconcile(self, op, observed):
            return proof

    _local_opt_in(control_world, monkeypatch)
    monkeypatch.setitem(registry._registry, ("local", 1), (registry._registry[("local", 1)][0], Recoverable))
    with control_world() as s:
        s.add(User(id="admin-b", username="admin-b", email="b@example.test", hashed_password="x",
                   is_admin=True, is_active=True))
        plan = _cooldown(s)
        op = service.enqueue(s, plan["plan_id"], plan["plan_hash"], "idle:1", "admin", True)
        gen = service.claim(s, op["operation_id"], "one")
        service.event(s, op["operation_id"], gen, "cooling", effect=True)
        service.finish(s, op["operation_id"], gen, "needs_attention", safe=False)
        row = s.get(EngineOperation, op["operation_id"])
        row.handles = dict(row.handles or {}, executor_exited=True)
        s.get(User, "admin").is_active = False
        s.commit()
        service.request_recovery(s, op["operation_id"], "admin-b")
    return op["operation_id"], calls


def _locked(control_world):
    from shared.engine_control.models import ControlResource

    with control_world() as s:
        return s.query(ControlResource).filter(ControlResource.operation_id.isnot(None)).count()


def test_a_recovery_reconciles_and_unlocks_only_with_proof(control_world, monkeypatch):  # noqa: F811
    from workers.engine_control.runner import run

    op_id, calls = _automatic_op_lost_mid_effect(
        control_world, monkeypatch, {"desired_applied": True, "safe_to_unlock": True})
    run(op_id, control_world)
    with control_world() as s:
        assert s.get(EngineOperation, op_id).state == "succeeded"
    assert calls == ["observe"] and _locked(control_world) == 0


def test_a_recovery_without_proof_stays_locked(control_world, monkeypatch):  # noqa: F811
    from workers.engine_control.runner import run

    op_id, calls = _automatic_op_lost_mid_effect(
        control_world, monkeypatch, {"desired_applied": False, "safe_to_unlock": False})
    run(op_id, control_world)
    with control_world() as s:
        assert s.get(EngineOperation, op_id).state == "needs_attention"
    assert calls == ["observe"] and _locked(control_world) == 1


def test_a_recovery_proving_the_effect_never_happened_ends_failed_without_replay(control_world, monkeypatch):  # noqa: F811
    from workers.engine_control.runner import run

    op_id, calls = _automatic_op_lost_mid_effect(
        control_world, monkeypatch, {"desired_applied": False, "safe_to_unlock": True})
    run(op_id, control_world)
    with control_world() as s:
        row = s.get(EngineOperation, op_id)
        assert (row.state, row.error["code"]) == ("failed", "AUTOMATIC_EFFECT_NOT_APPLIED")
        shown = service.operation_view(row)["error"]  # explained by the catalog, like other codes
        assert shown["human_message"] and "next_steps" in shown
    assert calls == ["observe"] and _locked(control_world) == 0


def test_a_human_recovery_proving_nothing_applied_is_unchanged(control_world):  # noqa: F811
    # (c) only automatic operations end failed on that proof; a human one stays needs_attention
    from shared.engine_control import registry
    from tests.test_engine_control import VMAdapter
    from workers.engine_control.runner import run

    class Unapplied(VMAdapter):
        def observe(self, engine, feature, p, ctx):
            return {}

        def reconcile(self, op, observed):
            return {"desired_applied": False, "safe_to_unlock": True}

    registry.register("test-vm", registry.descriptor("test-vm"), Unapplied)
    p = prepared(control_world)
    with control_world() as s:
        op = service.enqueue(s, p["plan_id"], p["plan_hash"], "human", "admin", True)
        gen = service.claim(s, op["operation_id"], "one")
        service.event(s, op["operation_id"], gen, "applying", effect=True)
        service.finish(s, op["operation_id"], gen, "needs_attention", safe=False)
        s.get(EngineOperation, op["operation_id"]).handles = {"executor_exited": True}
        s.commit()
        service.request_recovery(s, op["operation_id"])
    run(op["operation_id"], control_world)
    with control_world() as s:
        assert s.get(EngineOperation, op["operation_id"]).state == "needs_attention"
