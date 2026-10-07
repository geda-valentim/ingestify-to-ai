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
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES, transcript_object_name, transcript_result_object_name
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
    result_with_markdown, transcript_outputs = build_transcription_outputs(
        result, options=options, input_metadata={
            'format': file_path.suffix.lower().lstrip('.') or options.get('media_kind', 'audio'),
            'size_bytes': file_path.stat().st_size,
        }, processing_seconds=processing_seconds, compute_type=compute_type)
    markdown_content = result_with_markdown['markdown']
    store_transcript_outputs(job_id, transcript_outputs, result_with_markdown)

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

    try:
        es_success = es_client.store_job_result(
            job_id=job_id,
            markdown_content=markdown_content,
            user_id=user_id,
            filename=filename,
            total_pages=None,  # Audio files don't have pages
            metadata=result_with_markdown['metadata']
        )
    except Exception:
        logger.exception("[MAIN JOB %s] Indexing failed; durable result is available", job_id)
        es_success = False

    if es_success:
        logger.info(f"[MAIN JOB {job_id}] Result stored in Elasticsearch")
    else:
        logger.warning(f"[MAIN JOB {job_id}] Failed to store result in Elasticsearch")

    redis_client.update_job_progress(job_id, 90)

    # Update MySQL with completion
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            raise RuntimeError(f"Job {job_id} no longer exists")
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.utcnow()
        job.char_count = result['char_count']
        job.has_elasticsearch_result = es_success
        db.commit()
        logger.info(f"[MAIN JOB {job_id}] MySQL updated with completion")
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
    from shared.datalake.service import enqueue_export
    enqueue_export(job_id, session_factory=SessionLocal)

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


def store_transcript_outputs(job_id: str, outputs: dict, payload=None) -> None:
    """All writes must succeed before SQL completion or removal of source files."""
    minio_client = get_minio_client()
    for fmt, content in outputs.items():
        # Empty outputs are valid (e.g. SRT of a recording without speech) and stored too
        if not minio_client.upload_file(
            bucket_name=minio_client.bucket_audio,
            object_name=transcript_object_name(job_id, fmt),
            file_data=content.encode('utf-8'),
            content_type=TRANSCRIPT_CONTENT_TYPES[fmt],
        ):
            raise RuntimeError(f"Transcript {fmt} was not persisted for job {job_id}")
    if payload is not None:
        if not minio_client.upload_file(
            bucket_name=minio_client.bucket_audio,
            object_name=transcript_result_object_name(job_id),
            file_data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            content_type='application/json',
        ):
            raise RuntimeError(f"Full transcript result was not persisted for job {job_id}")


def build_transcription_outputs(result, *, options, input_metadata, processing_seconds, compute_type):
    """Shared formats/metadata for file input and strict live finalization."""
    outputs = {
        'vtt': format_vtt(result), 'srt': format_srt(result), 'txt': format_text(result),
        'json': json.dumps({**result, 'configuration': options}, ensure_ascii=False),
    }
    metadata = {
        **input_metadata, 'words': result['word_count'], 'language': result['language'],
        'duration': result['duration'], 'word_count': result['word_count'],
        'char_count': result['char_count'], 'provider': result.get('provider', 'unknown'),
        'model': result.get('model', 'unknown'), 'device': result.get('device'),
        'compute_type': compute_type, 'language_probability': result.get('language_probability'),
        'processing_seconds': processing_seconds, 'output_format': options.get('output_format', 'markdown'),
        'available_formats': ['markdown'] + list(outputs),
        'configuration': options,
    }
    return {'markdown': format_markdown(result, options.get('include_timestamps', True)),
            'metadata': metadata, 'transcript': outputs}, outputs
