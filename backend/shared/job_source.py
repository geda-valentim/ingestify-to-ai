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

The image assets a conversion extracts (`image_mode=referenced`, `page_images`;
shared/conversion_assets.py) are *outputs*, not source files: the purge never
deletes them when the job settles (the client still has to download them), it
schedules their deletion ASSET_RETENTION_SECONDS later (`schedule_expiry`, run by
the periodic beat). `DELETE /jobs/{id}/source` deletes them at once. The other
results (markdown, per-page markdown, transcripts, Elasticsearch) are always kept.

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

Image jobs (`source_type == "image"`, every `/images/*` route) keep their
original elsewhere; see "Image jobs" below. The same functions (`source_available`,
`delete_source`, `purge_source_if_requested`) cover them.

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
    if is_image_job(job):
        return image_source_available(job)
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

    if is_image_job(job):
        return delete_image_source(db, job, minio_factory)

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
    if job.status == JobStatus.CANCELLED and is_image_job(job):
        # A cancelled Full / face analysis is settled too (its run is terminal)
        return True
    return job.status in (JobStatus.FAILED, JobStatus.PARTIAL) and not has_pending_work(db, job, locked=locked)


def _schedule_asset_expiry(job: Job) -> None:
    from shared.conversion_assets import schedule_expiry

    try:
        schedule_expiry(job)
    except Exception as e:  # noqa: BLE001 - never block the purge over it
        logger.warning(f"[MAIN JOB {job.id}] Could not schedule the asset expiry: {e}")


def _discard_unlisted_assets(job: Job, minio_factory: Callable) -> None:
    """
    A job that settled FAILED / PARTIAL never got a manifest (only a completed merge
    writes one), so nothing can download the assets its completed pages stored;
    with the source gone no page retry can complete it either: delete them now.
    """
    from shared.conversion_assets import asset_prefix, job_options, manifest_of, wants_assets

    if job.status == JobStatus.COMPLETED or manifest_of(job) is not None or not wants_assets(job_options(job)):
        return
    try:
        minio = minio_factory()
        minio.delete_folder(minio.bucket_results, asset_prefix(job.id))
    except Exception as e:  # noqa: BLE001 - DELETE /jobs/{id} removes them later
        logger.warning(f"[MAIN JOB {job.id}] Could not delete the unlisted assets: {e}")


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
            # Assets are kept for the client to download, then expire (committed
            # with the delete below, which always commits)
            _schedule_asset_expiry(job)
            _discard_unlisted_assets(job, minio_factory)
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
    if not purge_due(db, job, locked=True):
        db.commit()  # the option is recorded: the worker that settles the job purges
        return DUPLICATE_SCHEDULED if source_available(job) else DUPLICATE_ALREADY_GONE
    _schedule_asset_expiry(job)  # settled: its assets expire like the worker purge's
    if not source_available(job):
        db.commit()
        return DUPLICATE_ALREADY_GONE
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


# ---------------------------------------------------------------------------
# Image jobs (POST /images/*)
# ---------------------------------------------------------------------------
#
# Where the ORIGINAL of an image job lives (every copy counts):
#
# - the local handoff `{TEMP_STORAGE_PATH}/images/{job_id}/`: the API writes the
#   upload there for the native tasks (describe / ocr / analyze), and the Full /
#   face worker downloads its durable source into `.../{job_id}/{holder}/`. Both
#   tasks remove it in their `finally`, and `workers.monitoring.cleanup_old_jobs`
#   (`sweep_image_handoffs`) sweeps what a killed worker left behind, so it
#   normally outlives the task only briefly. `wait=true` changes nothing here:
#   the echoed `image_base64` of a synchronous answer comes from the request's
#   own bytes, never from a stored copy;
# - native tasks: the stored result embeds it, `image.image_base64` of
#   `job:{id}:result` (Redis, a TTL cache: GET /jobs/{id}/result reads
#   Elasticsearch, then this) and `images/{job_id}/result.json` (results bucket,
#   `Job.minio_result_path`, the durable copy the datalake delivery reads);
# - Full / face analysis: the durable source `images/{job_id}/source`
#   (`ImageAnalysisRun.source_path`), the normalized full-size PNG of it
#   `images/{job_id}/preview/...` (`ImageAnalysisRun.preview_path`), and that
#   preview embedded in the report (`image.image_base64` of
#   `images/{job_id}/reports/...json` and of the Redis result).
#
# Everything else is the derived result and is kept: the description / OCR /
# regions / face boxes and landmarks (coordinates, never crops), the markdown and
# the per-step outputs (`images/{job_id}/steps/...`).
#
# With `purge_source=true` the workers never embed the image in the result they
# write, and the purge (when the job settles: completed, failed, partial or
# cancelled; image routes have no automatic retry) deletes the rest. Images are
# never deduplicated, so a duplicate request never reaches them.

IMAGE_SOURCE_TYPE = "image"
IMAGE_HANDOFF_AREA = "images"  # == workers.vision.image_input.IMAGE_HANDOFF_ROOT


def is_image_job(job: Optional[Job]) -> bool:
    return getattr(job, "source_type", None) == IMAGE_SOURCE_TYPE


def image_handoff_path(job_id: str) -> Path:
    """`{TEMP_STORAGE_PATH}/images/{job_id}`: every local copy of an image job's original."""
    return Path(get_settings().temp_storage_path) / IMAGE_HANDOFF_AREA / str(job_id)


def _image_run(job: Job, db=None):
    from sqlalchemy.orm import object_session
    from shared.models import ImageAnalysisRun

    session = db or object_session(job)
    if session is None:
        return None
    try:
        return session.get(ImageAnalysisRun, job.id)
    except Exception:  # noqa: BLE001 - no run table: a native job
        return None


def _image_result_embeds_original(job: Job) -> bool:
    """
    The stored result still carries the image (`image.image_base64`): written
    without it when the job asked for purge_source, stripped when the original was
    deleted. Durable, from the DB only (never reads the object).
    """
    return bool(job.minio_result_path) and job.source_deleted_at is None and not purge_requested(job)


def _cached_result_embeds_original(job_id: str) -> bool:
    """The Redis result (a TTL cache) still carries the image."""
    try:
        from shared.redis_client import get_redis_client

        payload = get_redis_client().get_job_result(job_id)
        image = payload.get("image") if isinstance(payload, dict) else None
        return bool(isinstance(image, dict) and image.get("image_base64"))
    except Exception:  # noqa: BLE001 - unknown is not "available"
        return False


def stored_original_objects(job: Job, minio) -> list:
    """
    Objects of the results bucket that are a copy of the original, listed (not
    only what the run row points at, so a preview written by a worker that lost
    its lease is found too): `images/{id}/source`, every `images/{id}/preview/...`,
    and every report other than the selected one (an older fence's, or the one a
    rewrite left behind: reports may embed the preview).
    """
    prefix = f"images/{job.id}/"
    names = minio.list_objects(minio.bucket_results, prefix) or []
    selected = job.minio_result_path
    return [name for name in names
            if name == prefix + "source" or name.startswith(prefix + "preview/")
            or (name.startswith(prefix + "reports/") and name != selected)]


def _listed_originals(job: Job) -> bool:
    try:
        from shared.minio_client import get_minio_client

        return bool(stored_original_objects(job, get_minio_client()))
    except Exception:  # noqa: BLE001 - storage unreachable: the row fields decide
        return False


def image_source_available(job: Job) -> bool:
    """True while any copy of an image job's original remains (see above)."""
    if job.minio_upload_path or _has_files(image_handoff_path(job.id)):
        return True
    run = _image_run(job)
    if run is not None and (run.source_path or run.preview_path or _listed_originals(job)):
        return True
    return _image_result_embeds_original(job) or _cached_result_embeds_original(job.id)


def strip_embedded_image(payload) -> bool:
    """Drop the original embedded in a vision result (`image.image_base64`). True when it had one."""
    image = payload.get("image") if isinstance(payload, dict) else None
    if not isinstance(image, dict) or not image.get("image_base64"):
        return False
    image["image_base64"] = None
    return True


def _missing_object(exc: Exception) -> bool:
    return isinstance(exc, KeyError) or getattr(exc, "code", None) in ("NoSuchKey", "NoSuchObject")


def _strip_stored_result(job: Job, minio) -> bool:
    """
    Write the job's stored result without the embedded image. A Full / face report
    is named after its content hash, so it is written under its new hash and
    `minio_result_path` moves to it; the old object is NOT deleted here: the caller
    commits the new path first, and then deletes it as a leftover report
    (`stored_original_objects`). A native `result.json` is rewritten in place.
    Raises when the storage refuses.
    """
    import json

    path = job.minio_result_path
    try:
        payload = json.loads(minio.download_file(minio.bucket_results, path))
    except Exception as e:  # noqa: BLE001
        if _missing_object(e):
            return False
        raise
    if not strip_embedded_image(payload):
        return False
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    directory, _, name = path.rpartition("/")
    if directory.endswith("/reports") and "-" in name:
        from shared.image_full import fingerprint

        path = f"{directory}/{name.split('-', 1)[0]}-{fingerprint(payload)}.json"
    minio.upload_file(bucket_name=minio.bucket_results, object_name=path,
                      file_data=data, content_type="application/json")
    job.minio_result_path = path
    return True


def _strip_cached_result(job_id: str) -> bool:
    """Best effort: the Redis result is a TTL cache (RESULT_TTL_SECONDS)."""
    try:
        from shared.redis_client import get_redis_client

        cache = get_redis_client()
        payload = cache.get_job_result(job_id)
        if payload and strip_embedded_image(payload):
            cache.set_job_result(job_id, payload)
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[IMAGE JOB {job_id}] Could not strip the cached result: {e}")
    return False


def delete_image_source(db, job: Job, minio_factory: Callable) -> bool:
    """
    Delete every copy of an image job's original (see "Image jobs" above) and keep
    the result. Records `source_deleted_at` when something was deleted or the job
    asked for purge_source (its workers already wrote the result without the
    image and removed their local copies: from then on nothing of it remains).

    Same contract as `delete_source`: the caller holds the row lock and checked
    `has_pending_work`; a storage failure commits what is already gone and raises
    SourceDeleteError (`source_deleted_at` stays unset, so the copies left are
    still reported and found again), and calling again finishes the job.

    Order: the result without the image is written and its path committed first,
    then the objects it replaces are deleted (a reader never gets a path whose
    object is already gone for good), all under the job's row lock (re-taken after
    that commit).
    """
    found = False
    minio = None
    job_id = job.id

    def storage():
        nonlocal minio
        minio = minio or minio_factory()
        return minio

    try:
        if job.minio_result_path and _strip_stored_result(job, storage()):
            found = True
            db.commit()
            job = lock_job(db, job_id)
            if job is None:  # deleted meanwhile: DELETE /jobs/{id} removed everything
                db.rollback()
                return found
        run = _image_run(job, db)
        if job.minio_upload_path:  # an original kept like a document's (uploads bucket)
            object_name = job.minio_upload_path
            if not storage().delete_file(source_bucket(minio, object_name), object_name):
                raise SourceDeleteError(f"MinIO did not delete {object_name}")
            job.minio_upload_path = None
            found = True
        if run is not None:
            if run.source_path or run.preview_path:
                found = True
            for name in stored_original_objects(job, storage()):
                if not minio.delete_file(minio.bucket_results, name):
                    raise SourceDeleteError(f"MinIO did not delete {name}")
                found = True
            # Also when listing came back empty (it hides S3 errors): the known paths
            if run.source_path and not minio.delete_file(minio.bucket_results, run.source_path):
                raise SourceDeleteError(f"MinIO did not delete {run.source_path}")
            if not minio.delete_folder(minio.bucket_results, f"images/{job_id}/preview/"):
                raise SourceDeleteError(f"MinIO did not delete images/{job_id}/preview/")
            run.source_path = ""  # NOT NULL column: empty means "deleted"
            run.preview_path = None
    except Exception as e:  # noqa: BLE001 - reported to the caller as one error
        try:
            db.commit()  # record what is already gone (releases the lock)
        except Exception:  # noqa: BLE001
            db.rollback()
        if isinstance(e, SourceDeleteError):
            raise
        raise SourceDeleteError(str(e)) from e

    found = _strip_cached_result(job_id) or found
    handoff = image_handoff_path(job_id)
    if handoff.exists():
        found = _has_files(handoff) or found
        shutil.rmtree(handoff, ignore_errors=True)

    if found or purge_requested(job):
        job.source_deleted_at = job.source_deleted_at or datetime.utcnow()
    db.commit()
    return found


def recheck_cached_result(job_id: str, session_factory) -> None:
    """
    A writer just cached a result that may embed the image, after the job's
    terminal commit: if the original was deleted meanwhile (DELETE /jobs/{id}/source
    or the purge), strip that cache again. Decided under the job's row lock, which
    the delete holds until it has stripped the cache itself, so either the delete
    sees this write or this check sees the delete. Never raises.
    """
    try:
        with session_factory() as db:
            job = lock_job(db, job_id)
            if job is not None and job.source_deleted_at is not None:
                _strip_cached_result(job_id)
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[IMAGE JOB {job_id}] Could not re-check the cached result: {e}")


# Image jobs whose purge failed (storage down when they settled) are retried by a
# periodic sweep; at most this many per run, oldest first
IMAGE_PURGE_RETRY_BATCH = 20


def retry_pending_image_purges(session_factory, minio_factory: Callable,
                               limit: int = IMAGE_PURGE_RETRY_BATCH) -> int:
    """
    Retry the purge of settled image jobs that asked for purge_source and still
    have no `source_deleted_at` (the purge raised and kept the copies). Bounded
    (`limit` jobs per call) and idempotent: each goes through
    `purge_source_if_requested`, which re-checks everything under the job's row
    lock, and a successful purge sets `source_deleted_at`, which takes the job out
    of this query. Returns how many purges completed. Never raises.
    """
    try:
        with session_factory() as db:
            job_ids = [row[0] for row in db.query(Job.id).filter(
                Job.source_type == IMAGE_SOURCE_TYPE,
                Job.purge_source.is_(True),
                Job.source_deleted_at.is_(None),
                Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PARTIAL, JobStatus.CANCELLED]),
            ).order_by(Job.completed_at, Job.created_at).limit(limit)]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[IMAGE PURGE] Could not list pending image purges: {e}")
        return 0
    done = 0
    for job_id in job_ids:
        purge_source_if_requested(job_id, session_factory=session_factory, minio_factory=minio_factory)
        try:
            with session_factory() as db:
                job = db.get(Job, job_id)
                done += bool(job is not None and job.source_deleted_at is not None)
        except Exception:  # noqa: BLE001
            pass
    return done
