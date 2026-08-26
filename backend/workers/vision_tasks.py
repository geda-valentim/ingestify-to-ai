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
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from celery.signals import worker_process_init

from shared.config import get_settings
from workers.celery_app import celery_app
from workers.vision.errors import VisionError
from workers.vision.factory import get_available_providers, get_image_describer

logger = logging.getLogger(__name__)

settings = get_settings()

# Soft limit fires first so a task gets a chance to fail cleanly before the
# hard limit kills the worker process out from under it.
_TASK_TIME_LIMIT = settings.vision_task_timeout_seconds
_TASK_SOFT_TIME_LIMIT = max(settings.vision_task_timeout_seconds - 15, 1)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="workers.vision_tasks.describe_image_task",
    time_limit=_TASK_TIME_LIMIT,
    soft_time_limit=_TASK_SOFT_TIME_LIMIT,
)
def describe_image_task(self, job_id: str, image_path: str, task: str) -> dict:
    """Caption one image. See module docstring for the failure contract."""
    return _run("describe", job_id, image_path, {"task": task} if task else None)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="workers.vision_tasks.ocr_image_task",
    time_limit=_TASK_TIME_LIMIT,
    soft_time_limit=_TASK_SOFT_TIME_LIMIT,
)
def ocr_image_task(self, job_id: str, image_path: str) -> dict:
    """Read text out of one image, with per-line regions."""
    return _run("ocr", job_id, image_path, None)


@celery_app.task(name="workers.vision_tasks.vision_capabilities_task")
def vision_capabilities_task() -> dict:
    """Report what this worker can actually do.

    Answered here rather than in the API because the only answer worth having
    describes the process that loads the model - and computing it in the API
    would force a torch import there.
    """
    from shared.device import device_report
    from workers.vision.download import model_is_cached

    report = device_report()
    providers = get_available_providers()
    provider = settings.vision_provider
    probe = providers.get(provider, {"available": False, "reason": f"unknown provider '{provider}'"})

    model_loaded = False
    reason: Optional[str] = probe.get("reason") or report.get("reason")
    try:
        # Cheap: builds the describer object but loads no weights.
        model_loaded = bool(get_image_describer().is_loaded)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"

    return {
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
    }


def _run(
    operation: str,
    job_id: str,
    image_path: str,
    options: Optional[Dict[str, Any]],
) -> dict:
    """Shared body for both vision tasks: run it, record it, report it."""
    _set_status(job_id, "processing", progress=10, started_at=datetime.utcnow())

    try:
        describer = get_image_describer()
        if operation == "describe":
            result = describer.describe(image_path, options)
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


def _store_result(job_id: str, payload: dict) -> None:
    """Write the result down the normal path, so a 504'd request can poll for it."""
    try:
        from shared.redis_client import get_redis_client

        get_redis_client().set_job_result(job_id, payload)
    except Exception as exc:
        logger.warning("vision: could not store result for job %s: %s", job_id, exc)


@worker_process_init.connect
def _preload_vision_model(**kwargs):
    """Load the weights at worker start when VISION_PRELOAD_MODEL is on.

    Without this the first request pays a 5-15s CPU load inside its 60s budget,
    and a first-ever request on a cold cache pays the ~0.5GB download and 504s.

    This must never abort worker startup: a GPU-less box that turned the flag on
    by accident still has to boot.
    """
    try:
        if not get_settings().vision_preload_model:
            return
        get_image_describer().load()
        logger.info("vision: model preloaded at worker start")
    except VisionError as exc:
        logger.warning("vision preload failed: %s", exc)
    except Exception as exc:
        logger.warning("vision preload failed unexpectedly: %s", exc)
