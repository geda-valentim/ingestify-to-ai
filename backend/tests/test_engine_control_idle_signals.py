"""
Spec 0007, section 4.6: the idle policy's Redis signals. A task refused ENGINE_NOT_RUNNING
(legacy media reach the generic worker through the default queue, which the policy does
not read) leaves a short-lived demand hint. Writing it never fails the task: without
Redis the task requeues exactly as before. Nothing authorizes on it.
"""

import pytest
from celery import Celery
from celery.exceptions import Reject

from shared.config import get_settings
from shared.engine_control import admission
from shared.engine_control.service import ControlError
from workers.engine_control import idle_signals, task_base


@pytest.fixture
def redis(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(idle_signals, "_redis", lambda: client)
    return client


def _down():
    raise ConnectionError("redis down")


def test_the_hint_names_the_engine_and_expires(redis):
    idle_signals.mark_demand("transcription", "local-1")
    idle_signals.mark_demand("vision")

    assert redis.get(idle_signals.demand_key("transcription")) == "local-1"
    assert redis.get(idle_signals.demand_key("vision")) == idle_signals.DEFAULT_ENGINE, "admission's default"
    assert 0 < redis.ttl(idle_signals.demand_key("transcription")) <= idle_signals.DEMAND_TTL_SECONDS


def test_without_redis_marking_never_raises(monkeypatch):
    monkeypatch.setattr(idle_signals, "_redis", _down)

    idle_signals.mark_demand("transcription")


def _refused_task(monkeypatch, code):
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)

    def refused(feature, holder, engine_id=None):
        raise ControlError(code, 503)

    monkeypatch.setattr(admission, "acquire", refused)
    app = Celery("idle-signal-test")

    @app.task(base=task_base.ManagedTask, bind=True, name="workers.vision_tasks.describe")
    def describe(self):
        pytest.fail("ran without admission")

    describe.push_request(id="t-1", hostname="node@x")
    try:
        with pytest.raises(Reject):
            describe()
    finally:
        describe.pop_request()


@pytest.mark.parametrize("redis_up", [True, False])
def test_a_task_refused_on_a_standby_service_marks_it_and_still_requeues(redis, monkeypatch, redis_up):
    if not redis_up:
        monkeypatch.setattr(idle_signals, "_redis", _down)

    _refused_task(monkeypatch, "ENGINE_NOT_RUNNING")

    assert (redis.get(idle_signals.demand_key("vision")) == "local") is redis_up


def test_a_maintenance_refusal_is_no_demand(redis, monkeypatch):
    _refused_task(monkeypatch, "ENGINE_MAINTENANCE")

    assert redis.get(idle_signals.demand_key("vision")) is None
