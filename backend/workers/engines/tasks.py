"""
Celery tasks of the dispatcher, on the `ingestify-dispatch` queue (worker-dispatch,
compose profile `engines`). Nothing here runs - or is ever published - on an
install without routes.

    probe_media(dispatch_id)  measure the item's duration; probing -> waiting; kick
    dispatch_tick()           one placement round as the epoch-fenced leader
    sweep_usage()             recover unclaimed and dead local attempts (Appendix E)
    refresh_speed()           learned speed/cost per (engine, feature, gpu, E) -> Redis, 1 h

Ticks come from kicks (submit's probe, settles, requeues; deduplicated to one per
500 ms) and from worker-dispatch's own beat every 5 s; the sweeper every 30 s.
"""

import logging
from datetime import datetime
from decimal import Decimal

from celery.exceptions import SoftTimeLimitExceeded

from shared.config import get_settings
from shared.engines import dispatch, ledger, routing
from shared.engines.media import probe_duration
from shared.models import Engine, JobDispatch
from workers.celery_app import celery_app
from workers.engines import dispatcher, sweeper

logger = logging.getLogger(__name__)
settings = get_settings()


def would_any_step_accept(db, route: routing.RouteSnapshot, media_seconds) -> bool:
    """
    False when no step could ever take the item: no local step, and the duration
    is above every remote engine's max_media_seconds (spec 0003, 4.3). A local
    step accepts anything, as today.
    """
    if route.has_local_step() or media_seconds is None:
        return True
    for engine in db.query(Engine).filter(Engine.id.in_(route.engine_ids())):
        limit = (engine.config or {}).get("max_media_seconds")
        if not limit or float(media_seconds) <= float(limit):
            return True
    return False


def probe(dispatch_id: int, *, session_factory=None, celery=None, redis_client=None, measure=None) -> str:
    """The probe's work, separate from the task for tests"""
    celery = celery or celery_app
    measure = measure or (lambda path: probe_duration(path, settings.probe_max_bytes))
    db = dispatcher._session(session_factory)
    try:
        d = db.get(JobDispatch, dispatch_id)
        if d is None or d.state not in ("probing", "waiting"):
            return "skipped"
        try:
            seconds = measure((d.payload or {}).get("kwargs", {}).get("source"))
        except SoftTimeLimitExceeded:
            seconds = None
        media = Decimal(str(round(seconds, 3))) if seconds is not None else None
        route = routing.load_route(db, d.feature)
        now = datetime.utcnow()
        if route is not None and route.active and not would_any_step_accept(db, route, media):
            change = ledger.fail_dispatch(db, d, "no_engine",
                                          "no_engine: the media is longer than every engine of the route accepts",
                                          now, from_states=("probing", "waiting"))
            db.commit()
            ledger.apply_job_change(redis_client or _redis(), change)
            return "failed"
        values = {"media_seconds": media} if media is not None else {}
        if d.state == "probing":
            ledger.cas_dispatch(db, d, ("probing",), now, state="waiting", **values)
        elif values:
            ledger.cas_dispatch(db, d, ("waiting",), now, **values)
        db.commit()
    finally:
        db.close()
    dispatch.kick(celery, redis_client)
    return "waiting"


def _redis():
    try:
        from shared.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


@celery_app.task(name="workers.engines.tasks.probe_media", soft_time_limit=settings.probe_timeout_seconds,
                 time_limit=settings.probe_timeout_seconds + 20)
def probe_media(dispatch_id: int):
    return probe(dispatch_id)


@celery_app.task(name="workers.engines.tasks.dispatch_tick", soft_time_limit=50, time_limit=60)
def dispatch_tick():
    result = dispatcher.run_tick(celery=celery_app)
    return {"led": result.led, "epoch": result.epoch, "placed": len(result.placed),
            "failed": len(result.failed), "drained": len(result.drained)}


@celery_app.task(name="workers.engines.tasks.sweep_usage", soft_time_limit=50, time_limit=60)
def sweep_usage():
    return sweeper.sweep(celery=celery_app)


@celery_app.task(name="workers.engines.tasks.refresh_speed", soft_time_limit=100, time_limit=120)
def refresh_speed():
    from shared.engines import speed

    db = dispatcher._session(None)
    try:
        return {"keys": len(speed.refresh_all(db))}
    finally:
        db.close()
