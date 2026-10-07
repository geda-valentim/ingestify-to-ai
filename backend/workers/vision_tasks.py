"""
Celery tasks for the vision endpoints.

These back a *synchronous* HTTP contract: a caller is holding a connection open
while the task runs. Three consequences shape everything here.

1. ``max_retries=0``. A retry cannot help a caller who is already waiting; it
   can only guarantee the 504.
2. The tasks carry their own ``time_limit``/``soft_time_limit``, deliberately
   about double the API's request deadline. When a request times out the task
   keeps running to completion, the job reaches ``completed``, and the caller
   picks the result up from ``/jobs/{job_id}/result`` - the codebase's normal
   async contract. The task is NOT revoked on timeout.
3. Typed failures are RETURNED, not raised. A raised exception reaches the API
   as an opaque traceback string; a returned dict survives the JSON result
   serializer with its error code and HTTP status intact, so a missing model
   stays a 503 that says how to fix it instead of becoming a generic 500.

Task names are given explicitly. With ``task_acks_late`` and
``task_reject_on_worker_lost`` both on, an unregistered name is not a one-off
error - the message is redelivered forever.

The task also owns the END of the image's life. The API writes the bytes to
``<temp_storage_path>/images/<job_id>/`` and hands over a path; the task deletes
that directory in a ``finally``, whatever happened. It cannot be the route's
job: a request may walk away with a 504 while the inference is still running
(that is the endpoint's contract), so a route-side cleanup would either delete
the file out from under a live task or skip the case that leaks most.

Capabilities are published as a HEARTBEAT rather than answered by a queued
probe - see ``publish_vision_heartbeat`` for why.
"""

import logging
import json
from pathlib import Path
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from celery.signals import worker_process_init

from shared.config import get_settings
from shared.database import SessionLocal
# Only the two module-level constants; `get_redis_client` stays a function-local
# import in the call sites below, so a Redis that is not there cannot take the
# module down at import time.
from shared.redis_client import VISION_HEARTBEAT_TTL_SECONDS
from workers.celery_app import celery_app
from workers.vision.errors import VisionError
from workers.vision.factory import (
    get_available_providers,
    get_image_describer,
    peek_image_describer,
)
from workers.vision.image_input import discard_image_handoff

logger = logging.getLogger(__name__)

settings = get_settings()

# Soft limit fires first so a task gets a chance to fail cleanly before the
# hard limit kills the worker process out from under it.
_TASK_TIME_LIMIT = settings.vision_task_timeout_seconds
_TASK_SOFT_TIME_LIMIT = max(settings.vision_task_timeout_seconds - 15, 1)

# How often a vision worker republishes what it can do. The lifetime itself is
# `VISION_HEARTBEAT_TTL_SECONDS`, defined next to the key in
# `shared/redis_client.py` so writer and reader cannot drift apart; refreshing
# at a third of it means two missed refreshes (a GC pause, a slow Redis) do not
# make a live worker look dead, while a worker that actually died stops being
# reported within the TTL.
HEARTBEAT_TTL_SECONDS = VISION_HEARTBEAT_TTL_SECONDS
HEARTBEAT_INTERVAL_SECONDS = max(HEARTBEAT_TTL_SECONDS // 3, 1)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="workers.vision_tasks.describe_image_task",
    time_limit=_TASK_TIME_LIMIT,
    soft_time_limit=_TASK_SOFT_TIME_LIMIT,
)
def describe_image_task(self, job_id: str, image_path: str, task: str, usage_id: Optional[int] = None) -> dict:
    """Caption one image. See module docstring for the failure contract."""
    return _run("describe", job_id, image_path, {"task": task} if task else None, usage_id=usage_id)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="workers.vision_tasks.ocr_image_task",
    time_limit=_TASK_TIME_LIMIT,
    soft_time_limit=_TASK_SOFT_TIME_LIMIT,
)
def ocr_image_task(self, job_id: str, image_path: str, usage_id: Optional[int] = None) -> dict:
    """Read text out of one image, with per-line regions."""
    return _run("ocr", job_id, image_path, None, usage_id=usage_id)


@celery_app.task(bind=True, max_retries=0, name="workers.vision_tasks.analyze_image_task",
                 time_limit=_TASK_TIME_LIMIT, soft_time_limit=_TASK_SOFT_TIME_LIMIT)
def analyze_image_task(self, job_id: str, image_path: str, options: dict, usage_id: Optional[int] = None) -> dict:
    return _run("analyze", job_id, image_path, options, usage_id=usage_id)


@celery_app.task(
    name="workers.vision_tasks.vision_capabilities_task",
    expires=HEARTBEAT_TTL_SECONDS,
    time_limit=30,
    soft_time_limit=20,
)
def vision_capabilities_task() -> dict:
    """Report what this worker can actually do.

    NO LONGER ON THE HOT PATH. ``GET /images/capabilities`` reads the heartbeat
    key instead of queueing this - see ``publish_vision_heartbeat``. It stays
    registered for two reasons, both about not breaking:

      - a straggler message from an API instance that predates the heartbeat
        would hit ``NotRegistered``, and with ``task_acks_late`` +
        ``task_reject_on_worker_lost`` that message is redelivered forever;
      - it is the manual probe (``celery call``) when someone wants an answer
        from one specific worker.

    ``expires`` is the guard for that first case: a probe that has been sitting
    behind a 120s inference is already answering about a moment that has passed,
    so the broker discards it instead of spending the one vision slot on it.
    """
    return capabilities_report()


def capabilities_report() -> Dict[str, Any]:
    """What this process can do, as the ``/images/capabilities`` body.

    Computed in the worker, never in the API: the only answer worth having
    describes the process that loads the model, and computing it in the API
    would force a torch import there.
    """
    from shared.device import device_report
    from workers.vision.download import model_is_cached

    report = device_report()
    from workers.vision.faces import capabilities as facial_capabilities
    faces = facial_capabilities()
    providers = get_available_providers()
    provider = settings.vision_provider
    probe = providers.get(provider, {"available": False, "reason": f"unknown provider '{provider}'"})

    model_loaded = False
    instance = None
    reason: Optional[str] = probe.get("reason") or report.get("reason")
    try:
        instance = peek_image_describer()
        if instance is None:
            # Nothing built yet, so nothing is loaded. Build a THROWAWAY anyway:
            # it costs no weights and it is what surfaces a DEVICE the box
            # cannot satisfy as a `reason` instead of as a failed request later.
            # `force_provider` is what keeps this off the process-wide cache -
            # this runs on a background thread, and a probe must never repoint
            # (or race with) the instance holding the loaded model.
            get_image_describer(force_provider=provider)
        else:
            model_loaded = bool(instance.is_loaded)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"

    return {
        "faces": faces,
        "enabled": settings.enable_image_description,
        "provider": provider,
        "model_id": settings.vision_model_id,
        "revision": settings.vision_model_revision,
        "device_requested": report.get("requested"),
        "device_resolved": report.get("resolved"),
        "torch_available": report.get("torch_available", False),
        "cuda_available": report.get("cuda_available", False),
        "cuda_device_name": report.get("cuda_device_name"),
        "dependencies_installed": bool(probe.get("available")),
        "model_downloaded": model_is_cached(
            settings.vision_model_id,
            settings.vision_model_revision,
            settings.vision_model_cache_dir,
        ),
        "model_loaded": model_loaded,
        "trust_remote_code": settings.vision_trust_remote_code,
        "reason": reason,
        "generation_defaults": {"max_new_tokens": getattr(instance, "max_new_tokens", settings.vision_max_new_tokens),
                                "num_beams": getattr(instance, "num_beams", settings.vision_num_beams)},
    }


def _run(
    operation: str,
    job_id: str,
    image_path: str,
    options: Optional[Dict[str, Any]],
    usage_id: Optional[int] = None,
) -> dict:
    """Shared body for both vision tasks: run it, record it, report it, bin it."""
    _set_status(job_id, "processing", progress=10, started_at=datetime.utcnow())
    try:
        if usage_id is not None:
            return _run_accounted(operation, job_id, image_path, options, usage_id)
        return _run_inner(operation, job_id, image_path, options)
    except Exception as exc:
        _set_status(job_id, "failed", error=str(exc), completed_at=datetime.utcnow())
        raise
    finally:
        # EVERY exit: success, typed failure, crash, SoftTimeLimitExceeded.
        # This is the only cleanup that runs in the normal case - the sweeper in
        # `workers/monitoring.cleanup_old_jobs` is a periodic backstop for the
        # hard-kill case, and periodic cannot bound a tight upload loop.
        discard_image_handoff(settings.temp_storage_path, job_id)


def _run_accounted(
    operation: str,
    job_id: str,
    image_path: str,
    options: Optional[Dict[str, Any]],
    usage_id: int,
) -> dict:
    """
    A request the API placed on the local engine of a vision route (spec 0003,
    4.14): claim the reservation, heartbeat it while the model runs, settle it.

    Unlike a backlog item there is nothing to send the request back to - a caller
    is waiting - so a lost claim (the reservation lapsed: the sweeper released it,
    or this is a redelivery) still runs the request, just outside the accounting,
    exactly as it would without a route.
    """
    from shared.engines import ledger
    from workers.engines.local import UsageHeartbeat

    holder = ledger.holder_id()
    try:
        outcome, _ = ledger.claim(usage_id, holder)
    except Exception as exc:  # accounting must never cost the caller the answer
        logger.warning("vision: could not claim usage %s for job %s: %s", usage_id, job_id, exc)
        outcome = ledger.LOST
    if outcome != ledger.CLAIMED:
        logger.info("vision: usage %s of job %s is %s; running outside the accounting", usage_id, job_id, outcome)
        return _run_inner(operation, job_id, image_path, options)

    def settle(succeeded: bool, code: str = "INTERNAL", detail: str = "") -> None:
        try:
            if succeeded:
                ledger.settle_succeeded(usage_id, holder, measured_seconds=round(time.monotonic() - started, 3))
            else:
                ledger.settle_failed(usage_id, holder, error_code=code[:32], detail=detail, counts=False,
                                     terminal=True)
        except Exception as exc:  # the sweeper settles a silent row; the caller still gets the answer
            logger.warning("vision: could not settle usage %s: %s", usage_id, exc)

    heartbeat = UsageHeartbeat(usage_id, holder).start()
    started = time.monotonic()
    try:
        payload = _run_inner(operation, job_id, image_path, options)
    except BaseException as exc:
        heartbeat.stop()
        settle(False, detail=f"{type(exc).__name__}: {exc}")
        raise
    heartbeat.stop()
    if payload.get("ok") is False:
        settle(False, str(payload.get("error_code") or "INTERNAL"), str(payload.get("detail") or ""))
    else:
        settle(True)
    return payload


def _run_inner(
    operation: str,
    job_id: str,
    image_path: str,
    options: Optional[Dict[str, Any]],
) -> dict:
    try:
        describer = get_image_describer()
        if operation == "describe":
            result = describer.describe(image_path, options)
        elif operation == "analyze":
            result = describer.analyze(image_path, options)
        else:
            result = describer.ocr(image_path, options)

        info = describer.info()
    except VisionError as exc:
        # Returned, not raised - see the module docstring.
        logger.warning(
            "vision %s failed for job %s: %s: %s",
            operation,
            job_id,
            exc.error_code,
            exc,
        )
        _set_status(job_id, "failed", error=str(exc), completed_at=datetime.utcnow())
        return {
            "ok": False,
            "job_id": job_id,
            "error_code": exc.error_code,
            "http_status": exc.http_status,
            "detail": str(exc),
        }
    except Exception as exc:
        # Genuinely unexpected: let it raise and become a 500 with a traceback
        # in the worker log, which is where an unknown failure belongs.
        logger.exception("vision %s crashed for job %s", operation, job_id)
        _set_status(job_id, "failed", error=str(exc), completed_at=datetime.utcnow())
        raise

    payload = {
        "ok": True,
        "job_id": job_id,
        **result,
        "model": {
            "model_id": info.get("model_id"),
            "revision": info.get("revision"),
            "device": info.get("device"),
            "dtype": info.get("dtype"),
        },
    }

    from shared.vision_results import vision_result
    from workers.vision.image_input import sniff_image_mime
    image_bytes = Path(image_path).read_bytes()
    payload = vision_result(payload, operation=operation, image_bytes=image_bytes,
                            mime=sniff_image_mime(image_bytes), filename=Path(image_path).name)
    _store_result(job_id, payload)
    _set_status(job_id, "completed", progress=100, completed_at=datetime.utcnow())
    return payload


def _set_status(job_id: str, status: str, **kwargs) -> None:
    """Record job state, tolerating a Redis that is not there.

    The inference result is the valuable thing; losing the status write must
    not lose it. Every other task in this codebase treats Redis the same way.
    """
    try:
        from shared.redis_client import get_redis_client

        get_redis_client().set_job_status(
            job_id=job_id, job_type="main", status=status, **kwargs
        )
    except Exception as exc:
        logger.warning("vision: could not set status for job %s: %s", job_id, exc)
    from shared.models import Job, JobStatus
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None and job.status != JobStatus.CANCELLED:
                job.status = JobStatus(status)
                for key in ("progress", "started_at", "completed_at"):
                    if key in kwargs:
                        setattr(job, key, kwargs[key])
                if "error" in kwargs:
                    job.error_message = kwargs["error"]
                db.commit()
    except Exception as exc:
        logger.warning("vision: could not persist status for job %s: %s", job_id, type(exc).__name__)


def _store_result(job_id: str, payload: dict) -> None:
    """Write the result down the normal path, so a 504'd request can poll for it."""
    try:
        from shared.redis_client import get_redis_client

        get_redis_client().set_job_result(job_id, payload)
    except Exception as exc:
        logger.warning("vision: could not store result for job %s: %s", job_id, exc)
    # Preserve the original and configuration after cache expiry. The temporary
    # handoff is still removed by the task; the object follows job retention.
    from shared.models import Job
    from shared.minio_client import get_minio_client
    try:
        storage = get_minio_client()
        object_name = f"images/{job_id}/result.json"
        storage.upload_file(bucket_name=storage.bucket_results, object_name=object_name,
                            file_data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                            content_type="application/json")
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                job.minio_result_path = object_name
                job.char_count = len(payload["markdown"])
                db.commit()
    except Exception as exc:
        logger.warning("vision: could not persist result for job %s: %s", job_id, type(exc).__name__)


# ---------------------------------------------------------------------------
# Heartbeat: how /images/capabilities learns the truth without queueing
# ---------------------------------------------------------------------------

def consumes_vision_queue() -> bool:
    """Does THIS process actually serve ``settings.vision_queue``?

    ``workers/celery_app.py`` imports this module in every process - the API,
    beat, and the five general workers - so "I imported the vision tasks" says
    nothing about whether anyone is consuming the vision queue. A general worker
    publishing a heartbeat would be the exact lie this fix exists to remove:
    ``/images/capabilities`` would report a healthy subsystem while
    ``/images/describe`` timed out against a queue with no consumer.

    The honest source is Celery's own selection: ``celery worker -Q <queue>``
    calls ``app.amqp.queues.select()``, and ``consume_from`` is the result. With
    no ``-Q`` it is just the default queue, which is not the vision one.
    """
    try:
        consume_from = celery_app.amqp.queues.consume_from or {}
        return settings.vision_queue in set(consume_from)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("vision: could not read the consumed queues: %s", exc)
        return False


def publish_vision_heartbeat() -> bool:
    """Write this worker's capabilities to Redis under a TTL.

    ## Why a heartbeat and not a probe task

    The probe used to be a Celery task on ``settings.vision_queue``: one slot,
    ``worker_prefetch_multiplier=1``. It therefore queued behind an inference of
    up to ``vision_task_timeout_seconds``, so the endpoint answered "no vision
    worker" precisely when a worker was there and busy - the one moment somebody
    is looking. Worse, nothing bounded the backlog: polling the endpoint
    enqueued probes faster than the single slot could drain them, starving real
    inference with the ops tooling. Reading a key costs the vision worker
    nothing and cannot be starved by it.

    ## The failure mode a heartbeat brings, and how it is closed

    A heartbeat can outlive the worker that wrote it. Two things stop it:
    the Redis TTL (``HEARTBEAT_TTL_SECONDS``), and ``published_at`` inside the
    payload, which lets the reader reject a stale record even if some future
    caller writes the key without an expiry. Absence is then unambiguous, and
    the API renders it as "no worker" - never as a healthy default.

    Returns:
        True if the report was written.
    """
    try:
        from shared.redis_client import get_redis_client

        payload = capabilities_report()
        payload["published_at"] = time.time()
        return get_redis_client().set_vision_heartbeat(payload, HEARTBEAT_TTL_SECONDS)
    except Exception as exc:
        logger.warning("vision: could not publish the capabilities heartbeat: %s", exc)
        return False


def _heartbeat_loop(stop_event: threading.Event, interval: float) -> None:
    """Republish until asked to stop. Runs on a daemon thread, never in a task.

    A periodic *task* would land on the one-slot vision queue and stop being
    published for exactly as long as the worker was busy - which is the state
    the heartbeat most needs to describe.
    """
    while not stop_event.wait(interval):
        publish_vision_heartbeat()


def start_vision_heartbeat(interval: float = HEARTBEAT_INTERVAL_SECONDS):
    """Publish once, then keep publishing on a daemon thread.

    The first publish is synchronous so that a request arriving right after the
    worker boots does not read an empty key and conclude nobody is home.

    Returns:
        ``(thread, stop_event)``, or ``None`` when this process does not serve
        the vision queue.
    """
    if not consumes_vision_queue():
        return None

    publish_vision_heartbeat()

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop,
        args=(stop_event, interval),
        name="vision-heartbeat",
        daemon=True,  # never hold up worker shutdown for a status write
    )
    thread.start()
    logger.info(
        "vision: publishing a capabilities heartbeat every %ss (ttl %ss)",
        interval,
        HEARTBEAT_TTL_SECONDS,
    )
    return thread, stop_event


@worker_process_init.connect
def _start_vision_heartbeat(**kwargs):
    """Start the heartbeat when a vision worker process comes up.

    Must never abort startup: a worker whose Redis is briefly unreachable still
    has to boot, and it will simply be reported as absent until it can publish.
    """
    if not consumes_vision_queue():
        return
    def start():
        try:
            start_vision_heartbeat()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("vision: could not start the capabilities heartbeat: %s", exc)
    # A first capability probe imports the device libraries. Celery kills a
    # prefork child whose init handlers block past four seconds, so the initial
    # probe must run after the signal returns, just like subsequent heartbeats.
    threading.Thread(target=start, name="vision-heartbeat-init", daemon=True).start()


@worker_process_init.connect
def _preload_vision_model(**kwargs):
    """Load the weights at worker start when VISION_PRELOAD_MODEL is on.

    Without this the first request pays a 5-15s CPU load inside its 60s budget,
    and a first-ever request on a cold cache pays the ~0.5GB download and 504s.

    This must never abort worker startup: a GPU-less box that turned the flag on
    by accident still has to boot.
    """
    if not consumes_vision_queue() or not get_settings().vision_preload_model:
        return
    def preload():
        try:
            get_image_describer().load()
            logger.info("vision: model preloaded at worker start")
        except VisionError as exc:
            logger.warning("vision preload failed: %s", exc)
        except Exception as exc:
            logger.warning("vision preload failed unexpectedly: %s", exc)
    threading.Thread(target=preload, name="vision-preload", daemon=True).start()
