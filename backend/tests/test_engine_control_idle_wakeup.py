"""
Spec 0007, section 4.6: a failed wakeup retries with backoff, at most five times,
then says so on the opt-in operation. A lost permission is not retried, nor is a
failed cooldown, and a failure from recovery waits its backoff like any other.

Split from test_engine_control_idle_policy.py; it shares that module's fixtures.
"""

from datetime import timedelta

import pytest

from shared.engine_control import service
from shared.engine_control.models import ControlResource, EngineOperation, OperationEvent, OperationOutbox, OperationPlan
from tests.test_engine_control_idle_policy import AUDIO, ACTOR, NOW, Session, _applied, redis  # noqa: F401
from workers.engine_control import idle_notes, idle_policy


class TestWakeupRetry:
    """A failed wakeup retries with backoff, at most 5 times, then says so; a clock, no sleep."""

    @pytest.fixture
    def standby(self, Session, monkeypatch):
        _applied(Session, mode="standby")
        created = Created()
        with Session() as db:  # the apply that turned the opt-in on
            applied = idle_policy.applied_profile(db, "local-1", "transcription")
            db.add(OperationPlan(id="opt-in-plan", engine_id="local-1", actor_id=ACTOR, engine_version=0,
                                 profile_id=applied.id, body={"type": "apply_profile", "feature": "transcription"},
                                 hash="h", expires_at=NOW))
            created.opt_in = _operation(db, "opt-in", state="succeeded", finished_at=NOW - timedelta(hours=2),
                                        plan_id="opt-in-plan").id
            row = db.get(ControlResource, AUDIO)  # the reference its publish left, kept by the cooldown
            row.applied = dict(row.applied, opt_in_operation_id=created.opt_in, opt_in_actor=ACTOR)
            db.commit()

        def create_plan(db, engine, request, actor):
            return {"plan_id": "plan", "plan_hash": "hash"}

        def enqueue(db, plan_id, plan_hash, key, actor):
            op = _operation(db, key)
            created.append(key)
            return {"operation_id": op.id}

        monkeypatch.setattr(service, "create_plan", create_plan)
        monkeypatch.setattr(service, "enqueue", enqueue)
        return created

    def _base(self, Session):
        with Session() as db:
            return idle_policy.idempotency_key(
                "start", "local-1", "transcription", idle_policy.applied_profile(db, "local-1", "transcription")
            )

    def _attempt(self, Session, number, state, ended=NOW, code="HOST_AGENT_NOT_READY"):
        with Session() as db:
            op = _operation(db, f"{self._base(Session)}:{number}", state=state, finished_at=ended,
                            error={"code": code} if state in ("failed", "cancelled") else None)
            return op.id

    def _wake(self, Session, at, waiting=4):
        return idle_policy._enqueue(Session, "local-1", "transcription", "start", ACTOR, at, waiting)

    def test_the_first_wakeup_is_attempt_one(self, Session, standby):
        assert self._wake(Session, NOW)
        assert standby == [f"{self._base(Session)}:1"]

    @pytest.mark.parametrize("state", ["queued", "running", "succeeded", "needs_attention"])
    def test_an_attempt_that_did_not_fail_is_not_repeated(self, Session, standby, state):
        op_id = self._attempt(Session, 1, state)

        assert self._wake(Session, NOW + timedelta(hours=1)) == op_id
        assert standby == []

    @pytest.mark.parametrize("number,minutes", [(1, 1), (2, 5), (3, 15), (4, 15)])
    def test_the_next_attempt_waits_its_backoff(self, Session, standby, number, minutes):
        for n in range(1, number + 1):
            self._attempt(Session, n, "failed")

        assert self._wake(Session, NOW + timedelta(minutes=minutes) - timedelta(seconds=1)) is None
        assert standby == []
        assert self._wake(Session, NOW + timedelta(minutes=minutes))
        assert standby == [f"{self._base(Session)}:{number + 1}"]

    def test_an_attempt_an_admin_cancelled_is_not_redone_as_the_opt_in_admin(self, Session, standby):
        """Only the API cancels (an admin): not transient, it ends the cycle."""
        op_id = self._attempt(Session, 1, "running")
        with Session() as db:
            service.request_cancel(db, op_id, "admin-b")
            _finish(db, op_id, "cancelled")

        assert self._wake(Session, NOW + timedelta(days=1)) is None
        assert standby == []

    def test_a_cancel_survives_a_recovery_that_then_fails(self, Session, standby):
        """The recovery clears the operation's cancel flag; the cancel event stays."""
        op_id = self._attempt(Session, 1, "running")
        with Session() as db:
            service.request_cancel(db, op_id, "admin-b")
            _finish(db, op_id, "needs_attention", handles={"executor_exited": True})
            db.add(OperationOutbox(operation_id=op_id, published_at=NOW))
            db.commit()
            service.request_recovery(db, op_id, "admin-c")
            assert db.get(EngineOperation, op_id).cancel_requested is False
            _finish(db, op_id, "failed", error={"code": "AUTOMATIC_EFFECT_NOT_APPLIED"})

        assert self._wake(Session, NOW + timedelta(days=1)) is None
        assert standby == []

    def test_without_a_cancel_the_same_recovered_failure_is_retried(self, Session, standby):
        op_id = self._attempt(Session, 1, "running")
        with Session() as db:
            _finish(db, op_id, "failed", error={"code": "AUTOMATIC_EFFECT_NOT_APPLIED"})

        assert self._wake(Session, NOW + timedelta(days=1))
        assert standby == [f"{self._base(Session)}:2"]

    def test_after_giving_up_later_ticks_skip_the_state_at_once(self, Session, standby, redis):
        for n in range(1, 6):
            self._attempt(Session, n, "failed")

        assert self._wake(Session, NOW + timedelta(days=1)) is None
        assert redis.keys("engine_idle:refused:*"), "no note lookup and row lock every 15 s"

    def test_after_five_attempts_it_gives_up_once_and_says_why(self, Session, standby):
        for n in range(1, 6):
            last = self._attempt(Session, n, "failed")

        for _ in range(3):
            assert self._wake(Session, NOW + timedelta(days=1), waiting=7) is None
        assert standby == []

        with Session() as db:
            events = db.query(OperationEvent).filter_by(type=idle_notes.WAKEUP_GAVE_UP).all()
        assert len(events) == 1
        assert events[0].operation_id == standby.opt_in != last, "on the opt-in operation, where the admin looks"
        assert "7 trabalhos esperando" in events[0].payload["message"]
        assert events[0].payload["author"] == idle_notes.SYSTEM_AUTHOR
        assert set(events[0].payload) == {"message", "waiting", "state", "author"}

    @pytest.mark.parametrize("code", ["ACCESS_DENIED", "ACCESS_REVOKED", "IDLE_POLICY_NOT_OPTED_IN"])
    def test_a_lost_permission_is_not_retried(self, Session, standby, code):
        """Refused by the server's own authorization: at the plan, at claim or before the effect."""
        self._attempt(Session, 1, "failed", code=code)

        assert self._wake(Session, NOW + timedelta(days=1)) is None
        assert standby == []
        with Session() as db:
            noted = db.query(OperationEvent).filter_by(operation_id=standby.opt_in, type=idle_notes.REFUSED_EVENT)
            assert noted.count() == (0 if code == "IDLE_POLICY_NOT_OPTED_IN" else 1), "a moved opt-in is no loss"

    def test_the_same_code_from_the_host_agent_is_an_ordinary_failure(self, Session, standby, redis):
        """The host's call was refused, not the actor: retried with backoff, no note, no refusal key."""
        with Session() as db:
            _operation(db, f"{self._base(Session)}:1", state="failed", finished_at=NOW,
                       error={"code": "ACCESS_REVOKED", "source": "host"})

        assert self._wake(Session, NOW + timedelta(minutes=1))
        assert standby == [f"{self._base(Session)}:2"]
        with Session() as db:
            assert db.query(OperationEvent).filter_by(type=idle_notes.REFUSED_EVENT).count() == 0
        assert not redis.keys("engine_idle:refused:*")

    def test_a_failure_from_recovery_waits_its_backoff_like_any_other(self, Session, standby):
        """A recovery that found the effect missing ends failed; nothing retries it at once."""
        op_id = self._attempt(Session, 1, "failed", code="RECOVERY_STATE_UNCONFIRMED")
        with Session() as db:
            db.get(EngineOperation, op_id).handles = {"recovery_mode": True}
            db.commit()

        assert self._wake(Session, NOW + timedelta(seconds=59)) is None
        assert standby == []
        assert self._wake(Session, NOW + timedelta(minutes=1))
        assert standby == [f"{self._base(Session)}:2"]

    def test_a_new_applied_state_starts_over(self, Session, standby):
        for n in range(1, 6):
            self._attempt(Session, n, "failed")
        with Session() as db:
            p = idle_policy.applied_profile(db, "local-1", "transcription")
            p.applied_at = NOW
            db.commit()

        assert self._wake(Session, NOW + timedelta(minutes=1))
        assert standby == [f"{self._base(Session)}:1"]

    def test_a_failed_cooldown_is_never_retried(self, Session, standby):
        _applied_running = idle_policy.applied_profile
        with Session() as db:
            key = idle_policy.idempotency_key("cooldown", "local-1", "transcription",
                                              _applied_running(db, "local-1", "transcription"))
            op = _operation(db, key, state="failed", finished_at=NOW, error={"code": "DRAIN_TIMEOUT"})
            op_id = op.id

        assert idle_policy._enqueue(Session, "local-1", "transcription", "cooldown", ACTOR,
                                    NOW + timedelta(days=1)) == op_id
        assert standby == []


def _finish(db, op_id, state, error=None, handles=None):
    op = db.get(EngineOperation, op_id)
    op.state, op.finished_at, op.error = state, NOW, error
    if handles:
        op.handles = handles
    db.commit()


class Created(list):
    """Keys of the operations the policy created; `.opt_in` is the opt-in operation's id."""


def _operation(db, key, state="queued", finished_at=None, error=None, plan_id="plan"):
    op = EngineOperation(engine_id="local-1", actor_id=ACTOR, plan_id=plan_id, idempotency_key=key,
                         request_hash="hash", state=state, deadline=NOW + timedelta(hours=2),
                         created_at=(finished_at or NOW) - timedelta(minutes=1), finished_at=finished_at,
                         error=error)
    db.add(op)
    db.commit()
    return op
