"""Fixtures and helpers of the idle cooldown tests (spec 0007 §4.6): local and remote engines,
revisions and the operations that applied them, and a local engine whose revision opted in."""
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
from shared.engine_control.applied_state import applied_state
from shared.engine_control.local_services import SERVICES
from shared.engine_control.models import ControlResource, EngineOperation, OperationPlan, RuntimeProfile
from shared.models import AdminAudit, Engine
from tests.test_engine_control import prepared, profile  # noqa: F401
from tests.test_engine_control import world as control_world  # noqa: F401  (fixture)
from tests.test_execution_profiles import constraints, grant
from tests.test_execution_profiles import world as iam_world  # noqa: F401  (fixture)


LOCAL = SimpleNamespace(id="l", adapter_type="local")


REMOTE = SimpleNamespace(id="m", adapter_type="modal")


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
                         profile={"idle_cooldown": idle, "provider_settings": {"host_id": "h"}},
                         applied_at=applied_at)
    db.add(row)
    db.flush()
    return row


def _keys(revision_row, feature):
    """The local adapter's layout: the feature's dedicated service and the shared generic worker."""
    host = ((revision_row.profile or {}).get("provider_settings") or {}).get("host_id", "h")
    return [f"local:{host}:service:{SERVICES[feature]}", f"local:{host}:service:worker"]


def _operation(db, revision_row, type_, actor, state="succeeded", finished=T0, engine_id="l", feature=None):
    """An operation on `revision_row`, published to its feature's resources as publish_applied
    does (not for test/reconcile), whatever its final state: call them in the order they ran."""
    feature = feature or revision_row.feature
    plan = OperationPlan(engine_id=engine_id, actor_id=actor, engine_version=0, profile_id=revision_row.id,
                         body={"type": type_, "feature": feature}, hash="h", expires_at=T0)
    db.add(plan)
    db.flush()
    op = EngineOperation(engine_id=engine_id, actor_id=actor, plan_id=plan.id, idempotency_key=plan.id,
                         request_hash="r", state=state, deadline=T0, finished_at=finished)
    db.add(op)
    db.flush()
    if type_ not in ("test", "reconcile"):
        for key in _keys(revision_row, feature):
            row = db.get(ControlResource, key) or ControlResource(key=key, owner_engine_id=engine_id)
            row.applied = applied_state(row.applied, revision_row, plan.body, op.id, actor)
            db.add(row)
        db.flush()


def _local_opt_in(control_world, monkeypatch, actor="admin"):
    """The control-test engine as a local transcription engine whose applied revision 1 opted
    in through `actor`'s apply_profile (the test adapter stands in for the local one)."""
    from shared.engine_control import registry
    from shared.models import User

    d = dict(registry.descriptor("test-vm"), type="local", features=["transcription", "vision"],
             actions=["scale", "drain_stop", "cooldown", "start", "apply_profile"])

    class LocalLayout(registry._registry[("test-vm", 1)][1]):
        """The test adapter with the local adapter's keys: a dedicated service per feature."""

        def validate(self, engine, feature, p, db):
            return p

        def resource_keys(self, engine, feature, p):
            return _keys(SimpleNamespace(profile=p), feature)

    monkeypatch.setitem(registry._registry, ("local", 1), (d, LocalLayout))
    prepared(control_world)
    with control_world() as s:
        s.get(Engine, "e").adapter_type = "local"
        s.add(User(id=actor, username=actor, email=actor + "@example.test", hashed_password="x",
                   is_admin=True, is_active=True))
        rev = s.query(RuntimeProfile).filter_by(engine_id="e", revision=1).one()
        rev.profile = dict(rev.profile, idle_cooldown=True, provider_settings={"host_id": "h"})
        rev.applied_at = datetime.utcnow()
        _operation(s, rev, "apply_profile", actor, finished=datetime.utcnow(), engine_id="e")
        s.commit()


def _cooldown(s, actor="admin", revision=1, feature="transcription"):
    e = s.get(Engine, "e")
    return service.create_plan(s, e, TriggeredPlanRequest(
        type="cooldown", feature=feature, engine_version=e.version, profile_revision=revision,
        max_usd="0.1", trigger="idle_policy"), actor)
