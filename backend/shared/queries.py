"""
Database query helpers for monitoring and recovery
"""

from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import func, and_, exists, or_
from sqlalchemy.orm import Session

from shared.models import Job, Page, JobStatus
from shared.database import SessionLocal
import logging

logger = logging.getLogger(__name__)


# A routed job whose attempt still heartbeats is long, not stuck (spec 0003, Appendix J):
# a 3 h transcription outlives the stuck threshold. Its own sweeper recovers it if
# the worker dies. Jobs with no usage row - every job without a route - are unaffected.
LIVE_USAGE_HEARTBEAT_SECONDS = 600


def _has_live_engine_usage():
    from shared.models import EngineUsage

    recent = datetime.utcnow() - timedelta(seconds=LIVE_USAGE_HEARTBEAT_SECONDS)
    return exists().where(
        EngineUsage.job_id == Job.id,
        EngineUsage.status.in_(("reserved", "spawning", "running")),
        EngineUsage.heartbeat_at >= recent,
    )


def _has_open_backlog_items():
    """A split job whose routed pages wait in the backlog is queued, not stuck (spec 0003, slice 8)"""
    from shared.models import JobDispatch

    return exists().where(
        JobDispatch.job_id == Job.id,
        JobDispatch.state.in_(("probing", "waiting", "assigned", "running", "bypassed")),
    )


def _page_has_live_engine_usage():
    from shared.models import EngineUsage

    recent = datetime.utcnow() - timedelta(seconds=LIVE_USAGE_HEARTBEAT_SECONDS)
    return exists().where(
        EngineUsage.subject_type == "page",
        EngineUsage.subject_id == Page.page_job_id,
        EngineUsage.status.in_(("reserved", "spawning", "running")),
        EngineUsage.heartbeat_at >= recent,
    )


def get_stuck_jobs(
    threshold_minutes: int = 30,
    batch_size: int = 100
) -> List[Job]:
    """
    Query MySQL for jobs stuck in "processing" state longer than threshold

    Args:
        threshold_minutes: Jobs processing longer than this are considered stuck
        batch_size: Maximum number of jobs to return

    Returns:
        List of Job objects that are stuck
    """
    db = SessionLocal()
    try:
        threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)

        stuck_jobs = db.query(Job).filter(
            and_(
                Job.status == JobStatus.PROCESSING,
                Job.started_at.isnot(None),
                # A describe stage (describe_images / ocr_images) is judged by its
                # heartbeat, refreshed by every figure, not by when the job started
                func.coalesce(Job.figures_stage_at, Job.started_at) < threshold_time,
                ~_has_live_engine_usage(),
                ~_has_open_backlog_items(),
            )
        ).limit(batch_size).all()

        logger.info(f"Found {len(stuck_jobs)} stuck jobs (threshold: {threshold_minutes}min)")
        return stuck_jobs

    except Exception as e:
        logger.error(f"Error querying stuck jobs: {e}")
        return []
    finally:
        db.close()


def get_stuck_pages(
    threshold_minutes: int = 30,
    batch_size: int = 100
) -> List[Page]:
    """
    Query MySQL for pages stuck in "processing" state longer than threshold

    Args:
        threshold_minutes: Pages processing longer than this are considered stuck
        batch_size: Maximum number of pages to return

    Returns:
        List of Page objects that are stuck
    """
    db = SessionLocal()
    try:
        threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)

        stuck_pages = db.query(Page).filter(
            and_(
                Page.status == JobStatus.PROCESSING,
                Page.created_at < threshold_time,  # Pages don't have started_at
                ~_page_has_live_engine_usage(),  # a routed page still heartbeating is running, not stuck
            )
        ).limit(batch_size).all()

        logger.info(f"Found {len(stuck_pages)} stuck pages (threshold: {threshold_minutes}min)")
        return stuck_pages

    except Exception as e:
        logger.error(f"Error querying stuck pages: {e}")
        return []
    finally:
        db.close()


def get_failed_pages_for_retry(
    max_retry_count: int = 3,
    batch_size: int = 100
) -> List[Page]:
    """
    Query MySQL for failed pages that can be retried

    Args:
        max_retry_count: Maximum number of retries allowed
        batch_size: Maximum number of pages to return

    Returns:
        List of Page objects that failed but can be retried
    """
    db = SessionLocal()
    try:
        failed_pages = db.query(Page).filter(
            and_(
                Page.status == JobStatus.FAILED,
                Page.retry_count < max_retry_count
            )
        ).limit(batch_size).all()

        logger.info(f"Found {len(failed_pages)} failed pages eligible for retry (max retries: {max_retry_count})")
        return failed_pages

    except Exception as e:
        logger.error(f"Error querying failed pages: {e}")
        return []
    finally:
        db.close()


def get_old_completed_jobs(
    days_old: int = 7,
    batch_size: int = 100
) -> List[Job]:
    """
    Query MySQL for completed jobs older than specified days

    Args:
        days_old: Jobs completed this many days ago
        batch_size: Maximum number of jobs to return

    Returns:
        List of old completed Job objects
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.utcnow() - timedelta(days=days_old)

        old_jobs = db.query(Job).filter(
            and_(
                or_(
                    Job.status == JobStatus.COMPLETED,
                    Job.status == JobStatus.FAILED
                ),
                Job.completed_at.isnot(None),
                Job.completed_at < cutoff_time
            )
        ).limit(batch_size).all()

        logger.info(f"Found {len(old_jobs)} old completed/failed jobs (>{days_old} days)")
        return old_jobs

    except Exception as e:
        logger.error(f"Error querying old jobs: {e}")
        return []
    finally:
        db.close()


def get_job_with_pages(job_id: str) -> Optional[tuple[Job, List[Page]]]:
    """
    Get a job and all its pages in a single query

    Args:
        job_id: The job ID to fetch

    Returns:
        Tuple of (Job, List[Page]) or None if not found
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None

        pages = db.query(Page).filter(Page.job_id == job_id).order_by(Page.page_number).all()

        return (job, pages)

    except Exception as e:
        logger.error(f"Error fetching job {job_id} with pages: {e}")
        return None
    finally:
        db.close()


def get_system_stats() -> dict:
    """
    Get system-wide statistics for monitoring dashboard

    Returns:
        Dictionary with various stats
    """
    db = SessionLocal()
    try:
        stats = {
            "total_jobs": db.query(Job).count(),
            "processing_jobs": db.query(Job).filter(Job.status == JobStatus.PROCESSING).count(),
            "completed_jobs": db.query(Job).filter(Job.status == JobStatus.COMPLETED).count(),
            "failed_jobs": db.query(Job).filter(Job.status == JobStatus.FAILED).count(),
            "pending_jobs": db.query(Job).filter(Job.status == JobStatus.PENDING).count(),
            "total_pages": db.query(Page).count(),
            "failed_pages": db.query(Page).filter(Page.status == JobStatus.FAILED).count(),
            "processing_pages": db.query(Page).filter(Page.status == JobStatus.PROCESSING).count(),
        }

        # Calculate stuck jobs count
        threshold_time = datetime.utcnow() - timedelta(minutes=30)
        stats["stuck_jobs"] = db.query(Job).filter(
            and_(
                Job.status == JobStatus.PROCESSING,
                Job.started_at.isnot(None),
                Job.started_at < threshold_time
            )
        ).count()

        stats["stuck_pages"] = db.query(Page).filter(
            and_(
                Page.status == JobStatus.PROCESSING,
                Page.created_at < threshold_time
            )
        ).count()

        return stats

    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        return {}
    finally:
        db.close()
