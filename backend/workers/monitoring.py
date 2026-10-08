"""
Monitoring and recovery tasks for stuck/failed jobs

These periodic tasks run via Celery Beat to automatically detect and recover from failures.
"""

from datetime import datetime, timedelta
import json
import logging
import re
from pathlib import Path
import time
import shutil
from uuid import uuid4

from workers.celery_app import celery_app
from shared.config import get_settings
from shared.queries import (
    get_stuck_jobs,
    get_stuck_pages,
    get_failed_pages_for_retry,
    get_old_completed_jobs,
)
from shared.redis_client import get_redis_client
from shared.database import SessionLocal
from shared.models import Job, Page, JobStatus

logger = logging.getLogger(__name__)
settings = get_settings()


def _purge_source_if_requested(job_id: str) -> None:
    """The MAIN job settled: purge_source applies (same hook as the workers; never raises)."""
    from shared.job_source import purge_source_if_requested
    from shared.minio_client import get_minio_client

    purge_source_if_requested(job_id, session_factory=SessionLocal, minio_factory=get_minio_client)


def _finish_describe_stage(job_id: str) -> bool:
    """
    A stuck job in the describe stage of describe_images / ocr_images: its
    conversion succeeded, so it is completed with the figure texts recorded so far
    (workers/figure_tasks.py), never failed. False when it is not in that stage.
    """
    from workers import figure_tasks

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.figures_stage != figure_tasks.STAGE_DESCRIBING:
            return False
    outcome = figure_tasks.force_finish(job_id, "stuck")
    logger.info(f"[MONITORING] Stuck describe stage of job {job_id} finished: {outcome.get('status')}")
    return outcome.get("status") == "completed"


def _fail_stuck_job(job_id: str, redis_client) -> bool:
    """
    Mark a stuck job FAILED: re-read under its row lock in this session (the row
    from the detection query belongs to a closed session; changing it writes
    nothing) and only while it is still PROCESSING. Then purge_source applies.
    """
    from shared.job_source import lock_job

    if _finish_describe_stage(job_id):
        return True
    error_message = (f"Job stuck in processing for >{settings.monitoring_stuck_job_threshold_minutes} "
                     f"minutes - marked as failed by monitoring system")
    db = SessionLocal()
    try:
        job = lock_job(db, job_id)
        if job is None or job.status != JobStatus.PROCESSING:
            db.rollback()
            return False
        started_at = job.started_at
        job_type = job.job_type
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        db.commit()
        logger.info(f"[MONITORING] Marked stuck job {job_id} as failed (processing since {started_at})")
    except Exception as e:
        logger.error(f"[MONITORING] Failed to update stuck job {job_id} in MySQL: {e}")
        db.rollback()
        return False
    finally:
        db.close()

    try:
        redis_client.set_job_status(
            job_id=job_id,
            job_type=(job_type or "main").lower(),
            status="failed",
            progress=0,
            error=error_message,
            completed_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error(f"[MONITORING] Failed to update stuck job {job_id} in Redis: {e}")

    _purge_source_if_requested(job_id)
    return True


def _fail_stuck_page(page_id: str, redis_client) -> bool:
    """
    Mark a stuck page FAILED (re-read in this session, under its job's row lock,
    only while still PROCESSING), recount its MAIN job (PARTIAL once every page
    settled with some failed) and let purge_source apply.
    """
    from shared.engines.ledger import recount_parent_pages
    from shared.job_source import lock_job

    error_message = (f"Page stuck in processing for >{settings.monitoring_stuck_job_threshold_minutes} "
                     f"minutes - marked as failed by monitoring system")
    db = SessionLocal()
    try:
        page = db.get(Page, page_id)
        if page is None:
            return False
        parent_job_id, page_number, page_job_id = page.job_id, page.page_number, page.page_job_id
        lock_job(db, parent_job_id)
        page = db.query(Page).filter(Page.id == page_id).with_for_update().populate_existing().first()
        if page is None or page.status != JobStatus.PROCESSING:
            db.rollback()
            return False
        page.status = JobStatus.FAILED
        page.error_message = error_message
        page.completed_at = datetime.utcnow()
        db.flush()
        recount_parent_pages(db, parent_job_id)
        db.commit()
        logger.info(f"[MONITORING] Marked stuck page {page_number} of job {parent_job_id} as failed")
    except Exception as e:
        logger.error(f"[MONITORING] Failed to update stuck page {page_id} in MySQL: {e}")
        db.rollback()
        return False
    finally:
        db.close()

    try:
        if page_job_id:
            redis_client.set_job_status(
                job_id=page_job_id,
                job_type="page",
                status="failed",
                parent_job_id=parent_job_id,
                page_number=page_number,
                error=error_message,
                completed_at=datetime.utcnow()
            )
    except Exception as e:
        logger.error(f"[MONITORING] Failed to update stuck page {page_id} in Redis: {e}")

    _purge_source_if_requested(parent_job_id)
    return True


@celery_app.task(name="workers.monitoring.detect_stuck_jobs")
def detect_stuck_jobs():
    """
    Periodic task to detect and mark stuck jobs/pages as failed

    Runs every N minutes (configured in celery_app.py)
    Queries MySQL for jobs/pages that have been "processing" for too long
    """
    if not settings.monitoring_enabled:
        logger.info("Monitoring is disabled - skipping stuck job detection")
        return {"skipped": True}

    logger.info(f"[MONITORING] Starting stuck job detection (threshold: {settings.monitoring_stuck_job_threshold_minutes}min)")

    redis_client = get_redis_client()
    stuck_jobs_count = 0
    stuck_pages_count = 0

    # 1. Detect stuck JOBS
    stuck_jobs = get_stuck_jobs(
        threshold_minutes=settings.monitoring_stuck_job_threshold_minutes,
        batch_size=settings.monitoring_batch_size
    )

    for stuck in stuck_jobs:
        job_id = stuck.id  # loaded by a closed session: only its id is used
        try:
            if _fail_stuck_job(job_id, redis_client):
                stuck_jobs_count += 1
        except Exception as e:
            logger.error(f"[MONITORING] Error processing stuck job {job_id}: {e}")

    # Describe stages whose watchdog chain died: re-armed from the durable marker
    try:
        from workers import figure_tasks

        figure_tasks.sweep(limit=settings.monitoring_batch_size)
    except Exception as e:
        logger.error(f"[MONITORING] Describe-stage sweep failed: {e}")

    # 2. Detect stuck PAGES
    stuck_pages = get_stuck_pages(
        threshold_minutes=settings.monitoring_stuck_job_threshold_minutes,
        batch_size=settings.monitoring_batch_size
    )

    for stuck in stuck_pages:
        page_id = stuck.id
        try:
            if _fail_stuck_page(page_id, redis_client):
                stuck_pages_count += 1
        except Exception as e:
            logger.error(f"[MONITORING] Error processing stuck page {page_id}: {e}")

    logger.info(f"[MONITORING] Stuck job detection complete: {stuck_jobs_count} jobs, {stuck_pages_count} pages marked as failed")

    return {
        "stuck_jobs_detected": stuck_jobs_count,
        "stuck_pages_detected": stuck_pages_count
    }


def _retry_failed_pages_of(job_id: str) -> int:
    """
    Requeue a job's FAILED pages under the retry limit, through the same path as
    the manual and admin retries (shared.page_retry): under the job's row lock, the
    original located first. A job whose original is gone (purge_source) is skipped
    and its pages stay FAILED. Returns how many pages were queued.
    """
    from shared import page_retry
    from shared.iam.remote import remote_use_of
    from shared.job_source import lock_job
    from shared.minio_client import get_minio_client
    from workers.tasks import process_page

    db = SessionLocal()
    try:
        job = lock_job(db, job_id)
        if job is None:
            db.rollback()
            return 0
        pages = [p for p in page_retry.locked_failed_pages(db, job_id)
                 if (p.retry_count or 0) < settings.monitoring_max_retry_count]
        if not pages:
            db.rollback()
            return 0
        try:
            queued, _ = page_retry.requeue_pages(
                db, job, pages, user_id=job.user_id,
                remote_use=remote_use_of(job.user_id, session_factory=SessionLocal),
                enqueue=process_page.delay, celery=celery_app,
                minio_factory=get_minio_client, temp_root=settings.temp_storage_path,
                today_queue=settings.celery_task_default_queue, redis_client=get_redis_client(),
                session_factory=SessionLocal,
            )
        except page_retry.SourceNotAvailable:
            logger.info(f"[MONITORING] Job {job_id}: original deleted, its failed pages cannot be retried")
            return 0
        for page, new_id in queued:
            logger.info(f"[MONITORING] Auto-retrying page {page.page_number} of job {job_id} as {new_id} "
                        f"(retry {page.retry_count}/{settings.monitoring_max_retry_count})")
        return len(queued)
    finally:
        db.close()


@celery_app.task(name="workers.monitoring.auto_retry_failed_pages")
def auto_retry_failed_pages():
    """
    Periodic task to automatically retry failed pages

    Runs every N minutes (configured in celery_app.py)
    Retries pages that failed but haven't exceeded max retry count
    """
    if not settings.monitoring_enabled or not settings.monitoring_auto_retry_enabled:
        logger.info("Auto-retry is disabled - skipping")
        return {"skipped": True}

    logger.info(f"[MONITORING] Starting auto-retry of failed pages (max retries: {settings.monitoring_max_retry_count})")

    retried_count = 0

    # Get failed pages eligible for retry (rows of a closed session: only their
    # job ids are used; each job is re-read under its row lock below)
    failed_pages = get_failed_pages_for_retry(
        max_retry_count=settings.monitoring_max_retry_count,
        batch_size=settings.monitoring_batch_size
    )

    for job_id in dict.fromkeys(page.job_id for page in failed_pages):
        try:
            retried_count += _retry_failed_pages_of(job_id)
        except Exception as e:
            logger.error(f"[MONITORING] Error auto-retrying the failed pages of job {job_id}: {e}")

    logger.info(f"[MONITORING] Auto-retry complete: {retried_count} pages requeued")

    return {
        "pages_retried": retried_count
    }


@celery_app.task(name="workers.monitoring.cleanup_old_jobs")
def cleanup_old_jobs():
    """
    Periodic task to cleanup old completed/failed jobs from Redis

    Runs daily (configured in celery_app.py)
    Removes Redis keys for jobs older than N days to prevent memory bloat
    MySQL records are preserved for historical tracking
    """
    if not settings.monitoring_enabled:
        logger.info("Monitoring is disabled - skipping cleanup")
        return {"skipped": True}

    logger.info(f"[MONITORING] Starting cleanup of old jobs (>{settings.monitoring_cleanup_days} days)")

    redis_client = get_redis_client()
    cleaned_count = 0

    # Get old completed/failed jobs
    old_jobs = get_old_completed_jobs(
        days_old=settings.monitoring_cleanup_days,
        batch_size=settings.monitoring_batch_size
    )

    for job in old_jobs:
        try:
            # Key names must match those written by RedisClient (shared/redis_client.py).
            # Note: page status lives at job:{id}:page:{n}, NOT job:{id}:page:{n}:status.
            keys_to_delete = [
                f"job:{job.id}:status",
                f"job:{job.id}:result",
                f"job:{job.id}:pages:total",
                f"job:{job.id}:owner",
            ]

            if job.total_pages and job.total_pages > 1:
                for page_num in range(1, job.total_pages + 1):
                    keys_to_delete.append(f"job:{job.id}:page:{page_num}")
                    keys_to_delete.append(f"job:{job.id}:page:{page_num}:result")

            try:
                redis_client.client.delete(*keys_to_delete)
            except Exception as e:
                # Do not count this job as cleaned - it must be retried on the next run.
                logger.error(f"[MONITORING] Error deleting Redis keys for job {job.id}: {e}")
                continue

            # Drop the job from the owner's index set so it does not leak entries.
            if job.user_id:
                redis_client.remove_job_from_user(job.user_id, job.id)

            logger.debug(f"[MONITORING] Cleaned up Redis keys for job {job.id} (completed {job.completed_at})")
            cleaned_count += 1

        except Exception as e:
            logger.error(f"[MONITORING] Error cleaning up job {job.id}: {e}")

    images_swept = sweep_orphaned_vision_images()

    logger.info(f"[MONITORING] Cleanup complete: {cleaned_count} jobs cleaned from Redis")

    return {
        "jobs_cleaned": cleaned_count,
        "vision_images_swept": images_swept,
    }


# The floor for how long an orphan must sit before it is swept. Deleting a file
# a running inference still needs would be a far worse bug than leaving it a few
# extra minutes, so this is deliberately far above any legitimate hold time
# (`vision_task_timeout_seconds`, 120s by default).
VISION_IMAGE_ORPHAN_MIN_AGE_SECONDS = 3600


def sweep_orphaned_vision_images() -> int:
    """
    Delete image handoff directories that nobody is coming back for.

    A BACKSTOP, not the mechanism. `/images/*` writes the image to
    `<temp_storage_path>/images/<job_id>/` and the vision task deletes it in a
    `finally`, so in every ordinary outcome - success, typed failure, crash,
    soft time limit - it is already gone before this ever runs. What is left for
    here is the case where that `finally` never executed at all: a HARD time
    limit or an OOM killing the worker process mid-inference, or a message that
    was dispatched and never delivered.

    This is explicitly NOT a fix for an upload loop: it runs daily, and a caller
    in a tight loop fills the disk in minutes. The bound on that is the task's
    own cleanup.

    Returns:
        The number of directories removed.
    """
    from workers.vision.image_input import sweep_image_handoffs

    max_age = max(
        settings.vision_task_timeout_seconds * 4,
        VISION_IMAGE_ORPHAN_MIN_AGE_SECONDS,
    )
    swept = sweep_image_handoffs(settings.temp_storage_path, max_age)
    if swept:
        logger.warning(
            f"[MONITORING] Swept {swept} orphaned vision image handoff(s) older than "
            f"{max_age}s. Each one is a vision task that died before its cleanup ran."
        )
    return swept


@celery_app.task(name="workers.monitoring.cleanup_stale_files")
def cleanup_stale_files():
    """
    Periodic task to delete leftover local files

    Completed jobs delete their files right away; this removes what is left
    behind by jobs that failed for good, crashed workers and aborted uploads
    (staging files), once older than TEMP_FILES_RETENTION_HOURS. The originals
    stay in MinIO.
    """
    return remove_stale_temp_files(
        Path(settings.temp_storage_path),
        max_age_seconds=settings.temp_files_retention_hours * 3600,
        is_job_active=_is_job_active,
    )


_ACTIVE_JOB_STATUSES = (JobStatus.PENDING, JobStatus.PROCESSING)


def _is_job_active(job_id: str) -> bool:
    """True if the job is still queued or processing (its files are still needed)"""
    db = SessionLocal()
    try:
        row = db.query(Job.status).filter(Job.id == job_id).first()
        return row is not None and row[0] in _ACTIVE_JOB_STATUSES
    finally:
        db.close()


_APP_ENTRY_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def remove_stale_temp_files(base: Path, max_age_seconds: int, now: float = None, is_job_active=None) -> dict:
    """
    Delete entries under the temp storage that were not modified for max_age_seconds.

    Job directories of jobs that are still queued/processing are kept (e.g. a long
    worker backlog), since the worker reads the upload from disk. If the job state
    can't be checked, the directory is kept too.
    """
    now = now if now is not None else time.time()
    removed = 0
    staging_dirs = {base / "uploads" / ".staging", base / "audio" / ".staging"}

    # {temp}/{job_id}/ work dirs, {temp}/uploads/{job_id}/, {temp}/audio/{job_id}/
    # and the per-request staging files in {temp}/uploads|audio/.staging/
    containers = [base, base / "uploads", base / "audio", base / "uploads" / ".staging", base / "audio" / ".staging"]
    keep = {base / "uploads", base / "audio", base / "uploads" / ".staging", base / "audio" / ".staging"}

    for container in containers:
        if not container.is_dir():
            continue
        for entry in container.iterdir():
            # Only touch what this app creates (named after job IDs / request UUIDs), so a
            # TEMP_STORAGE_PATH shared with other software (e.g. /tmp) is never swept
            if entry in keep or not _APP_ENTRY_NAME.match(entry.name):
                continue
            try:
                if now - entry.stat().st_mtime < max_age_seconds:
                    continue
                if container not in staging_dirs and is_job_active is not None:
                    job_id = _APP_ENTRY_NAME.match(entry.name).group(0)
                    try:
                        if is_job_active(job_id):
                            continue
                    except Exception as e:
                        logger.warning(f"[MONITORING] Could not check job {job_id}, keeping {entry}: {e}")
                        continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed += 1
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.error(f"[MONITORING] Could not remove stale file {entry}: {e}")

    logger.info(f"[MONITORING] Removed {removed} stale temp entries from {base}")
    return {"removed": removed}


@celery_app.task(name="workers.monitoring.check_broker_unacked")
def check_broker_unacked():
    """
    Flag broker messages left unacknowledged by a worker that died.

    With acks_late, a message stays in the broker's `unacked` hash while its task
    runs; if the worker dies (container recreated, OOM), it only returns to its queue
    after the visibility timeout - hours. A message no live worker reports holding,
    seen on two consecutive checks and older than the grace period, is orphaned:
    logged as an error and listed for admins, who can put it back on its queue
    (POST /admin/broker/unacked/{delivery_tag}/requeue). Never requeued here: a
    worker that merely failed to answer the inspect would then run the task twice.
    """
    from shared import broker_unacked

    inspect = celery_app.control.inspect(timeout=5)
    live = broker_unacked.live_task_ids(inspect)
    messages = broker_unacked.list_unacked(broker_unacked.broker_client())

    cache = get_redis_client().client
    previous = {}
    try:
        previous = json.loads(cache.get(broker_unacked.REPORT_KEY) or "{}")
    except (ValueError, TypeError):
        pass

    if live is None:
        logger.warning(
            f"[MONITORING] No worker answered the inspect; skipping the check of "
            f"{len(messages)} unacked broker messages"
        )
        return {"unacked": len(messages), "orphans": 0, "skipped": True}

    suspects = broker_unacked.find_orphans(messages, live, settings.monitoring_unacked_grace_seconds)
    seen_before = set(previous.get("suspect_task_ids") or [])
    orphans = [m for m in suspects if m.task_id in seen_before]

    for m in orphans:
        logger.error(
            f"[MONITORING] Orphaned broker message: task {m.task_name} id={m.task_id} "
            f"job={m.job_id} queue={m.queue} unacked for {m.age_seconds:.0f}s with no live worker "
            f"holding it; requeue with POST /admin/broker/unacked/{m.delivery_tag}/requeue"
        )

    report = {
        "checked_at": datetime.utcnow().isoformat(),
        "unacked_total": len(messages),
        "visibility_timeout_seconds": settings.celery_visibility_timeout_seconds,
        "suspect_task_ids": [m.task_id for m in suspects if m.task_id],
        "orphans": [m.to_dict() for m in orphans],
    }
    cache.set(broker_unacked.REPORT_KEY, json.dumps(report), ex=3600)
    return {"unacked": len(messages), "orphans": len(orphans), "skipped": False}


@celery_app.task(name="workers.monitoring.health_check")
def health_check():
    """
    Periodic health check task to verify monitoring system is working

    This task just logs that it ran - useful for verifying Celery Beat is functioning
    """
    logger.info("[MONITORING] Health check - monitoring system is operational")
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }
