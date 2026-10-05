"""
Real concurrency against MySQL (spec 0003, slice 3b): what SQLite cannot show.

Skipped unless ENGINES_TEST_DATABASE_URL points at a scratch MySQL - every table
there is dropped. Threads race on the same rows; the conditional updates and the
epoch-fenced lease must still allow one winner, never over capacity, never a
double placement.

The server's default collation must be utf8mb4_general_ci, as on production's
MariaDB: the projects/folders tables (spec 0004) declare it explicitly and their
foreign keys to users.id need the same collation. A stock MySQL 8 defaults to
utf8mb4_0900_ai_ci, so start it with
`--character-set-server=utf8mb4 --collation-server=utf8mb4_general_ci`.
"""

import os
import threading
from collections import Counter

import pytest

from shared.engines import ledger
from shared.models import EngineUsage, JobDispatch
from workers.engines import dispatcher

pytestmark = pytest.mark.skipif(
    not os.environ.get("ENGINES_TEST_DATABASE_URL"), reason="needs a scratch MySQL (ENGINES_TEST_DATABASE_URL)"
)

from tests._engines_world import World  # noqa: E402


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    yield w
    w.close()


def _race(n, fn):
    barrier = threading.Barrier(n)
    results, errors = [None] * n, []

    def run(i):
        try:
            barrier.wait()
            results[i] = fn(i)
        except Exception as e:  # surfaced below, so a crash cannot pass as "lost the race"
            errors.append(e)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors, errors
    return results


def test_eight_claims_of_one_reservation_have_one_winner(world):
    world.set_route(["eng-local"])
    world.add_item()
    world.tick()
    [usage_id] = [s.kwargs["usage_id"] for s in world.celery.local_runs()]

    outcomes = _race(8, lambda i: ledger.claim(usage_id, f"worker-{i}", session_factory=world.Session)[0])

    assert Counter(outcomes)[ledger.CLAIMED] == 1
    assert world.usage(usage_id).status == "running"


def test_racing_dispatchers_never_exceed_capacity_nor_place_twice(world):
    world.set_route(["eng-local"])
    items = [world.add_item(wait=i) for i in range(20)]

    for _ in range(5):  # several rounds of six dispatchers ticking at once
        _race(6, lambda i: dispatcher.run_tick(celery=world.celery, session_factory=world.Session,
                                               holder=f"dispatcher-{i}", now=world.now,
                                               alive=lambda feature: 2, redis_client=world.redis))

    placed = world.celery.local_runs()
    usage_ids = [s.kwargs["usage_id"] for s in placed]
    assert len(usage_ids) == len(set(usage_ids))  # no usage published twice
    assert world.in_flight() == 2  # filled up to the local engine's configured capacity, never past it
    with world.Session() as db:
        assigned = db.query(JobDispatch).filter(JobDispatch.id.in_(items), JobDispatch.state == "assigned").count()
        reserved = db.query(EngineUsage).filter(EngineUsage.status == "reserved").count()
    assert assigned == reserved == world.in_flight()
