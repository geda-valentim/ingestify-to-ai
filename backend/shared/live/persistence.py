"""Strict completion: durable formats, ES, cache, then fenced SQL publication.

Only generation-specific objects are ever cleaned on failure. Existing batch
completion retains its historical best-effort policy.
"""
import time
from datetime import datetime
from shared.database import SessionLocal
from shared.live.lifecycle import lock_rows
from shared.live.protocol import LiveError
from shared.models import JobStatus
from shared.minio_client import get_minio_client
from shared.transcripts import transcript_object_name, TRANSCRIPT_CONTENT_TYPES
from workers.engines.pipeline import build_transcription_outputs


def finish_live(job_id, generation, result, store, redis_client, es_client, processing_seconds, compute_type):
    payload, outputs = build_transcription_outputs(
        result, options={}, input_metadata={'format': 'pcm', 'size_bytes': int(result['duration'] * 16000) * 2,
            'input_mode': 'live', 'protocol': 1, 'generation': generation}, processing_seconds=processing_seconds, compute_type=compute_type)
    minio = get_minio_client()
    written = []
    published = False
    indexed = False
    try:
        # No DB transaction is held during inference or external writes.
        with SessionLocal() as db:
            job, live = lock_rows(db, job_id)
            if not job or not live or live.state != 'finalizing' or live.generation != generation:
                raise LiveError('LIVE_SESSION_GONE', 4404)
            user_id, filename = job.user_id, job.filename
        for fmt, content in outputs.items():
            if not store.valid(job_id, generation):
                raise LiveError('LIVE_LEASE_LOST', 1011)
            object_name = transcript_object_name(job_id, fmt, generation)
            # Include even a failed attempt in cleanup (upload can write then
            # lose the acknowledgement).
            written.append(object_name)
            if not minio.upload_file(bucket_name=minio.bucket_audio, object_name=object_name,
                                     file_data=content.encode('utf-8'), content_type=TRANSCRIPT_CONTENT_TYPES[fmt]):
                raise LiveError('LIVE_STORAGE_FAILED', 1011)
        for attempt in range(3):
            if not store.valid(job_id, generation):
                raise LiveError('LIVE_LEASE_LOST', 1011)
            indexed = es_client.store_job_result(job_id=job_id, markdown_content=payload['markdown'],
                user_id=user_id, filename=filename, total_pages=None, metadata=payload['metadata'])
            if indexed:
                break
            time.sleep(.1 * (attempt + 1))
        if not indexed:
            raise LiveError('LIVE_INDEX_FAILED', 1011)
        with SessionLocal() as db:
            job, live = lock_rows(db, job_id)
            if not job or not live or live.state != 'finalizing' or live.generation != generation or not store.valid(job_id, generation):
                raise LiveError('LIVE_SESSION_GONE', 4404)
            # Status remains processing until after the SQL publication. Live
            # result routes additionally require a completed MySQL session.
            if not redis_client.set_job_result(job_id, payload):
                raise LiveError('LIVE_STORE_UNAVAILABLE', 1011)
            completed_at = datetime.utcnow()
            from shared.config import get_settings
            if get_settings().engine_control_enabled:
                from shared.engine_control.models import ControlAdmission
                db.query(ControlAdmission).filter(ControlAdmission.holder == 'live:' + job_id,
                    ControlAdmission.released_at.is_(None)).update({'released_at':datetime.utcnow()}, synchronize_session=False)
            live.state, live.ended_at = 'completed', completed_at
            job.status, job.completed_at = JobStatus.COMPLETED, live.ended_at
            job.char_count, job.has_elasticsearch_result = result['char_count'], True
            # Cache publication is inside the same row lock as DELETE/cancel.
            # No cache mutation after commit can resurrect a deleted job.
            if not redis_client.set_job_status(job_id, 'main', 'completed', progress=100, completed_at=completed_at):
                raise LiveError('LIVE_STORE_UNAVAILABLE', 1011)
            redis_client.delete_partial_transcript(job_id)
            db.commit()
            published = True
        return payload
    finally:
        if not published:
            for name in written:
                minio.delete_file(minio.bucket_audio, name)
            if indexed:
                es_client.delete_job_result(job_id)
            redis_client.client.delete(f'job:{job_id}:result')
