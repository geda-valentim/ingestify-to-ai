"""Automatic operations of the idle cooldown (spec 0007 §4.6): plans with a trigger, the rule
checked at every point from plan to effect, the IAM-off actor rule, and the recovery of an
automatic operation whose effect was admitted.
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
from tests._idle_world import (  # noqa: F401  (db is a fixture)
    LOCAL,
    REMOTE,
    RUNTIME,
    T0,
    _cooldown,
    _keys,
    _local_engine,
    _local_opt_in,
    _operation,
    _revision,
    _scope,
    db,
)


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
    from shared.access.models import ResourceScope
    from shared.engine_control.models import ControlResource
    from tests.test_execution_profiles import ADAPTER, draft, settings

    base = registry.descriptor(ADAPTER)
    d = dict(base, type="local", actions=["scale", "drain_stop", "cooldown", "start", "apply_profile"],
             model_profiles=[dict(m, adapters=["local"]) for m in base["model_profiles"]],
             provider_fields=base["provider_fields"] + [dict(name="host_id", type="text")])
    class LocalLayout(registry._registry[(ADAPTER, 1)][1]):
        def resource_keys(self, engine, feature, p):  # the local adapter's: a dedicated service row
            return _keys(SimpleNamespace(profile=p), feature)

    monkeypatch.setitem(registry._registry, ("local", 1), (d, LocalLayout))
    with iam_world() as db:
        db.get(Engine, "engine-a").adapter_type = "local"
        for key in _keys(SimpleNamespace(profile={"provider_settings": {"host_id": "h"}}), "transcription"):
            db.add(ControlResource(key=key, owner_engine_id="engine-a"))
            db.add(ResourceScope(key=key, consumers=[dict(engine_id="engine-a", feature="transcription")],
                                 qualified=True))
        db.commit()
        p = draft(db, adapter_type="local",
                  settings=dict(settings(provider_settings={"zone": "test-a", "host_id": "h"}), idle_cooldown=True))
        p = access.publish(db, p["id"], C.Publish(version=p["version"], revision_id=p["revisions"][0]["id"]),
                           "bootstrap")
        scope = constraints(adapters=["local"], profile_ids=[p["id"]], host_ids=["h"])
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
        assert db.query(ControlResource).filter(ControlResource.operation_id.isnot(None)).count() == 2  # both keys


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
