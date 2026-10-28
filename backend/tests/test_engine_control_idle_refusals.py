"""
Spec 0007, section 4.6: the idle policy's operations through the real plan path, and
what happens when the opt-in's admin lost the permission: one refusal, one note on the
opt-in operation signed by the system, and no retry storm, with or without Redis.

Split from test_engine_control_idle_policy.py; it shares that module's fixtures.
"""

from datetime import datetime, timedelta

import pytest

from shared.config import get_settings
from shared.engine_control import service
from shared.engine_control.applied_state import applied_state
from shared.engine_control.models import (
    ControlHost,
    ControlResource,
    EngineOperation,
    OperationEvent,
    OperationPlan,
    RuntimeProfile,
)
from shared.models import Engine, User
from tests.test_engine_control_idle_policy import (  # noqa: F401  (fixtures)
    ACTOR,
    AUDIO,
    HOST,
    NOW,
    Session,
    _profile,
    redis,
)
from workers.engine_control import idle_notes, idle_policy


class TestRealOperation:
    """The plan and the operation come from the same service path as the admin's button."""

    @pytest.fixture
    def local(self, Session, monkeypatch):
        monkeypatch.setattr(get_settings(), "audio_transcriber_provider", "faster-whisper")
        with Session() as db:
            db.add(ControlHost(id=HOST, seen_at=datetime.utcnow(), inventory={
                "services": ["worker", "worker-audio", "worker-vision"], "manifest_hash": "m", "gpu_uuids": []}))
            db.commit()
            raw = {k: v for k, v in _profile().items() if k not in ("warm_until", "memory_mb", "idle_cooldown")}
            saved = service.save_profile(db, db.get(Engine, "local-1"), "transcription", raw, 0, "admin")
            p = db.query(RuntimeProfile).filter_by(engine_id="local-1", revision=saved["revision"]).one()
            p.profile = dict(p.profile, idle_cooldown=True)
            p.applied_at = datetime.utcnow() - timedelta(hours=1)
            # The apply that turned the opt-in on, by its admin: where a refusal is noted.
            db.add(User(id=ACTOR, username=ACTOR, email="opt-in@example.test", hashed_password="x",
                        is_admin=True, is_active=True))  # an automatic plan re-checks its actor
            db.add(OperationPlan(id="opt-in-plan", engine_id="local-1", actor_id=ACTOR, engine_version=0,
                                 profile_id=p.id,
                                 body={"type": "apply_profile", "feature": "transcription",
                                       "profile_revision": saved["revision"]},
                                 hash="h", expires_at=datetime.utcnow()))
            db.add(EngineOperation(id="opt-in-op", engine_id="local-1", actor_id=ACTOR, plan_id="opt-in-plan",
                                   idempotency_key="opt-in", request_hash="h", state="succeeded",
                                   deadline=datetime.utcnow(), finished_at=datetime.utcnow() - timedelta(hours=1)))
            for row in db.query(ControlResource).filter_by(owner_engine_id="local-1"):  # as its publish did
                row.applied = applied_state(row.applied, p, {"type": "apply_profile", "feature": "transcription"},
                                            "opt-in-op", ACTOR)
            db.commit()
        return Session

    def test_the_same_applied_state_never_gets_a_second_operation(self, local):
        first = idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)
        second = idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        assert first and first == second
        with local() as db:
            op = db.get(EngineOperation, first)
            assert op.actor_id == ACTOR
            assert db.query(EngineOperation).filter(EngineOperation.idempotency_key.like("idle:%")).count() == 1
            assert db.query(OperationPlan).filter(OperationPlan.id != "opt-in-plan").count() == 1, \
                "a found operation needs no new plan"

    def test_the_applied_state_records_the_operation_that_changed_it(self, local):
        op_id = idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)
        with local() as db:
            generation = service.claim(db, op_id, "runner")
            service.publish_applied(db, op_id, generation, {"replicas_alive": 0})
            applied = db.get(ControlResource, AUDIO).applied

        assert applied["operation_id"] == op_id
        assert applied["type"] == "cooldown" and applied["feature_modes"]["transcription"] == "standby"
        assert applied["trigger"] == "idle_policy"
        with local() as db:
            body = db.get(OperationPlan, db.get(EngineOperation, op_id).plan_id).body
        assert body["trigger"] == "idle_policy", "the plan says it is automatic, for the audit"

    def test_an_opt_in_that_moved_is_not_remembered_as_a_lost_permission(self, local):
        """Real create_plan: an actor that is no longer the opt-in's is refused, nothing noted, asked again."""
        for _ in range(2):
            with pytest.raises(service.ControlError) as refused:
                idle_policy._enqueue(local, "local-1", "transcription", "cooldown", "someone-else")
            assert refused.value.code == "IDLE_POLICY_NOT_OPTED_IN"

        with local() as db:
            assert db.query(OperationEvent).filter_by(type=idle_notes.REFUSED_EVENT).count() == 0

    def test_a_revoked_actor_is_asked_once_noted_once_and_left_alone(self, local, monkeypatch):
        """403: one create_plan, one visible event, and no create_plan on the following ticks."""
        asked = []

        def denied(*args, **kwargs):
            asked.append(args)
            raise service.ControlError("ACCESS_DENIED", 403)

        monkeypatch.setattr(service, "create_plan", denied)
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)
        for _ in range(3):
            assert idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR) is None
            assert idle_policy._enqueue(local, "local-1", "transcription", "start", ACTOR) is None

        assert len(asked) == 1
        with local() as db:
            events = db.query(OperationEvent).filter_by(operation_id="opt-in-op",
                                                        type=idle_notes.REFUSED_EVENT).all()
        assert len(events) == 1
        assert "não tem mais permissão" in events[0].payload["message"]
        # Written by the system with the admin already revoked, never in the admin's name.
        assert events[0].payload["author"] == idle_notes.SYSTEM_AUTHOR != ACTOR
        assert events[0].payload["code"] == "ACCESS_DENIED"
        assert set(events[0].payload) == {"message", "action", "code", "state", "author"}

    def test_the_note_finds_the_opt_in_after_many_automatic_operations(self, local, monkeypatch):
        """No window over the actor's recent operations: its own cooldowns/starts never hide the opt-in."""
        with local() as db:
            applied = idle_policy.applied_profile(db, "local-1", "transcription")
            db.add(OperationPlan(id="auto-plan", engine_id="local-1", actor_id=ACTOR, engine_version=0,
                                 profile_id=applied.id,  # as a real automatic plan: same revision
                                 body={"type": "cooldown", "feature": "transcription", "trigger": "idle_policy"},
                                 hash="h", expires_at=datetime.utcnow()))
            for n in range(60):
                db.add(EngineOperation(engine_id="local-1", actor_id=ACTOR, plan_id="auto-plan",
                                       idempotency_key=f"auto-{n}", request_hash="h", state="succeeded",
                                       deadline=datetime.utcnow(), finished_at=datetime.utcnow()))
            db.commit()
        monkeypatch.setattr(service, "create_plan",
                            lambda *a, **k: (_ for _ in ()).throw(service.ControlError("ACCESS_DENIED", 403)))
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        with local() as db:
            assert db.query(OperationEvent).filter_by(operation_id="opt-in-op",
                                                      type=idle_notes.REFUSED_EVENT).count() == 1

    def test_a_refused_actor_that_is_not_the_opt_in_s_is_never_noted_on_it(self, local, monkeypatch):
        monkeypatch.setattr(service, "create_plan",
                            lambda *a, **k: (_ for _ in ()).throw(service.ControlError("ACCESS_DENIED", 403)))
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", "someone-else")

        with local() as db:
            assert db.query(OperationEvent).filter_by(type=idle_notes.REFUSED_EVENT).count() == 0

    def test_a_new_applied_state_is_asked_again(self, local, monkeypatch):
        asked = []

        def denied(*args, **kwargs):
            asked.append(args)
            raise service.ControlError("ACCESS_DENIED", 403)

        monkeypatch.setattr(service, "create_plan", denied)
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)
        with local() as db:
            db.query(RuntimeProfile).filter_by(engine_id="local-1").one().applied_at = datetime.utcnow()
            db.commit()
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        assert len(asked) == 2
        with local() as db:  # a new state is noted again
            events = db.query(OperationEvent).filter_by(operation_id="opt-in-op", type=idle_notes.REFUSED_EVENT)
            assert events.count() == 2

    def test_the_key_only_suppresses_it_never_authorizes(self, local, monkeypatch, redis):
        """A lost key costs one more attempt, refused again by the database, and no new event."""
        asked = []

        def denied(*args, **kwargs):
            asked.append(args)
            raise service.ControlError("ACCESS_DENIED", 403)

        monkeypatch.setattr(service, "create_plan", denied)
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)
        redis.flushall()
        with pytest.raises(service.ControlError):
            idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        assert len(asked) == 2
        with local() as db:
            events = db.query(OperationEvent).filter_by(operation_id="opt-in-op", type=idle_notes.REFUSED_EVENT)
            assert events.count() == 1, "the reborn key must not repeat the event"
        keys = redis.keys("engine_idle:refused:*")
        assert len(keys) == 1 and 0 < redis.ttl(keys[0]) <= idle_notes.REFUSAL_TTL_SECONDS

    def test_without_redis_the_database_still_refuses(self, local, monkeypatch):
        def down():
            raise ConnectionError("redis down")

        monkeypatch.setattr(idle_notes, "_redis", down)
        monkeypatch.setattr(service, "create_plan",
                            lambda *a, **k: (_ for _ in ()).throw(service.ControlError("ACCESS_DENIED", 403)))

        for _ in range(2):
            with pytest.raises(service.ControlError):
                idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        with local() as db:  # the note does not depend on Redis: deduplicated by the database
            assert db.query(OperationEvent).filter_by(operation_id="opt-in-op",
                                                      type=idle_notes.REFUSED_EVENT).count() == 1

    def test_a_permission_lost_after_the_enqueue_is_noted_once_and_suppressed(self, local, redis):
        """Refused at claim, before the effect or by the host agent: the cooldown failed ACCESS_REVOKED."""
        with local() as db:
            profile = idle_policy.applied_profile(db, "local-1", "transcription")
            key = idle_policy.idempotency_key("cooldown", "local-1", "transcription", profile)
            db.add(EngineOperation(id="refused-later", engine_id="local-1", actor_id=ACTOR, plan_id="opt-in-plan",
                                   idempotency_key=key, request_hash="h", state="failed", deadline=NOW,
                                   finished_at=NOW, error={"code": "ACCESS_REVOKED"}))
            db.commit()

        for _ in range(3):
            assert idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR) in ("refused-later", None)

        with local() as db:
            events = db.query(OperationEvent).filter_by(operation_id="opt-in-op", type=idle_notes.REFUSED_EVENT).all()
        assert len(events) == 1 and events[0].payload["code"] == "ACCESS_REVOKED"
        assert redis.keys("engine_idle:refused:*"), "later ticks stop asking"

    def test_a_transient_refusal_is_retried(self, local, monkeypatch):
        asked = []

        def busy(*args, **kwargs):
            asked.append(args)
            raise service.ControlError("HOST_AGENT_NOT_READY", 503)

        monkeypatch.setattr(service, "create_plan", busy)
        for _ in range(2):
            with pytest.raises(service.ControlError):
                idle_policy._enqueue(local, "local-1", "transcription", "cooldown", ACTOR)

        assert len(asked) == 2
