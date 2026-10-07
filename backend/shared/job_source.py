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
The choice is stored with the job (`Job.purge_source`; when it was part of the
request also in its requested configuration, `JobConfiguration.options`), never
only in the Celery message, so whichever worker settles the job honours it.

When they are deleted (automatically or by `DELETE /jobs/{id}/source`) the job
records `Job.source_deleted_at`; `GET /jobs/{id}` reports it and the page-PDF
endpoint answers 410 `SOURCE_PURGED`. A page retry is then impossible.

Bookkeeping (`purge_source` added by a duplicate request, `source_deleted_at`,
the dedup `operation_key`) lives in `jobs` columns, never in
`JobConfiguration.options`: that is the configuration the user requested, shown
as such by `GET /jobs/{id}` and the UI.

Locking: every purge (worker hook, duplicate request, `DELETE /jobs/{id}/source`)
and every page retry take the MAIN job's row lock (`lock_job`, SELECT ... FOR
UPDATE) and decide under it. A purge re-checks `purge_due` / `has_pending_work`
under the lock and deletes everything before its single commit, so a page retry
(which commits its page PENDING under the same lock) either runs before it and
makes it refuse, or after it and finds no source (409 SOURCE_NOT_AVAILABLE).
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
# JobConfiguration.operation for a conversion request that carries options
CONVERSION_OPERATION = "conversion"


class SourceDeleteError(RuntimeError):
    """The source files exist but could not be deleted (MinIO refused or is down)."""


# ---------------------------------------------------------------------------
# Durable options
# ---------------------------------------------------------------------------

def _options(job: Optional[Job]) -> dict:
    row = getattr(job, "configuration_row", None) if job is not None else None
    options = getattr(row, "options", None) if row is not None else None
    return options if isinstance(options, dict) else {}


def _set_requested_option(db, job: Job, key: str, value) -> None:
    """Add one option the request asked for to the job's configuration row (no commit)."""
    row = getattr(job, "configuration_row", None)
    if row is None:
        from shared.job_configuration import save_configuration

        save_configuration(db, job, operation=CONVERSION_OPERATION, options={key: value})
        return
    # A new dict, so the JSON column is seen as changed; the fingerprint describes
    # the result-affecting options and is left alone
    row.options = {**(row.options or {}), key: value}


def save_purge_option(db, job: Job) -> None:
    """
    The request that creates the job asked for `purge_source=true` (no commit: the
    caller commits with the job). Durable on the job, and part of its requested
    configuration.
    """
    job.purge_source = True
    _set_requested_option(db, job, PURGE_OPTION, True)


def record_purge_option(db, job: Job) -> None:
    """
    A later request (a duplicate with `purge_source=true`) asked for it: durable on
    the job only; the job's requested configuration is not rewritten (no commit).
    """
    job.purge_source = True


def purge_requested(job: Optional[Job]) -> bool:
    """Whether the job is to delete its source files once settled (durable, from the DB)."""
    if job is None:
        return False
    return bool(getattr(job, "purge_source", None)) or bool(_options(job).get(PURGE_OPTION))


def source_deleted_at(job: Optional[Job]) -> Optional[datetime]:
    """When the source files were deleted (UTC), or None."""
    return getattr(job, "source_deleted_at", None) if job is not None else None


def lock_job(db, job_id: str) -> Optional[Job]:
    """
    The MAIN job's row, locked (SELECT ... FOR UPDATE) and re-read: purges and page
    retries serialize on it. Held until the session commits or rolls back.
    """
    return db.query(Job).filter(Job.id == job_id).with_for_update().populate_existing().first()


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


def has_pending_work(db, job: Job, *, locked: bool = False) -> bool:
    """
    Whether something queued or running may still read the job's source files.

    Durable, from the DB only (Redis is a cache): the MAIN job PENDING/PROCESSING
    (a Celery retry of `process_conversion` waits as PENDING, see workers.tasks),
    or any of its pages PENDING/PROCESSING (a page retry, or a page whose Celery
    retry is scheduled).

    `locked`: the caller holds the job's row lock and is about to delete; the pages
    are read with a locking read too, so a page retry committed just before is seen
    (a plain read may return the transaction's older snapshot).
    """
    from shared.models import Page

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        return True
    query = db.query(Page.id).filter(
        Page.job_id == job.id,
        Page.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
    )
    if locked:
        query = query.with_for_update()
    return query.first() is not None


# ---------------------------------------------------------------------------
# Deleting them
# ---------------------------------------------------------------------------

def delete_source(db, job: Job, minio_factory: Callable) -> bool:
    """
    Delete a job's source files: the original (MinIO object + local copies) and
    the split per-page PDFs (MinIO + local). Records `source_deleted_at`.

    The caller holds the job's row lock (`lock_job`) and checked `has_pending_work`
    under it. Everything is deleted before the one commit at the end, so the lock
    is held for the whole delete: a page retry cannot queue in between and then
    lose the local copy it was handed.

    Returns False when there was nothing to delete. Raises SourceDeleteError when
    MinIO refused; what was already deleted is recorded and committed
    (`minio_upload_path`, `Page.minio_page_path` cleared), what was not stays
    referenced (local copies included), so nothing is orphaned and calling again
    finishes the job.
    """
    from shared.models import Page

    found = False
    minio = None

    def failed(e) -> SourceDeleteError:
        # Record what is already gone (releases the lock: nothing else is deleted)
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return SourceDeleteError(str(e))

    if job.minio_upload_path:
        found = True
        minio = minio_factory()
        object_name = job.minio_upload_path
        try:
            deleted = minio.delete_file(source_bucket(minio, object_name), object_name)
        except Exception as e:  # noqa: BLE001 - reported to the caller as one error
            raise failed(e) from e
        if not deleted:
            raise failed(f"MinIO did not delete {object_name}")
        job.minio_upload_path = None

    pages = db.query(Page).filter(Page.job_id == job.id, Page.minio_page_path.isnot(None)) \
        .populate_existing().all()
    if pages:
        found = True
        minio = minio or minio_factory()
        try:
            deleted = minio.delete_folder(minio.bucket_pages, f"pages/{job.id}/")
        except Exception as e:  # noqa: BLE001
            raise failed(e) from e
        if not deleted:
            raise failed(f"MinIO did not delete pages/{job.id}/")
        for page in pages:
            page.minio_page_path = None

    for directory in local_source_dirs(job.id):
        if directory.exists():
            found = found or _has_files(directory)
            shutil.rmtree(directory, ignore_errors=True)

    if found:
        job.source_deleted_at = datetime.utcnow()
    db.commit()
    return found


def purge_due(db, job: Optional[Job], *, locked: bool = False) -> bool:
    """The job is settled for good: COMPLETED, or FAILED / PARTIAL with nothing pending."""
    if job is None:
        return False
    if job.status == JobStatus.COMPLETED:
        return not has_pending_work(db, job, locked=locked)
    return job.status in (JobStatus.FAILED, JobStatus.PARTIAL) and not has_pending_work(db, job, locked=locked)


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
            # Decided under the job's row lock: a page retry queued meanwhile has
            # committed its page PENDING (purge_due is then False), or waits for us
            job = lock_job(db, job_id)
            if not purge_due(db, job, locked=True):
                db.rollback()
                return False
            if not (requested or purge_requested(job)):
                db.rollback()
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
    with nothing pending, delete its source files now, under the job's row lock.
    Never raises.
    """
    job_id = job.id
    try:
        locked = lock_job(db, job_id)
    except Exception as e:  # noqa: BLE001 - the request still returns the existing job
        db.rollback()
        logger.error(f"[MAIN JOB {job_id}] Could not lock the duplicate: {e}")
        return DUPLICATE_SCHEDULED if source_available(job) else DUPLICATE_ALREADY_GONE
    if locked is None:
        db.rollback()
        return DUPLICATE_ALREADY_GONE
    job = locked
    try:
        if not getattr(job, "purge_source", None):
            record_purge_option(db, job)
            db.flush()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error(f"[MAIN JOB {job_id}] Could not record purge_source on the duplicate: {e}")
        return DUPLICATE_SCHEDULED if source_available(job) else DUPLICATE_ALREADY_GONE
    if not source_available(job):
        db.commit()
        return DUPLICATE_ALREADY_GONE
    if not purge_due(db, job, locked=True):
        db.commit()  # the option is recorded: the worker that settles the job purges
        return DUPLICATE_SCHEDULED
    try:
        delete_source(db, job, minio_factory)  # commits the option with the delete
    except Exception as e:  # noqa: BLE001 - never fail the request over the purge
        db.rollback()
        try:  # keep the option even though the delete failed (DELETE /jobs/{id}/source later)
            again = lock_job(db, job_id)
            if again is not None:
                record_purge_option(db, again)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        logger.error(f"[MAIN JOB {job_id}] Could not purge the duplicate's source files, keeping them: {e}")
        return DUPLICATE_KEPT
    logger.info(f"[MAIN JOB {job_id}] Source files purged (purge_source on a duplicate request)")
    return DUPLICATE_PURGED
