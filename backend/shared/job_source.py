"""
The source files of a job, and `purge_source`.

"Source files" are what a conversion was made *from*, as opposed to its results:

- the original: in MinIO (`Job.minio_upload_path`: `uploads/...` in the uploads
  bucket, `audio/...` in the audio bucket) and, while the job runs, a local copy
  under `{TEMP_STORAGE_PATH}/uploads/{job_id}/` or `.../audio/{job_id}/`. A URL /
  Drive / Dropbox source is never stored in MinIO: the worker downloads it into
  the job's work dir `{TEMP_STORAGE_PATH}/{job_id}/`, removed when the job
  completes (a failed job, or one with failed pages, may still have it there);
- the split per-page PDFs of a multi-page PDF (`pages/{job_id}/...` in the pages
  bucket, what `GET /jobs/{id}/pages/{n}/pdf` serves) and their local copies in
  the work dir.

Document conversion stores no extracted images/assets (the markdown export keeps
image placeholders), so there is nothing else to delete. The results (markdown,
per-page markdown, transcripts, Elasticsearch) are always kept.

`purge_source=true` deletes the source files once the job is settled for good:
COMPLETED, or FAILED / PARTIAL after every automatic retry ran (never while a
Celery retry, a page or a backlog item is still pending: `has_pending_work`).
The choice is stored with the job (a `JobConfiguration` row), never only in the
Celery message, so whichever worker settles the job honours it.

When they are deleted (automatically or by `DELETE /jobs/{id}/source`) the job
records `source_deleted_at` in the same row; `GET /jobs/{id}` reports it and the
page-PDF endpoint answers 410 `SOURCE_PURGED`. A page retry is then impossible.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from shared.config import get_settings
from shared.models import Job, JobStatus

logger = logging.getLogger(__name__)

PURGE_OPTION = "purge_source"
DELETED_AT_OPTION = "source_deleted_at"
# JobConfiguration.operation for a conversion request that carries options
CONVERSION_OPERATION = "conversion"


class SourceDeleteError(RuntimeError):
    """The source files exist but could not be deleted (MinIO refused or is down)."""


# ---------------------------------------------------------------------------
# Durable options (JobConfiguration.options)
# ---------------------------------------------------------------------------

def _options(job: Optional[Job]) -> dict:
    row = getattr(job, "configuration_row", None) if job is not None else None
    options = getattr(row, "options", None) if row is not None else None
    return options if isinstance(options, dict) else {}


def _set_option(db, job: Job, key: str, value) -> None:
    """Set one option on the job's configuration row, creating it if needed (no commit)."""
    row = getattr(job, "configuration_row", None)
    if row is None:
        from shared.job_configuration import save_configuration

        save_configuration(db, job, operation=CONVERSION_OPERATION, options={key: value})
        return
    # A new dict, so the JSON column is seen as changed; the fingerprint describes
    # the result-affecting options and is left alone
    row.options = {**(row.options or {}), key: value}


def save_purge_option(db, job: Job) -> None:
    """Persist `purge_source=true` with the job (no commit: the caller commits with the job)."""
    _set_option(db, job, PURGE_OPTION, True)


record_purge_option = save_purge_option


def purge_requested(job: Optional[Job]) -> bool:
    """Whether the job was created with `purge_source=true` (durable, from the DB)."""
    return bool(_options(job).get(PURGE_OPTION))


def source_deleted_at(job: Optional[Job]) -> Optional[datetime]:
    """When the source files were deleted (UTC), or None."""
    value = _options(job).get(DELETED_AT_OPTION)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).rstrip("Z"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Where the source files are
# ---------------------------------------------------------------------------

def source_bucket(minio, object_name: str) -> str:
    """The bucket of an original: transcriptions live in the audio bucket, the rest in uploads."""
    if object_name.startswith("audio/"):
        return minio.bucket_audio
    return minio.bucket_uploads


def local_source_dirs(job_id: str) -> list:
    """Where a local copy of the original can be: the API's upload copy for the
    worker, and the job's work dir (URL / Drive / Dropbox downloads, split pages)."""
    base = Path(get_settings().temp_storage_path)
    return [base / "uploads" / str(job_id), base / "audio" / str(job_id), base / str(job_id)]


def _has_files(directory: Path) -> bool:
    try:
        return directory.is_dir() and any(p.is_file() for p in directory.rglob("*"))
    except OSError:
        return False


def _has_local_copy(job_id: str) -> bool:
    return any(_has_files(directory) for directory in local_source_dirs(job_id))


def _has_page_pdfs(job: Job) -> bool:
    try:
        return any(page.minio_page_path for page in (job.pages or []))
    except Exception:  # noqa: BLE001 - a detached job: only the original counts
        return False


def source_available(job: Optional[Job]) -> bool:
    """True while any source file still exists (original, local copy, page PDFs)."""
    if job is None:
        return False
    return bool(job.minio_upload_path) or _has_page_pdfs(job) or _has_local_copy(job.id)


def has_pending_work(db, job: Job) -> bool:
    """
    Whether something queued or running may still read the job's source files.

    Durable, from the DB only (Redis is a cache): the MAIN job PENDING/PROCESSING
    (a Celery retry of `process_conversion` waits as PENDING, see workers.tasks),
    or any of its pages PENDING/PROCESSING (a page retry, or a page whose Celery
    retry is scheduled).
    """
    from shared.models import Page

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        return True
    return db.query(Page.id).filter(
        Page.job_id == job.id,
        Page.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
    ).first() is not None


# ---------------------------------------------------------------------------
# Deleting them
# ---------------------------------------------------------------------------

def delete_source(db, job: Job, minio_factory: Callable) -> bool:
    """
    Delete a job's source files: the original (MinIO object + local copies) and
    the split per-page PDFs (MinIO + local). Records `source_deleted_at`. Commits.

    Returns False when there was nothing to delete. Raises SourceDeleteError when
    MinIO refused; what was already deleted is recorded (`minio_upload_path`,
    `Page.minio_page_path` cleared) and what was not stays referenced, so nothing
    is orphaned and calling again finishes the job.
    """
    found = False
    minio = None
    if job.minio_upload_path:
        found = True
        minio = minio_factory()
        object_name = job.minio_upload_path
        try:
            deleted = minio.delete_file(source_bucket(minio, object_name), object_name)
        except Exception as e:  # noqa: BLE001 - reported to the caller as one error
            raise SourceDeleteError(str(e)) from e
        if not deleted:
            raise SourceDeleteError(f"MinIO did not delete {object_name}")
        job.minio_upload_path = None
        db.commit()

    pages = [page for page in (job.pages or []) if page.minio_page_path]
    if pages:
        found = True
        minio = minio or minio_factory()
        try:
            deleted = minio.delete_folder(minio.bucket_pages, f"pages/{job.id}/")
        except Exception as e:  # noqa: BLE001
            raise SourceDeleteError(str(e)) from e
        if not deleted:
            raise SourceDeleteError(f"MinIO did not delete pages/{job.id}/")
        for page in pages:
            page.minio_page_path = None
        db.commit()

    for directory in local_source_dirs(job.id):
        if directory.exists():
            found = found or _has_files(directory)
            shutil.rmtree(directory, ignore_errors=True)

    if found:
        _set_option(db, job, DELETED_AT_OPTION, datetime.utcnow().isoformat())
        db.commit()
    return found


def purge_due(db, job: Optional[Job]) -> bool:
    """The job is settled for good: COMPLETED, or FAILED / PARTIAL with nothing pending."""
    if job is None:
        return False
    if job.status == JobStatus.COMPLETED:
        return True
    return job.status in (JobStatus.FAILED, JobStatus.PARTIAL) and not has_pending_work(db, job)


def purge_source_if_requested(job_id: str, *, session_factory, minio_factory: Callable,
                              requested: bool = False) -> bool:
    """
    Worker hook, called when a MAIN job settles (completed, or failed / partial
    after its last automatic retry): delete its source files when the job asked for
    it (`requested`, or the durable option) and nothing is pending any more.

    Never raises: a purge that fails is logged and the files are kept; the job's
    status is never changed by it.
    """
    try:
        db = session_factory()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not purge_due(db, job):
                return False
            if not (requested or purge_requested(job)):
                return False
            if delete_source(db, job, minio_factory):
                logger.info(f"[MAIN JOB {job_id}] Source files purged (purge_source, job {job.status.value})")
            return True
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 - never fail a settled job over its purge
        logger.error(f"[MAIN JOB {job_id}] Could not purge the source files, keeping them: {e}")
        return False


# ---------------------------------------------------------------------------
# Deduplication (POST /upload, /convert, /transcribe return an existing job)
# ---------------------------------------------------------------------------

# What happened to the source files of a reused job when the request asked for purge_source
DUPLICATE_PURGED = "purged"          # it was settled: deleted now
DUPLICATE_SCHEDULED = "scheduled"    # still running: deleted when it settles
DUPLICATE_KEPT = "kept"              # the delete failed: kept (DELETE /jobs/{id}/source later)
DUPLICATE_ALREADY_GONE = "already_gone"


def reusable_for(job: Job, purge_source: bool) -> bool:
    """
    Can this existing job answer a new request for the same file?

    A request that keeps its original (`purge_source=false`) is not answered by a
    job whose original is already gone, or that was asked to delete it: the user
    gets a new job and keeps the file. With `purge_source=true` any duplicate does.
    """
    if purge_source:
        return True
    return source_available(job) and not purge_requested(job)


def apply_purge_to_duplicate(db, job: Job, minio_factory: Callable) -> str:
    """
    A duplicate request with `purge_source=true`: record the option on the existing
    job (so whichever worker settles it honours it) and, when it is already settled
    with nothing pending, delete its source files now. Never raises.
    """
    try:
        if not purge_requested(job):
            record_purge_option(db, job)
            db.commit()
    except Exception as e:  # noqa: BLE001 - the request still returns the existing job
        db.rollback()
        logger.error(f"[MAIN JOB {job.id}] Could not record purge_source on the duplicate: {e}")
    if not source_available(job):
        return DUPLICATE_ALREADY_GONE
    if not purge_due(db, job):
        return DUPLICATE_SCHEDULED
    try:
        delete_source(db, job, minio_factory)
    except Exception as e:  # noqa: BLE001 - never fail the request over the purge
        db.rollback()
        logger.error(f"[MAIN JOB {job.id}] Could not purge the duplicate's source files, keeping them: {e}")
        return DUPLICATE_KEPT
    logger.info(f"[MAIN JOB {job.id}] Source files purged (purge_source on a duplicate request)")
    return DUPLICATE_PURGED
