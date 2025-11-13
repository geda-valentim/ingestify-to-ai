"""
Admin routes for monitoring and recovery

These endpoints provide system administrators with tools to:
- View system statistics
- Manually trigger recovery tasks
- Monitor stuck jobs
- Bulk retry failed pages
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from datetime import datetime
import logging

from shared.config import get_settings
from shared.queries import (
    get_stuck_jobs,
    get_stuck_pages,
    get_failed_pages_for_retry,
    get_system_stats,
    get_job_with_pages,
)
from shared.models import Job, Page, JobStatus
from shared.database import SessionLocal
from shared.redis_client import get_redis_client
from shared.auth import get_current_active_user
from workers.monitoring import detect_stuck_jobs, auto_retry_failed_pages, cleanup_old_jobs
from workers.tasks import convert_page_task
from uuid import uuid4

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/admin", tags=["Admin & Monitoring"])


# Simple admin check (you can enhance this with proper role-based auth)
def require_admin(current_user=Depends(get_current_active_user)):
    """
    Dependency to check if user is admin
    For now, all authenticated users are considered admins
    TODO: Add is_admin field to User model and check it here
    """
    return current_user


@router.get("/stats", summary="Get system statistics")
async def get_stats(admin_user=Depends(require_admin)) -> Dict[str, Any]:
    """
    Get comprehensive system statistics for monitoring dashboard

    Returns counts of jobs/pages by status, stuck jobs, etc.
    Useful for building admin dashboards and monitoring tools.
    """
    try:
        stats = get_system_stats()

        # Add Redis info
        redis_client = get_redis_client()
        try:
            redis_info = redis_client.redis.info()
            stats["redis"] = {
                "connected_clients": redis_info.get("connected_clients", 0),
                "used_memory_human": redis_info.get("used_memory_human", "unknown"),
                "uptime_days": redis_info.get("uptime_in_days", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            stats["redis"] = {"error": str(e)}

        # Add monitoring config
        stats["monitoring_config"] = {
            "enabled": settings.monitoring_enabled,
            "stuck_threshold_minutes": settings.monitoring_stuck_job_threshold_minutes,
            "auto_retry_enabled": settings.monitoring_auto_retry_enabled,
            "max_retry_count": settings.monitoring_max_retry_count,
            "check_interval_minutes": settings.monitoring_check_interval_minutes,
        }

        return stats

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


@router.get("/jobs/stuck", summary="List stuck jobs")
async def list_stuck_jobs(
    threshold_minutes: int = None,
    limit: int = 100,
    admin_user=Depends(require_admin)
) -> Dict[str, Any]:
    """
    List all jobs currently stuck in processing state

    Args:
        threshold_minutes: Override default threshold (from config if not specified)
        limit: Maximum number of jobs to return

    Returns:
        List of stuck jobs with details
    """
    try:
        threshold = threshold_minutes or settings.monitoring_stuck_job_threshold_minutes

        stuck_jobs = get_stuck_jobs(threshold_minutes=threshold, batch_size=limit)
        stuck_pages = get_stuck_pages(threshold_minutes=threshold, batch_size=limit)

        return {
            "threshold_minutes": threshold,
            "stuck_jobs_count": len(stuck_jobs),
            "stuck_pages_count": len(stuck_pages),
            "stuck_jobs": [
                {
                    "job_id": job.id,
                    "filename": job.filename,
                    "status": job.status.value,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "total_pages": job.total_pages,
                    "pages_completed": job.pages_completed,
                    "pages_failed": job.pages_failed,
                }
                for job in stuck_jobs
            ],
            "stuck_pages": [
                {
                    "page_id": page.id,
                    "job_id": page.job_id,
                    "page_number": page.page_number,
                    "page_job_id": page.page_job_id,
                    "status": page.status.value,
                    "created_at": page.created_at.isoformat() if page.created_at else None,
                    "retry_count": page.retry_count,
                }
                for page in stuck_pages
            ],
        }

    except Exception as e:
        logger.error(f"Error listing stuck jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list stuck jobs: {str(e)}")


@router.post("/jobs/recover-stuck", summary="Manually trigger stuck job recovery")
async def recover_stuck_jobs(
    threshold_minutes: int = None,
    admin_user=Depends(require_admin)
) -> Dict[str, Any]:
    """
    Manually trigger the stuck job detection and recovery process

    This runs the same logic as the periodic monitoring task,
    but can be triggered on-demand by administrators.

    Args:
        threshold_minutes: Override default threshold (from config if not specified)

    Returns:
        Number of jobs/pages marked as failed
    """
    try:
        logger.info(f"[ADMIN] Manual stuck job recovery triggered by {admin_user.email}")

        # Temporarily override threshold if specified
        original_threshold = settings.monitoring_stuck_job_threshold_minutes
        if threshold_minutes:
            settings.monitoring_stuck_job_threshold_minutes = threshold_minutes

        # Run the monitoring task synchronously
        result = detect_stuck_jobs()

        # Restore original threshold
        if threshold_minutes:
            settings.monitoring_stuck_job_threshold_minutes = original_threshold

        return {
            "success": True,
            "jobs_recovered": result.get("stuck_jobs_detected", 0),
            "pages_recovered": result.get("stuck_pages_detected", 0),
            "triggered_by": admin_user.email,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error recovering stuck jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to recover stuck jobs: {str(e)}")


@router.post("/jobs/{job_id}/retry-all-failed", summary="Bulk retry all failed pages of a job")
async def retry_all_failed_pages(
    job_id: str,
    admin_user=Depends(require_admin)
) -> Dict[str, Any]:
    """
    Retry all failed pages of a specific job

    This is useful when multiple pages failed due to temporary issues
    and you want to retry them all at once instead of individually.

    Args:
        job_id: The job ID whose failed pages should be retried

    Returns:
        Number of pages queued for retry
    """
    try:
        logger.info(f"[ADMIN] Bulk retry requested for job {job_id} by {admin_user.email}")

        # Get job and all its pages
        result = get_job_with_pages(job_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job, pages = result

        # Find failed pages
        failed_pages = [p for p in pages if p.status == JobStatus.FAILED]

        if not failed_pages:
            return {
                "success": True,
                "message": "No failed pages found for this job",
                "pages_retried": 0,
            }

        # Check retry limits
        retryable_pages = [
            p for p in failed_pages
            if p.retry_count < settings.monitoring_max_retry_count
        ]

        if not retryable_pages:
            return {
                "success": False,
                "message": "All failed pages have exceeded max retry count",
                "pages_failed": len(failed_pages),
                "max_retry_count": settings.monitoring_max_retry_count,
            }

        # Queue retry tasks for each page
        retried_count = 0
        errors = []

        for page in retryable_pages:
            try:
                # Increment retry count
                db = SessionLocal()
                try:
                    page.retry_count += 1
                    page.status = JobStatus.PENDING
                    page.error_message = None
                    db.commit()
                except Exception as e:
                    logger.error(f"Failed to update page {page.id}: {e}")
                    db.rollback()
                    errors.append(f"Page {page.page_number}: {str(e)}")
                    continue
                finally:
                    db.close()

                # Note: Actual re-queuing requires page file from MinIO
                # For now, we just mark as pending and log
                logger.warning(
                    f"[ADMIN] Page {page.page_number} of job {job_id} marked for retry "
                    f"(retry {page.retry_count}/{settings.monitoring_max_retry_count}). "
                    f"Use individual page retry endpoint to actually re-queue."
                )

                retried_count += 1

            except Exception as e:
                logger.error(f"Error retrying page {page.id}: {e}")
                errors.append(f"Page {page.page_number}: {str(e)}")

        return {
            "success": True,
            "job_id": job_id,
            "total_pages": len(pages),
            "failed_pages": len(failed_pages),
            "retryable_pages": len(retryable_pages),
            "pages_marked_for_retry": retried_count,
            "errors": errors if errors else None,
            "triggered_by": admin_user.email,
            "note": "Pages marked as pending. Use individual page retry endpoints to re-queue with file download.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk retrying pages for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry pages: {str(e)}")


@router.post("/cleanup", summary="Manually trigger cleanup of old jobs")
async def trigger_cleanup(
    days_old: int = None,
    admin_user=Depends(require_admin)
) -> Dict[str, Any]:
    """
    Manually trigger cleanup of old completed/failed jobs from Redis

    Args:
        days_old: Override default days threshold (from config if not specified)

    Returns:
        Number of jobs cleaned up
    """
    try:
        logger.info(f"[ADMIN] Manual cleanup triggered by {admin_user.email}")

        # Temporarily override days if specified
        original_days = settings.monitoring_cleanup_days
        if days_old:
            settings.monitoring_cleanup_days = days_old

        # Run cleanup task synchronously
        result = cleanup_old_jobs()

        # Restore original setting
        if days_old:
            settings.monitoring_cleanup_days = original_days

        return {
            "success": True,
            "jobs_cleaned": result.get("jobs_cleaned", 0),
            "days_threshold": days_old or original_days,
            "triggered_by": admin_user.email,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error during manual cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup: {str(e)}")


@router.get("/health/monitoring", summary="Check monitoring system health")
async def monitoring_health(admin_user=Depends(require_admin)) -> Dict[str, Any]:
    """
    Check if the monitoring system (Celery Beat) is functioning

    Returns information about scheduled tasks and their last run times
    """
    try:
        from workers.celery_app import celery_app

        # Try to get beat schedule
        beat_schedule = celery_app.conf.beat_schedule if settings.monitoring_enabled else {}

        # Try to inspect scheduled tasks
        try:
            inspect = celery_app.control.inspect()
            scheduled = inspect.scheduled()
            active = inspect.active()
            registered = inspect.registered()
        except Exception as e:
            logger.warning(f"Could not inspect Celery: {e}")
            scheduled = {}
            active = {}
            registered = {}

        return {
            "monitoring_enabled": settings.monitoring_enabled,
            "beat_schedule_configured": len(beat_schedule) > 0,
            "scheduled_tasks": list(beat_schedule.keys()) if beat_schedule else [],
            "workers_online": len(scheduled) if scheduled else 0,
            "registered_tasks": registered,
            "celery_status": "healthy" if scheduled or active else "unknown",
        }

    except Exception as e:
        logger.error(f"Error checking monitoring health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")
