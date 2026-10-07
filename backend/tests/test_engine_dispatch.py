"""
Backlog and placement (spec 0003, slice 3b): the dispatcher, its epoch-fenced lease,
conditional transitions, the sweeper, the API watchdog and route draining - with
the local executor and a fake remote one.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from shared.engines import dispatch, ledger
from shared.models import DispatcherLease, EngineFeatureState, EngineUsage, FeatureRoute, JobDispatch, JobStatus
from workers.engines import dispatcher, lease, sweeper, watchdog
from workers.engines.tasks import probe
from tests._engines_world import ALICE, ROOT, World

LOCAL = "eng-local"


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    yield w
    w.close()


def placed_on(world, dispatch_id):
    d = world.item(dispatch_id)
    return d.engine_id if d.state in ("assigned", "running") else None


@pytest.mark.parametrize('provider,model,task,expected', [
    ('faster-whisper', 'turbo', 'transcribe', True),
    ('faster-whisper', 'medium', 'transcribe', False),
    ('openai-whisper', 'turbo', 'transcribe', False),
    ('openai-api', 'turbo', 'transcribe', False),
    ('faster-whisper', 'medium', 'translate', False),
])
def test_remote_checkpoint_never_replaces_the_requested_provider_model_or_task(world, monkeypatch, provider, model, task, expected):
    settings = dispatch.get_settings()
    monkeypatch.setattr(settings, 'audio_transcriber_provider', provider)
    monkeypatch.setattr(settings, 'whisper_model', model)
    world.set_route([LOCAL])
    world.dispatcher_alive()
    job_id = world.add_job()
    payload = dispatch.transcription_payload(job_id, '/audio.wav', {'transcriber_provider': provider, 'task': task}, 'ingestify-audio')
    dispatch.submit(feature='transcription', job_id=job_id, user_id=ROOT, is_admin=True, payload=payload,
                    today=None, celery=world.celery, session_factory=world.Session, now=world.now)
    with world.Session() as db:
        item = db.query(JobDispatch).filter(JobDispatch.job_id == job_id).one()
        assert item.remote_allowed is expected


# --- placement on the local engine -------------------------------------------------


def test_a_local_only_route_fills_the_configured_capacity_and_no_more(world):
    world.set_route([LOCAL])
    items = [world.add_item(wait=100 - i) for i in range(10)]

    result = world.tick()

    assert [p[0] for p in result.placed] == items[:2]  # FIFO
    assert world.in_flight() == 2
    runs = world.celery.local_runs()
    assert len(runs) == 2 and all(r.queue == "ingestify-audio" for r in runs)
    assert runs[0].kwargs["job_id"] == world.item(items[0]).job_id and runs[0].kwargs["source_type"] == "file"
    usage = world.usage(runs[0].kwargs["usage_id"])
    assert (usage.status, usage.placed_by, usage.reserved_usd, usage.dispatch_epoch) == ("reserved", "dispatcher", 0, 1)
    assert usage.published_at is not None
    assert world.item(items[2]).state == "waiting"

    assert world.tick(world.now + timedelta(seconds=5)).placed == []  # full: nothing more

    # One finishes: exactly one more goes
    ledger.claim(usage.id, "w1", session_factory=world.Session)
    ledger.settle_succeeded(usage.id, "w1", session_factory=world.Session)
    assert len(world.tick(world.now + timedelta(seconds=10)).placed) == 1
    assert world.in_flight() == 2


def test_items_waiting_for_a_backoff_are_not_candidates(world):
    world.set_route([LOCAL])
    later = world.add_item(wait=50, not_before=world.now + timedelta(seconds=60))
    now = world.add_item(wait=10)
    assert [p[0] for p in world.tick().placed] == [now]
    assert world.item(later).state == "waiting"


def test_heartbeats_never_count_as_capacity(world):
    """Zero live workers right after a restart: capacity is still the configured 2"""
    world.set_route([LOCAL])
    for _ in range(3):
        world.add_item()
    assert len(world.tick(alive=lambda f: 0).placed) == 2


def test_a_lane_without_live_workers_for_180s_is_unhealthy(world):
    world.set_route([LOCAL])
    item = world.add_item()
    world.tick(alive=lambda f: 0)  # first look: grace starts now (and places)
    second = world.add_item()
    world.add_item()
    # 170 s later still nobody, but within the grace: placements continue up to capacity
    assert [p[0] for p in world.tick(world.now + timedelta(seconds=170), alive=lambda f: 0).placed] == [second]
    with world.Session() as db:
        db.query(EngineUsage).delete()
        db.query(JobDispatch).filter(JobDispatch.id.in_([item, second])).update({"state": "done"})
        db.commit()
    assert world.tick(world.now + timedelta(seconds=200), alive=lambda f: 0).placed == []
    # A worker comes back: healthy again
    assert len(world.tick(world.now + timedelta(seconds=205), alive=lambda f: 1).placed) == 1


# --- remote rules, with a fake remote executor ---------------------------------------


def test_local_first_then_cloud_after_waiting(world):
    fake = world.add_remote("fake_1")
    world.add_remote("fake_2")
    world.set_route([LOCAL], {"engine_ids": [fake, "eng-fake_2"], "group_strategy": "fill_first",
                              "when": {"min_wait_seconds": 600}})
    items = [world.add_item(user=ROOT, remote_allowed=True, media=60, wait=10) for _ in range(10)]

    result = world.tick()
    assert [p[1] for p in result.placed] == ["local", "local"]
    assert world.remote.published == []

    # 640 s later the waiting ones may go to the cloud: fill_first keeps to one account (1 slot)
    result = world.tick(world.now + timedelta(seconds=640))
    assert [p[1] for p in result.placed] == ["fake_1"]
    assert placed_on(world, items[2]) == fake


def test_reversing_the_order_uses_the_cloud_first(world):
    fake = world.add_remote("fake_1")
    world.set_route([fake], [LOCAL])
    for _ in range(4):
        world.add_item(user=ROOT, remote_allowed=True, media=60)
    assert [p[1] for p in world.tick().placed] == ["fake_1", "local", "local"]


def test_an_admin_item_behind_fifty_local_only_items_goes_to_the_cloud_in_the_same_tick(world):
    fake = world.add_remote("fake_1")
    world.set_route([LOCAL], [fake])
    with world.Session() as db:  # both local slots busy
        for i in range(2):
            db.add(EngineUsage(kind="job", engine_id=LOCAL, feature="transcription", subject_type="job",
                               subject_id=f"busy-{i}", attempt=1, period_start=world.now.date(), status="running",
                               heartbeat_at=world.now))
        db.commit()
    for i in range(50):
        world.add_item(wait=1000 - i)
    admin_item = world.add_item(user=ROOT, remote_allowed=True, media=120, wait=1)

    result = world.tick()

    assert [(p[0], p[1]) for p in result.placed] == [(admin_item, "fake_1")]


def test_a_big_item_without_budget_never_holds_the_small_ones(world):
    fake = world.add_remote("fake_1", limit_usd="1")  # 1 - 0.5 min_remaining = 0.50 to spend
    world.set_route([fake])
    big = world.add_item(user=ROOT, remote_allowed=True, media=3600, wait=100)  # US$ 3.60
    small = world.add_item(user=ROOT, remote_allowed=True, media=60, wait=50)  # US$ 0.06

    for second in range(0, 15 * 5, 5):  # many ticks, the small one settling each time
        world.tick(world.now + timedelta(seconds=second))
        with world.Session() as db:
            for u in db.query(EngineUsage).filter(EngineUsage.status == "reserved"):
                u.status, u.outcome, u.actual_usd = "settled", "succeeded", 0
                db.query(JobDispatch).filter(JobDispatch.usage_id == u.id).update({"state": "done"})
            db.commit()
        world.add_item(user=ROOT, remote_allowed=True, media=60)

    assert world.item(small).state == "done"
    assert world.item(big).skip_count == 0 and world.item(big).blocked_engine_id is None


def test_a_blocking_item_stops_later_ones_on_that_engine_only(world):
    fake = world.add_remote("fake_1", limit_usd="2")  # 1.50 to spend
    world.set_route([fake], [LOCAL])
    with world.Session() as db:  # 0.60 reserved by work in flight on the account (not a job slot here)
        db.add(EngineUsage(kind="probe", engine_id=fake, feature="transcription",
                           period_start=world.now.date().replace(day=1), status="running",
                           reserved_usd=Decimal("0.60"), estimated_usd=Decimal("0.60")))
        db.commit()
    # 1.00, and kept off the local engine so only the cloud can take it
    patient = world.add_item(user=ROOT, remote_allowed=True, media=1000, wait=100, skip_count=9,
                             exclude_engines=[{"engine_id": LOCAL, "until": None}])
    small = world.add_item(user=ROOT, remote_allowed=True, media=100, wait=50)  # 0.10: fits (0.70 <= 1.50)

    world.tick()
    assert placed_on(world, small) == fake  # the small one went to the cloud ...
    blocked = world.item(patient)
    assert blocked.skip_count == 10 and blocked.blocked_engine_id == fake  # ... the 10th skip

    # From now on later items do not take fake_1, but still go elsewhere (local)
    with world.Session() as db:
        db.query(EngineUsage).filter(EngineUsage.engine_id == fake, EngineUsage.kind == "job").update(
            {"status": "settled", "outcome": "succeeded", "actual_usd": 0})
        db.commit()
    later = world.add_item(user=ROOT, remote_allowed=True, media=100)
    world.tick(world.now + timedelta(seconds=5))
    assert placed_on(world, later) == LOCAL
    assert placed_on(world, patient) is None  # still does not fit next to the 0.60

    # The reservation ends: the patient one takes fake_1
    with world.Session() as db:
        db.query(EngineUsage).filter(EngineUsage.kind == "probe").update({"status": "settled", "actual_usd": 0})
        db.commit()
    world.tick(world.now + timedelta(seconds=10))
    assert placed_on(world, patient) == fake


def test_an_item_that_could_never_fit_never_blocks(world):
    fake = world.add_remote("fake_1", limit_usd="1")
    world.set_route([fake], [LOCAL])
    huge = world.add_item(user=ROOT, remote_allowed=True, media=10_000, wait=100, skip_count=9,  # 10.00
                          exclude_engines=[{"engine_id": LOCAL, "until": None}])
    world.add_item(user=ROOT, remote_allowed=True, media=10, wait=50)
    world.tick()
    assert world.item(huge).blocked_engine_id is None and world.item(huge).skip_count == 9


def test_fill_first_moves_on_at_once_when_the_current_account_has_no_budget(world):
    first = world.add_remote("fake_1", limit_usd="0.55")  # 0.05 to spend
    second = world.add_remote("fake_2")
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first"})
    item = world.add_item(user=ROOT, remote_allowed=True, media=100)  # 0.10
    world.tick()
    assert placed_on(world, item) == second


def test_fill_first_waits_for_a_full_current_account_before_scaling_out(world):
    first = world.add_remote("fake_1")
    second = world.add_remote("fake_2")
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first", "scale_out_after_seconds": 300})
    a = world.add_item(user=ROOT, remote_allowed=True, media=10, wait=30)
    b = world.add_item(user=ROOT, remote_allowed=True, media=10, wait=20)

    world.tick()
    assert placed_on(world, a) == first and placed_on(world, b) is None  # current full: wait
    with world.Session() as db:
        assert db.get(EngineFeatureState, (first, "transcription")).full_since == world.now

    world.tick(world.now + timedelta(seconds=200))
    assert placed_on(world, b) is None
    world.tick(world.now + timedelta(seconds=301))
    assert placed_on(world, b) == second


def test_fill_first_current_account_ignores_probes_and_benchmarks(world):
    first = world.add_remote("fake_1")
    second = world.add_remote("fake_2")
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first"})
    with world.Session() as db:
        db.add(EngineUsage(kind="benchmark", engine_id=second, feature="transcription",
                           period_start=world.now.date(), status="settled", actual_usd=0, created_at=world.now))
        db.commit()
    item = world.add_item(user=ROOT, remote_allowed=True, media=10)
    world.tick()
    assert placed_on(world, item) == first


def test_spend_cap_counts_reservations(world):
    fake = world.add_remote("fake_1", config={})
    with world.Session() as db:
        from shared.models import Engine
        engine = db.get(Engine, fake)
        engine.config = {"features": {"transcription": {"gpu_type": "L4", "workers": 8}}}
        engine.deployments = {"transcription": {"binding": {"gpu_type": "L4", "workers": 8,
                                                            "executions_per_worker": 1}}}
        db.commit()
    world.set_route({"engine_ids": [fake], "spend_cap": {"usd": "1.50", "window": "day"}})
    for _ in range(8):
        world.add_item(user=ROOT, remote_allowed=True, media=400)  # 0.40 each
    world.tick()
    with world.Session() as db:
        committed = sum(u.reserved_usd for u in db.query(EngineUsage).filter(EngineUsage.engine_id == fake))
    assert committed <= Decimal("1.50") and committed == Decimal("1.20")


def test_non_admin_items_never_go_remote(world):
    fake = world.add_remote("fake_1")
    world.set_route([fake], [LOCAL])
    item = world.add_item(user=ALICE, remote_allowed=False, media=10)
    world.tick()
    assert placed_on(world, item) == LOCAL and world.remote.published == []


def test_engines_without_an_executor_are_never_placed(world):
    world.add_remote("fake_1")
    with world.Session() as db:
        from shared.models import Engine
        db.get(Engine, "eng-fake_1").adapter_type = "modal"  # a real remote adapter: not in this slice
        db.commit()
    world.set_route(["eng-fake_1"])
    item = world.add_item(user=ROOT, remote_allowed=True, media=10)
    world.tick()
    assert world.item(item).state == "waiting" and world.count(EngineUsage) == 0


def test_on_no_engine_fail_fails_after_the_grace(world):
    fake = world.add_remote("fake_1", limit_usd="0.6")
    world.set_route([fake], on_no_engine="fail", fail_after_seconds=60)
    item = world.add_item(user=ROOT, remote_allowed=True, media=1000)
    world.tick()
    assert world.item(item).unplaceable_since == world.now
    world.tick(world.now + timedelta(seconds=61))
    d = world.item(item)
    assert (d.state, d.error_code) == ("failed", "budget_exhausted")
    assert world.job(d.job_id).status == JobStatus.FAILED


# --- the lease ------------------------------------------------------------------------


def test_the_lease_is_taken_once_and_expires(world):
    with world.Session() as db:
        assert lease.acquire(db, "a", "dispatcher", world.now) == 1
        assert lease.acquire(db, "b", "dispatcher", world.now + timedelta(seconds=5)) is None
        assert lease.renew(db, 1, "a", "dispatcher", world.now + timedelta(seconds=10))
        assert lease.acquire(db, "b", "dispatcher", world.now + timedelta(seconds=26)) == 2
        assert not lease.renew(db, 1, "a", "dispatcher", world.now + timedelta(seconds=27))
        assert db.get(DispatcherLease, 1).dispatcher_seen_at == world.now + timedelta(seconds=26)


def test_a_superseded_leader_places_nothing(world, monkeypatch):
    world.set_route([LOCAL])
    a = world.add_item(wait=20)
    b = world.add_item(wait=10)

    real_publish = dispatch.publish_local

    def publish_then_lose_the_lease(celery, feature, payload, usage_id):
        real_publish(celery, feature, payload, usage_id)
        with world.Session() as db:  # the watchdog takes over in the middle of the tick
            db.get(DispatcherLease, 1).epoch += 1
            db.commit()

    monkeypatch.setattr(dispatch, "publish_local", publish_then_lose_the_lease)
    result = world.tick()

    assert [p[0] for p in result.placed] == [a]
    assert world.item(b).state == "waiting" and world.in_flight() == 1
    # Next round it cannot renew (epoch moved) and the lease is still fresh: it does nothing
    assert not world.tick(world.now + timedelta(seconds=1)).led


def test_every_transition_is_conditional(world):
    world.set_route([LOCAL])
    item = world.add_item()
    with world.Session() as db:
        stale = db.get(JobDispatch, item)
        db.expunge(stale)
    world.tick()
    with world.Session() as db:  # a writer holding the old version changes nothing
        assert not ledger.cas_dispatch(db, stale, ("waiting",), world.now, state="failed")
        db.commit()
    assert world.item(item).state == "assigned"


# --- claim, settle and recovery -------------------------------------------------------


def place_one(world):
    world.set_route([LOCAL])
    item = world.add_item()
    world.tick()
    d = world.item(item)
    return item, d.usage_id


def test_a_claim_is_won_once(world):
    item, usage_id = place_one(world)
    assert ledger.claim(usage_id, "w1", session_factory=world.Session)[0] == ledger.CLAIMED
    assert ledger.claim(usage_id, "w2", session_factory=world.Session)[0] == ledger.LOST
    assert world.item(item).state == "running" and world.usage(usage_id).holder == "w1"


def test_a_claim_after_the_job_completed_settles_without_running(world):
    item, usage_id = place_one(world)
    with world.Session() as db:
        from shared.models import Job
        db.get(Job, world.item(item).job_id).status = JobStatus.COMPLETED
        db.commit()
    assert ledger.claim(usage_id, "w1", session_factory=world.Session)[0] == ledger.ALREADY_DONE
    usage = world.usage(usage_id)
    assert (usage.status, usage.outcome) == ("settled", "succeeded") and usage.output_persisted_at is not None
    assert world.item(item).state == "done"


def test_an_unclaimed_placement_goes_back_after_the_claim_timeout(world):
    item, usage_id = place_one(world)
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session,
                           now=world.now + timedelta(seconds=60), redis_client=world.redis)
    assert counts["released"] == 0
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session,
                           now=world.now + timedelta(seconds=121), redis_client=world.redis)
    assert counts["released"] == 1
    d = world.item(item)
    assert (d.state, d.priority, d.job_failures, d.usage_id) == ("waiting", 0, 0, None)
    assert world.usage(usage_id).status == "released"
    # The late message is acknowledged without running
    assert ledger.claim(usage_id, "w1", session_factory=world.Session)[0] == ledger.LOST
    # And the item may be placed again - the local engine is not excluded
    world.tick(world.now + timedelta(seconds=122))
    assert world.item(item).state == "assigned" and world.item(item).placements == 2


def test_a_reservation_never_published_is_published_by_the_sweeper(world, monkeypatch):
    world.set_route([LOCAL])
    item = world.add_item()
    real_publish = dispatch.publish_local
    broker = {"up": False}

    def flaky(*a, **k):
        if not broker["up"]:
            raise ConnectionError("broker down")
        return real_publish(*a, **k)

    monkeypatch.setattr(dispatch, "publish_local", flaky)
    world.tick()
    usage_id = world.item(item).usage_id
    assert world.usage(usage_id).published_at is None
    broker["up"] = True
    world.celery.sent.clear()
    sweeper.sweep(celery=world.celery, session_factory=world.Session, now=world.now + timedelta(seconds=61),
                  redis_client=world.redis)
    assert [r.kwargs["usage_id"] for r in world.celery.local_runs()] == [usage_id]


@pytest.mark.parametrize("completed", [False, True])
def test_a_dead_local_worker_is_given_up_after_local_stale_seconds(world, completed):
    """Crash scenarios A (child killed) and C (container removed)"""
    item, usage_id = place_one(world)
    ledger.claim(usage_id, "w1", session_factory=world.Session, now=world.now)
    job_id = world.item(item).job_id
    if completed:
        with world.Session() as db:
            from shared.models import Job
            db.get(Job, job_id).status = JobStatus.COMPLETED
            db.commit()

    sweeper.sweep(celery=world.celery, session_factory=world.Session, now=world.now + timedelta(seconds=80),
                  redis_client=world.redis)
    assert world.usage(usage_id).status == "running"

    sweeper.sweep(celery=world.celery, session_factory=world.Session, now=world.now + timedelta(seconds=91),
                  redis_client=world.redis)
    usage, d = world.usage(usage_id), world.item(item)
    if completed:
        assert (usage.outcome, d.state) == ("succeeded", "done")
    else:
        assert (usage.status, usage.outcome, usage.actual_usd) == ("settled", "lost", 0)
        assert (d.state, d.job_failures, d.priority) == ("waiting", 1, 0)
        job = world.job(job_id)
        assert job.status == JobStatus.PENDING and job.started_at is None
        assert world.redis.get_job_status(job_id)["status"] == "queued"
    # The redelivered message finds the row settled: acknowledged without running
    assert ledger.claim(usage_id, "w2", session_factory=world.Session)[0] == ledger.LOST


def test_local_losses_count_toward_max_attempts(world):
    world.set_route([LOCAL], max_attempts=2)
    item = world.add_item()
    at = world.now
    for attempt in range(2):
        world.tick(at)
        usage_id = world.item(item).usage_id
        ledger.claim(usage_id, "w", session_factory=world.Session, now=at)
        at += timedelta(seconds=100)
        sweeper.sweep(celery=world.celery, session_factory=world.Session, now=at, redis_client=world.redis)
        at += timedelta(seconds=200)  # past the backoff
    d = world.item(item)
    assert (d.state, d.error_code, d.job_failures) == ("failed", "engine_error", 2)
    assert world.job(d.job_id).status == JobStatus.FAILED


def test_a_failed_attempt_backs_off_like_self_retry_did(world):
    item, usage_id = place_one(world)
    ledger.claim(usage_id, "w1", session_factory=world.Session, now=world.now)
    ok, change = ledger.settle_failed(usage_id, "w1", error_code="INTERNAL", detail="boom",
                                      session_factory=world.Session, now=world.now)
    d = world.item(item)
    assert ok and change.status == "queued"
    assert (d.state, d.job_failures, d.not_before) == ("waiting", 1, world.now + timedelta(seconds=60))
    usage = world.usage(usage_id)
    assert (usage.outcome, usage.error_code, usage.counts_toward_attempts) == ("failed", "INTERNAL", True)


# --- probe -------------------------------------------------------------------------------


def test_the_probe_records_the_duration_and_kicks(world):
    world.set_route([LOCAL])
    item = world.add_item(state="probing")
    assert probe(item, session_factory=world.Session, celery=world.celery, redis_client=world.redis,
                 measure=lambda path: 61.25) == "waiting"
    d = world.item(item)
    assert d.state == "waiting" and d.media_seconds == Decimal("61.25")
    assert world.celery.named(dispatch.TICK_TASK)


def test_an_item_no_step_would_take_fails_at_the_probe(world):
    fake = world.add_remote("fake_1", config={"max_media_seconds": 600})
    world.set_route([fake])
    item = world.add_item(state="probing")
    assert probe(item, session_factory=world.Session, celery=world.celery, redis_client=world.redis,
                 measure=lambda path: 3600.0) == "failed"
    assert (world.item(item).state, world.item(item).error_code) == ("failed", "no_engine")


# --- fallback and watchdog ---------------------------------------------------------------


def test_fallback_rows_count_in_flight_and_hold_back_new_local_work(world):
    world.set_route([LOCAL])  # dispatcher never seen: down
    for _ in range(3):
        job_id = world.add_job()
        payload = dispatch.transcription_payload(job_id, "/x.mp3", {}, "ingestify-audio")
        assert dispatch.submit(feature="transcription", job_id=job_id, user_id=ALICE, is_admin=False,
                               payload=payload, today=None, celery=world.celery,
                               session_factory=world.Session) == "fallback"
    assert world.in_flight() == 3  # above capacity 2: allowed, but counted
    world.add_item()
    world.dispatcher_alive()
    assert world.tick().placed == []
    assert all(u.placed_by == "fallback" for u in _usages(world))


def _usages(world):
    with world.Session() as db:
        rows = db.query(EngineUsage).all()
        for r in rows:
            db.expunge(r)
        return rows


def test_the_watchdog_places_at_most_the_free_local_capacity(world):
    world.set_route([LOCAL])
    with world.Session() as db:
        db.add(EngineUsage(kind="job", engine_id=LOCAL, feature="transcription", subject_type="job",
                           subject_id="busy", attempt=1, period_start=world.now.date(), status="running",
                           heartbeat_at=world.now))
        db.commit()
    for i in range(5):
        world.add_item(wait=10 - i)

    result = watchdog.watchdog_round(celery=world.celery, session_factory=world.Session, now=world.now,
                                     redis_client=world.redis, alive=lambda f: 2)

    assert len(result.placed) == 1
    assert all(u.placed_by in ("watchdog", None) for u in _usages(world))
    with world.Session() as db:
        lease_row = db.get(DispatcherLease, 1)
        assert lease_row.holder is None and lease_row.epoch == 1  # took a new epoch, released it


def test_the_watchdog_only_alerts_with_hold(world):
    world.set_route([LOCAL], dispatcher_fallback="hold")
    world.add_item()
    assert watchdog.watchdog_round(celery=world.celery, session_factory=world.Session, now=world.now,
                                   redis_client=world.redis) is None
    assert world.count(EngineUsage) == 0


def test_the_watchdog_stays_out_while_the_dispatcher_ticks(world):
    world.set_route([LOCAL])
    world.add_item()
    world.dispatcher_alive()
    assert watchdog.watchdog_round(celery=world.celery, session_factory=world.Session,
                                   now=world.now + timedelta(seconds=30)) is None


# --- draining ------------------------------------------------------------------------------


def test_a_removed_route_drains_back_to_todays_path(world):
    world.set_route([LOCAL], state="draining")
    waiting = [world.add_item() for _ in range(3)]
    running = world.add_item(state="running")

    result = world.tick()

    assert sorted(result.drained) == sorted(waiting)
    today = [s for s in world.celery.named(dispatch.PROCESS_CONVERSION)]
    assert len(today) == 3 and all("usage_id" not in s.kwargs and s.queue == "ingestify-audio" for s in today)
    assert world.count(FeatureRoute) == 1  # one item still running

    with world.Session() as db:
        db.query(JobDispatch).filter(JobDispatch.id == running).update({"state": "done"})
        db.commit()
    world.tick(world.now + timedelta(seconds=5))
    assert world.count(FeatureRoute) == 0


def test_a_draining_route_sends_new_items_down_todays_path(world):
    world.set_route([LOCAL], state="draining")
    called = []
    assert dispatch.submit(feature="transcription", job_id="j", user_id=ALICE, is_admin=False, payload={},
                           today=lambda: called.append(1), celery=world.celery,
                           session_factory=world.Session) == "today"
    assert called == [1] and world.count(JobDispatch) == 0


# --- stuck-job detection ---------------------------------------------------------------------


def test_stuck_job_detection_ignores_the_backlog_and_live_attempts(world):
    from shared.models import Job
    from shared.queries import get_stuck_jobs

    old = world.now - timedelta(hours=2)
    queued = world.add_job()  # PENDING, started_at NULL: in the backlog
    live = world.add_job(status=JobStatus.PROCESSING)
    dead = world.add_job(status=JobStatus.PROCESSING)
    with world.Session() as db:
        for job_id in (live, dead):
            db.get(Job, job_id).started_at = old
        db.add(EngineUsage(kind="job", engine_id=LOCAL, feature="transcription", subject_type="job", subject_id=live,
                           job_id=live, attempt=1, period_start=world.now.date(), status="running",
                           heartbeat_at=world.now))
        db.commit()
    stuck = {j.id for j in get_stuck_jobs(threshold_minutes=30)}
    assert stuck == {dead} and queued not in stuck
