"""
The original file a job was created from, and `purge_source`.

A MAIN job created by `/upload`, `/convert` or `/transcribe` keeps its original
in MinIO (`Job.minio_upload_path`: `uploads/...` in the uploads bucket, `audio/...`
in the audio bucket) and, while it runs, a local copy under
`{TEMP_STORAGE_PATH}/uploads/{job_id}/` or `.../audio/{job_id}/`.

`purge_source=true` asks for that original to go away once the job ends
COMPLETED. The choice is stored with the job (a `JobConfiguration` row, see
`save_purge_option`), never only in the Celery message, so whichever worker
completes the job — the first run, the merge after a page retry — honours it.

A job that ends failed, or with failed pages, keeps its original: a page retry
restores it from MinIO. The split per-page PDFs are separate objects and are kept.
"""
import logging
import shutil
from pathlib import Path
from typing import Callable, Optional

from shared.config import get_settings
from shared.models import Job, JobStatus

logger = logging.getLogger(__name__)

PURGE_OPTION = "purge_source"
# JobConfiguration.operation for a conversion request that carries options
CONVERSION_OPERATION = "conversion"


class SourceDeleteError(RuntimeError):
    """The original exists but could not be deleted (MinIO refused or is down)."""


def save_purge_option(db, job: Job) -> None:
    """Persist `purge_source=true` with the job (no commit: the caller commits with the job)."""
    from shared.job_configuration import save_configuration

    save_configuration(db, job, operation=CONVERSION_OPERATION, options={PURGE_OPTION: True})


def purge_requested(job: Optional[Job]) -> bool:
    """Whether the job was created with `purge_source=true` (durable, from the DB)."""
    row = getattr(job, "configuration_row", None) if job is not None else None
    options = getattr(row, "options", None) if row is not None else None
    return bool(isinstance(options, dict) and options.get(PURGE_OPTION))


def source_bucket(minio, object_name: str) -> str:
    """The bucket of an original: transcriptions live in the audio bucket, the rest in uploads."""
    if object_name.startswith("audio/"):
        return minio.bucket_audio
    return minio.bucket_uploads


def local_source_dirs(job_id: str) -> list:
    """Where the API leaves the local copy of an upload for the worker."""
    base = Path(get_settings().temp_storage_path)
    return [base / "uploads" / str(job_id), base / "audio" / str(job_id)]


def _has_local_copy(job_id: str) -> bool:
    for directory in local_source_dirs(job_id):
        try:
            if directory.is_dir() and any(p.is_file() for p in directory.iterdir()):
                return True
        except OSError:
            continue
    return False


def source_available(job: Optional[Job]) -> bool:
    """True while the original still exists (MinIO path recorded, or a local copy)."""
    if job is None:
        return False
    return bool(job.minio_upload_path) or _has_local_copy(job.id)


def delete_source(db, job: Job, minio_factory: Callable) -> bool:
    """
    Delete a job's original: the MinIO object and the local copies. Commits.

    Returns False when there was nothing to delete. Raises SourceDeleteError when
    the MinIO object could not be removed; `minio_upload_path` is then kept, so
    the original is never orphaned (still referenced, still retryable).
    """
    found = False
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
    for directory in local_source_dirs(job.id):
        if directory.exists():
            found = True
            shutil.rmtree(directory, ignore_errors=True)
    return found


def purge_source_if_requested(job_id: str, *, session_factory, minio_factory: Callable,
                              requested: bool = False) -> bool:
    """
    Worker hook, called after a MAIN job completed: delete its original when the job
    asked for it (`requested`, or the durable option) and it really is COMPLETED.

    Never raises: a purge that fails is logged and the original is kept; the job
    stays completed.
    """
    try:
        db = session_factory()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job is None or job.status != JobStatus.COMPLETED:
                return False
            if not (requested or purge_requested(job)):
                return False
            if delete_source(db, job, minio_factory):
                logger.info(f"[MAIN JOB {job_id}] Original file purged (purge_source)")
            return True
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 - never fail a completed job over its purge
        logger.error(f"[MAIN JOB {job_id}] Could not purge the original file, keeping it: {e}")
        return False
