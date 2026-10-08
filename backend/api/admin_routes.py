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
import json
import logging

from shared.config import get_settings
from shared.queries import (
    get_stuck_jobs,
    get_stuck_pages,
    get_failed_pages_for_retry,
    get_system_stats,
)
from shared.models import Job, Page, JobStatus
from shared.database import SessionLocal, get_db
from sqlalchemy.orm import Session
from shared.redis_client import get_redis_client
from shared.auth import get_current_active_user
from shared.iam.decide import is_bootstrap_admin
from api.iam_deps import require
from workers.monitoring import detect_stuck_jobs, auto_retry_failed_pages, cleanup_old_jobs
from uuid import uuid4

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/admin", tags=["Admin & Monitoring"])


def require_admin(current_user=Depends(get_current_active_user)):
    """
    Dependency that restricts an endpoint to administrators.

    Only the 0009 engine routes still use it (spec 0014 §2); every route of this
    module declares its platform permission with `require(...)` (§4.7), decided
    by `shared.iam` under IAM_MODE. Removed in 0014 §8 item 7.

    The rule is bootstrap (`shared.iam.decide.is_bootstrap_admin`): the admin
    column set with scripts/make_admin.py, or an ID listed in ADMIN_USER_IDS
    (comma-separated). Both default to nobody.

    Raises:
        HTTPException 403: If the authenticated user is not an admin
    """
    if not is_bootstrap_admin(current_user, settings):
        logger.warning(f"[ADMIN] Access denied for user {current_user.id}")
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: privilégios de administrador necessários"
        )
    return current_user


@router.get("/stats", summary="Estatísticas do sistema")
async def get_stats(admin_user=Depends(require("platform.stats.read"))) -> Dict[str, Any]:
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
            redis_info = redis_client.client.info()
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
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@router.get("/jobs/stuck", summary="Listar jobs travados")
async def list_stuck_jobs(
    threshold_minutes: int = None,
    limit: int = 100,
    admin_user=Depends(require("platform.jobs.read"))
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
        raise HTTPException(status_code=500, detail="Failed to list stuck jobs")


@router.post("/jobs/recover-stuck", summary="Recuperar jobs travados")
async def recover_stuck_jobs(
    threshold_minutes: int = None,
    admin_user=Depends(require("platform.jobs.recover"))
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
        raise HTTPException(status_code=500, detail="Failed to recover stuck jobs")


@router.post("/jobs/{job_id}/retry-all-failed", summary="Refazer todas as páginas com falha de um job")
async def retry_all_failed_pages(
    job_id: str,
    admin_user=Depends(require("platform.jobs.recover")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retry all failed pages of a specific job

    Requeues every FAILED page still under the retry limit
    (`MONITORING_MAX_RETRY_COUNT`), exactly like the per-page retry
    (`POST /jobs/{job_id}/pages/{n}/retry`): the original PDF is located first,
    then the pages become pending and the job processing, under the job's row
    lock (the same lock the source purge takes).

    Returns:
        Number of pages queued for retry

    Errors:
        404: job not found
        409 `SOURCE_NOT_AVAILABLE`: the original was deleted (purge_source /
        DELETE /jobs/{id}/source); nothing was changed
    """
    from shared import error_catalog, page_retry
    from shared.iam.remote import remote_use_of
    from shared.job_source import lock_job
    from shared.minio_client import get_minio_client
    from workers.celery_app import celery_app
    from workers.tasks import process_page

    logger.info(f"[ADMIN] Bulk retry requested for job {job_id} by {admin_user.email}")
    try:
        job = lock_job(db, job_id)
        if job is None:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        total_pages = db.query(Page).filter(Page.job_id == job_id).count()
        failed_pages = page_retry.locked_failed_pages(db, job_id)

        if not failed_pages:
            db.rollback()
            return {
                "success": True,
                "message": "No failed pages found for this job",
                "pages_retried": 0,
            }

        retryable_pages = [p for p in failed_pages if (p.retry_count or 0) < settings.monitoring_max_retry_count]
        if not retryable_pages:
            db.rollback()
            return {
                "success": False,
                "message": "All failed pages have exceeded max retry count",
                "pages_failed": len(failed_pages),
                "max_retry_count": settings.monitoring_max_retry_count,
            }

        try:
            queued, failed = page_retry.requeue_pages(
                db, job, retryable_pages, user_id=job.user_id,
                remote_use=remote_use_of(job.user_id, session_factory=SessionLocal),
                enqueue=process_page.delay, celery=celery_app,
                minio_factory=lambda: get_minio_client(), temp_root=settings.temp_storage_path,
                today_queue=settings.celery_task_default_queue, redis_client=get_redis_client(),
                session_factory=SessionLocal,
            )
        except page_retry.SourceNotAvailable:
            raise HTTPException(status_code=409, detail=error_catalog.detail("SOURCE_NOT_AVAILABLE"))

        for page, new_id in queued:
            logger.info(f"[ADMIN] Page {page.page_number} of job {job_id} requeued as {new_id} "
                        f"(retry {page.retry_count}/{settings.monitoring_max_retry_count})")
        return {
            "success": bool(queued),
            "job_id": job_id,
            "total_pages": total_pages,
            "failed_pages": len(failed_pages),
            "retryable_pages": len(retryable_pages),
            "pages_retried": len(queued),
            "page_job_ids": {page.page_number: new_id for page, new_id in queued},
            "errors": [f"Page {page.page_number}: {error}" for page, error in failed] or None,
            "triggered_by": admin_user.email,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error bulk retrying pages for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry pages")


@router.post("/cleanup", summary="Limpar jobs antigos")
async def trigger_cleanup(
    days_old: int = None,
    admin_user=Depends(require("platform.jobs.cleanup"))
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
        raise HTTPException(status_code=500, detail="Failed to cleanup")


@router.get("/health/monitoring", summary="Saúde do monitoramento")
async def monitoring_health(admin_user=Depends(require("platform.monitoring.read"))) -> Dict[str, Any]:
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
        raise HTTPException(status_code=500, detail="Failed to check health")


@router.get("/broker/unacked", summary="Listar mensagens não confirmadas do broker")
async def list_broker_unacked(admin_user=Depends(require("platform.monitoring.read"))) -> Dict[str, Any]:
    """
    Messages the Celery broker holds as delivered but not yet acknowledged.

    Each one is either a task running now or one whose worker died - the latter only
    returns to its queue after CELERY_VISIBILITY_TIMEOUT_SECONDS (hours). `orphans` is
    the latest check by workers.monitoring.check_broker_unacked: messages no live
    worker held on two consecutive checks. Requeue one with
    POST /admin/broker/unacked/{delivery_tag}/requeue.
    """
    from starlette.concurrency import run_in_threadpool
    from shared import broker_unacked

    messages = await run_in_threadpool(lambda: broker_unacked.list_unacked(broker_unacked.broker_client()))
    report = get_redis_client().client.get(broker_unacked.REPORT_KEY)
    return {
        "visibility_timeout_seconds": settings.celery_visibility_timeout_seconds,
        "unacked": [m.to_dict() for m in messages],
        "last_check": json.loads(report) if report else None,
    }


@router.post("/broker/unacked/{delivery_tag}/requeue", summary="Reenfileirar mensagem órfã do broker")
async def requeue_broker_unacked(delivery_tag: str, admin_user=Depends(require("platform.broker.requeue"))) -> Dict[str, Any]:
    """
    Put an orphaned message back at the head of its queue, so its task runs again now
    instead of after the visibility timeout.

    Refused (409) unless the latest monitoring check flagged it as orphaned AND no
    worker reports holding it right now - otherwise a task still running would run
    twice.
    """
    from starlette.concurrency import run_in_threadpool
    from shared import broker_unacked
    from workers.celery_app import celery_app

    report = json.loads(get_redis_client().client.get(broker_unacked.REPORT_KEY) or "{}")
    flagged = {o["delivery_tag"]: o for o in report.get("orphans") or []}
    if delivery_tag not in flagged:
        raise HTTPException(
            status_code=409,
            detail="Not flagged as orphaned by the latest monitoring check; wait for the next check",
        )

    live = await run_in_threadpool(
        lambda: broker_unacked.live_task_ids(celery_app.control.inspect(timeout=5))
    )
    if live is None:
        raise HTTPException(status_code=409, detail="No worker answered; cannot confirm the task is not running")
    if flagged[delivery_tag].get("task_id") in live:
        raise HTTPException(status_code=409, detail="A worker is holding this task now; not requeued")

    if not await run_in_threadpool(lambda: broker_unacked.requeue(broker_unacked.broker_client(), delivery_tag)):
        raise HTTPException(status_code=404, detail="No longer unacknowledged (acked or already restored)")

    logger.warning(
        f"[ADMIN] Requeued orphaned broker message {delivery_tag} "
        f"(task {flagged[delivery_tag].get('task_id')}, job {flagged[delivery_tag].get('job_id')})"
    )
    return {"requeued": True, **flagged[delivery_tag]}
