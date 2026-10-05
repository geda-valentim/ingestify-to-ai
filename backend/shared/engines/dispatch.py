"""
Where a routed feature's work enters the system (spec 0003, section 4.3).

    submit(feature, ...):
      no route (or the route is draining, or it cannot be read) -> today(): the
          exact call the code always made                                       END
      dispatcher down for longer than dispatcher_down_seconds, fallback
      local_direct and the route has a local step -> job_dispatches(bypassed)
          + engine_usage(local, reserved, placed_by=fallback) in one transaction,
          then the local task with usage_id. It does not check capacity (neither
          does today's path) but the row counts in flight, so nothing new is
          placed locally until it drains                                        END
      otherwise -> job_dispatches(probing), then probe_media on the dispatch
          queue; the probe moves it to `waiting` and kicks the dispatcher.

Only MySQL and Redis are touched here, never `modal`, never media. Celery is
reached through `celery.send_task` (task names, not imports), so shared/ does
not depend on workers/.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.engines import routing
from shared.engines.budget import period_start
from shared.engines.capacity import bindings
from shared.engines.features import get_feature
from shared.engines.ledger import run_txn
from shared.models import DispatcherLease, Engine, EngineUsage, JobDispatch

logger = logging.getLogger(__name__)

PROCESS_CONVERSION = "workers.tasks.process_conversion"
PROBE_TASK = "workers.engines.tasks.probe_media"
TICK_TASK = "workers.engines.tasks.dispatch_tick"
SWEEP_TASK = "workers.engines.tasks.sweep_usage"
KICK_KEY = "engines:kick"
KICK_DEDUP_MS = 500
SEEN_CACHE_SECONDS = 5.0

CONVERT_PAGE = "workers.tasks.convert_page_task"

# The local task of each routed backlog feature (the LocalAdapter's `execute` is the task
# of today). Vision is synchronous and has no backlog: see place_now().
LOCAL_TASKS = {"transcription": PROCESS_CONVERSION, "document_conversion": CONVERT_PAGE}

# Features whose items are measured before placement (media duration). A PDF page
# needs no probe: it is one unit, and only local steps run it for now.
PROBED_FEATURES = frozenset({"transcription"})

# Allowlisted payload of a transcription item: the arguments of process_conversion
# for a file already on the shared temp volume. Never an auth token (spec S21).
TRANSCRIPTION_OPTIONS = frozenset({
    "language", "audio_language", "include_timestamps", "include_word_timestamps", "output_format",
    "media_kind", "is_audio", "purge_source", "temperature", "beam_size",
})

# The options /transcribe uses when the caller says nothing; /upload and /convert
# audio routed to the transcription backlog get the same (R5)
DEFAULT_TRANSCRIPTION_OPTIONS = {
    "include_timestamps": True,
    "include_word_timestamps": False,
    "output_format": "markdown",
    "media_kind": "audio",
    "is_audio": True,
    "purge_source": False,
}


def transcription_payload(job_id: str, source: str, options: Dict[str, Any], today_queue: str) -> Dict[str, Any]:
    """The backlog payload of a transcription: what the local task needs, and where today's path sends it"""
    return {
        "kwargs": {
            "job_id": str(job_id),
            "source_type": "file",
            "source": str(source),
            "options": {k: v for k, v in (options or {}).items() if k in TRANSCRIPTION_OPTIONS},
        },
        "today_queue": today_queue,
    }


# Allowlisted payload of a document page (spec 0003, 4.14 and S21): what convert_page_task
# needs for one page. The converter reads only the preset; nothing else is carried.
PAGE_OPTIONS = frozenset({"docling_preset"})


def page_payload(*, page_job_id: str, parent_job_id: str, page_number: int, options: Optional[Dict[str, Any]],
                 page_file_path: Optional[str] = None, source_pdf_path: Optional[str] = None,
                 today_queue: str) -> Dict[str, Any]:
    """The backlog payload of one PDF page (a split page file, or the whole PDF for a retry)"""
    kwargs: Dict[str, Any] = {
        "page_job_id": str(page_job_id),
        "parent_job_id": str(parent_job_id),
        "page_number": int(page_number),
        "options": {k: v for k, v in (options or {}).items() if k in PAGE_OPTIONS},
    }
    if page_file_path:
        kwargs["page_file_path"] = str(page_file_path)
    else:
        kwargs["source_pdf_path"] = str(source_pdf_path)
    return {"kwargs": kwargs, "today_queue": today_queue}


def local_queue(feature: str) -> str:
    return getattr(get_settings(), get_feature(feature).local_queue_setting)


# --- dispatcher liveness, as the submit sees it -------------------------------------

_seen_cache: Dict[str, Tuple[float, Optional[datetime]]] = {}
_seen_lock = threading.Lock()


def dispatcher_seen_at(session_factory=None, clock=time.monotonic) -> Optional[datetime]:
    """When the dispatcher last ticked as leader (cached 5 s); None if never, or unreadable"""
    now = clock()
    with _seen_lock:
        hit = _seen_cache.get("seen")
        if hit and hit[0] > now:
            return hit[1]
    try:
        def read(db: Session):
            lease = db.get(DispatcherLease, 1)
            return lease.dispatcher_seen_at if lease else None
        seen = run_txn(session_factory, read)
    except Exception as e:
        logger.warning(f"[ENGINES] Could not read the dispatcher lease: {type(e).__name__}")
        seen = None
    with _seen_lock:
        _seen_cache["seen"] = (now + SEEN_CACHE_SECONDS, seen)
    return seen


def reset_caches() -> None:
    with _seen_lock:
        _seen_cache.clear()
    routing.invalidate_cache()


def dispatcher_down(route: routing.RouteSnapshot, seen: Optional[datetime], now: datetime) -> bool:
    return seen is None or now - seen > timedelta(seconds=route.dispatcher_down_seconds)


# --- submit ---------------------------------------------------------------------------


def submit(*, feature: str, job_id: str, user_id: Optional[str], is_admin: bool, payload: Dict[str, Any],
           today: Optional[Callable[[], Any]], celery, media_bytes: Optional[int] = None, allow_remote: bool = True,
           session_factory=None, now: Optional[datetime] = None, subject_type: str = "job",
           subject_id: Optional[str] = None) -> str:
    """
    Hand one item of a feature to its route. Returns "today" (no route: `today()`
    was called, or nothing was done when it is None), "fallback" or "queued".
    A publish failure (Redis down) raises, as today's path does.

    The subject is the job itself, or (document_conversion) one page: subject_type
    "page", subject_id the page job id, job_id the parent job.
    """
    route = routing.get_route(feature, session_factory)
    if route is None or not route.active:
        if today is not None:
            today()
        return "today"

    subject = (subject_type, str(subject_id or job_id))
    now = now or datetime.utcnow()
    remote_allowed = bool(allow_remote and (route.remote_allowed_for == "all" or is_admin))
    down = dispatcher_down(route, dispatcher_seen_at(session_factory), now)

    if down and route.dispatcher_fallback == "local_direct" and route.has_local_step():
        usage_id, dispatch_id = _reserve_fallback(route, feature, job_id, user_id, remote_allowed, payload,
                                                  media_bytes, session_factory, now, subject)
        try:
            publish_local(celery, feature, payload, usage_id)
        except Exception:
            _forget(session_factory, dispatch_id, usage_id)
            raise
        mark_published(session_factory, usage_id, now)
        logger.warning(f"[ENGINES] Dispatcher down: {feature} {subject[0]} {subject[1]} sent straight to the local "
                       f"workers (fallback, usage {usage_id})")
        return "fallback"

    probed = feature in PROBED_FEATURES
    dispatch_id = _insert_item(feature, job_id, user_id, remote_allowed, payload, media_bytes, session_factory, now,
                               subject, "probing" if probed else "waiting")
    try:
        if probed:
            celery.send_task(PROBE_TASK, args=[dispatch_id], queue=get_settings().dispatch_queue)
    except Exception:
        _forget(session_factory, dispatch_id, None)
        raise
    if not probed:
        kick(celery)
    if down:
        logger.warning(f"[ENGINES] Dispatcher down and {feature} fallback is {route.dispatcher_fallback}: "
                       f"{subject[0]} {subject[1]} waits in the backlog")
    return "queued"


def _insert_item(feature, job_id, user_id, remote_allowed, payload, media_bytes, session_factory, now, subject,
                 state) -> int:
    def work(db: Session):
        d = JobDispatch(feature=feature, subject_type=subject[0], subject_id=subject[1], job_id=str(job_id),
                        user_id=user_id, remote_allowed=remote_allowed, state=state, priority=5,
                        payload=payload, media_bytes=media_bytes, enqueued_at=now, updated_at=now,
                        exclude_engines=[])
        db.add(d)
        db.flush()
        return d.id

    return run_txn(session_factory, work)


def _reserve_fallback(route, feature, job_id, user_id, remote_allowed, payload, media_bytes, session_factory,
                      now, subject) -> Tuple[int, int]:
    def work(db: Session):
        local_id = next(e for s in route.steps for e in s["engine_ids"] if e in route.local_engine_ids)
        engine = db.get(Engine, local_id)
        binding = bindings(engine.config or {}).get(feature)
        usage = EngineUsage(
            kind="job", engine_id=engine.id, feature=feature, subject_type=subject[0], subject_id=subject[1],
            attempt=1, job_id=str(job_id), user_id=user_id, period_start=period_start(engine, now),
            status="reserved", placed_by="fallback", gpu_type=binding.gpu_ref if binding else None,
            executions_per_worker=binding.executions_per_worker if binding else None,
            estimated_usd=0, reserved_usd=0, rate_usd_per_s=0, heartbeat_at=now, created_at=now,
        )
        db.add(usage)
        db.flush()
        d = JobDispatch(feature=feature, subject_type=subject[0], subject_id=subject[1], job_id=str(job_id),
                        user_id=user_id, remote_allowed=remote_allowed, state="bypassed", priority=5,
                        payload=payload, media_bytes=media_bytes, enqueued_at=now, updated_at=now,
                        exclude_engines=[], placements=1, usage_id=usage.id, engine_id=engine.id,
                        place_reason="fallback", assigned_at=now)
        db.add(d)
        db.flush()
        return usage.id, d.id

    return run_txn(session_factory, work)


def _forget(session_factory, dispatch_id: Optional[int], usage_id: Optional[int]) -> None:
    """Undo rows whose message never left (the caller fails the request, as today)"""
    def work(db: Session):
        if dispatch_id is not None:
            db.query(JobDispatch).filter(JobDispatch.id == dispatch_id).delete(synchronize_session=False)
        if usage_id is not None:
            db.query(EngineUsage).filter(EngineUsage.id == usage_id).delete(synchronize_session=False)
    try:
        run_txn(session_factory, work)
    except Exception as e:
        logger.error(f"[ENGINES] Could not undo backlog rows {dispatch_id}/{usage_id}: {e}")


def publish_local(celery, feature: str, payload: Dict[str, Any], usage_id: int) -> None:
    """The local executor: today's task, on the feature's own lane, with the reservation it must claim"""
    kwargs = dict(payload["kwargs"])
    kwargs["usage_id"] = usage_id
    celery.send_task(LOCAL_TASKS[feature], kwargs=kwargs, queue=local_queue(feature))


def publish_today(celery, feature: str, payload: Dict[str, Any]) -> None:
    """Today's path for an item leaving the backlog (route removed): no usage_id, its original queue"""
    celery.send_task(LOCAL_TASKS[feature], kwargs=dict(payload["kwargs"]),
                     queue=payload.get("today_queue") or local_queue(feature))


def mark_published(session_factory, usage_id: int, now: Optional[datetime] = None) -> None:
    from sqlalchemy import update

    def work(db: Session):
        db.execute(update(EngineUsage).where(EngineUsage.id == usage_id, EngineUsage.published_at.is_(None))
                   .values(published_at=now or datetime.utcnow()).execution_options(synchronize_session=False))
    try:
        run_txn(session_factory, work)
    except Exception as e:  # the sweeper republishes rows without published_at; never fail over this
        logger.warning(f"[ENGINES] Could not record the publication of usage {usage_id}: {e}")


def kick(celery, redis_client=None) -> bool:
    """Ask for a dispatcher tick now; deduplicated to one per 500 ms"""
    try:
        if redis_client is None:
            from shared.redis_client import get_redis_client
            redis_client = get_redis_client()
        if not redis_client.client.set(KICK_KEY, "1", nx=True, px=KICK_DEDUP_MS):
            return False
    except Exception:
        pass  # without Redis there is no broker either; the send below fails on its own
    try:
        celery.send_task(TICK_TASK, queue=get_settings().dispatch_queue, expires=30)
        return True
    except Exception as e:
        logger.warning(f"[ENGINES] Could not kick the dispatcher: {e}")
        return False


# --- synchronous features: placed inline by the API (vision; spec 0003, 4.14) ---------

# How long a caller refused with 503 is told to wait before trying again
SYNC_RETRY_AFTER_SECONDS = 30


@dataclass(frozen=True)
class Placement:
    """
    What place_now decided: "today" (no route, or nothing fits and the route has a
    local step: the feature's own queue, exactly as without a route), "placed" (a
    reservation to hand the local task as usage_id) or "unavailable" (503 with
    Retry-After: nothing can take it now and there is no local step to fall back on).
    """
    outcome: str
    usage_id: Optional[int] = None
    engine_slug: Optional[str] = None
    retry_after: Optional[int] = None
    reason: Optional[str] = None


def place_now(*, feature: str, subject_id: str, job_id: Optional[str], user_id: Optional[str], is_admin: bool,
              allow_remote: bool = True, session_factory=None, now: Optional[datetime] = None) -> Placement:
    """
    Place one synchronous request without a backlog: walk the route's steps in
    order and reserve the first engine with a free slot, under its row lock, like
    the dispatcher does. A caller is holding a connection open, so nothing waits:
    a remote engine is only eligible when it is warm (no cold start inside the
    request) and none is yet - remote vision has no adapter in this slice -, so
    today only local slots are placed; a full local engine sends the request down
    today's path (the vision queue) rather than refusing it.
    """
    route = routing.get_route(feature, session_factory)
    if route is None or not route.active:
        return Placement("today")
    now = now or datetime.utcnow()
    remote_allowed = bool(allow_remote and (route.remote_allowed_for == "all" or is_admin))

    def work(db: Session) -> Placement:
        from shared.engines.store import in_flight

        refusals = []
        for step in route.steps:
            for engine_id in step["engine_ids"]:
                engine = db.get(Engine, engine_id)
                if engine is None:
                    continue
                why = _sync_ineligible(engine, feature, remote_allowed, now)
                if why:
                    refusals.append(f"{engine.slug}:{why}")
                    continue
                binding = bindings(engine.config or {})[feature]
                locked = db.query(Engine).filter(Engine.id == engine.id).with_for_update().one()
                if in_flight(db, locked.id, feature) >= binding.capacity:
                    refusals.append(f"{engine.slug}:full")
                    continue
                usage = EngineUsage(
                    kind="job", engine_id=locked.id, feature=feature, subject_type="vision_request",
                    subject_id=str(subject_id), attempt=1, job_id=job_id, user_id=user_id,
                    period_start=period_start(locked, now), status="reserved", placed_by=None,
                    gpu_type=binding.gpu_type or binding.gpu_ref, executions_per_worker=binding.executions_per_worker,
                    estimated_usd=0, reserved_usd=0, rate_usd_per_s=0, heartbeat_at=now, created_at=now,
                )
                db.add(usage)
                db.flush()
                return Placement("placed", usage_id=usage.id, engine_slug=locked.slug)
        reason = ", ".join(refusals) or "no engine"
        if route.has_local_step():
            return Placement("today", reason=reason)
        return Placement("unavailable", retry_after=SYNC_RETRY_AFTER_SECONDS, reason=reason)

    return run_txn(session_factory, work)


def _sync_ineligible(engine: Engine, feature: str, remote_allowed: bool, now: datetime) -> Optional[str]:
    if engine.status != "active":
        return "paused"
    if engine.health in routing.BAD_HEALTH and (engine.health_until is None or engine.health_until > now):
        return "unhealthy"
    binding = bindings(engine.config or {}).get(feature)
    if binding is None or binding.capacity <= 0:
        return "no_binding"
    if engine.adapter_type != "local":
        # A synchronous request cannot wait for a cold container, and no remote adapter
        # runs this feature yet (spec 0003, slice 8: remote vision is out of this slice)
        return "not_remote_allowed" if not remote_allowed else "no_warm_remote"
    return None


def publish_sync(session_factory, usage_id: int, send: Callable[[], Any], now: Optional[datetime] = None):
    """Send a placed synchronous request; a send that fails gives the slot back at once"""
    try:
        result = send()
    except Exception:
        release_sync(session_factory, usage_id, "PUBLISH_FAILED")
        raise
    mark_published(session_factory, usage_id, now)
    return result


def release_sync(session_factory, usage_id: int, error_code: str) -> None:
    from sqlalchemy import update

    def work(db: Session):
        db.execute(update(EngineUsage).where(EngineUsage.id == usage_id, EngineUsage.status == "reserved")
                   .values(status="released", finished_at=datetime.utcnow(), error_code=error_code, actual_usd=0)
                   .execution_options(synchronize_session=False))
    try:
        run_txn(session_factory, work)
    except Exception as e:  # the sweeper releases an unclaimed reservation anyway
        logger.warning(f"[ENGINES] Could not release usage {usage_id}: {e}")


# --- what the job page may say (owner only) -----------------------------------------


def job_signal(db: Session, job_id: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    (engine, queue_reason) for GET /jobs/{id}: engine.kind is local or cloud once
    placed; queue_reason is in_queue (backlog) or starting (placed, not started).
    Nothing about budgets or other users (spec S18). (None, None) without routing.
    """
    d = db.query(JobDispatch).filter(JobDispatch.subject_type == "job", JobDispatch.subject_id == str(job_id)).first()
    if not isinstance(d, JobDispatch):
        return None, None
    reason = {"probing": "in_queue", "waiting": "in_queue", "assigned": "starting", "bypassed": "starting"}.get(d.state)
    engine = None
    if d.engine_id:
        adapter = db.query(Engine.adapter_type).filter(Engine.id == d.engine_id).scalar()
        if isinstance(adapter, str):
            engine = {"kind": "local" if adapter == "local" else "cloud"}
    return engine, reason
