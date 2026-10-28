"""
Spec 0007 CA10 / section 4.6: local idle cooldown and standby wakeup.

A local dedicated service whose applied profile opted in (`idle_cooldown`) goes to
standby after `idle_timeout_seconds` without work, and comes back when work waits
for it. Both are ordinary operations by the admin who opted in. Never a Modal or
paid engine, never the generic worker, never a feature the admin stopped, never a
second operation for the same applied state, and never a retry storm after the
actor lost the permission.
"""

from datetime import datetime, timedelta
from typing import NamedTuple
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.config import get_settings
from shared.database import Base
from shared.engine_control import service
from shared.engine_control.models import (
    ControlAdmission,
    ControlResource,
    EngineOperation,
    RuntimeProfile,
)
from shared.models import Engine, FeatureRoute, JobDispatch
from workers.engine_control import idle_notes, idle_policy, idle_signals

HOST = "h1"
AUDIO = f"local:{HOST}:service:worker-audio"
GENERIC = f"local:{HOST}:service:worker"
NOW = datetime(2026, 10, 27, 12, 0, 0)
ACTOR = "admin-who-opted-in"


class OptIn(NamedTuple):  # the shape of shared.engine_control.idle_opt_in.OptIn
    actor: str
    revision: int


@pytest.fixture(autouse=True)
def redis(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(idle_notes, "_redis", lambda: client)
    monkeypatch.setattr(idle_signals, "_redis", lambda: client)
    return client


@pytest.fixture
def Session(monkeypatch):
    bind = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind)
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)
    with factory() as db:
        db.add(Engine(id="local-1", slug="local-1", display_name="Local", adapter_type="local",
                      config={"features": {}}, deployments={}, version=0))
        db.commit()
    yield factory
    bind.dispose()


def _profile(**overrides):
    return dict(
        dict(provider_settings={"host_id": HOST}, idle_cooldown=True, idle_timeout_seconds=60,
             min_ready_replicas=0, desired_replicas=1, max_replicas=1, model_profile_id="whisper-local",
             binding={"workers": 1, "executions_per_worker": 1}, adapter_version=1, schema_version=1,
             warmup_mode="on_start", warm_until=None, memory_mb=None),
        **overrides,
    )


IDLE_COOLDOWN = ("cooldown", "idle_policy", ACTOR, 1)


def _applied(Session, engine_id="local-1", feature="transcription", applied_at=NOW - timedelta(hours=1),
             mode="running", last=None, **profile):
    """`last` is the operation that changed the applied state: (type, trigger, actor, revision).
    A standby defaults to this opt-in's own idle cooldown."""
    last = last or (IDLE_COOLDOWN if mode == "standby" else None)
    with Session() as db:
        p = RuntimeProfile(engine_id=engine_id, feature=feature, revision=1, profile=_profile(**profile),
                           applied_at=applied_at)
        db.add(p)
        db.flush()
        applied = {"profile_id": p.id, "feature_modes": {feature: mode}}
        if last:
            kind, trigger, actor, revision = last
            op = EngineOperation(engine_id=engine_id, actor_id=actor, plan_id="plan", idempotency_key=f"last-{kind}",
                                 request_hash="hash", state="succeeded", deadline=NOW, finished_at=applied_at)
            db.add(op)
            db.flush()
            applied.update(type=kind, trigger=trigger, revision=revision, operation_id=op.id)
        db.add(ControlResource(key=AUDIO, owner_engine_id=engine_id, applied=applied))
        db.add(ControlResource(key=GENERIC, owner_engine_id=engine_id, applied={}))
        db.commit()


def _ticket(Session, key=AUDIO, released_at=NOW - timedelta(hours=1)):
    with Session() as db:
        db.add(ControlAdmission(resource_key=key, holder="task:x", created_at=NOW - timedelta(hours=2),
                                released_at=released_at))
        db.commit()


def _decide(Session, depth=0, feature="transcription"):
    with Session() as db:
        engine = db.get(Engine, "local-1")
        profile = idle_policy.applied_profile(db, "local-1", feature)
        return idle_policy.decide(db, engine, feature, profile, depth, NOW, ACTOR)


class TestCooldown:
    def test_an_idle_opted_in_service_cools_down(self, Session):
        _applied(Session)
        _ticket(Session)

        assert _decide(Session) == "cooldown"

    def test_not_opted_in_stays_up(self, Session):
        _applied(Session, idle_cooldown=False)

        assert _decide(Session) is None

    def test_a_warm_minimum_is_never_cooled(self, Session):
        _applied(Session, min_ready_replicas=1)

        assert _decide(Session) is None

    @pytest.mark.parametrize("depth", [1, None], ids=["queued", "queue-unknown"])
    def test_work_on_the_queue_or_an_unreadable_queue_is_not_idle(self, Session, depth):
        _applied(Session)

        assert _decide(Session, depth=depth) is None

    def test_an_open_ticket_is_work_in_flight(self, Session):
        _applied(Session)
        _ticket(Session, released_at=None)

        assert _decide(Session) is None

    def test_the_timeout_counts_from_the_last_finished_work(self, Session):
        _applied(Session)
        _ticket(Session, released_at=NOW - timedelta(seconds=59))

        assert _decide(Session) is None

    def test_the_timeout_counts_from_the_last_apply_too(self, Session):
        """A service just woken up gets its full idle window."""
        _applied(Session, applied_at=NOW - timedelta(seconds=59))

        assert _decide(Session) is None

    def test_work_on_the_generic_worker_does_not_keep_audio_up(self, Session):
        """The generic worker's key also counts document conversions."""
        _applied(Session)
        _ticket(Session, key=GENERIC, released_at=None)

        assert _decide(Session) == "cooldown"

    def test_a_dispatch_placed_on_the_engine_is_work(self, Session):
        _applied(Session)
        with Session() as db:
            db.add(JobDispatch(feature="transcription", subject_type="job", subject_id="j1",
                               state="running", engine_id="local-1"))
            db.commit()

        assert _decide(Session) is None

    def test_an_operation_on_the_resource_blocks_any_decision(self, Session):
        _applied(Session)
        with Session() as db:
            db.get(ControlResource, GENERIC).operation_id = "op-1"
            db.commit()

        assert _decide(Session) is None


def _backlog(Session, engine_ids=("local-1",), not_before=None, state="waiting"):
    with Session() as db:
        db.add(FeatureRoute(feature="transcription", state="active",
                            steps=[{"position": 1, "engine_ids": list(engine_ids)}]))
        db.add(JobDispatch(feature="transcription", subject_type="job", subject_id="j1", state=state,
                           not_before=not_before))
        db.commit()


class TestBacklog:
    """Spec 0007 §4.6: an item waiting for this engine/feature is work, never idle."""

    @pytest.mark.parametrize("not_before", [None, NOW + timedelta(minutes=5)], ids=["due", "in-backoff"])
    def test_a_waiting_item_keeps_a_running_service_up(self, Session, not_before):
        _applied(Session)
        _backlog(Session, not_before=not_before)

        assert _decide(Session) is None, "else a cooldown here and a wakeup on the next tick, forever"

    def test_an_item_still_being_probed_keeps_it_up_too(self, Session):
        """It becomes `waiting` seconds later: cooling down now would only reload the model."""
        _applied(Session)
        _backlog(Session, state="probing")

        assert _decide(Session) is None

    def test_an_item_in_a_dispatcher_backoff_does_not_wake_it_yet(self, Session):
        _applied(Session, mode="standby")
        _backlog(Session, not_before=NOW + timedelta(minutes=5))

        assert _decide(Session, depth=0) is None

    def test_an_item_whose_backoff_ended_wakes_it(self, Session):
        _applied(Session, mode="standby")
        _backlog(Session, not_before=NOW)

        assert _decide(Session, depth=0) == "start"


class TestWakeup:
    def test_queued_work_wakes_a_standby_service(self, Session):
        _applied(Session, mode="standby")

        assert _decide(Session, depth=3) == "start"

    def test_no_demand_keeps_standby(self, Session):
        """Standby is the desired state: nothing restarts it without work."""
        _applied(Session, mode="standby")

        assert _decide(Session, depth=0) is None

    def test_a_routed_backlog_for_this_engine_wakes_it(self, Session):
        _applied(Session, mode="standby")
        with Session() as db:
            db.add(FeatureRoute(feature="transcription", state="active",
                                steps=[{"position": 1, "engine_ids": ["local-1"]}]))
            db.add(JobDispatch(feature="transcription", subject_type="job", subject_id="j1", state="waiting"))
            db.commit()

        assert _decide(Session, depth=0) == "start"

    def test_a_backlog_routed_elsewhere_does_not(self, Session):
        _applied(Session, mode="standby")
        with Session() as db:
            db.add(FeatureRoute(feature="transcription", state="active",
                                steps=[{"position": 1, "engine_ids": ["modal-1"]}]))
            db.add(JobDispatch(feature="transcription", subject_type="job", subject_id="j1", state="waiting"))
            db.commit()

        assert _decide(Session, depth=0) is None

    def test_another_feature_writing_the_shared_row_does_not_block_the_wakeup(self, Session):
        """Vision's operations also write the generic worker's row: only the dedicated row tells
        who changed this feature last (spec 0007, 4.6)."""
        _applied(Session, mode="standby")
        with Session() as db:
            db.get(ControlResource, GENERIC).applied = {
                "type": "drain_stop", "trigger": None, "operation_id": "vision-op",
                "feature_modes": {"vision": "stopped"}}
            db.commit()

        assert _decide(Session, depth=3) == "start"

    def test_a_drain_stop_by_another_admin_after_the_idle_cooldown_is_not_undone(self, Session):
        _applied(Session, mode="stopped", last=("drain_stop", None, "admin-b", 1))

        assert _decide(Session, depth=3) is None

    @pytest.mark.parametrize("actor", ["admin-b", ACTOR], ids=["another-admin", "the-opt-in-admin-by-hand"])
    def test_a_manual_cooldown_is_not_undone(self, Session, actor):
        _applied(Session, mode="standby", last=("cooldown", None, actor, 1))

        assert _decide(Session, depth=3) is None

    def test_an_idle_cooldown_by_another_opt_in_is_not_ours(self, Session):
        _applied(Session, mode="standby", last=("cooldown", "idle_policy", "admin-b", 1))

        assert _decide(Session, depth=3) is None

    def test_an_idle_cooldown_of_another_revision_is_not_ours(self, Session):
        _applied(Session, mode="standby", last=("cooldown", "idle_policy", ACTOR, 2))

        assert _decide(Session, depth=3) is None

    def test_a_standby_with_no_recorded_operation_is_left_to_the_admin(self, Session):
        """Applied before this version recorded who changed it."""
        with Session() as db:
            db.add(RuntimeProfile(engine_id="local-1", feature="transcription", revision=1, profile=_profile(),
                                  applied_at=NOW - timedelta(hours=1)))
            db.add(ControlResource(key=AUDIO, owner_engine_id="local-1",
                                   applied={"feature_modes": {"transcription": "standby"}}))
            db.commit()

        assert _decide(Session, depth=3) is None

    def test_a_stopped_feature_is_left_to_the_admin(self, Session):
        _applied(Session, mode="stopped")

        assert _decide(Session, depth=3) is None


class TestTick:
    def test_only_local_engines_are_ever_considered(self, Session):
        """A Modal engine with a forged opt-in is not even read."""
        with Session() as db:
            db.add(Engine(id="modal-1", slug="modal-1", display_name="Modal", adapter_type="modal",
                          config={"features": {}}, deployments={}, version=0))
            db.add(RuntimeProfile(engine_id="modal-1", feature="transcription", revision=1,
                                  profile=_profile(), applied_at=NOW - timedelta(hours=1)))
            db.commit()
        seen = []
        real = idle_policy.decide

        def spy(db, engine, *args):
            seen.append(engine.adapter_type)
            return real(db, engine, *args)

        idle_policy.decide, original = spy, real
        try:
            idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 1), now=NOW)
        finally:
            idle_policy.decide = original

        assert set(seen) <= {"local"}

    def test_enqueue_refuses_a_non_local_engine(self, Session):
        with Session() as db:
            db.add(Engine(id="modal-1", slug="modal-1", display_name="Modal", adapter_type="modal",
                          config={"features": {}}, deployments={}, version=0))
            db.commit()

        assert idle_policy._enqueue(Session, "modal-1", "transcription", "cooldown", ACTOR) is None

    def test_without_an_opt_in_actor_nothing_is_created(self, Session, monkeypatch):
        _applied(Session)
        _ticket(Session)
        called = []
        monkeypatch.setattr(idle_policy, "_enqueue", lambda *a: called.append(a))

        assert idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: None, now=NOW) == []
        assert called == []

    def test_an_opt_in_for_another_revision_is_no_opt_in(self, Session, monkeypatch):
        """The applied revision is what the admin opted in, or the policy keeps out."""
        _applied(Session)
        _ticket(Session)
        called = []
        monkeypatch.setattr(idle_policy, "_enqueue", lambda *a: called.append(a))

        assert idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 2),
                                now=NOW) == []
        assert called == []

    def test_the_plan_names_the_opted_in_revision(self, Session, monkeypatch):
        _applied(Session)
        _ticket(Session)
        plans = []

        def create_plan(db, engine, request, actor):
            plans.append(request.profile_revision)
            raise service.ControlError("HOST_AGENT_NOT_READY", 503)

        monkeypatch.setattr(service, "create_plan", create_plan)

        idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 1), now=NOW)

        assert plans == [1]

    def test_a_revision_applied_after_the_look_is_left_to_the_next_tick(self, Session, monkeypatch):
        _applied(Session)
        monkeypatch.setattr(service, "create_plan", lambda *a: pytest.fail("planned a stale state"))

        assert idle_policy._enqueue(Session, "local-1", "transcription", "cooldown", ACTOR, NOW, 0, 2) is None

    def test_a_state_reapplied_after_the_look_is_left_to_the_next_tick(self, Session, monkeypatch):
        """Same revision, newer applied_at (an admin's drain_stop or start in between)."""
        _applied(Session)
        monkeypatch.setattr(service, "create_plan", lambda *a: pytest.fail("planned a stale state"))

        assert idle_policy._enqueue(Session, "local-1", "transcription", "start", ACTOR, NOW, 0, 1,
                                    NOW - timedelta(days=1)) is None

    def test_a_database_error_on_one_engine_does_not_skip_the_others(self, Session, monkeypatch):
        _applied(Session)
        with Session() as db:
            db.add(RuntimeProfile(engine_id="local-1", feature="vision", revision=1, profile=_profile(),
                                  applied_at=NOW - timedelta(hours=1)))
            db.commit()
        monkeypatch.setattr(idle_policy, "decide", lambda *a, **k: "cooldown")
        called = []

        def enqueue(session_factory, engine_id, feature, *rest):
            called.append(feature)
            if len(called) == 1:
                raise RuntimeError("lock wait timeout")
            return "op"

        monkeypatch.setattr(idle_policy, "_enqueue", enqueue)
        done = idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 1), now=NOW)

        assert len(called) == 2 and len(done) == 1

    def test_a_refused_plan_is_retried_next_tick_not_raised(self, Session, monkeypatch):
        _applied(Session)
        _ticket(Session)

        def busy(*args):
            raise service.ControlError("RESOURCE_BUSY")

        monkeypatch.setattr(idle_policy, "_enqueue", busy)

        assert idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 1), now=NOW) == []

    def test_the_decision_becomes_an_operation_by_the_opt_in_actor(self, Session, monkeypatch):
        _applied(Session)
        _ticket(Session)
        calls = []

        def enqueue(session_factory, engine_id, feature, action, actor, *rest):
            calls.append((engine_id, feature, action, actor))
            return "op-1"

        monkeypatch.setattr(idle_policy, "_enqueue", enqueue)

        done = idle_policy.tick(Session, depth_of=lambda q: 0, opt_in_of=lambda db, e, f: OptIn(ACTOR, 1), now=NOW)

        assert done == [("local-1", "transcription", "cooldown", "op-1")]
        assert calls == [("local-1", "transcription", "cooldown", ACTOR)]
