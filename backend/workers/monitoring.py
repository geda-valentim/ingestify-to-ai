"""
Monitoring and recovery tasks for stuck/failed jobs

These periodic tasks run via Celery Beat to automatically detect and recover from failures.
"""

from datetime import datetime, timedelta
import logging
from uuid import uuid4

from workers.celery_app import celery_app
from workers.tasks import convert_page_task
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

    for job in stuck_jobs:
        try:
            error_message = f"Job stuck in processing for >{settings.monitoring_stuck_job_threshold_minutes} minutes - marked as failed by monitoring system"

            # Update MySQL
            db = SessionLocal()
            try:
                job.status = JobStatus.FAILED
                job.error_message = error_message
                job.completed_at = datetime.utcnow()
                db.commit()
                logger.info(f"[MONITORING] Marked stuck job {job.id} as failed (processing since {job.started_at})")
            except Exception as e:
                logger.error(f"[MONITORING] Failed to update stuck job {job.id} in MySQL: {e}")
                db.rollback()
            finally:
                db.close()

            # Update Redis
            try:
                redis_client.set_job_status(
                    job_id=job.id,
                    job_type=job.job_type or "main",
                    status="failed",
                    progress=0,
                    error=error_message,
                    completed_at=datetime.utcnow()
                )
            except Exception as e:
                logger.error(f"[MONITORING] Failed to update stuck job {job.id} in Redis: {e}")

            stuck_jobs_count += 1

        except Exception as e:
            logger.error(f"[MONITORING] Error processing stuck job {job.id}: {e}")

    # 2. Detect stuck PAGES
    stuck_pages = get_stuck_pages(
        threshold_minutes=settings.monitoring_stuck_job_threshold_minutes,
        batch_size=settings.monitoring_batch_size
    )

    for page in stuck_pages:
        try:
            error_message = f"Page stuck in processing for >{settings.monitoring_stuck_job_threshold_minutes} minutes - marked as failed by monitoring system"

            # Update MySQL
            db = SessionLocal()
            try:
                page.status = JobStatus.FAILED
                page.error_message = error_message
                page.completed_at = datetime.utcnow()
                db.commit()

                # Update parent job failed count
                parent_job = db.query(Job).filter(Job.id == page.job_id).first()
                if parent_job:
                    failed_count = db.query(Page).filter(
                        Page.job_id == page.job_id,
                        Page.status == JobStatus.FAILED
                    ).count()
                    parent_job.pages_failed = failed_count
                    db.commit()

                logger.info(f"[MONITORING] Marked stuck page {page.page_number} of job {page.job_id} as failed")
            except Exception as e:
                logger.error(f"[MONITORING] Failed to update stuck page {page.id} in MySQL: {e}")
                db.rollback()
            finally:
                db.close()

            # Update Redis
            try:
                if page.page_job_id:
                    redis_client.set_job_status(
                        job_id=page.page_job_id,
                        job_type="page",
                        status="failed",
                        parent_job_id=page.job_id,
                        page_number=page.page_number,
                        error=error_message,
                        completed_at=datetime.utcnow()
                    )
            except Exception as e:
                logger.error(f"[MONITORING] Failed to update stuck page {page.id} in Redis: {e}")

            stuck_pages_count += 1

        except Exception as e:
            logger.error(f"[MONITORING] Error processing stuck page {page.id}: {e}")

    logger.info(f"[MONITORING] Stuck job detection complete: {stuck_jobs_count} jobs, {stuck_pages_count} pages marked as failed")

    return {
        "stuck_jobs_detected": stuck_jobs_count,
        "stuck_pages_detected": stuck_pages_count
    }


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

    # Get failed pages eligible for retry
    failed_pages = get_failed_pages_for_retry(
        max_retry_count=settings.monitoring_max_retry_count,
        batch_size=settings.monitoring_batch_size
    )

    for page in failed_pages:
        try:
            logger.info(f"[MONITORING] Auto-retrying page {page.page_number} of job {page.job_id} (retry {page.retry_count + 1}/{settings.monitoring_max_retry_count})")

            # Increment retry count in MySQL
            db = SessionLocal()
            try:
                page.retry_count += 1
                page.status = JobStatus.PENDING  # Reset to pending
                page.error_message = None
                db.commit()
            except Exception as e:
                logger.error(f"[MONITORING] Failed to update retry count for page {page.id}: {e}")
                db.rollback()
                continue
            finally:
                db.close()

            # Queue the page conversion task again
            if page.minio_page_path:
                # We need the actual file path, which we can reconstruct from MinIO path
                # OR we trigger a new page conversion task
                # For now, we'll create a new page job ID and queue it

                new_page_job_id = str(uuid4())

                # Update page_job_id in MySQL
                db = SessionLocal()
                try:
                    page.page_job_id = new_page_job_id
                    db.commit()
                except Exception as e:
                    logger.error(f"[MONITORING] Failed to update page_job_id: {e}")
                    db.rollback()
                    continue
                finally:
                    db.close()

                # Download page from MinIO and queue conversion
                # Note: This requires the page file to exist in MinIO or temp storage
                # For now, we'll log that manual intervention is needed
                logger.warning(
                    f"[MONITORING] Page {page.page_number} of job {page.job_id} requires manual retry - "
                    f"automatic retry from MinIO not yet implemented. "
                    f"Use POST /admin/jobs/{page.job_id}/pages/{page.page_number}/retry"
                )

                # TODO: Implement automatic page retrieval from MinIO and re-queuing
                # This would require:
                # 1. Download page PDF from MinIO using page.minio_page_path
                # 2. Save to temp location
                # 3. Queue convert_page_task with the file path

            retried_count += 1

        except Exception as e:
            logger.error(f"[MONITORING] Error auto-retrying page {page.id}: {e}")

    logger.info(f"[MONITORING] Auto-retry complete: {retried_count} pages marked for retry")

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
            # Delete Redis keys for this job
            # Pattern: job:{job_id}:*
            keys_to_delete = [
                f"job:{job.id}:status",
                f"job:{job.id}:result",
                f"job:{job.id}:pages",
                f"job:{job.id}:child_jobs",
            ]

            for key in keys_to_delete:
                try:
                    redis_client.redis.delete(key)
                except Exception as e:
                    logger.error(f"[MONITORING] Error deleting Redis key {key}: {e}")

            # Also delete page keys if this was a multi-page job
            if job.total_pages and job.total_pages > 1:
                for page_num in range(1, job.total_pages + 1):
                    try:
                        redis_client.redis.delete(f"job:{job.id}:page:{page_num}:status")
                        redis_client.redis.delete(f"job:{job.id}:page:{page_num}:result")
                    except Exception as e:
                        logger.error(f"[MONITORING] Error deleting page {page_num} keys: {e}")

            logger.debug(f"[MONITORING] Cleaned up Redis keys for job {job.id} (completed {job.completed_at})")
            cleaned_count += 1

        except Exception as e:
            logger.error(f"[MONITORING] Error cleaning up job {job.id}: {e}")

    logger.info(f"[MONITORING] Cleanup complete: {cleaned_count} jobs cleaned from Redis")

    return {
        "jobs_cleaned": cleaned_count
    }


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
