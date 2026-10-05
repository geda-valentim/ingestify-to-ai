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

A redelivered message of an item handled here finds its row out of `reserved`
and is acknowledged without running. Remote rows arrive with slice 4a.
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


def _session(session_factory) -> Session:
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


def sweep(*, celery, session_factory=None, now: Optional[datetime] = None, redis_client=None) -> Dict[str, int]:
    now = now or datetime.utcnow()
    counts = {"published": 0, "released": 0, "lost": 0, "succeeded": 0, "probes": 0}
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
        _republish_probes(db, celery, now, counts)
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
