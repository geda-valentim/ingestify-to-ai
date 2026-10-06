"""
The remote executor (spec 0003, 4.7): what happens to an item the dispatcher
placed on a remote engine.

Dispatcher side (worker-dispatch, API watchdog) - RemoteExecutor, no provider code:

    estimate   worst-case hold for the item (pricing.hold_usd), reserved at placement
    publish    execute_remote(usage_id) on `ingestify-remote`, after the commit

worker-remote side - run(usage_id), one thread per in-flight item:

    CHECK 2  claim reserved -> spawning under the engine's lock; refused (paused,
             unhealthy, redeploy pending, budget formula broken) -> released, requeued
    open the engine's sealed credentials (only here), build the adapter
    read the media from the shared temp volume (or MinIO), send it with the spawn
    record the call id and deadline_at = spawned_at + reserved / rate, then wait in
    15 s slices with a heartbeat; past the deadline: cancel
    validate the output -> finish_transcription(), exactly like a local item
    CHECK 3  settle: actual = max(reported, measured) x rate, output_persisted_at
    failure  classify -> settle what was used, mark the engine (Appendix J), and
             requeue at the head of the backlog off this engine (engine errors do not
             count toward max_attempts)

A redelivered or republished message finds its row out of `reserved`: with a live
holder it is acknowledged; with a dead one it is taken over and the recorded call
resumed (or, before the call id was recorded, spawned again under the same
attempt_key - the container refuses a second run of one attempt).
"""

import functools
import logging
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import uuid4

from shared.config import get_settings
from shared.engines import alerts, budget, budget_watch, dispatch, ledger, pricing, speed
from shared.engines.capacity import Binding, bindings, deploy_state
from shared.engines.redact import redact, register_secret
from shared.models import Engine, EngineUsage, Job, JobDispatch, JobStatus
from workers.engines.base import EngineError, ErrorCode, ExecutionContext

logger = logging.getLogger(__name__)

EXECUTE_TASK = "workers.engines.remote_tasks.execute_remote"
CANCEL_TASK = "workers.engines.remote_tasks.cancel_remote"
LIVE_HOLDER_SECONDS = 60
BAD_HEALTH = ("unhealthy", "exhausted", "degraded")

# What each engine error does to the engine and to the item (spec 0003, Appendix J):
# (counts toward max_attempts, terminal, minutes the item stays off this engine)
ERROR_POLICY: Dict[str, Tuple[bool, bool, Optional[int]]] = {
    ErrorCode.AUTH: (False, False, 15),
    ErrorCode.QUOTA_EXHAUSTED: (False, False, 15),
    ErrorCode.CAPACITY: (False, False, 5),
    ErrorCode.RATE_LIMITED: (False, False, 5),
    ErrorCode.NOT_DEPLOYED: (False, False, 15),
    ErrorCode.COLD_START_FAILED: (False, False, 15),
    ErrorCode.TRANSIENT: (False, False, 1),
    ErrorCode.LOST: (False, False, None),
    ErrorCode.TIMEOUT: (True, False, None),
    ErrorCode.INTERNAL: (True, False, 15),
    ErrorCode.INPUT_REJECTED: (False, True, None),
}
UNHEALTHY_AFTER_FAILURES = 3
UNHEALTHY_MINUTES = 10


def _session(session_factory):
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


@functools.lru_cache(maxsize=64)
def _fingerprint(feature: str, config_json: str, binding_json: str) -> str:
    import json

    from workers.engines.modal_apps.fingerprint import expected_fingerprint
    return expected_fingerprint(feature, json.loads(config_json), Binding(**json.loads(binding_json)))


def expected_fingerprint(engine: Engine, feature: str, binding: Binding) -> str:
    """What a deploy of the engine's current binding would record (cached per configuration)"""
    import json
    return _fingerprint(feature, json.dumps(engine.config or {}, sort_keys=True, default=str),
                        json.dumps(binding.model_dump(exclude_none=True), sort_keys=True))


def engine_deploy_state(engine: Engine, feature: str, binding: Binding) -> str:
    """deployed | not_deployed | needs_redeploy - binding and code both as recorded by the last deploy"""
    return deploy_state(engine.adapter_type, engine.deployments, feature, binding,
                        expected_fingerprint=expected_fingerprint(engine, feature, binding))


class RemoteExecutor:
    """The dispatcher's view of a remote adapter type: money and publication, no provider code"""
    remote = True

    wants_db = True  # the estimate reads the key's learned speed (shared/engines/speed.py)

    def estimate(self, engine: Engine, binding: Binding, item: JobDispatch, db=None) -> Decimal:
        stats = None
        profile = ((((item.payload or {}).get('kwargs') or {}).get('options') or {}).get('transcription_profile') or {})
        if db is not None and profile.get('provider') != 'whisperx':
            try:
                stats = speed.get_stats(db, engine.id, item.feature, binding.gpu_type, binding.executions_per_worker)
            except Exception as e:  # never block placement on the cache: the defaults are the worst case
                logger.warning(f"[ENGINES] Speed of {engine.slug} unavailable, using the defaults: {type(e).__name__}")
        return pricing.hold_usd(engine.config or {}, binding, float(item.media_seconds), stats)

    def reservation_values(self, engine: Engine, binding: Binding, feature: str) -> Dict[str, Any]:
        config = engine.config or {}
        return {
            "rate_usd_per_s": pricing.rate_usd_per_s(config, binding),
            "price_snapshot": pricing.prices(config, binding),
            "fingerprint": expected_fingerprint(engine, feature, binding),
        }

    def deploy_state(self, engine: Engine, feature: str, binding: Binding) -> str:
        return engine_deploy_state(engine, feature, binding)

    def publish(self, celery, engine: Engine, item: JobDispatch, usage_id: int) -> None:
        celery.send_task(EXECUTE_TASK, args=[usage_id], queue=get_settings().remote_queue)


# --- worker-remote ------------------------------------------------------------------------


def open_credentials(engine: Engine) -> Dict[str, str]:
    """The engine's credentials, opened with this process's private keys (worker-remote only)"""
    from shared.engines.sealing import open_sealed

    if not engine.credentials_sealed:
        raise EngineError(ErrorCode.AUTH, f"engine {engine.slug} has no credentials")
    try:
        credentials = open_sealed(engine.credentials_sealed, get_settings().engine_private_keys(), engine.id,
                                  engine.credentials_key_id or "")
    except Exception as e:  # SealingError, unreadable key file: never the key itself
        raise EngineError(ErrorCode.AUTH, f"credentials of {engine.slug} cannot be opened: {type(e).__name__}: {e}")
    for value in credentials.values():
        register_secret(str(value))
    return credentials


def snapshot(engine: Engine) -> Dict[str, Any]:
    return {"id": engine.id, "slug": engine.slug, "config": dict(engine.config or {}),
            "deployments": dict(engine.deployments or {})}


def default_adapter_factory(engine: Engine, credentials: Dict[str, str]):
    if engine.adapter_type != "modal":
        raise EngineError(ErrorCode.INTERNAL, f"no remote adapter for {engine.adapter_type!r}")
    from workers.engines.adapters.modal import ModalAdapter
    return ModalAdapter(snapshot(engine), credentials)


# Replaced in tests (a ModalAdapter over a fake `modal` module)
adapter_factory: Callable = default_adapter_factory

_uploads: Optional[threading.BoundedSemaphore] = None
_uploads_lock = threading.Lock()


def _upload_slot() -> threading.BoundedSemaphore:
    global _uploads
    with _uploads_lock:
        if _uploads is None:
            _uploads = threading.BoundedSemaphore(max(1, get_settings().remote_max_concurrent_uploads))
    return _uploads


def claim_check(feature: str, now: datetime) -> Callable:
    """CHECK 2, run by ledger.claim_remote under the engine's row lock"""
    def check(db, usage: EngineUsage, engine: Engine) -> Optional[str]:
        if engine.status != "active":
            return "ENGINE_PAUSED"
        if engine.health in BAD_HEALTH and (engine.health_until is None or engine.health_until > now):
            return "ENGINE_UNHEALTHY"
        binding = bindings(engine.config or {}).get(feature)
        if binding is None or engine_deploy_state(engine, feature, binding) != "deployed":
            return "NEEDS_REDEPLOY"
        if engine.limit_usd is None:
            return "NO_BUDGET"
        room = budget.headroom(db, engine, usage.period_start)  # this reservation included
        if room is None or room < 0:
            return "BUDGET"
        return None
    return check


def _resolve_media(job: Job, source: str) -> Path:
    """The item's media on the shared temp volume, fetched back from MinIO if it is gone"""
    settings = get_settings()
    base = Path(settings.temp_storage_path).resolve()
    allowed = [base / "audio" / job.id, base / "uploads" / job.id]
    path = Path(source).resolve() if source else None
    if path is None or not any(path.is_relative_to(d) for d in allowed):
        raise EngineError(ErrorCode.INPUT_REJECTED, "the item's media is not in its job directory")
    if path.exists():
        return path
    if not job.minio_upload_path:
        raise EngineError(ErrorCode.INTERNAL, "the media is gone from the temp volume and not in MinIO")
    from shared.minio_client import get_minio_client

    minio = get_minio_client()
    bucket = minio.bucket_audio if job.minio_upload_path.startswith("audio/") else minio.bucket_uploads
    path.parent.mkdir(parents=True, exist_ok=True)
    minio.download_file(bucket, job.minio_upload_path, file_path=str(path))
    return path


def _mark_engine(session_factory, engine_id: str, code: Optional[str], detail: str, now: datetime,
                 period_end: Optional[datetime] = None) -> None:
    """The engine's health after an attempt (spec 0003, Appendix J); success clears the failure count"""
    def work(db):
        engine = db.query(Engine).filter(Engine.id == engine_id).with_for_update().one()
        if code is None:
            engine.consecutive_failures = 0
            if engine.health in ("unknown", "degraded") or (engine.health_until and engine.health_until <= now):
                engine.health, engine.health_reason, engine.health_until = "healthy", None, None
            return
        reason = redact(f"{code}: {detail}")[:1000]
        if code == ErrorCode.AUTH:
            engine.health, engine.health_reason, engine.health_until = "unhealthy", reason, None
        elif code == ErrorCode.QUOTA_EXHAUSTED:
            engine.health, engine.health_reason, engine.health_until = "exhausted", reason, period_end
        elif code in (ErrorCode.NOT_DEPLOYED, ErrorCode.COLD_START_FAILED):
            engine.health, engine.health_reason = "unhealthy", reason
            engine.health_until = now + timedelta(minutes=UNHEALTHY_MINUTES)
        elif code in ErrorCode.COUNTED:
            engine.consecutive_failures = (engine.consecutive_failures or 0) + 1
            if engine.consecutive_failures >= UNHEALTHY_AFTER_FAILURES:
                engine.health, engine.health_reason = "unhealthy", reason
                engine.health_until = now + timedelta(minutes=UNHEALTHY_MINUTES)
    try:
        ledger.run_txn(session_factory, work)
    except Exception as e:
        logger.warning(f"[ENGINES] Could not record the health of engine {engine_id}: {e}")


def _period_end(engine: Engine, now: datetime) -> datetime:
    return budget.period_end(engine, now)


def _set_processing(session_factory, redis_client, job_id: str) -> None:
    def work(db):
        job = db.get(Job, job_id)
        if job is not None and job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
            job.status = JobStatus.PROCESSING
            job.started_at = job.started_at or datetime.utcnow()
    ledger.run_txn(session_factory, work)
    try:
        redis_client.set_job_status(job_id=job_id, job_type="main", status="processing", progress=10,
                                    started_at=datetime.utcnow())
    except Exception as e:
        logger.warning(f"[MAIN JOB {job_id}] Could not mirror the processing state: {e}")


def _job_open(session_factory, job_id: str) -> bool:
    def work(db):
        job = db.get(Job, job_id)
        return job is not None and job.status in (JobStatus.PENDING, JobStatus.PROCESSING)
    return ledger.run_txn(session_factory, work)


def _live_captions(redis_client, job_id: str) -> Callable[[list], None]:
    """
    Live captions of a remote attempt (spec 0003, slice 7): segments the container
    pushed to its Queue partition, drained by the adapter between waits, go to the
    same Redis list the local path writes (job:{id}:transcript:partial), so
    GET /jobs/{id}/transcript/partial and the job page work the same for both.
    """
    def on_segments(segments: list) -> None:
        redis_client.append_partial_transcript(job_id, segments)
    return on_segments


def _drop_live_text(redis_client, job_id: str) -> None:
    try:
        redis_client.delete_partial_transcript(job_id)
    except Exception:
        pass


def _progress(redis_client, job_id: str, expected_seconds: float) -> Callable[[float], None]:
    """Estimated progress while the remote call runs (the live text comes separately, _live_captions)"""
    def on_progress(elapsed: float) -> None:
        share = min(elapsed / max(expected_seconds, 1.0), 0.95)
        try:
            redis_client.update_job_progress(job_id, 30 + int(40 * share))
        except Exception:
            pass
    return on_progress


def run(usage_id: int, *, session_factory=None, celery=None, redis_client=None, es_client=None,
        finish: Optional[Callable] = None, now: Optional[Callable[[], datetime]] = None) -> str:
    """Execute (or take over) one remote attempt; returns what happened, for the task result and tests"""
    clock = now or datetime.utcnow
    holder = f"{ledger.holder_id()}:{threading.get_ident()}"
    if redis_client is None:
        from shared.redis_client import get_redis_client
        redis_client = get_redis_client()

    def read():
        db = _session(session_factory)
        try:
            usage = db.get(EngineUsage, usage_id)
            if usage is None:
                return None, None, None
            engine = db.get(Engine, usage.engine_id)
            d = ledger.dispatch_of(db, usage)
            for row in (usage, engine, d):
                if row is not None:
                    db.expunge(row)
            return usage, engine, d
        finally:
            db.close()

    usage, engine, d = read()
    if usage is None or usage.status in ("settled", "released"):
        return "skipped"
    feature = usage.feature
    mode = "spawn"
    if usage.status == "reserved":
        attempt_key = str(uuid4())
        outcome, reason, change = ledger.claim_remote(usage_id, holder, attempt_key, claim_check(feature, clock()),
                                                     session_factory=session_factory, now=clock())
        if outcome != ledger.CLAIMED:
            ledger.apply_job_change(redis_client, change)
            if outcome != ledger.LOST and celery is not None:
                dispatch.kick(celery, redis_client)
            if reason:
                logger.info(f"[ENGINES] Usage {usage_id} refused at claim on {engine.slug}: {reason}; requeued")
            return outcome if not reason else f"refused:{reason}"
    else:
        age = (clock() - usage.heartbeat_at).total_seconds() if usage.heartbeat_at else None
        if age is not None and age < LIVE_HOLDER_SECONDS:
            return "busy"  # another worker-remote thread is on it
        if not ledger.take_over(usage_id, holder, usage.heartbeat_at, session_factory=session_factory, now=clock()):
            return "busy"
        mode = "resume" if usage.status == "running" and usage.provider_call_id else "respawn"
        logger.warning(f"[ENGINES] Usage {usage_id}: taking over a {usage.status} attempt ({mode})")
    usage, engine, d = read()
    return _execute(usage, engine, d, holder, mode, session_factory=session_factory, celery=celery,
                    redis_client=redis_client, es_client=es_client, finish=finish, clock=clock)


def _execute(usage: EngineUsage, engine: Engine, d: Optional[JobDispatch], holder: str, mode: str, *,
             session_factory, celery, redis_client, es_client, finish, clock) -> str:
    usage_id, job_id, feature = usage.id, usage.job_id, usage.feature
    binding = bindings(engine.config or {}).get(feature)
    rate = Decimal(str(usage.rate_usd_per_s or 0))
    if rate <= 0 and binding is not None:
        rate = pricing.rate_usd_per_s(engine.config or {}, binding)
    spawned_at: Optional[datetime] = usage.spawned_at
    started = time.monotonic()
    change = None
    try:
        if d is None or not d.payload:
            raise EngineError(ErrorCode.INTERNAL, "the backlog row of this attempt is gone")
        kwargs = d.payload.get("kwargs") or {}
        options = kwargs.get("options") or {}
        adapter = adapter_factory(engine, open_credentials(engine))

        def record(call_id: str, at: datetime, deadline_at: datetime) -> None:
            nonlocal spawned_at
            spawned_at = at
            if not ledger.record_call(usage_id, holder, call_id, at, deadline_at, session_factory=session_factory):
                logger.warning(f"[ENGINES] Usage {usage_id}: call {call_id} recorded after the row was given up")

        ctx = ExecutionContext(
            usage_id=usage_id, attempt_key=usage.attempt_key, record_call_id=record,
            heartbeat=lambda: ledger.heartbeat(usage_id, holder, session_factory=session_factory),
            deadline_at=usage.deadline_at,
        )
        expected = float(d.media_seconds or 0) / float((engine.config or {}).get("default_speed") or
                                                       pricing.DEFAULT_SPEED) + pricing.DEFAULT_COLD_START_SECONDS
        ctx.on_progress = _progress(redis_client, job_id, expected)
        ctx.on_segments = _live_captions(redis_client, job_id)

        job_row = ledger.run_txn(session_factory, lambda db: _detached(db, Job, job_id))
        if job_row is None:
            raise EngineError(ErrorCode.INTERNAL, "the job is gone")
        if isinstance(getattr(job_row, 'transcription_profile', None), dict):
            from shared.transcription import options_from_profile
            options = options_from_profile(job_row.transcription_profile, options)
        if options.get('transcriber_provider') == 'whisperx':
            from workers.engines.pipeline import begin_transcription_attempt
            options = dict(options, _usage_id=usage_id, _usage_holder=holder)
            # The provider attempt key persists across worker takeover/resume.
            begin_transcription_attempt(job_id, options, session_factory=session_factory,
                                        attempt_id=usage.attempt_key[:36])
        file_path = _resolve_media(job_row, kwargs.get("source"))
        _set_processing(session_factory, redis_client, job_id)

        if mode == "respawn":
            entry = adapter.lookup_attempt(usage.attempt_key) or {}
            if entry.get("call_id"):
                mode = "resume"
                spawned_at = datetime.utcfromtimestamp(float(entry.get("started_unix") or time.time()))
                deadline = spawned_at + timedelta(seconds=pricing.deadline_seconds(usage.reserved_usd, rate))
                record(entry["call_id"], spawned_at, deadline)
                ctx.deadline_at = deadline
                usage.provider_call_id = entry["call_id"]
        if mode == "resume":
            if ctx.deadline_at is not None and clock() > ctx.deadline_at:
                adapter.cancel(usage.provider_call_id, usage.attempt_key)
            result = adapter.resume(usage.provider_call_id, ctx, spawned_at or clock())
        else:
            # A fresh spawn: whatever live text an earlier attempt left is not this one's
            _drop_live_text(redis_client, job_id)
            budget_seconds = pricing.deadline_seconds(usage.reserved_usd, rate)
            max_bytes = int((engine.config or {}).get("max_input_bytes") or 0) or None
            extra = {"max_media_bytes": max_bytes} if max_bytes else {}
            result = adapter.execute(media=file_path.read_bytes, suffix=file_path.suffix.lower(), options=options,
                                     ctx=ctx, budget_seconds=budget_seconds, spawn_guard=_upload_slot, **extra)

        actual = pricing.settle_usd(result.usage.reported_seconds, result.usage.measured_seconds, rate)
        if not _job_open(session_factory, job_id):
            logger.warning(f"[MAIN JOB {job_id}] The job is no longer open; the remote transcript is discarded")
            ledger.settle_failed(usage_id, holder, error_code="CANCELLED", detail="job no longer open", counts=False,
                                 terminal=True, outcome="cancelled", session_factory=session_factory,
                                 actual_usd=actual, container_id=result.usage.container_id,
                                 measured_seconds=result.usage.measured_seconds)
            return "cancelled"

        (finish or _finish)(job_id, result.output, options=options, file_path=file_path,
                            processing_seconds=round(result.usage.measured_seconds, 1),
                            compute_type=result.usage.units.get("compute_type"), redis_client=redis_client,
                            es_client=es_client)
        _check_divergence(usage_id, result.usage)
        settled = ledger.settle_succeeded(
            usage_id, holder, measured_seconds=round(result.usage.measured_seconds, 3), session_factory=session_factory,
            actual_usd=actual, reported_seconds=round(result.usage.reported_seconds or 0, 3),
            cost_basis="measured" if result.usage.measured_seconds >= (result.usage.reported_seconds or 0) else "reported",
            container_id=result.usage.container_id, cold_start_seconds=result.usage.cold_start_seconds,
            exec_started_at=result.usage.exec_started_at, exec_ended_at=result.usage.exec_ended_at,
            units=result.usage.units,
        )
        if not settled:
            logger.warning(f"[ENGINES] Usage {usage_id} was given up while running; its output is persisted anyway")
        _mark_engine(session_factory, engine.id, None, "", clock())
        logger.info(f"[ENGINES] Usage {usage_id} on {engine.slug}: succeeded, US$ {actual} "
                    f"(reported {result.usage.reported_seconds:.1f}s, measured {result.usage.measured_seconds:.1f}s)")
        return "succeeded"
    except Exception as exc:
        error = exc if isinstance(exc, EngineError) else EngineError(ErrorCode.INTERNAL, f"{type(exc).__name__}: {exc}")
        if not isinstance(exc, EngineError):
            logger.error(f"[ENGINES] Usage {usage_id} failed: {redact(str(exc))}", exc_info=True)
        change = _fail(usage, engine, holder, error, spawned_at, rate, started, session_factory, clock)
        return f"failed:{error.code}"
    finally:
        ledger.apply_job_change(redis_client, change)
        budget_watch.check(engine.id, session_factory=session_factory, now=clock())  # soft/hard alerts, exhausted
        if celery is not None:
            dispatch.kick(celery, redis_client)


def _detached(db, model, key):
    row = db.get(model, key)
    if row is not None:
        db.expunge(row)
    return row


def _finish(job_id, result, **kwargs) -> None:
    from workers.engines.pipeline import finish_transcription
    finish_transcription(job_id, result, **kwargs)


def _check_divergence(usage_id: int, usage) -> None:
    """With E = 1 the executor's clock and the container's should roughly agree (spec 0003, 4.7)"""
    if usage.reported_seconds and usage.reported_seconds > 0:
        ratio = usage.measured_seconds / usage.reported_seconds
        if abs(ratio - 1) > 0.3:
            alerts.alert(alerts.COST_DIVERGENCE, None,
                         f"usage {usage_id}: measured {usage.measured_seconds:.1f}s vs reported "
                         f"{usage.reported_seconds:.1f}s (x{ratio:.2f}); billed the larger",
                         {"usage_id": usage_id, "ratio": round(ratio, 3)})


def _fail(usage: EngineUsage, engine: Engine, holder: str, error: EngineError, spawned_at: Optional[datetime],
          rate: Decimal, started: float, session_factory, clock):
    counts, terminal, exclude = ERROR_POLICY.get(error.code, ERROR_POLICY[ErrorCode.INTERNAL])
    now = clock()
    measured = error.usage.measured_seconds or ((now - spawned_at).total_seconds() if spawned_at else 0.0)
    actual = pricing.settle_usd(error.usage.reported_seconds, measured, rate) if spawned_at else Decimal("0")
    if error.code == ErrorCode.LOST:
        outcome, change = ledger.settle_remote_lost(usage.id, session_factory=session_factory, now=now,
                                                    error_code="OUTPUT_EXPIRED")
        logger.warning(f"[ENGINES] Usage {usage.id}: the call's output expired at the provider -> {outcome}")
        return change
    _, change = ledger.settle_failed(
        usage.id, holder, error_code=error.code, detail=error.detail, counts=counts, terminal=terminal,
        exclude_minutes=exclude, session_factory=session_factory, now=now, actual_usd=actual,
        measured_seconds=round(measured, 3), container_id=error.usage.container_id,
    )
    _mark_engine(session_factory, engine.id, error.code, error.detail, now, period_end=_period_end(engine, now))
    if error.code == ErrorCode.QUOTA_EXHAUSTED:
        budget_watch.quota_exhausted(engine.id, redact(error.detail), session_factory=session_factory, now=now)
    logger.warning(f"[ENGINES] Usage {usage.id} on {engine.slug}: {error.code} ({redact(error.detail)[:200]}); "
                   f"charged US$ {actual}, " + ("job failed" if terminal else "item back in the backlog"))
    return change
