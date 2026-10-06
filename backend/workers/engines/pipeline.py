"""
What happens to a feature's result after it was computed, wherever it ran.

The local transcription and, later, a remote engine's both end here, so a
transcript is formatted, stored and indexed the same way whichever engine
produced it (spec 0003, slice 1a).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from shared.database import SessionLocal
from shared.minio_client import get_minio_client
from shared.models import Job, JobStatus
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES, transcript_object_name
from workers.audio.base_transcriber import format_markdown, format_srt, format_text, format_vtt

logger = logging.getLogger(__name__)


def finish_transcription(
    job_id: str,
    result: Dict[str, Any],
    *,
    options: Dict[str, Any],
    file_path: Path,
    processing_seconds: float,
    compute_type: Optional[str],
    redis_client,
    es_client,
) -> None:
    """
    Turn a transcription result into the job's outputs and complete the job.

    `result` has the shape AudioTranscriber.transcribe() returns (text, segments,
    language, duration, word_count, char_count, provider, model, device, ...).
    Formats markdown/vtt/srt/txt/json, stores them in MinIO and the Redis result,
    indexes the markdown in Elasticsearch, marks the job COMPLETED in MySQL and
    Redis, and removes the job's local files (and the source media with
    purge_source).
    """
    if result.get('schema_version') == 2:
        return _finish_strict(job_id, result, options=options, file_path=file_path,
            processing_seconds=processing_seconds, compute_type=compute_type,
            redis_client=redis_client, es_client=es_client)
    result_with_markdown, transcript_outputs = build_transcription_outputs(
        result, options=options, input_metadata={
            'format': file_path.suffix.lower().lstrip('.') or options.get('media_kind', 'audio'),
            'size_bytes': file_path.stat().st_size,
        }, processing_seconds=processing_seconds, compute_type=compute_type)
    markdown_content = result_with_markdown['markdown']
    store_transcript_outputs(job_id, transcript_outputs)

    redis_client.set_job_result(job_id, result_with_markdown)
    redis_client.delete_partial_transcript(job_id)  # the full result supersedes it
    redis_client.update_job_progress(job_id, 80)

    # Store result in Elasticsearch
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
        total_pages=None,  # Audio files don't have pages
        metadata=result_with_markdown['metadata']
    )

    if es_success:
        logger.info(f"[MAIN JOB {job_id}] Result stored in Elasticsearch")
    else:
        logger.warning(f"[MAIN JOB {job_id}] Failed to store result in Elasticsearch")

    redis_client.update_job_progress(job_id, 90)

    # Update MySQL with completion
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.char_count = result['char_count']
            job.has_elasticsearch_result = es_success
            db.commit()
            logger.info(f"[MAIN JOB {job_id}] MySQL updated with completion")
    except Exception as e:
        logger.error(f"[MAIN JOB {job_id}] MySQL update error: {e}")
    finally:
        db.close()

    # Mark as completed
    redis_client.set_job_status(
        job_id=job_id,
        job_type="main",
        status="completed",
        progress=100,
        completed_at=datetime.utcnow()
    )

    # Shared with the document path, so it stays in tasks; imported here to keep
    # tasks -> pipeline the only import direction at module load
    from workers.tasks import _remove_job_files

    _remove_job_files(job_id)
    if options.get('purge_source'):
        purge_audio_source(job_id)


def purge_audio_source(job_id: str) -> None:
    """Delete a transcription's uploaded media from MinIO, keeping only the transcripts (purge_source=true)"""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or not job.minio_upload_path:
            return
        minio_client = get_minio_client()
        if minio_client.delete_file(minio_client.bucket_audio, job.minio_upload_path):
            job.minio_upload_path = None
            db.commit()
            logger.info(f"[MAIN JOB {job_id}] Source media purged")
    except Exception as e:
        logger.error(f"[MAIN JOB {job_id}] Could not purge source media: {e}")
    finally:
        db.close()


def store_transcript_outputs(job_id: str, outputs: dict) -> None:
    """Persist transcript formats in the private audio bucket so they outlive the Redis result TTL"""
    try:
        minio_client = get_minio_client()
    except Exception as e:
        logger.warning(f"[MAIN JOB {job_id}] MinIO unavailable, transcript files kept only in Redis: {e}")
        return

    for fmt, content in outputs.items():
        # Empty outputs are valid (e.g. SRT of a recording without speech) and stored too
        try:
            minio_client.upload_file(
                bucket_name=minio_client.bucket_audio,
                object_name=transcript_object_name(job_id, fmt),
                file_data=content.encode('utf-8'),
                content_type=TRANSCRIPT_CONTENT_TYPES[fmt],
            )
        except Exception as e:
            logger.warning(f"[MAIN JOB {job_id}] Failed to store transcript.{fmt} in MinIO: {e}")


def build_transcription_outputs(result, *, options, input_metadata, processing_seconds, compute_type):
    """Shared formats/metadata for file input and strict live finalization."""
    from workers.engines.transcript_schema import validate_result
    result = validate_result(result)
    fields = ('language', 'duration', 'text', 'segments')
    if result.get('schema_version') == 2:
        fields += ('schema_version', 'speakers', 'diarization', 'alignment', 'provenance')
    outputs = {
        'vtt': format_vtt(result), 'srt': format_srt(result), 'txt': format_text(result),
        'json': json.dumps({k: result.get(k) for k in fields},
                           ensure_ascii=False, allow_nan=False),
    }
    metadata = {
        **input_metadata, 'words': result['word_count'], 'language': result['language'],
        'duration': result['duration'], 'word_count': result['word_count'],
        'char_count': result['char_count'], 'provider': result.get('provider', 'unknown'),
        'model': result.get('model', 'unknown'), 'device': result.get('device'),
        'compute_type': compute_type, 'language_probability': result.get('language_probability'),
        'processing_seconds': processing_seconds, 'output_format': options.get('output_format', 'markdown'),
        'available_formats': ['markdown'] + list(outputs),
    }
    for field in ('schema_version', 'speakers', 'diarization', 'alignment', 'provenance'):
        if field in result:
            metadata[field] = result[field]
    return {'markdown': format_markdown(result, options.get('include_timestamps', True)),
            'metadata': metadata, 'transcript': outputs}, outputs


def begin_transcription_attempt(job_id, options, *, session_factory=None, attempt_id=None):
    """Fence a fresh schema 2 attempt before inference; retries supersede old IDs."""
    from uuid import uuid4
    attempt_id = attempt_id or str(uuid4())
    with (session_factory or SessionLocal)() as db:
        _check_usage_fence(db, options)
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
            raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')
        if '_expected_attempt_id' in options and options['_expected_attempt_id'] != job.transcript_attempt_id:
            raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')
        job.transcript_attempt_id = attempt_id
        db.commit()
    options['_transcript_attempt_id'] = attempt_id
    return attempt_id


def _finish_strict(job_id, result, *, options, file_path, processing_seconds,
                   compute_type, redis_client, es_client):
    """All durable artifacts precede success; only this fenced attempt is cleaned.

    External object writes use immutable attempt prefixes outside a transaction.
    The small publication transaction serializes with cancellation/retry/deletion;
    ES acknowledgement and cache publication happen while owning the SQL row.
    """
    attempt = options.get('_transcript_attempt_id')
    if not attempt:
        raise RuntimeError('TRANSCRIPTION_ATTEMPT_REQUIRED')
    payload, outputs = build_transcription_outputs(result, options=options,
        input_metadata={'format': file_path.suffix.lstrip('.'), 'size_bytes': file_path.stat().st_size,
                        'transcript_attempt_id': attempt},
        processing_seconds=processing_seconds, compute_type=compute_type)
    minio = get_minio_client()
    written, published = [], False
    try:
        for fmt, content in outputs.items():
            with SessionLocal() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING) or job.transcript_attempt_id != attempt:
                    raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')
            name = transcript_object_name(job_id, fmt, attempt_id=attempt)
            written.append(name)
            if not minio.upload_file(bucket_name=minio.bucket_audio, object_name=name,
                    file_data=content.encode('utf-8'), content_type=TRANSCRIPT_CONTENT_TYPES[fmt]):
                raise RuntimeError('TRANSCRIPT_STORAGE_FAILED')
        with SessionLocal() as db:
            _check_usage_fence(db, options)
            job = db.query(Job).filter(Job.id == job_id).with_for_update().populate_existing().first()
            if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING) or job.transcript_attempt_id != attempt:
                raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')
            if not es_client.store_job_result(job_id=job_id, markdown_content=payload['markdown'],
                    user_id=job.user_id, filename=job.filename, total_pages=None, metadata=payload['metadata']):
                raise RuntimeError('TRANSCRIPT_INDEX_FAILED')
            try:
                job.status, job.completed_at = JobStatus.COMPLETED, datetime.utcnow()
                job.char_count, job.has_elasticsearch_result = result['char_count'], True
                # SQL completion is the authoritative publication gate. Reader
                # checks it even if the cache is populated before this commit.
                if not redis_client.set_job_result(job_id, payload):
                    raise RuntimeError('TRANSCRIPT_CACHE_FAILED')
                db.commit()
                published = True
            except Exception:
                db.rollback()
                # Never delete canonical ES/cache after releasing the SQL lock:
                # a newer attempt may have published meanwhile. SQL keeps this
                # failed publication invisible; retry replaces the payload.
                raise
        # Reacquire the row before post-commit cache mutation: DELETE may have
        # run after publication; cache writes must not resurrect its results.
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
            if job and job.status == JobStatus.COMPLETED and job.transcript_attempt_id == attempt:
                redis_client.delete_partial_transcript(job_id)
                redis_client.set_job_status(job_id=job_id, job_type='main', status='completed', progress=100,
                                            completed_at=job.completed_at)
        from workers.tasks import _remove_job_files
        _remove_job_files(job_id)
        if options.get('purge_source'):
            purge_audio_source(job_id)
    finally:
        if not published:
            for name in written:
                minio.delete_file(minio.bucket_audio, name)


def _check_usage_fence(db, options):
    usage_id = options.get('_usage_id')
    if usage_id is None:
        return
    from shared.models import EngineUsage, JobDispatch
    usage = db.query(EngineUsage).filter(EngineUsage.id == usage_id).with_for_update().first()
    dispatch = db.query(JobDispatch).filter(JobDispatch.subject_type == 'job',
                                           JobDispatch.subject_id == usage.job_id).first() if usage else None
    if not usage or usage.holder != options.get('_usage_holder') or usage.status not in ('spawning', 'running') or not dispatch or dispatch.usage_id != usage_id:
        raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')


def with_transcription_attempt(job_id, options, callback, *, session_factory=None):
    """Serialize transient updates with terminal state, takeover and publication."""
    with (session_factory or SessionLocal)() as db:
        try:
            _check_usage_fence(db, options)
        except RuntimeError:
            return False
        job = db.query(Job).filter(Job.id == job_id).with_for_update().populate_existing().first()
        if not job or job.status not in (JobStatus.PENDING, JobStatus.PROCESSING) or job.transcript_attempt_id != options.get('_transcript_attempt_id'):
            return False
        callback()
        return True
