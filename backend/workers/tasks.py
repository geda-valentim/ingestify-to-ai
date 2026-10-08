"""
Tasks Celery com arquitetura hierárquica de jobs

Hierarquia:
  MAIN JOB
    ├─> SPLIT JOB (divide PDF)
    ├─> PAGE JOB 1, 2, 3... (processa páginas em paralelo)
    └─> MERGE JOB (combina resultados)
"""

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from pathlib import Path
from datetime import datetime
from uuid import uuid4
import json
import logging
import asyncio
import shutil
import time

from workers.celery_app import celery_app
from workers.converter import get_converter
from workers.sources import get_source_handler
from shared.redis_client import get_redis_client
from shared.elasticsearch_client import get_es_client
from shared.minio_client import get_minio_client
from shared.database import SessionLocal
from shared.models import Job, Page, JobStatus
from shared.config import get_settings
from shared.pdf_splitter import PDFSplitter, should_split_pdf
from shared.engines.media import AUDIO_EXTENSIONS
from shared import conversion_assets
# Moved to workers.engines.pipeline; the old names stay importable from here
from workers.engines.pipeline import (  # noqa: F401
    finish_transcription,
    purge_audio_source as _purge_audio_source,
    store_transcript_outputs as _store_transcript_outputs,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _resolve_uploaded_file(source: str, job_id: str) -> Path:
    """
    Resolve the path of a file uploaded through the API for this job.

    Only files the API saved under {temp}/uploads/{job_id}/ or {temp}/audio/{job_id}/
    are accepted, so a crafted `source` cannot make the worker read arbitrary
    local files (other users' uploads, container files) and return their content.
    """
    if not source:
        raise ValueError("Missing uploaded file path")

    file_path = Path(source).resolve()
    base = Path(settings.temp_storage_path).resolve()
    allowed_dirs = [base / "uploads" / job_id, base / "audio" / job_id]

    if not any(file_path.is_relative_to(d) for d in allowed_dirs):
        logger.warning(f"[MAIN JOB {job_id}] Rejected file source outside upload dir: {source}")
        raise ValueError("Invalid uploaded file path")

    return file_path


def _remove_job_files(job_id: str) -> None:
    """
    Delete a finished job's local files: work dir, uploaded file and audio.

    The original upload is kept in MinIO (page retries restore it from there),
    so nothing is needed on disk once the job completed. Failed jobs keep their
    files for Celery retries; the periodic cleanup_stale_files task removes them.
    """
    base = Path(settings.temp_storage_path)
    for directory in (base / job_id, base / "uploads" / job_id, base / "audio" / job_id):
        try:
            if directory.exists():
                shutil.rmtree(directory)
        except Exception as e:
            # Not fatal for the job, but the (possibly sensitive) files stay on disk
            logger.error(f"[JOB {job_id}] Could not remove {directory}: {e}")


def _purge_source_if_requested(job_id: str) -> None:
    """
    After a MAIN job settled (completed, or failed / partial after its last automatic
    retry): delete its source files (original + split page PDFs) when it was created
    with purge_source=true and nothing is pending. The option is read from the DB,
    so a merge run by any worker, after any page retry, honours it. Never raises.
    """
    from shared.job_source import purge_source_if_requested

    purge_source_if_requested(job_id, session_factory=SessionLocal, minio_factory=get_minio_client)


def _will_retry(task) -> bool:
    """Whether `raise task.retry(...)` now schedules another attempt of this task."""
    request = task.request
    if getattr(request, "called_directly", True):
        return False  # .run() / a direct call: retry() just re-raises
    return (request.retries or 0) < (task.max_retries or 0)


def _catalog_error(code: str, technical) -> str:
    """A job error message from shared.error_catalog, with the technical cause after it."""
    from shared import error_catalog

    message = error_catalog.describe(code)[0]
    return f"{message} ({technical})" if technical else message


def _with_durable_image_options(job_id: str, options: dict) -> dict:
    """
    `options` plus the image-asset options stored with the MAIN job (its requested
    configuration), so a retry, a page retry or a redelivered message honours
    them whatever its Celery message carries. Unchanged for a job without assets.
    """
    durable = conversion_assets.durable_options(job_id, SessionLocal)
    if conversion_assets.wants_assets(durable):
        return {**options, **durable}
    return options


def _asset_collector(job_id: str, options: dict, page_number: int = None):
    """The AssetCollector of a run that asked for image assets, else None."""
    if not conversion_assets.wants_assets(options):
        return None
    from workers.image_assets import AssetCollector

    budget = None
    if page_number:
        # The page jobs of a split PDF share the per-job limits (Redis fast path;
        # the merge stays the authority)
        budget = conversion_assets.JobAssetBudget(
            get_redis_client(), job_id, max_count=int(settings.conversion_asset_max_count),
            max_bytes=int(settings.conversion_asset_max_total_mb) * 1024 * 1024)
    return AssetCollector(job_id, get_minio_client, page_offset=(page_number - 1) if page_number else 0,
                          budget=budget)


def _publish_manifest(job_id: str, markdown: str, manifest):
    """
    Persist the asset manifest BEFORE any result (Redis, Elasticsearch, MySQL page
    rows) is published, and fail closed: when it cannot be written, the markdown
    references go back to placeholders and the stored PNGs are deleted, so no URL
    is ever published without a manifest that serves it.

    Returns (markdown, manifest or None).
    """
    if manifest is None:
        return markdown, None
    try:
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
            if job is None:
                raise RuntimeError("job row not found")
            job.assets_manifest = manifest
            db.commit()
        return markdown, manifest
    except Exception as e:  # noqa: BLE001 - the conversion itself still succeeds
        logger.error(f"[MAIN JOB {job_id}] Could not store the asset manifest, dropping the assets: {e}")
        for asset in manifest.get("assets") or []:
            markdown = conversion_assets.unreference(markdown, asset["url"])
        try:
            minio = get_minio_client()
            minio.delete_folder(minio.bucket_results, conversion_assets.asset_prefix(job_id))
        except Exception as cleanup_error:  # noqa: BLE001
            logger.warning(f"[MAIN JOB {job_id}] Could not delete the unlisted assets: {cleanup_error}")
        return markdown, None


def _convert(converter, file_path, options: dict, collector):
    """convert_to_markdown, called exactly as before when the job wants no assets."""
    if collector is None:
        return converter.convert_to_markdown(file_path, options)
    return converter.convert_to_markdown(file_path, options, assets=collector)


def _retry_or_settle(task, *, countdown, exc=None, settle=None, **retry_kwargs):
    """
    `raise _retry_or_settle(...)` in place of `raise task.retry(...)`.

    An attempt that will be retried records the job (or page) as waiting for it
    (PENDING); if the retry then cannot be published (broker down), nothing would
    ever run it and it would wait forever. `settle(error)`, given only when the
    attempt was recorded as retrying, records the failure for good instead (and
    lets purge_source apply); the publish error is re-raised.
    """
    from celery.exceptions import Retry

    try:
        return task.retry(exc=exc, countdown=countdown, **retry_kwargs)
    except Retry:
        raise
    except Exception as publish_error:
        if settle is not None and publish_error is not exc:
            logger.error(f"Could not schedule the retry of {task.name}: {publish_error}")
            try:
                settle(_catalog_error("RETRY_NOT_QUEUED", exc or publish_error))
            except Exception as e:  # noqa: BLE001 - the publish error is what matters
                logger.error(f"Could not record the unscheduled retry of {task.name}: {e}")
        raise


def _record_main_failure(job_id: str, redis_client, error: str, *, retrying: bool) -> None:
    """
    A failed attempt of a MAIN job. When Celery will retry it, the job waits as
    PENDING (queued) with the error, not FAILED: the DB is the durable record that
    work is still due, so DELETE /jobs/{id}/source refuses (409) while a retry may
    still read the original. The last attempt marks it FAILED.
    """
    now = datetime.utcnow()
    redis_client.set_job_status(
        job_id=job_id,
        job_type="main",
        status="queued" if retrying else "failed",
        progress=0,
        error=error,
        completed_at=None if retrying else now,
    )
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.PENDING if retrying else JobStatus.FAILED
            job.error_message = error
            job.completed_at = None if retrying else now
            db.commit()
    except Exception as e:
        logger.error(f"[MAIN JOB {job_id}] MySQL failure update error: {e}")
    finally:
        db.close()
    if not retrying:
        # Settled for good (no automatic retry left): purge_source applies now
        _purge_source_if_requested(job_id)


# ============================================
# MAIN JOB - Ponto de entrada
# ============================================

# Transcription owns this slice of a job's overall progress (see process_conversion)
TRANSCRIPTION_PROGRESS_START = 30
TRANSCRIPTION_PROGRESS_END = 70

# Live text is pushed to Redis in batches, at most this often (wall-clock seconds)
LIVE_TRANSCRIPT_FLUSH_SECONDS = 2.0


def _transcription_progress(redis_client, job_id: str, clock=time.monotonic):
    """
    Progress callback for a transcription: maps the transcribed share of the media onto
    the job's 30-70% slice and records how far in it is (transcribed_seconds of
    media_duration), for the job page. Writes only when the percentage moves, so a
    long recording costs at most ~40 Redis writes.

    Each decoded segment is also appended to the job's live transcript, in batches
    every LIVE_TRANSCRIPT_FLUSH_SECONDS, so the job page can show the text as it comes.
    A call at 0 seconds with no segment means the transcription (re)started - e.g. the
    CPU retry after a GPU failure - and drops what the failed attempt had written.
    """
    state = {"progress": None, "pending": [], "flushed_at": clock()}

    def flush() -> None:
        pending, state["pending"] = state["pending"], []
        state["flushed_at"] = clock()
        redis_client.append_partial_transcript(job_id, pending)

    def on_progress(transcribed_seconds: float, total_seconds: float, segment=None) -> None:
        try:
            if segment is None and transcribed_seconds <= 0:
                state["pending"] = []
                redis_client.delete_partial_transcript(job_id)
            elif segment is not None and segment.get("text"):
                state["pending"].append(segment)
                if clock() - state["flushed_at"] >= LIVE_TRANSCRIPT_FLUSH_SECONDS:
                    flush()
        except Exception as e:  # live text is cosmetic: never fail a transcription over it
            logger.warning(f"[MAIN JOB {job_id}] Could not record live transcript: {e}")

        if not total_seconds or total_seconds <= 0:
            return
        share = min(max(transcribed_seconds / total_seconds, 0.0), 1.0)
        span = TRANSCRIPTION_PROGRESS_END - TRANSCRIPTION_PROGRESS_START
        progress = TRANSCRIPTION_PROGRESS_START + int(span * share)
        if progress == state["progress"]:
            return
        state["progress"] = progress
        try:
            redis_client.update_job_progress(
                job_id,
                progress,
                transcribed_seconds=round(transcribed_seconds, 1),
                media_duration=round(total_seconds, 1),
            )
        except Exception as e:  # progress is cosmetic: never fail a transcription over it
            logger.warning(f"[MAIN JOB {job_id}] Could not record transcription progress: {e}")

    return on_progress


class _AttemptNoLongerWanted(Exception):
    """The job stopped being open (deleted, failed for good) while a routed attempt ran"""


def _transcribe_audio(job_id: str, file_path: Path, options: dict, redis_client, es_client, guard=None) -> None:
    """
    Transcribe a media file and complete the job (outputs, index, status). `guard`,
    when given, is asked right before the outputs are written; False aborts.
    """
    from workers.audio import transcribe_with_gpu_fallback

    # Durable SQL snapshot is authoritative, including late-discovered media.
    from shared.transcription import options_from_profile
    with SessionLocal() as profile_db:
        profile_job = profile_db.query(Job).filter(Job.id == job_id).first()
        durable_profile = getattr(profile_job, 'transcription_profile', None)
    if isinstance(durable_profile, dict):
        options.update(options_from_profile(durable_profile, options))
    provider_override = options.get('transcriber_provider')

    progress_callback = _transcription_progress(redis_client, job_id)
    # Transcribe audio
    transcription_options = {
        'language': options.get('audio_language') or options.get('language'),
        'include_word_timestamps': options.get('include_word_timestamps', False),
        'temperature': options.get('temperature', 0.0),
        'beam_size': options.get('beam_size', 5),
        **{key: options[key] for key in ('diarize', 'min_speakers', 'max_speakers', 'transcription_profile') if key in options},
    }

    strict = provider_override == 'whisperx' or (provider_override is None and settings.audio_transcriber_provider == 'whisperx')
    if strict:
        from workers.engines.pipeline import begin_transcription_attempt, with_transcription_attempt
        begin_transcription_attempt(job_id, options)
        raw_progress = progress_callback
        def progress_callback(*args):
            if not with_transcription_attempt(job_id, options, lambda: raw_progress(*args)):
                raise _AttemptNoLongerWanted(job_id)
        transcription_options['_should_cancel'] = lambda: not with_transcription_attempt(job_id, options, lambda: None) or (guard is not None and not guard())
        transcription_options['_reset_progress'] = lambda: progress_callback(0, 0)
        transcription_options['_on_phase'] = lambda phase: with_transcription_attempt(job_id, options,
            lambda: redis_client.update_job_progress(job_id, TRANSCRIPTION_PROGRESS_START, phase=phase))
        with_transcription_attempt(job_id, options,
            lambda: redis_client.update_job_progress(job_id, TRANSCRIPTION_PROGRESS_START))
    else:
        redis_client.update_job_progress(job_id, TRANSCRIPTION_PROGRESS_START)
    # Uses the GPU when available (detected once per worker) and falls back to CPU
    transcription_started = time.monotonic()
    result, transcriber = transcribe_with_gpu_fallback(
        file_path,
        transcription_options,
        force_provider=provider_override,
        on_progress=progress_callback,
    )
    processing_seconds = round(time.monotonic() - transcription_started, 1)

    logger.info(
        f"[MAIN JOB {job_id}] Transcription complete with {transcriber.__class__.__name__} "
        f"on {result.get('device')}: {result['word_count']} words, "
        f"{result['duration']:.2f}s, language={result['language']}"
    )
    if strict:
        if not with_transcription_attempt(job_id, options,
                lambda: redis_client.update_job_progress(job_id, TRANSCRIPTION_PROGRESS_END)):
            raise _AttemptNoLongerWanted(job_id)
    else:
        redis_client.update_job_progress(job_id, TRANSCRIPTION_PROGRESS_END)

    if guard is not None and not guard():
        raise _AttemptNoLongerWanted(job_id)

    finish_transcription(
        job_id,
        result,
        options=options,
        file_path=file_path,
        processing_seconds=processing_seconds,
        compute_type=getattr(transcriber, 'compute_type', None),
        redis_client=redis_client,
        es_client=es_client,
    )


def _divert_audio_to_backlog(job_id: str, file_path: Path, options: dict, redis_client):
    """
    process_conversion without usage_id met audio and transcription has a route:
    move the file to the shared audio directory, put the job back to PENDING and
    hand it to dispatch.submit (spec 0003, 4.3). Returns (diverted, file path).
    Without an active route it returns at once and touches nothing.
    """
    from shared.iam.remote import remote_use_of
    from shared.engines import dispatch as engine_dispatch
    from shared.engines import routing

    route = routing.get_route("transcription", session_factory=SessionLocal)
    if route is None or not route.active:
        # URL/download discovery can happen on the document worker. Keep the
        # durable snapshot and send WhisperX to its isolated audio image.
        from celery import current_task
        delivery = getattr(getattr(current_task, 'request', None), 'delivery_info', None) or {}
        queue = delivery.get('routing_key')
        profile = options.get('transcription_profile') or {}
        if profile.get('provider') == 'whisperx' and queue and queue != settings.transcription_queue:
            celery_app.send_task(engine_dispatch.PROCESS_CONVERSION, kwargs={
                'job_id': job_id, 'source_type': 'file', 'source': str(file_path),
                'options': dict(options, is_audio=True)}, queue=settings.transcription_queue)
            return True, file_path
        return False, file_path

    audio_dir = Path(settings.temp_storage_path) / "audio" / job_id
    if not file_path.resolve().is_relative_to(audio_dir.resolve()):
        audio_dir.mkdir(parents=True, exist_ok=True)
        moved = audio_dir / file_path.name
        shutil.move(str(file_path), moved)
        file_path = moved

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        user_id = job.user_id if job else None
        remote_use = remote_use_of(user_id, session_factory=SessionLocal)  # decided only on 'admins' routes
        name = job.name if job else None
        if job:
            job.status = JobStatus.PENDING
            job.started_at = None
            db.commit()
    finally:
        db.close()
    redis_client.set_job_status(job_id=job_id, job_type="main", status="queued", progress=0, name=name)

    routed_options = dict(engine_dispatch.DEFAULT_TRANSCRIPTION_OPTIONS)
    routed_options.update({k: v for k, v in options.items() if k in engine_dispatch.TRANSCRIPTION_OPTIONS})
    payload = engine_dispatch.transcription_payload(job_id, file_path, routed_options,
                                                    today_queue=settings.celery_task_default_queue)
    outcome = engine_dispatch.submit(
        feature="transcription", job_id=job_id, user_id=user_id, remote_use=remote_use, payload=payload,
        today=None, celery=celery_app, media_bytes=file_path.stat().st_size, session_factory=SessionLocal,
    )
    if outcome == "today":  # the route went away in between: transcribe here after all
        _set_processing(job_id)
        return False, file_path
    logger.info(f"[MAIN JOB {job_id}] Audio handed to the transcription route ({outcome})")
    return True, file_path


def _set_processing(job_id: str, redis_client=None, options=None) -> None:
    with SessionLocal() as db:
        if options:
            from workers.engines.pipeline import _check_usage_fence
            _check_usage_fence(db, options)
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
            raise _AttemptNoLongerWanted(job_id)
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.utcnow()
        if redis_client is not None:
            redis_client.set_job_status(job_id=job_id, job_type='main', status='processing', progress=10, started_at=job.started_at)
        db.commit()


def _job_still_open(job_id: str) -> bool:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        return job is not None and job.status in (JobStatus.PENDING, JobStatus.PROCESSING)
    finally:
        db.close()


def _run_routed_transcription(job_id: str, source: str, options: dict, usage_id: int):
    """
    A transcription placed by the dispatcher on the local engine (spec 0003, 4.7).

    Claims the reservation before any work (lost claim => acknowledge and leave:
    a redelivered or late message never runs twice), heartbeats the usage row,
    and settles it. Never self.retry: a failure settles `failed` and the backlog
    decides - back to the queue with backoff until max_attempts, then FAILED.
    """
    from shared.engines import dispatch as engine_dispatch
    from shared.engines import ledger
    from workers.engines.local import UsageHeartbeat

    holder = ledger.holder_id()
    outcome, _ = ledger.claim(usage_id, holder, session_factory=SessionLocal)
    if outcome != ledger.CLAIMED:
        logger.info(f"[MAIN JOB {job_id}] Usage {usage_id}: {outcome} - acknowledged without running")
        if outcome != ledger.LOST:
            engine_dispatch.kick(celery_app)
        return {"job_id": job_id, "status": outcome}

    redis_client = get_redis_client()
    es_client = get_es_client()
    heartbeat = UsageHeartbeat(usage_id, holder, session_factory=SessionLocal).start()
    started = time.monotonic()
    change = None
    try:
        logger.info(f"[MAIN JOB {job_id}] Routed transcription, usage {usage_id}")
        routed_options = dict(options, _usage_id=usage_id, _usage_holder=holder)
        _set_processing(job_id, redis_client, routed_options)
        file_path = _resolve_uploaded_file(source, job_id)
        if not _strict_audio_task(options):
            redis_client.update_job_progress(job_id, 20)
        _transcribe_audio(job_id, file_path, routed_options, redis_client, es_client, guard=lambda: _job_still_open(job_id))
    except _AttemptNoLongerWanted:
        heartbeat.stop()
        logger.warning(f"[MAIN JOB {job_id}] The job is no longer open; its transcript is discarded")
        ledger.settle_failed(usage_id, holder, error_code="CANCELLED", detail="job no longer open",
                             counts=False, terminal=True, outcome="cancelled", session_factory=SessionLocal)
        return {"job_id": job_id, "status": "cancelled"}
    except SoftTimeLimitExceeded:
        heartbeat.stop()
        # As on today's path, a transcription that ran out of time would again: fail for good
        error = f"Task exceeded soft time limit ({settings.conversion_timeout_seconds - 30}s)"
        logger.warning(f"[MAIN JOB {job_id}] {error}")
        _, change = ledger.settle_failed(usage_id, holder, error_code="TIMEOUT", detail=error, terminal=True,
                                         session_factory=SessionLocal)
        return {"job_id": job_id, "status": "failed", "error": error}
    except Exception as exc:
        heartbeat.stop()
        logger.error(f"[MAIN JOB {job_id}] Routed transcription failed: {exc}", exc_info=True)
        _, change = ledger.settle_failed(usage_id, holder, error_code="INTERNAL", detail=str(exc),
                                         session_factory=SessionLocal)
        if not _strict_audio_task(options):
            try:
                shutil.rmtree(Path(settings.temp_storage_path) / job_id, ignore_errors=True)
            except Exception:
                pass
        return {"job_id": job_id, "status": change.status if change else "failed"}
    finally:
        heartbeat.stop()
        ledger.apply_job_change(redis_client, change)
        if change is not None:
            engine_dispatch.kick(celery_app)

    ledger.settle_succeeded(usage_id, holder, measured_seconds=round(time.monotonic() - started, 3),
                            session_factory=SessionLocal)
    engine_dispatch.kick(celery_app)
    return {"job_id": job_id, "status": "completed"}


def _strict_audio_task(options):
    return options.get('transcriber_provider') == 'whisperx' or (options.get('transcription_profile') or {}).get('provider') == 'whisperx' or bool(options.get('_transcript_attempt_id'))


def _fail_transcription_attempt(job_id, options, redis_client, error, *, retry):
    """Only the still-current execution may publish failure or schedule its retry.

    Audio/source/staging cleanup is deliberately absent: retry needs the source,
    and an old task must never delete files shared with its successor.
    """
    from workers.engines.pipeline import _check_usage_fence
    with SessionLocal() as db:
        try:
            _check_usage_fence(db, options)
        except RuntimeError:
            return False
        job = db.query(Job).filter(Job.id == job_id).with_for_update().populate_existing().first()
        expected = options.get('_transcript_attempt_id', options.get('_expected_attempt_id'))
        if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING) or job.transcript_attempt_id != expected:
            return False
        job.status = JobStatus.PENDING if retry else JobStatus.FAILED
        job.error_message = error
        job.completed_at = None if retry else datetime.utcnow()
        redis_client.set_job_status(job_id=job_id, job_type='main', status='queued' if retry else 'failed',
                                   progress=0, error=error, completed_at=job.completed_at)
        db.commit()
    if not retry:
        _purge_source_if_requested(job_id)
    return True


@celery_app.task(bind=True, max_retries=3, name="workers.tasks.process_conversion")
def process_conversion(
    self,
    job_id: str,
    source_type: str,
    source: str,
    options: dict = None,
    callback_url: str = None,
    auth_token: str = None,
    usage_id: int = None,
):
    """
    Main job - processa conversão de documento

    Args:
        job_id: MAIN job ID
        source_type: Tipo de fonte (file, url, gdrive, dropbox)
        source: Fonte do documento
        options: Opções de conversão
        callback_url: Webhook opcional
        auth_token: Legacy - only messages queued before the S-01 fix carry it. The
            provider token of gdrive/dropbox is read from Redis (job:{id}:source_token)
        usage_id: Set only when the dispatcher (or its fallback) placed this item on
            the local engine (spec 0003): the reservation to claim before running.
            Without it, everything below runs exactly as it always did.
    """
    options = dict(options or {})

    if usage_id is not None:
        return _run_routed_transcription(job_id, source, options, usage_id)

    redis_client = get_redis_client()
    es_client = get_es_client()

    # Get preset from options
    preset = options.get('docling_preset') if options else None

    logger.info(f"[MAIN JOB {job_id}] Starting conversion: {source_type} (preset={preset})")

    # Terminal SQL state is authoritative even for a redelivered task.
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None or job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return {"job_id": job_id, "status": "discarded"}
        if isinstance(getattr(job, 'transcription_profile', None), dict):
            from shared.transcription import options_from_profile
            options.update(options_from_profile(job.transcription_profile, options))
        # Image assets (image_mode / page_images): durable with the job, so every
        # retry and every page of a split honours them
        image_options = conversion_assets.job_options(job)
        if conversion_assets.wants_assets(image_options):
            options.update(image_options)
        if _strict_audio_task(options):
            current = job.transcript_attempt_id
            expected = options.get('_expected_attempt_id', current)
            if expected != current or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
                return {"job_id": job_id, "status": "discarded"}
            options['_expected_attempt_id'] = current
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.utcnow()
        redis_client.set_job_status(job_id=job_id, job_type="main", status="processing", progress=10,
                                    started_at=job.started_at)
        db.commit()

    try:
        # 1. Download file (10% -> 20%)
        logger.info(f"[MAIN JOB {job_id}] Downloading from {source_type}...")
        handler = get_source_handler(source_type)

        temp_dir = Path(settings.temp_storage_path) / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        if source_type == 'file':
            file_path = _resolve_uploaded_file(source, job_id)
        else:
            # The provider's token comes out of band (S-01); auth_token survives only
            # for messages queued before that change
            source_token = auth_token
            if source_type in ('gdrive', 'dropbox') and not source_token:
                source_token = redis_client.get_source_token(job_id)
            file_path = asyncio.run(
                handler.download(
                    source=source,
                    temp_path=temp_dir,
                    auth_token=source_token
                )
            )
            if source_type in ('gdrive', 'dropbox'):
                redis_client.delete_source_token(job_id)

        logger.info(f"[MAIN JOB {job_id}] File downloaded: {file_path}")
        if _strict_audio_task(options):
            with SessionLocal() as db:
                job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
                if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING) or job.transcript_attempt_id != options.get('_expected_attempt_id'):
                    return {"job_id": job_id, "status": "discarded"}
                redis_client.update_job_progress(job_id, 20)
        else:
            redis_client.update_job_progress(job_id, 20)

        # 2. Check if this is an audio file for transcription
        is_audio = options.get('is_audio', False) or source_type == 'audio'
        audio_extensions = AUDIO_EXTENSIONS
        file_ext = file_path.suffix.lower()

        from shared.transcription import is_media_filename
        if not (is_audio or file_ext in audio_extensions or is_media_filename(file_path.name)) and options.get('diarization_explicit'):
            raise ValueError('DIARIZATION_MEDIA_REQUIRED')
        if is_audio or file_ext in audio_extensions or is_media_filename(file_path.name):
            # With a transcription route, audio that only revealed itself here (URL,
            # Drive, Dropbox, or a route created after the upload) joins the backlog
            # instead of transcribing in this worker. No route: nothing changes.
            diverted, file_path = _divert_audio_to_backlog(job_id, file_path, options, redis_client)
            if diverted:
                return {"job_id": job_id, "status": "queued"}

            logger.info(f"[MAIN JOB {job_id}] Audio file detected - transcribing with Whisper")

            options['is_audio'] = True
            _transcribe_audio(job_id, file_path, options, redis_client, es_client)
            logger.info(f"[MAIN JOB {job_id}] Audio transcription completed successfully")
            return

        # 3. Check if PDF needs splitting
        if should_split_pdf(file_path, min_pages=2):
            logger.info(f"[MAIN JOB {job_id}] PDF multi-page detected - creating split job")

            # Create SPLIT JOB
            split_job_id = str(uuid4())
            split_pdf_task.delay(
                split_job_id=split_job_id,
                parent_job_id=job_id,
                file_path=str(file_path),
                options=options
            )

            # Add split job as child
            redis_client.add_child_job(job_id, "split", split_job_id)

            logger.info(f"[MAIN JOB {job_id}] Split job created: {split_job_id}")

            # Main job agora espera os child jobs completarem
            # Progress será atualizado pelos page jobs

        else:
            # Documento não-PDF ou PDF single page - processar direto
            logger.info(f"[MAIN JOB {job_id}] Single document - converting directly")

            collector = _asset_collector(job_id, options)
            if collector is not None:
                converter = get_converter(preset=preset, picture_images=options.get('image_mode') == 'referenced')
            else:
                converter = get_converter(preset=preset)
            result = _convert(converter, file_path, options, collector)
            assets_manifest = None
            if collector is not None:
                result["markdown"], assets_manifest = _publish_manifest(
                    job_id, result.get("markdown", ""),
                    {"assets": result.get("assets") or [],
                     "skipped": result.get("assets_skipped") or conversion_assets.empty_skipped()})
                if assets_manifest is None:
                    result.pop("assets", None)
                    result.pop("assets_skipped", None)

            logger.info(f"[MAIN JOB {job_id}] Conversion complete")
            redis_client.update_job_progress(job_id, 80)

            # Store result in Redis
            redis_client.set_job_result(job_id, result)
            redis_client.update_job_progress(job_id, 90)

            # Store result in Elasticsearch
            markdown_content = result.get("markdown", "")
            metadata = result.get("metadata", {})

            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                filename = job.filename if job else None
                user_id = job.user_id if job else None
            finally:
                db.close()

            es_success = es_client.store_job_result(
                job_id=job_id,
                markdown_content=markdown_content,
                user_id=user_id,
                filename=filename,
                total_pages=metadata.get("pages"),
                metadata=metadata
            )

            # Update MySQL: Mark job as completed
            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.utcnow()
                    job.char_count = len(markdown_content)
                    job.has_elasticsearch_result = es_success
                    db.commit()
            except Exception as e:
                logger.error(f"[MAIN JOB {job_id}] MySQL completion error: {e}")
            finally:
                db.close()

            # Cleanup (work dir and the uploaded file; the original stays in MinIO
            # unless the job asked for purge_source)
            _remove_job_files(job_id)
            _purge_source_if_requested(job_id)

            # Mark as completed in Redis
            redis_client.set_job_status(
                job_id=job_id,
                job_type="main",
                status="completed",
                progress=100,
                completed_at=datetime.utcnow(),
            )

            logger.info(f"[MAIN JOB {job_id}] Completed successfully")

            # Callback
            if callback_url:
                send_callback(callback_url, job_id, "completed", result)

        return {"job_id": job_id, "status": "completed"}

    except SoftTimeLimitExceeded:
        # Gracefully handle soft timeout - mark as failed and retry
        logger.warning(f"[MAIN JOB {job_id}] Soft timeout exceeded - marking as failed for retry")

        error_msg = f"Task exceeded soft time limit ({settings.conversion_timeout_seconds - 30}s)"
        if _strict_audio_task(options):
            changed = _fail_transcription_attempt(job_id, options, redis_client, error_msg, retry=False)
            return {"job_id": job_id, "status": "failed" if changed else "discarded"}
        # A transcription that ran out of time will run out of time again: fail for good
        is_audio_job = bool(options.get('is_audio'))

        retrying = not is_audio_job and _will_retry(self)
        _record_main_failure(job_id, redis_client, error_msg, retrying=retrying)

        # Cleanup temp files
        try:
            temp_dir = Path(settings.temp_storage_path) / job_id
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        if is_audio_job:
            return {"job_id": job_id, "status": "failed", "error": error_msg}

        # Retry with backoff (settled FAILED if the retry cannot be scheduled)
        raise _retry_or_settle(
            self, countdown=60 * (2 ** self.request.retries),
            settle=(lambda error: _record_main_failure(job_id, redis_client, error, retrying=False))
            if retrying else None)

    except Exception as exc:
        logger.error(f"[MAIN JOB {job_id}] Failed: {exc}", exc_info=True)
        if _strict_audio_task(options):
            retry = self.request.retries < self.max_retries
            changed = _fail_transcription_attempt(job_id, options, redis_client, str(exc), retry=retry)
            if not changed:
                return {"job_id": job_id, "status": "discarded"}
            if retry:
                options['_expected_attempt_id'] = options.get('_transcript_attempt_id', options.get('_expected_attempt_id'))
                options.pop('_transcript_attempt_id', None)
                raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries), args=(), kwargs={
                    'job_id': job_id, 'source_type': source_type, 'source': source, 'options': options,
                    'callback_url': callback_url, 'auth_token': auth_token})
            return {"job_id": job_id, "status": "failed", "error": str(exc)}

        retrying = _will_retry(self)
        _record_main_failure(job_id, redis_client, str(exc), retrying=retrying)

        # Cleanup on failure
        try:
            temp_dir = Path(settings.temp_storage_path) / job_id
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        raise _retry_or_settle(
            self, exc=exc, countdown=60 * (2 ** self.request.retries),
            settle=(lambda error: _record_main_failure(job_id, redis_client, error, retrying=False))
            if retrying else None)


# ============================================
# SPLIT JOB - Divide PDF em páginas
# ============================================

@celery_app.task(bind=True, max_retries=2, name="workers.tasks.split_pdf_task")
def split_pdf_task(
    self,
    split_job_id: str,
    parent_job_id: str,
    file_path: str,
    options: dict = None,
):
    """
    Split job - divide PDF em páginas individuais

    Args:
        split_job_id: ID deste split job
        parent_job_id: ID do main job
        file_path: Caminho do PDF
        options: Opções de conversão
    """
    if options is None:
        options = {}

    redis_client = get_redis_client()

    logger.info(f"[SPLIT JOB {split_job_id}] Starting PDF split")

    try:
        # Mark split job as processing in Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="processing",
            parent_job_id=parent_job_id,
            started_at=datetime.utcnow(),
        )

        # Split PDF
        temp_dir = Path(settings.temp_storage_path) / parent_job_id / "pages"
        splitter = PDFSplitter(temp_dir)
        page_files = splitter.split_pdf(Path(file_path), job_id=parent_job_id)

        total_pages = len(page_files)
        logger.info(f"[SPLIT JOB {split_job_id}] PDF split into {total_pages} pages")

        # Store total pages in parent job (Redis)
        redis_client.set_job_pages(parent_job_id, total_pages)

        # Update MySQL: Update parent job with total_pages
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.total_pages = total_pages
                db.commit()
        except Exception as e:
            logger.error(f"[SPLIT JOB {split_job_id}] MySQL update error: {e}")
        finally:
            db.close()

        # With a document_conversion route each page joins the backlog and the
        # dispatcher places it (spec 0003, 4.14); without one, nothing changes
        page_route = _page_route()

        # Create PAGE records in MySQL and PAGE JOBS for each page. Idempotent: a
        # split retry reuses the rows (and page job ids) an earlier attempt created
        # (uq_pages_job_page), and does not run again a page that already started
        for page_num, page_file_path, minio_path in page_files:
            page_job_id, dispatch = _upsert_split_page(split_job_id, parent_job_id, page_num, minio_path)
            if not dispatch:
                logger.info(f"[SPLIT JOB {split_job_id}] Page {page_num} already started ({page_job_id}), "
                            f"not queued again")
                continue

            logger.info(f"[SPLIT JOB {split_job_id}] Creating page job {page_job_id} for page {page_num}")

            # Add page job as child of main job (Redis); before a routed page can run,
            # so the merge trigger always sees every page
            if page_route is not None:
                redis_client.add_child_job(parent_job_id, "page", page_job_id)
                _submit_page(page_job_id, parent_job_id, page_num, options, page_file_path=str(page_file_path))
                continue

            # Launch page conversion task
            convert_page_task.delay(
                page_job_id=page_job_id,
                parent_job_id=parent_job_id,
                page_number=page_num,
                page_file_path=str(page_file_path),
                options=options
            )

            # Add page job as child of main job (Redis)
            redis_client.add_child_job(parent_job_id, "page", page_job_id)

        # Mark split job as completed in Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="completed",
            parent_job_id=parent_job_id,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[SPLIT JOB {split_job_id}] Completed - {total_pages} page jobs created")

        return {"split_job_id": split_job_id, "pages_created": total_pages}

    except Exception as exc:
        logger.error(f"[SPLIT JOB {split_job_id}] Failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=split_job_id,
            job_type="split",
            status="failed",
            parent_job_id=parent_job_id,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        def settle(error):
            # No attempt left: the MAIN job fails for good (DB + Redis) and
            # purge_source applies, instead of PROCESSING forever
            _record_main_failure(parent_job_id, redis_client, error, retrying=False)

        retrying = _will_retry(self)
        if not retrying:
            settle(_catalog_error("SPLIT_FAILED", exc))
        raise _retry_or_settle(self, exc=exc, countdown=30 * (2 ** self.request.retries),
                               settle=settle if retrying else None)


def _upsert_split_page(split_job_id: str, parent_job_id: str, page_number: int, minio_path):
    """
    The Page row of one split page: created on the first attempt, reused by a split
    retry (one row per (job, page number), uq_pages_job_page). Returns
    (page job id, whether to queue it): a page an earlier attempt already started
    (PROCESSING / COMPLETED / FAILED) is not queued again; a PENDING one is (its
    queueing may be what failed), under the same page job id.
    """
    from sqlalchemy.exc import IntegrityError
    from shared.models import Page as PageModel

    db = SessionLocal()
    try:
        for _ in range(3):
            # Looked up with a plain read, then locked by primary key: a locking read
            # of a row that does not exist yet takes an InnoDB gap lock, and two
            # sessions holding the same gap that both insert deadlock (1213) - a
            # redelivered split, or another job's split whose rows share the gap
            found = db.query(PageModel.id).filter(
                PageModel.job_id == parent_job_id, PageModel.page_number == page_number,
            ).order_by(PageModel.created_at).first()
            page = None
            if found is not None:
                page = db.query(PageModel).filter(PageModel.id == found.id) \
                    .with_for_update().populate_existing().first()
                if page is None:  # deleted meanwhile (DELETE /jobs/{id}): look again
                    db.rollback()
                    continue
            if page is not None:
                if minio_path:
                    page.minio_page_path = minio_path
                page_job_id = page.page_job_id or str(uuid4())
                page.page_job_id = page_job_id
                dispatch = page.status == JobStatus.PENDING
                db.commit()
                return page_job_id, dispatch
            page_job_id = str(uuid4())
            db.add(PageModel(id=str(uuid4()), job_id=parent_job_id, page_number=page_number,
                             page_job_id=page_job_id, minio_page_path=minio_path, status=JobStatus.PENDING))
            try:
                db.commit()
                return page_job_id, True
            except IntegrityError:
                db.rollback()  # created concurrently: reuse it
        raise RuntimeError(f"page {page_number} of job {parent_job_id}: no Page row")
    except Exception as e:
        db.rollback()
        logger.error(f"[SPLIT JOB {split_job_id}] MySQL page creation error: {e}")
        raise
    finally:
        db.close()


def _page_route():
    """The active document_conversion route, or None (no route: today's path, untouched)"""
    from shared.engines import routing

    route = routing.get_route("document_conversion", session_factory=SessionLocal)
    return route if route is not None and route.active else None


def _submit_page(page_job_id: str, parent_job_id: str, page_number: int, options: dict, *,
                 page_file_path: str = None, source_pdf_path: str = None, today=None) -> str:
    """Hand one PDF page to the document_conversion route (subject_type=page)"""
    from shared.iam.remote import remote_use_of
    from shared.engines import dispatch as engine_dispatch

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == parent_job_id).first()
        user_id = job.user_id if job else None
        remote_use = remote_use_of(user_id, session_factory=SessionLocal)  # decided only on 'admins' routes
    finally:
        db.close()
    payload = engine_dispatch.page_payload(
        page_job_id=page_job_id, parent_job_id=parent_job_id, page_number=page_number, options=options,
        page_file_path=page_file_path, source_pdf_path=source_pdf_path,
        today_queue=settings.celery_task_default_queue,
    )
    if today is None:
        def today():
            convert_page_task.delay(**payload["kwargs"])
    path = Path(page_file_path or source_pdf_path)
    return engine_dispatch.submit(
        feature="document_conversion", job_id=parent_job_id, subject_type="page", subject_id=page_job_id,
        user_id=user_id, remote_use=remote_use, payload=payload, today=today, celery=celery_app,
        media_bytes=path.stat().st_size if path.exists() else None, session_factory=SessionLocal,
    )


# ============================================
# PAGE JOB - Converte página individual
# ============================================

def _recount_parent_pages(db, parent_job_id: str) -> bool:
    """Recompute pages_completed / pages_failed on the parent job (and commit).

    Both counters are recomputed on every outcome: a retry that succeeds moves a
    page out of FAILED, so pages_failed is only correct if it is recounted too.
    Returns True when this recount settled the MAIN job (PARTIAL).
    """
    from shared.engines.ledger import recount_parent_pages

    settled = recount_parent_pages(db, parent_job_id)
    db.commit()
    return settled


def _mark_page_failed(
    log_prefix: str,
    page_job_id: str,
    parent_job_id: str,
    page_number: int,
    error_msg: str,
    retrying: bool = False,
):
    """
    Record a page failure in Redis and MySQL.

    `retrying`: Celery will run the page again, so it waits as PENDING (queued)
    with the error instead of FAILED; the MAIN job is not settled and its original
    cannot be deleted meanwhile. The last attempt marks it FAILED, and once every
    page is terminal the MAIN job becomes PARTIAL (ledger.recount_parent_pages).
    """
    redis_client = get_redis_client()

    redis_client.set_job_status(
        job_id=page_job_id,
        job_type="page",
        status="queued" if retrying else "failed",
        parent_job_id=parent_job_id,
        page_number=page_number,
        error=error_msg,
        completed_at=None if retrying else datetime.utcnow(),
    )

    db = SessionLocal()
    try:
        from shared.models import Page as PageModel
        # Every row of this page (uq_pages_job_page keeps it to one; a database
        # not migrated yet may still hold an old split retry's duplicate)
        pages = db.query(PageModel).filter(
            PageModel.job_id == parent_job_id,
            PageModel.page_number == page_number
        ).all()
        for page in pages:
            page.status = JobStatus.PENDING if retrying else JobStatus.FAILED
            page.error_message = error_msg
        if pages:
            db.commit()

        _recount_parent_pages(db, parent_job_id)
    except Exception as e:
        logger.error(f"{log_prefix} MySQL failure update error: {e}")
    finally:
        db.close()
    if not retrying:
        # The last page to settle may have made the MAIN job PARTIAL
        _purge_source_if_requested(parent_job_id)


def _run_page_conversion(
    task,
    page_job_id: str,
    parent_job_id: str,
    page_number: int,
    page_file_path: str = None,
    source_pdf_path: str = None,
    options: dict = None,
    on_failure=None,
):
    """Convert a single PDF page and record the outcome.

    Shared body of `convert_page_task` (fed a page file that `split_pdf_task`
    already produced) and of the deprecated `process_page` shim (fed the whole
    source PDF, extracting the page itself). Both paths must produce identical
    effects; see tests/test_tasks_page_conversion.py.

    Args:
        task: The bound Celery task, used for `task.retry(...)`.
        page_job_id: ID of this page job.
        parent_job_id: ID of the main job.
        page_number: 1-indexed page number.
        page_file_path: Path to an already-split single-page PDF.
        source_pdf_path: Path to the full PDF; the page is extracted here.
        options: Conversion options.
        on_failure: Routed pages only (spec 0003, slice 8): called with
            (exception, timed_out) instead of marking the page failed and
            retrying - the backlog decides what a failed attempt means.
    """
    if bool(page_file_path) == bool(source_pdf_path):
        raise ValueError(
            "Exactly one of page_file_path / source_pdf_path must be supplied "
            f"(page_job_id={page_job_id}, page_number={page_number})"
        )

    if options is None:
        options = {}
    options = _with_durable_image_options(parent_job_id, options)

    redis_client = get_redis_client()
    es_client = get_es_client()
    # Page assets are stored under the MAIN job, with the absolute page number
    collector = _asset_collector(parent_job_id, options, page_number)
    if collector is not None:
        converter = get_converter(preset=options.get("docling_preset"),
                                  picture_images=options.get("image_mode") == "referenced")
    else:
        converter = get_converter(preset=options.get("docling_preset"))

    log_prefix = f"[PAGE JOB {page_job_id}]"
    logger.info(f"{log_prefix} Processing page {page_number} of job {parent_job_id}")

    # Update MySQL: Set page to processing
    db = SessionLocal()
    try:
        from shared.models import Page as PageModel
        # Every row of this page (uq_pages_job_page keeps it to one; a database
        # not migrated yet may still hold an old split retry's duplicate)
        pages = db.query(PageModel).filter(
            PageModel.job_id == parent_job_id,
            PageModel.page_number == page_number
        ).all()
        for page in pages:
            page.status = JobStatus.PROCESSING
            page.page_job_id = page_job_id  # a retry runs under a new page job id
        if pages:
            db.commit()
    except Exception as e:
        logger.error(f"{log_prefix} MySQL update error: {e}")
    finally:
        db.close()

    # Only a page we extracted ourselves is ours to delete; the files produced
    # by split_pdf_task are cleaned up by merge_pages_task.
    extracted_page_file = None

    try:
        # Mark page job as processing in Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="processing",
            parent_job_id=parent_job_id,
            page_number=page_number,
            started_at=datetime.utcnow(),
        )

        if page_file_path:
            page_path = Path(page_file_path)
        else:
            temp_dir = Path(settings.temp_storage_path) / parent_job_id / "retry_pages"
            temp_dir.mkdir(parents=True, exist_ok=True)

            splitter = PDFSplitter(temp_dir)
            # extract_single_page returns (local_page_path, minio_path)
            page_path, _page_minio_path = splitter.extract_single_page(
                Path(source_pdf_path), page_number
            )
            extracted_page_file = page_path

            logger.info(f"{log_prefix} Extracted page {page_number} to {page_path}")

        # Convert page
        result = _convert(converter, page_path, options, collector)

        # Store page result in Redis
        redis_client.set_job_result(page_job_id, result)

        # Store page result in Elasticsearch
        markdown_content = result.get("markdown", "")
        metadata = result.get("metadata", {})

        es_success = es_client.store_page_result(
            job_id=parent_job_id,
            page_number=page_number,
            markdown_content=markdown_content,
            metadata=metadata
        )

        # Store page markdown in MinIO
        try:
            minio_client = get_minio_client()
            minio_object_name = f"results/{parent_job_id}/page_{page_number:04d}.md"
            minio_client.upload_file(
                bucket_name=minio_client.bucket_results,
                object_name=minio_object_name,
                file_data=markdown_content.encode('utf-8'),
                content_type="text/markdown",
            )
            logger.info(f"{log_prefix} Page {page_number} markdown uploaded to MinIO: {minio_object_name}")
        except Exception as e:
            logger.error(f"{log_prefix} Failed to upload page {page_number} markdown to MinIO: {e}")

        # Update MySQL: Mark page as completed with markdown content
        settled = False
        db = SessionLocal()
        try:
            from shared.models import Page as PageModel
            # Every row of this page (uq_pages_job_page keeps it to one; a database
            # not migrated yet may still hold an old split retry's duplicate)
            pages = db.query(PageModel).filter(
                PageModel.job_id == parent_job_id,
                PageModel.page_number == page_number
            ).all()
            for page in pages:
                page.status = JobStatus.COMPLETED
                page.markdown_content = markdown_content
                page.char_count = len(markdown_content)
                page.has_elasticsearch_result = es_success
                page.error_message = None
                page.completed_at = datetime.utcnow()
            if pages:
                db.commit()

            settled = _recount_parent_pages(db, parent_job_id)
        except Exception as e:
            logger.error(f"{log_prefix} MySQL completion error: {e}")
        finally:
            db.close()
        if settled:
            # The last page to settle was this completion and an earlier page failed
            # for good: the MAIN job is PARTIAL now, purge_source applies
            _purge_source_if_requested(parent_job_id)

        # Mark page job as completed in Redis
        redis_client.set_job_status(
            job_id=page_job_id,
            job_type="page",
            status="completed",
            parent_job_id=parent_job_id,
            page_number=page_number,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"{log_prefix} Page {page_number} completed")

        # Update main job progress
        total_pages = redis_client.get_job_pages_total(parent_job_id)
        completed_pages = redis_client.count_completed_page_jobs(parent_job_id)

        if total_pages and completed_pages:
            # Progress: 20% (download) + 70% (pages) + 10% (merge)
            pages_progress = int((completed_pages / total_pages) * 70)
            main_progress = 20 + pages_progress
            redis_client.update_job_progress(parent_job_id, main_progress)

            logger.info(f"{log_prefix} Main job progress: {main_progress}% ({completed_pages}/{total_pages} pages)")

        # Check if all pages completed - trigger merge
        if redis_client.all_page_jobs_completed(parent_job_id):
            logger.info(f"{log_prefix} All pages completed - creating merge job")

            merge_job_id = str(uuid4())
            merge_pages_task.delay(
                merge_job_id=merge_job_id,
                parent_job_id=parent_job_id
            )

            redis_client.add_child_job(parent_job_id, "merge", merge_job_id)

        return {"page_job_id": page_job_id, "page_number": page_number, "status": "completed"}

    except SoftTimeLimitExceeded:
        error_msg = f"Page conversion exceeded soft time limit ({settings.conversion_timeout_seconds - 30}s)"
        logger.warning(f"{log_prefix} Page {page_number} soft timeout exceeded - marking as failed for retry")

        if on_failure is not None:
            return on_failure(error_msg, True)

        retrying = _will_retry(task)
        _mark_page_failed(log_prefix, page_job_id, parent_job_id, page_number, error_msg, retrying=retrying)

        raise _retry_or_settle(
            task, exc=SoftTimeLimitExceeded(), countdown=30 * (2 ** task.request.retries),
            settle=(lambda error: _mark_page_failed(log_prefix, page_job_id, parent_job_id, page_number, error))
            if retrying else None)

    except Exception as exc:
        logger.error(f"{log_prefix} Page {page_number} failed: {exc}", exc_info=True)

        if on_failure is not None:
            return on_failure(str(exc), False)

        retrying = _will_retry(task)
        _mark_page_failed(log_prefix, page_job_id, parent_job_id, page_number, str(exc), retrying=retrying)

        raise _retry_or_settle(
            task, exc=exc, countdown=30 * (2 ** task.request.retries),
            settle=(lambda error: _mark_page_failed(log_prefix, page_job_id, parent_job_id, page_number, error))
            if retrying else None)

    finally:
        if extracted_page_file is not None:
            try:
                Path(extracted_page_file).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"{log_prefix} Could not remove extracted page file: {e}")


def _run_routed_page(task, usage_id: int, *, page_job_id: str, parent_job_id: str, page_number: int,
                     page_file_path: str = None, source_pdf_path: str = None, options: dict = None):
    """
    A PDF page placed by the dispatcher on the local engine (spec 0003, 4.14).

    Claims the reservation before any work (lost claim => acknowledge and leave),
    heartbeats the usage row and settles it. Never task.retry: a failure settles
    `failed` and the backlog decides - back to the queue with backoff until
    max_attempts, then the page (never the whole document) is FAILED.
    """
    from shared.engines import dispatch as engine_dispatch
    from shared.engines import ledger
    from workers.engines.local import UsageHeartbeat

    log_prefix = f"[PAGE JOB {page_job_id}]"
    holder = ledger.holder_id()
    outcome, _ = ledger.claim(usage_id, holder, session_factory=SessionLocal)
    if outcome != ledger.CLAIMED:
        logger.info(f"{log_prefix} Usage {usage_id}: {outcome} - acknowledged without running")
        if outcome != ledger.LOST:
            engine_dispatch.kick(celery_app)
        return {"page_job_id": page_job_id, "page_number": page_number, "status": outcome}

    heartbeat = UsageHeartbeat(usage_id, holder, session_factory=SessionLocal).start()
    started = time.monotonic()
    failed = {}

    def on_failure(error: str, timed_out: bool):
        heartbeat.stop()
        _, failed["change"] = ledger.settle_failed(usage_id, holder, error_code="TIMEOUT" if timed_out else "INTERNAL",
                                                   detail=error, session_factory=SessionLocal)
        change = failed["change"]
        return {"page_job_id": page_job_id, "page_number": page_number,
                "status": change.status if change else "failed"}

    try:
        logger.info(f"{log_prefix} Routed page {page_number} of job {parent_job_id}, usage {usage_id}")
        result = _run_page_conversion(task, page_job_id=page_job_id, parent_job_id=parent_job_id,
                                      page_number=page_number, page_file_path=page_file_path,
                                      source_pdf_path=source_pdf_path, options=options, on_failure=on_failure)
    finally:
        heartbeat.stop()
    if "change" in failed or (result or {}).get("status") != "completed":
        change = failed.get("change")
        ledger.apply_job_change(get_redis_client(), change)
        engine_dispatch.kick(celery_app)
        return result
    ledger.settle_succeeded(usage_id, holder, measured_seconds=round(time.monotonic() - started, 3),
                            session_factory=SessionLocal)
    engine_dispatch.kick(celery_app)
    return result


@celery_app.task(bind=True, max_retries=3, name="workers.tasks.convert_page_task")
def convert_page_task(
    self,
    page_job_id: str,
    parent_job_id: str,
    page_number: int,
    page_file_path: str = None,
    source_pdf_path: str = None,
    options: dict = None,
    usage_id: int = None,
):
    """
    Page job - converte página individual de PDF

    Exactly one of `page_file_path` / `source_pdf_path` must be supplied.

    Args:
        page_job_id: ID deste page job
        parent_job_id: ID do main job
        page_number: Número da página
        page_file_path: Caminho de uma página já dividida (fluxo split_pdf_task)
        source_pdf_path: Caminho do PDF completo; a página é extraída aqui
        options: Opções de conversão
        usage_id: Set only when the dispatcher placed this page on the local engine
            (spec 0003, document_conversion route): the reservation to claim first.
            Without it, everything runs exactly as it always did.
    """
    if usage_id is not None:
        return _run_routed_page(self, usage_id, page_job_id=page_job_id, parent_job_id=parent_job_id,
                                page_number=page_number, page_file_path=page_file_path,
                                source_pdf_path=source_pdf_path, options=options)
    return _run_page_conversion(
        self,
        page_job_id=page_job_id,
        parent_job_id=parent_job_id,
        page_number=page_number,
        page_file_path=page_file_path,
        source_pdf_path=source_pdf_path,
        options=options,
    )


# ============================================
# PAGE RETRY - Shim depreciado
# ============================================

@celery_app.task(bind=True, max_retries=3, name="workers.tasks.process_page")
def process_page(
    self,
    job_id: str,
    parent_job_id: str,
    pdf_path: str,
    page_number: int,
    options: dict = None,
):
    """
    DEPRECATED - use `convert_page_task(source_pdf_path=...)` instead.

    This task duplicated convert_page_task and mishandled the tuple returned by
    PDFSplitter.extract_single_page. It survives only as a thin forwarder so
    that messages already sitting on the queue under the name
    "workers.tasks.process_page" still execute: with task_acks_late and
    task_reject_on_worker_lost, an unregistered name would requeue forever.

    Remove this task (and switch POST /jobs/{id}/pages/{n}/retry over to
    convert_page_task) once the queue has drained.

    Args:
        job_id: ID do novo page job (mapeia para page_job_id)
        parent_job_id: ID do main job
        pdf_path: Caminho do PDF completo (mapeia para source_pdf_path)
        page_number: Número da página a processar
        options: Opções de conversão
    """
    logger.warning(
        "[DEPRECATED] workers.tasks.process_page called for page %s of job %s - "
        "forwarding to convert_page_task",
        page_number, parent_job_id,
    )
    return _run_page_conversion(
        self,
        page_job_id=job_id,
        parent_job_id=parent_job_id,
        page_number=page_number,
        source_pdf_path=pdf_path,
        options=options,
    )


# ============================================
# MERGE JOB - Combina resultados das páginas
# ============================================

@celery_app.task(bind=True, max_retries=2, name="workers.tasks.merge_pages_task")
def merge_pages_task(
    self,
    merge_job_id: str,
    parent_job_id: str,
):
    """
    Merge job - combina resultados de todas as páginas

    Args:
        merge_job_id: ID deste merge job
        parent_job_id: ID do main job
    """
    redis_client = get_redis_client()
    es_client = get_es_client()

    logger.info(f"[MERGE JOB {merge_job_id}] Starting merge")

    try:
        # Mark merge job as processing in Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="processing",
            parent_job_id=parent_job_id,
            started_at=datetime.utcnow(),
        )

        # Get all page jobs
        page_job_ids = redis_client.get_page_jobs(parent_job_id)
        total_pages = len(page_job_ids)

        logger.info(f"[MERGE JOB {merge_job_id}] Merging {total_pages} pages")

        # Collect all page results in order
        page_results = []
        total_words = 0

        for page_job_id in page_job_ids:
            page_status = redis_client.get_job_status(page_job_id)
            if not page_status:
                continue

            page_num = page_status.get("page_number")
            page_result = redis_client.get_job_result(page_job_id)

            if page_result:
                page_results.append((page_num, page_result["markdown"], page_result.get("assets") or [],
                                     page_result.get("assets_skipped")))
                total_words += page_result.get("metadata", {}).get("words", 0)

        # Sort by page number
        page_results.sort(key=lambda x: x[0])

        # Image assets: concatenated in page order, served under the MAIN job, the
        # per-job limits applied across pages (shared/conversion_assets.py)
        # (pages that stored assets decide too: unknown options never hide them)
        assets_manifest = None
        wants = conversion_assets.wants_assets(conversion_assets.durable_options(parent_job_id, SessionLocal))
        if wants or any(assets for _, _, assets, _ in page_results):
            markdowns, assets, skipped, dropped = conversion_assets.combine_pages(
                parent_job_id, page_results, max_count=int(settings.conversion_asset_max_count),
                max_bytes=int(settings.conversion_asset_max_total_mb) * 1024 * 1024)
            _delete_dropped_assets(parent_job_id, dropped)
            assets_manifest = {"assets": assets, "skipped": skipped}
        else:
            markdowns = [markdown for _, markdown, _, _ in page_results]

        # Combine all pages
        combined_markdown = "\n\n---\n\n".join(markdowns)
        combined_markdown, assets_manifest = _publish_manifest(parent_job_id, combined_markdown, assets_manifest)

        # Create merged result
        merged_result = {
            "markdown": combined_markdown,
            "metadata": {
                "pages": total_pages,
                "words": total_words,
                "format": "pdf",
                "size_bytes": 0,
                "title": None,
                "author": None,
            }
        }
        if assets_manifest is not None:
            merged_result["assets"] = conversion_assets.public_assets(assets_manifest["assets"])
            merged_result["assets_skipped"] = assets_manifest["skipped"]

        # Store merged result in main job (Redis)
        redis_client.set_job_result(parent_job_id, merged_result)

        # Store merged result in Elasticsearch
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            filename = job.filename if job else None
            user_id = job.user_id if job else None
        finally:
            db.close()

        es_success = es_client.store_job_result(
            job_id=parent_job_id,
            markdown_content=combined_markdown,
            user_id=user_id,
            filename=filename,
            total_pages=total_pages,
            metadata=merged_result.get("metadata", {})
        )

        # Update MySQL: Mark parent job as completed
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.char_count = len(combined_markdown)
                job.has_elasticsearch_result = es_success
                db.commit()
        except Exception as e:
            logger.error(f"[MERGE JOB {merge_job_id}] MySQL completion error: {e}")
        finally:
            db.close()

        # Mark merge job as completed in Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="completed",
            parent_job_id=parent_job_id,
            completed_at=datetime.utcnow(),
        )

        # Mark main job as completed in Redis
        redis_client.set_job_status(
            job_id=parent_job_id,
            job_type="main",
            status="completed",
            progress=100,
            completed_at=datetime.utcnow(),
        )

        logger.info(f"[MERGE JOB {merge_job_id}] Completed - main job {parent_job_id} finished")

        # Cleanup temp files (pages, merged output and the uploaded file; the original
        # and the split per-page PDFs stay in MinIO unless the job asked for purge_source)
        _remove_job_files(parent_job_id)
        # purge_source: deletes the original *and* the split per-page PDFs (MinIO + local)
        _purge_source_if_requested(parent_job_id)
        logger.info(f"[MERGE JOB {merge_job_id}] Cleanup completed")

        return {"merge_job_id": merge_job_id, "pages_merged": total_pages}

    except Exception as exc:
        logger.error(f"[MERGE JOB {merge_job_id}] Failed: {exc}", exc_info=True)

        # Update Redis
        redis_client.set_job_status(
            job_id=merge_job_id,
            job_type="merge",
            status="failed",
            parent_job_id=parent_job_id,
            error=str(exc),
            completed_at=datetime.utcnow(),
        )

        # Update MySQL: the parent stays PROCESSING while Celery will run the merge
        # again (its source files must not be purged meanwhile); FAILED after the last try
        retrying = _will_retry(self)
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == parent_job_id).first()
            if job:
                job.status = JobStatus.PROCESSING if retrying else JobStatus.FAILED
                job.error_message = f"Merge failed: {str(exc)}"
                job.completed_at = None if retrying else datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.error(f"[MERGE JOB {merge_job_id}] MySQL failure error: {e}")
        finally:
            db.close()
        if not retrying:
            _purge_source_if_requested(parent_job_id)

        raise _retry_or_settle(
            self, exc=exc, countdown=30 * (2 ** self.request.retries),
            settle=(lambda error: _record_main_failure(parent_job_id, redis_client, error, retrying=False))
            if retrying else None)


def _delete_dropped_assets(job_id: str, dropped: list) -> None:
    """The merge dropped these assets (per-job limits across pages): their PNGs go too."""
    if not dropped:
        return
    try:
        minio = get_minio_client()
        for asset in dropped:
            minio.delete_file(minio.bucket_results, conversion_assets.object_name(job_id, asset["name"]))
    except Exception as e:  # noqa: BLE001 - unlisted, never served; DELETE /jobs/{id} removes them
        logger.warning(f"[MERGE] Could not delete {len(dropped)} assets over the limits of job {job_id}: {e}")


# ============================================
# Helper functions
# ============================================

def send_callback(callback_url: str, job_id: str, status: str, result: dict = None):
    """Send webhook callback"""
    import httpx

    payload = {
        "job_id": job_id,
        "status": status,
        "completed_at": datetime.utcnow().isoformat(),
        "result_url": f"/jobs/{job_id}/result",
    }

    if result:
        payload["result"] = result

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(callback_url, json=payload)
            response.raise_for_status()
            logger.info(f"Callback sent successfully to {callback_url}")
    except Exception as e:
        logger.error(f"Failed to send callback: {e}")
        raise


