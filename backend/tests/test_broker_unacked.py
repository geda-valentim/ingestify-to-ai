"""
Unacknowledged broker messages: the visibility timeout and orphan recovery.

With acks_late, Celery's Redis broker keeps a running task's message in the
`unacked` hash and hands it to another worker once it is older than the
visibility timeout. Kombu's default of 1 h was below worker-audio's 3 h time limit,
so a long transcription was redelivered while still running. Raising the timeout
fixes that but makes a dead worker's message wait hours to come back, so a
monitoring check flags those orphans and admins can requeue them.
"""

import asyncio
import json
from types import SimpleNamespace

import fakeredis
import pytest
from fastapi import HTTPException

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import admin_routes
from shared import broker_unacked
from shared.config import Settings
from workers import monitoring
from workers.celery_app import celery_app

NOW = 1_800_000_000.0


def _deliver(client, tag, task_id, job_id, queue="ingestify-audio", delivered_at=NOW - 3600, exchange=""):
    payload = {
        "body": "e30=",
        "headers": {
            "id": task_id,
            "task": "workers.tasks.process_conversion",
            "retries": 0,
            "kwargsrepr": repr({"job_id": job_id, "source_type": "file"}),
        },
        "properties": {"delivery_tag": tag},
    }
    client.hset(broker_unacked.UNACKED_KEY, tag, json.dumps([payload, exchange, queue]))
    client.zadd(broker_unacked.UNACKED_INDEX_KEY, {tag: delivered_at})
    return payload


class FakeInspect:
    def __init__(self, active=None, reserved=None, scheduled=None):
        self._active, self._reserved, self._scheduled = active, reserved, scheduled

    def active(self):
        return self._active

    def reserved(self):
        return self._reserved

    def scheduled(self):
        return self._scheduled


# --- configuration -------------------------------------------------------------


def test_the_broker_outlasts_the_longest_task():
    options = celery_app.conf.broker_transport_options
    assert options["visibility_timeout"] == Settings(_env_file=None).celery_visibility_timeout_seconds
    assert options["visibility_timeout"] > 10800  # worker-audio's TRANSCRIPTION_TIMEOUT_SECONDS default


def test_a_visibility_timeout_shorter_than_a_task_refuses_to_start():
    with pytest.raises(ValueError, match="CELERY_VISIBILITY_TIMEOUT_SECONDS"):
        Settings(_env_file=None, conversion_timeout_seconds=10800, celery_visibility_timeout_seconds=3600)


# --- reading the unacked hash ----------------------------------------------------


def test_unacked_messages_are_listed_with_their_job_and_age():
    client = fakeredis.FakeRedis()
    _deliver(client, "tag-old", "task-1", "job-1", delivered_at=NOW - 7200)
    _deliver(client, "tag-new", "task-2", "job-2", queue="ingestify", delivered_at=NOW - 60)

    messages = broker_unacked.list_unacked(client, now=NOW)

    assert [(m.delivery_tag, m.task_id, m.job_id, m.queue, m.age_seconds) for m in messages] == [
        ("tag-old", "task-1", "job-1", "ingestify-audio", 7200.0),
        ("tag-new", "task-2", "job-2", "ingestify", 60.0),
    ]


def test_orphans_are_old_messages_no_live_worker_holds():
    client = fakeredis.FakeRedis()
    _deliver(client, "running", "task-live", "job-1", delivered_at=NOW - 7200)
    _deliver(client, "dead", "task-dead", "job-2", delivered_at=NOW - 7200)
    _deliver(client, "just-taken", "task-new", "job-3", delivered_at=NOW - 30)

    orphans = broker_unacked.find_orphans(
        broker_unacked.list_unacked(client, now=NOW), live_task_ids={"task-live"}, min_age_seconds=600
    )

    assert [m.delivery_tag for m in orphans] == ["dead"]


def test_live_task_ids_cover_running_prefetched_and_retry_scheduled_tasks():
    inspect = FakeInspect(
        active={"w1": [{"id": "a"}]},
        reserved={"w1": [{"id": "r"}], "w2": []},
        scheduled={"w2": [{"eta": "…", "request": {"id": "s"}}]},
    )
    assert broker_unacked.live_task_ids(inspect) == {"a", "r", "s"}


def test_no_worker_answering_means_nothing_can_be_judged():
    assert broker_unacked.live_task_ids(FakeInspect()) is None


# --- requeue -------------------------------------------------------------------------


def test_requeue_puts_the_message_next_in_its_queue():
    client = fakeredis.FakeRedis()
    payload = _deliver(client, "dead", "task-dead", "job-2")
    client.rpush("ingestify-audio", "older-waiting-message")

    assert broker_unacked.requeue(client, "dead") is True

    assert client.hget(broker_unacked.UNACKED_KEY, "dead") is None
    assert client.zscore(broker_unacked.UNACKED_INDEX_KEY, "dead") is None
    # consumers BRPOP from the right: the requeued message is taken next
    assert json.loads(client.lindex("ingestify-audio", -1)) == payload


def test_requeue_of_a_message_already_acked_does_nothing():
    client = fakeredis.FakeRedis()
    assert broker_unacked.requeue(client, "gone") is False
    assert client.llen("ingestify-audio") == 0


def test_requeue_refuses_a_non_default_exchange():
    client = fakeredis.FakeRedis()
    _deliver(client, "routed", "task-x", "job-x", exchange="custom")
    assert broker_unacked.requeue(client, "routed") is False
    assert client.hget(broker_unacked.UNACKED_KEY, "routed") is not None


# --- the monitoring check ---------------------------------------------------------------


@pytest.fixture
def check(monkeypatch):
    broker, cache = fakeredis.FakeRedis(), fakeredis.FakeRedis(decode_responses=True)
    inspect = {"value": FakeInspect(active={"w1": []})}
    monkeypatch.setattr(broker_unacked, "broker_client", lambda: broker)
    monkeypatch.setattr(monitoring, "get_redis_client", lambda: SimpleNamespace(client=cache))
    monkeypatch.setattr(celery_app.control, "inspect", lambda timeout=None: inspect["value"])
    return SimpleNamespace(broker=broker, cache=cache, inspect=inspect)


def _report(cache):
    return json.loads(cache.get(broker_unacked.REPORT_KEY))


def test_an_orphan_is_flagged_on_the_second_check_only(check):
    _deliver(check.broker, "dead", "task-dead", "job-2", delivered_at=0)  # very old

    first = monitoring.check_broker_unacked()
    assert first["orphans"] == 0  # one sighting could be a worker slow to answer
    assert _report(check.cache)["suspect_task_ids"] == ["task-dead"]

    second = monitoring.check_broker_unacked()
    assert second["orphans"] == 1
    assert _report(check.cache)["orphans"][0]["job_id"] == "job-2"


def test_a_running_task_is_never_flagged(check):
    _deliver(check.broker, "running", "task-live", "job-1", delivered_at=0)
    check.inspect["value"] = FakeInspect(active={"w1": [{"id": "task-live"}]})

    monitoring.check_broker_unacked()
    assert monitoring.check_broker_unacked()["orphans"] == 0


def test_the_check_is_skipped_when_no_worker_answers(check):
    _deliver(check.broker, "dead", "task-dead", "job-2", delivered_at=0)
    check.inspect["value"] = FakeInspect()

    assert monitoring.check_broker_unacked()["skipped"] is True


# --- admin endpoints ------------------------------------------------------------------------


@pytest.fixture
def admin(monkeypatch, check):
    monkeypatch.setattr(admin_routes, "get_redis_client", lambda: SimpleNamespace(client=check.cache))
    return check


def _requeue(tag):
    return asyncio.run(admin_routes.requeue_broker_unacked(tag, admin_user=None))


def test_admin_requeues_a_flagged_orphan(admin):
    _deliver(admin.broker, "dead", "task-dead", "job-2", delivered_at=0)
    monitoring.check_broker_unacked()
    monitoring.check_broker_unacked()

    result = _requeue("dead")

    assert result["requeued"] is True and result["job_id"] == "job-2"
    assert admin.broker.llen("ingestify-audio") == 1


def test_admin_cannot_requeue_what_the_check_has_not_flagged(admin):
    _deliver(admin.broker, "dead", "task-dead", "job-2", delivered_at=0)
    monitoring.check_broker_unacked()  # only a suspect so far

    with pytest.raises(HTTPException) as exc:
        _requeue("dead")
    assert exc.value.status_code == 409
    assert admin.broker.llen("ingestify-audio") == 0


def test_admin_cannot_requeue_a_task_a_worker_picked_back_up(admin):
    _deliver(admin.broker, "dead", "task-dead", "job-2", delivered_at=0)
    monitoring.check_broker_unacked()
    monitoring.check_broker_unacked()
    admin.inspect["value"] = FakeInspect(active={"w1": [{"id": "task-dead"}]})

    with pytest.raises(HTTPException) as exc:
        _requeue("dead")
    assert exc.value.status_code == 409


def test_admin_lists_unacked_messages_and_the_last_check(admin):
    _deliver(admin.broker, "dead", "task-dead", "job-2", delivered_at=0)
    monitoring.check_broker_unacked()

    listing = asyncio.run(admin_routes.list_broker_unacked(admin_user=None))

    assert [m["delivery_tag"] for m in listing["unacked"]] == ["dead"]
    assert listing["last_check"]["suspect_task_ids"] == ["task-dead"]
