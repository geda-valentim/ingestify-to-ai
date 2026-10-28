"""
Spec 0007, section 4.6: the idle policy's Redis signals. One tick at a time, within a
time budget, and a standby service woken up by legacy media that reach it through the
default queue (refused ENGINE_NOT_RUNNING), which the policy cannot see on its queues.
None of them authorizes anything; without Redis the tick does nothing and the task
still requeues.
"""

import pytest
from celery import Celery
from celery.exceptions import Reject

from shared.config import get_settings
from shared.engine_control import admission
from shared.engine_control.service import ControlError
from shared.models import Engine
from tests.test_engine_control_idle_policy import (  # noqa: F401  (fixtures)
    ACTOR,
    NOW,
    OptIn,
    Session,
    _applied,
    _ticket,
    redis,
)
from workers.engine_control import idle_policy, idle_signals


def _tick(Session, **kwargs):
    kwargs.setdefault("depth_of", lambda q: 0)
    kwargs.setdefault("opt_in_of", lambda db, e, f: OptIn(ACTOR, 1))
    return idle_policy.tick(Session, now=NOW, **kwargs)


def _down():
    raise ConnectionError("redis down")


class TestOneTickAtATime:
    def test_a_tick_already_running_keeps_the_second_out(self, Session, redis, monkeypatch):
        _applied(Session)
        _ticket(Session)
        monkeypatch.setattr(idle_policy, "_enqueue", lambda *a: pytest.fail("two ticks acted"))
        redis.set(idle_signals.TICK_LOCK, "other", ex=idle_signals.TICK_LOCK_SECONDS)

        assert _tick(Session) == []

    def test_without_redis_there_is_no_tick(self, Session, monkeypatch):
        monkeypatch.setattr(idle_signals, "_redis", _down)

        assert _tick(lambda: pytest.fail("opened the database")) == []

    def test_the_lock_is_released_and_always_expires(self, Session, redis):
        _applied(Session)
        seen = []

        _tick(Session, depth_of=lambda q: seen.append(redis.ttl(idle_signals.TICK_LOCK)) or 0)

        assert 0 < seen[0] <= idle_signals.TICK_LOCK_SECONDS
        assert redis.get(idle_signals.TICK_LOCK) is None


class TestBudget:
    def test_a_slow_redis_ends_the_tick_without_acting(self, Session, monkeypatch):
        _applied(Session)
        _ticket(Session)
        monkeypatch.setattr(idle_policy, "_enqueue", lambda *a: pytest.fail("acted past the budget"))
        monkeypatch.setattr(idle_policy, "decide", lambda *a, **k: pytest.fail("kept reading past the budget"))
        now = [0.0]

        def slow(queue):
            now[0] += idle_policy.TICK_BUDGET_SECONDS  # each queue read takes the whole budget
            return 0

        assert _tick(Session, depth_of=slow, clock=lambda: now[0]) == []

    def test_the_queues_are_read_before_any_database_session(self, Session, redis):
        opened = []

        def factory():
            opened.append(True)
            return Session()

        _tick(factory, depth_of=lambda q: pytest.fail("read inside a session") if opened else 0)


class TestLegacyDemand:
    def test_a_refused_task_wakes_its_standby_service(self, Session, monkeypatch):
        _applied(Session, mode="standby")
        idle_signals.mark_demand("transcription", "local-1")
        planned = []
        monkeypatch.setattr(idle_policy, "_enqueue", lambda sf, e, f, action, *rest: planned.append(action) or "op")

        assert _tick(Session) == [("local-1", "transcription", "start", "op")]

    def test_a_task_without_an_engine_names_the_default_one(self, Session):
        idle_signals.mark_demand("vision")
        with Session() as db:
            db.add(Engine(id="e-2", slug="local", display_name="L", adapter_type="local", config={},
                          deployments={}, version=0))
            db.commit()
            assert idle_signals.demanded(db.get(Engine, "e-2"), idle_signals.demand("vision"))
            assert not idle_signals.demanded(db.get(Engine, "local-1"), idle_signals.demand("vision"))

    def test_the_hint_expires(self, redis):
        idle_signals.mark_demand("transcription", "local-1")

        assert 0 < redis.ttl(idle_signals.demand_key("transcription")) <= idle_signals.DEMAND_TTL_SECONDS

    @pytest.mark.parametrize("redis_up", [True, False])
    def test_the_managed_task_marks_it_and_still_requeues(self, redis, monkeypatch, redis_up):
        from workers.engine_control import task_base

        if not redis_up:
            monkeypatch.setattr(idle_signals, "_redis", _down)
        monkeypatch.setattr(get_settings(), "engine_control_enabled", True)

        def refused(feature, holder, engine_id=None):
            raise ControlError("ENGINE_NOT_RUNNING", 503)

        monkeypatch.setattr(admission, "acquire", refused)
        app = Celery("idle-signal-test")

        @app.task(base=task_base.ManagedTask, bind=True, name="workers.vision_tasks.describe")
        def describe(self):
            pytest.fail("ran on a standby service")

        describe.push_request(id="t-1", hostname="node@x")
        try:
            with pytest.raises(Reject):
                describe()
        finally:
            describe.pop_request()

        assert (redis.get(idle_signals.demand_key("vision")) == "local") is redis_up


def test_a_missing_opt_in_is_warned_once_per_applied_state(Session, caplog, monkeypatch):
    """Not every 15 s: an applied state from before the reference existed stays without one."""
    _applied(Session)
    _ticket(Session)
    monkeypatch.setattr(idle_policy, "_warned", {})

    for _ in range(3):
        _tick(Session, opt_in_of=lambda db, e, f: None)

    assert sum("has no opt-in" in r.getMessage() for r in caplog.records) == 1
