"""
The sweeper: recovers routed items through the backlog, never through broker
redelivery (spec 0003, Appendix E). Every action is conditional, so two sweepers
(the dispatcher's and the API watchdog's) cannot double up.

    local `reserved`, never published, for 60 s       -> publish the local task
    local `reserved` for local_claim_timeout_seconds    -> `released`; the subject goes back
      after being published (default 120)                  to `waiting` (no attempt counted)
    local `running` without a heartbeat for             -> job COMPLETED: settled/succeeded;
      local_stale_seconds (default 90)                     otherwise settled/lost (US$ 0,
                                                           counts) and back to the backlog
    `probing` for 60 s                                  -> republish probe_media (3 tries,
                                                           then `waiting` without a duration)

Remote rows (slice 4a) are never settled while their call may still finish -
the sweeper only republishes execute_remote, whose next holder resumes the
recorded call (or cancels it past its deadline):

    remote `reserved`, never published, for 60 s       -> publish execute_remote
    remote `reserved` with no claim for 5 min           -> republish; after 3 -> `released`
    remote `spawning`/`running` silent for 120 s        -> republish (republish_count++)
    remote `running` past deadline_at + 60 s            -> cancel_remote on the control lane
    remote with republish_count >= 5 and still silent   -> settled/lost charging the whole
                                                           reservation; back to the backlog
    `benchmark` rows silent for 15 min (CLI died)        -> settled/lost charging the reservation

A redelivered message of an item handled here finds its row out of `reserved`
and is acknowledged without running.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.engines import dispatch, ledger
from shared.models import Engine, EngineUsage, JobDispatch

logger = logging.getLogger(__name__)

PUBLISH_AFTER_SECONDS = 60
PROBE_RETRY_SECONDS = 60
PROBE_MAX_TRIES = 3
LOCAL_CLAIM_TIMEOUT_SECONDS = 120
LOCAL_STALE_SECONDS = 90
REMOTE_UNCLAIMED_SECONDS = 300
REMOTE_UNCLAIMED_REPUBLISH = 3
REMOTE_SILENT_SECONDS = 120
REMOTE_MAX_REPUBLISH = 5
REMOTE_CANCEL_GRACE_SECONDS = 60
BENCHMARK_STALE_SECONDS = 900  # the benchmark CLI heartbeats its rows every 15 s


def _session(session_factory) -> Session:
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


def sweep(*, celery, session_factory=None, now: Optional[datetime] = None, redis_client=None) -> Dict[str, int]:
    now = now or datetime.utcnow()
    counts = {"published": 0, "released": 0, "lost": 0, "succeeded": 0, "probes": 0, "remote_republished": 0,
              "remote_cancelled": 0, "benchmarks_lost": 0}
    changes = []
    db = _session(session_factory)
    try:
        local = {e.id: e for e in db.query(Engine).filter(Engine.adapter_type == "local")}
        if local:
            _publish_unpublished(db, celery, session_factory, local, now, counts)
            for engine in local.values():
                config = engine.config or {}
                claim_timeout = config.get("local_claim_timeout_seconds", LOCAL_CLAIM_TIMEOUT_SECONDS)
                stale = config.get("local_stale_seconds", LOCAL_STALE_SECONDS)

                unclaimed = [u for u, in db.query(EngineUsage.id).filter(
                    EngineUsage.engine_id == engine.id, EngineUsage.kind == "job", EngineUsage.status == "reserved",
                    EngineUsage.published_at.isnot(None),
                    EngineUsage.published_at < now - timedelta(seconds=claim_timeout))]
                for usage_id in unclaimed:
                    released, change = ledger.release(usage_id, session_factory=session_factory, now=now)
                    if released:
                        counts["released"] += 1
                        changes.append(change)
                        logger.warning(f"[ENGINES] Usage {usage_id} not claimed within {claim_timeout}s: "
                                       f"released, its item is back in the backlog")

                dead = [u for u, in db.query(EngineUsage.id).filter(
                    EngineUsage.engine_id == engine.id, EngineUsage.kind == "job", EngineUsage.status == "running",
                    EngineUsage.heartbeat_at < now - timedelta(seconds=stale))]
                for usage_id in dead:
                    outcome, change = ledger.mark_lost(usage_id, stale_before=now - timedelta(seconds=stale),
                                                       session_factory=session_factory, now=now)
                    if outcome:
                        counts["succeeded" if outcome == "succeeded" else "lost"] += 1
                        changes.append(change)
                        logger.warning(f"[ENGINES] Usage {usage_id}: no heartbeat for {stale}s -> {outcome}")
        db.commit()
        remote_ids = [e for e, in db.query(Engine.id).filter(Engine.adapter_type != "local")]
        db.commit()
        if remote_ids:
            _sweep_remote(db, celery, session_factory, remote_ids, now, counts, changes)
        _republish_probes(db, celery, now, counts)
        _sweep_benchmarks(db, now, counts)
    finally:
        db.close()

    if redis_client is None and any(changes):
        try:
            from shared.redis_client import get_redis_client
            redis_client = get_redis_client()
        except Exception:
            redis_client = None
    for change in changes:
        ledger.apply_job_change(redis_client, change)
    if counts["released"] or counts["lost"]:
        dispatch.kick(celery, redis_client)
    return counts


def _sweep_benchmarks(db: Session, now: datetime, counts: Dict[str, int]) -> None:
    """
    A benchmark whose CLI died stops heartbeating; its ephemeral app went with it
    (the provider stops an ephemeral app when its client disconnects). Settle it
    `lost`, charging the whole reservation on a remote engine (conservative, like a
    lost remote attempt) so the money is not held forever.
    """
    rows = db.query(EngineUsage).filter(
        EngineUsage.kind == "benchmark", EngineUsage.status.in_(ledger.IN_FLIGHT),
        EngineUsage.heartbeat_at < now - timedelta(seconds=BENCHMARK_STALE_SECONDS)).all()
    for usage in rows:
        charge = usage.reserved_usd if usage.rate_usd_per_s and usage.rate_usd_per_s > 0 else 0
        n = db.execute(update(EngineUsage).where(EngineUsage.id == usage.id, EngineUsage.status == usage.status,
                                                 EngineUsage.heartbeat_at == usage.heartbeat_at)
                       .values(status="settled", outcome="lost", actual_usd=charge, cost_basis="reserved",
                               finished_at=now, error_code="BENCHMARK_LOST")
                       .execution_options(synchronize_session=False)).rowcount
        db.commit()
        if n:
            counts["benchmarks_lost"] += 1
            logger.warning(f"[ENGINES] Benchmark usage {usage.id} silent for {BENCHMARK_STALE_SECONDS}s: "
                           f"settled lost, charged US$ {charge}")


def _publish_unpublished(db: Session, celery, session_factory, local: Dict[str, Engine], now: datetime,
                         counts: Dict[str, int]) -> None:
    """A reservation whose publish never happened (crash, broker hiccup between commit and send)"""
    rows = db.query(EngineUsage).filter(
        EngineUsage.engine_id.in_(list(local)), EngineUsage.kind == "job", EngineUsage.status == "reserved",
        EngineUsage.published_at.is_(None),
        EngineUsage.created_at < now - timedelta(seconds=PUBLISH_AFTER_SECONDS)).all()
    for usage in rows:
        d = db.query(JobDispatch).filter(JobDispatch.subject_type == usage.subject_type,
                                         JobDispatch.subject_id == usage.subject_id).first()
        if d is None or d.usage_id != usage.id:
            continue
        claimed = db.execute(
            update(EngineUsage).where(EngineUsage.id == usage.id, EngineUsage.status == "reserved",
                                      EngineUsage.published_at.is_(None))
            .values(published_at=now, republish_count=EngineUsage.republish_count + 1)
            .execution_options(synchronize_session=False)).rowcount
        db.commit()
        if not claimed:
            continue
        try:
            dispatch.publish_local(celery, d.feature, d.payload, usage.id)
            counts["published"] += 1
        except Exception as e:  # the claim timeout releases it if this never arrives
            logger.error(f"[ENGINES] Could not publish usage {usage.id}: {e}")


def _republish_probes(db: Session, celery, now: datetime, counts: Dict[str, int]) -> None:
    rows = db.query(JobDispatch).filter(
        JobDispatch.state == "probing",
        JobDispatch.updated_at < now - timedelta(seconds=PROBE_RETRY_SECONDS)).limit(100).all()
    for d in rows:
        payload = dict(d.payload or {})
        tries = int(payload.get("probe_tries", 0)) + 1
        payload["probe_tries"] = tries
        if tries > PROBE_MAX_TRIES:
            # Give up measuring: the item can still run on local steps (remote ones need a duration)
            ledger.cas_dispatch(db, d, ("probing",), now, state="waiting", payload=payload)
            db.commit()
            dispatch.kick(celery)
            continue
        if not ledger.cas_dispatch(db, d, ("probing",), now, payload=payload):
            db.rollback()
            continue
        db.commit()
        try:
            celery.send_task(dispatch.PROBE_TASK, args=[d.id], queue=get_settings().dispatch_queue)
            counts["probes"] += 1
        except Exception as e:
            logger.error(f"[ENGINES] Could not republish the probe of item {d.id}: {e}")


def _send_remote(celery, task: str, usage_id: int, queue: str) -> bool:
    try:
        celery.send_task(task, args=[usage_id], queue=queue)
        return True
    except Exception as e:
        logger.error(f"[ENGINES] Could not send {task} for usage {usage_id}: {e}")
        return False


def _mark_sent(db: Session, usage: EngineUsage, now: datetime, **extra) -> bool:
    """Conditional bump of a row about to be (re)published: two sweepers never both send"""
    n = db.execute(update(EngineUsage)
                   .where(EngineUsage.id == usage.id, EngineUsage.status == usage.status,
                          EngineUsage.republish_count == usage.republish_count)
                   .values(published_at=now, **extra).execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n == 1


def _sweep_remote(db: Session, celery, session_factory, remote_ids, now: datetime, counts: Dict[str, int],
                  changes: list) -> None:
    from workers.engines.remote import CANCEL_TASK, EXECUTE_TASK

    settings = get_settings()
    rows = db.query(EngineUsage).filter(EngineUsage.engine_id.in_(remote_ids), EngineUsage.kind == "job",
                                        EngineUsage.status.in_(("reserved", "spawning", "running"))).all()
    db.commit()
    for usage in rows:
        if usage.status == "reserved":
            if usage.published_at is None and usage.created_at < now - timedelta(seconds=PUBLISH_AFTER_SECONDS):
                if _mark_sent(db, usage, now, republish_count=EngineUsage.republish_count + 1) and \
                        _send_remote(celery, EXECUTE_TASK, usage.id, settings.remote_queue):
                    counts["published"] += 1
            elif usage.published_at is not None and \
                    usage.published_at < now - timedelta(seconds=REMOTE_UNCLAIMED_SECONDS):
                if usage.republish_count >= REMOTE_UNCLAIMED_REPUBLISH:
                    released, change = ledger.release(usage.id, error_code="REMOTE_UNCLAIMED",
                                                      session_factory=session_factory, now=now)
                    if released:
                        counts["released"] += 1
                        changes.append(change)
                        logger.warning(f"[ENGINES] Remote usage {usage.id} never claimed (is worker-remote up?): "
                                       f"released, its item is back in the backlog")
                elif _mark_sent(db, usage, now, republish_count=EngineUsage.republish_count + 1) and \
                        _send_remote(celery, EXECUTE_TASK, usage.id, settings.remote_queue):
                    counts["remote_republished"] += 1
            continue

        silent = usage.heartbeat_at is None or usage.heartbeat_at < now - timedelta(seconds=REMOTE_SILENT_SECONDS)
        resent_recently = usage.published_at is not None and \
            usage.published_at >= now - timedelta(seconds=REMOTE_SILENT_SECONDS)
        cancel_after = usage.deadline_at + timedelta(seconds=REMOTE_CANCEL_GRACE_SECONDS) if usage.deadline_at else None
        if usage.status == "running" and cancel_after is not None and now > cancel_after:
            # published_at doubles as "cancel sent at": once per REMOTE_SILENT_SECONDS
            cancel_sent = usage.published_at is not None and usage.published_at > cancel_after and resent_recently
            if not cancel_sent and _mark_sent(db, usage, now) and \
                    _send_remote(celery, CANCEL_TASK, usage.id, settings.remote_ctl_queue):
                counts["remote_cancelled"] += 1
                logger.warning(f"[ENGINES] Remote usage {usage.id} is past its deadline: cancel requested")
        if not silent or resent_recently:  # a live holder settles it; a dead one needs a new executor
            continue
        if usage.republish_count >= REMOTE_MAX_REPUBLISH:
            outcome, change = ledger.settle_remote_lost(usage.id, session_factory=session_factory, now=now)
            if outcome:
                counts["succeeded" if outcome == "succeeded" else "lost"] += 1
                changes.append(change)
                logger.error(f"[ENGINES] ALERT remote usage {usage.id}: no executor after {usage.republish_count} "
                             f"republishes -> {outcome}, reservation charged in full")
            continue
        if _mark_sent(db, usage, now, republish_count=EngineUsage.republish_count + 1) and \
                _send_remote(celery, EXECUTE_TASK, usage.id, settings.remote_queue):
            counts["remote_republished"] += 1
            logger.warning(f"[ENGINES] Remote usage {usage.id} silent for {REMOTE_SILENT_SECONDS}s: republished")
