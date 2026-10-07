"""
Requeue failed pages of a split PDF: one code path for the manual page retry
(POST /jobs/{id}/pages/{n}/retry), the admin bulk retry
(POST /admin/jobs/{id}/retry-all-failed) and the monitoring auto-retry.

Every caller holds the MAIN job's row lock (`shared.job_source.lock_job`) and
re-read the pages under it, the same lock the purges take (worker hook,
duplicate request, DELETE /jobs/{id}/source). Here the original PDF is located
first; when it is gone (purge_source / DELETE /jobs/{id}/source) nothing is
changed and SourceNotAvailable is raised (the API answers 409
SOURCE_NOT_AVAILABLE). Otherwise the pages become PENDING and the MAIN job
PROCESSING in one commit, then each page is enqueued; a page that cannot be
enqueued is put back as it was (FAILED).
"""
import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple
from uuid import uuid4

from shared.engines import dispatch as engine_dispatch
from shared.job_source import local_source_dirs, lock_job, source_bucket
from shared.models import Job, JobStatus, Page

logger = logging.getLogger(__name__)


class SourceNotAvailable(RuntimeError):
    """The original PDF a page retry extracts its page from is gone (nothing was changed)."""


def retry_source_pdf(job: Job, *, minio_factory: Callable, temp_root: str) -> Optional[str]:
    """
    The original PDF a page retry extracts its page from: a local copy (the upload
    copy, or a URL download in the work dir), else restored from MinIO into
    {temp}/uploads/{job_id}/. None when the original is gone (purge_source /
    DELETE /jobs/{id}/source) or is not a PDF.
    """
    for directory in local_source_dirs(job.id):
        try:
            found = sorted(p for p in directory.glob("*.pdf") if p.is_file()) if directory.is_dir() else []
        except OSError:
            found = []
        if found:
            return str(found[0])

    if not job.minio_upload_path:
        return None
    restored = Path(temp_root) / "uploads" / job.id / Path(job.minio_upload_path).name
    if restored.suffix.lower() != ".pdf":
        return None
    try:
        restored.parent.mkdir(parents=True, exist_ok=True)
        minio = minio_factory()
        minio.download_file(source_bucket(minio, job.minio_upload_path), job.minio_upload_path,
                            file_path=str(restored))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not restore original PDF of job {job.id} from MinIO: {e}")
        restored.unlink(missing_ok=True)  # never leave a partial download behind as "the original"
        return None
    return str(restored) if restored.is_file() else None


def locked_failed_pages(db, job_id: str, page_numbers: Optional[List[int]] = None) -> List[Page]:
    """The job's FAILED pages (or those numbered), re-read with a locking read."""
    query = db.query(Page).filter(Page.job_id == job_id)
    if page_numbers is not None:
        query = query.filter(Page.page_number.in_(page_numbers))
    else:
        query = query.filter(Page.status == JobStatus.FAILED)
    return query.order_by(Page.page_number).with_for_update().populate_existing().all()


def requeue_pages(db, job: Job, pages: List[Page], *, user_id: Optional[str], remote_use: Any,
                  enqueue: Callable[..., Any], celery, minio_factory: Callable, temp_root: str,
                  today_queue: str, redis_client=None, session_factory=None,
                  ) -> Tuple[List[Tuple[Page, str]], List[Tuple[Page, str]]]:
    """
    Requeue `pages` (FAILED, re-read under the lock) of `job` (locked with lock_job).

    Raises SourceNotAvailable, after rolling back, when the original PDF is gone:
    nothing changed. Otherwise commits pages PENDING + job PROCESSING (which
    releases the lock: from then on a purge sees the pending pages and refuses),
    enqueues each page (`enqueue(job_id=, parent_job_id=, pdf_path=, page_number=)`
    when there is no document_conversion route) and returns (queued, failed) as
    lists of (page, new page job id | error).
    """
    if not pages:
        db.rollback()
        return [], []
    pdf_path = retry_source_pdf(job, minio_factory=minio_factory, temp_root=temp_root)
    if pdf_path is None:
        db.rollback()
        raise SourceNotAvailable(job.id)

    job_id = job.id
    previous_job = (job.status, job.completed_at, job.error_message)
    plan = []
    for page in pages:
        new_id = str(uuid4())
        plan.append((page, new_id, (page.page_job_id, page.error_message)))
        page.status = JobStatus.PENDING
        page.page_job_id = new_id
        page.error_message = None
        page.retry_count = (page.retry_count or 0) + 1
    # The MAIN job is open again until it settles (completed after the merge, or
    # partial if a page fails again)
    job.status = JobStatus.PROCESSING
    job.completed_at = None
    job.error_message = None
    db.commit()

    queued, failed = [], []
    for page, new_id, _ in plan:
        number = page.page_number
        try:
            if redis_client is not None:
                redis_client.set_job_status(job_id=new_id, job_type="page", status="queued", progress=0,
                                            parent_job_id=job_id, page_number=number)
                if user_id:
                    redis_client.set_job_owner(new_id, user_id)

            def today(new_id=new_id, number=number):
                enqueue(job_id=new_id, parent_job_id=job_id, pdf_path=pdf_path, page_number=number)

            engine_dispatch.submit(
                feature="document_conversion", job_id=job_id, subject_type="page", subject_id=new_id,
                user_id=user_id, remote_use=remote_use,
                payload=engine_dispatch.page_payload(
                    page_job_id=new_id, parent_job_id=job_id, page_number=number, options={},
                    source_pdf_path=pdf_path, today_queue=today_queue),
                today=today, celery=celery, session_factory=session_factory,
            )
            queued.append((page, new_id))
        except Exception as e:  # noqa: BLE001 - this page is put back, the others stay queued
            logger.error(f"Could not queue the retry of page {number} of job {job_id}: {e}", exc_info=True)
            failed.append((page, str(e)))

    if redis_client is not None and queued:
        try:
            redis_client.update_job_progress(
                job_id, (redis_client.get_job_status(job_id) or {}).get("progress") or 0,
                status="processing", error=None)
        except Exception as e:  # noqa: BLE001 - Redis is a cache
            logger.warning(f"Could not update the cached status of job {job_id}: {e}")

    if failed:
        _put_back(db, job_id, [(p, old) for p, new_id, old in plan if any(p is f for f, _ in failed)],
                  previous_job if not queued else None)
    return queued, failed


def _put_back(db, job_id: str, pages, previous_job) -> None:
    """Pages that were not enqueued go back to FAILED; the job too when nothing was queued."""
    from shared.engines.ledger import recount_parent_pages

    try:
        job = lock_job(db, job_id)
        for page, (old_id, old_error) in pages:
            row = db.query(Page).filter(Page.id == page.id).with_for_update().populate_existing().first()
            if row is None or row.status != JobStatus.PENDING:
                continue
            row.status = JobStatus.FAILED
            row.retry_count = max((row.retry_count or 1) - 1, 0)
            row.page_job_id = old_id
            row.error_message = old_error
        if job is not None and previous_job is not None:
            job.status, job.completed_at, job.error_message = previous_job
        elif job is not None:
            recount_parent_pages(db, job_id)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error(f"Could not put back the pages of job {job_id} that were not queued: {e}")
