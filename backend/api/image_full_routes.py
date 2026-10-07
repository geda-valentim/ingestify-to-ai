"""Full image submission and cancellation; native image endpoints stay intact."""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from shared.models import Job, JobStatus, ImageAnalysisRun as Run, ImageAnalysisSubmission as Submission
from shared.config import get_settings
from shared.image_full import fingerprint, TERMINAL
from shared.job_configuration import save_configuration
from shared.minio_client import get_minio_client
from shared.tags import set_job_tags
from shared.schemas import ImageFullAnalyzeResponse
from shared.datalake.service import prepare_destination, bind_destination


class _AttemptRace(Exception):
    """Another request started the next attempt of this Idempotency-Key first."""


@dataclass
class Previous:
    """The latest attempt recorded for one (user, Idempotency-Key)."""
    row: Submission
    job_id: str
    attempt: int
    failed: bool  # FAILED for good: the same key starts the next attempt


def lookup(db, user_id, key_hash, request_hash):
    """
    The latest attempt of a key (None when the key is new). 410 when its job was
    deleted, 409 when the key was used for another request.

    Idempotency-Key covers one *attempt*: while the latest attempt is queued,
    running or settled other than FAILED, the same key replays it; once it FAILED
    for good, the same key starts attempt+1 (a new job), so a retry with the same
    key never returns the failed job.
    """
    row = db.query(Submission).filter_by(user_id=user_id, key_hash=key_hash).first()
    if row is None:
        return None
    job = db.get(Job, row.job_id) if row.job_id else None
    if row.deleted_at or job is None:
        if row.deleted_at and row.purged_at and row.deleted_at < datetime.utcnow()-timedelta(hours=24):
            db.delete(row)
            db.commit()
            return None
        raise HTTPException(410, 'Job excluído; use nova Idempotency-Key para outra solicitação')
    if row.request_hash != request_hash:
        raise HTTPException(409, 'Idempotency-Key já utilizada com outra solicitação')
    return Previous(row=row, job_id=row.job_id, attempt=row.attempt or 1, failed=job.status == JobStatus.FAILED)


def replay(db, user_id, key_hash, request_hash):
    """The job a repeated request returns, or None when it must create one."""
    previous = lookup(db, user_id, key_hash, request_hash)
    return previous.job_id if previous is not None and not previous.failed else None


def submit(request, http_request, image_bytes, filename, current_user, db, tags, plan):
    from api.image_routes import _validate_image_bytes, _safe_filename, _location_step
    from api.projects_api import resolve_upload_location
    settings = get_settings()
    key = http_request.headers.get('Idempotency-Key')
    if not key or not key.strip() or len(key) > 128:
        raise HTTPException(422, 'Idempotency-Key é obrigatória para análise composta (1..128 caracteres)')
    mime = _validate_image_bytes(image_bytes)
    name = _safe_filename(filename, mime)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    standalone_faces = hasattr(request, 'face_options')
    mode = 'faces' if standalone_faces else 'full'
    raw_options = request.face_options.effective() if standalone_faces else request.full_options.model_dump(mode='json')
    request_hash = fingerprint({'image_sha256': hashlib.sha256(image_bytes).hexdigest(), 'filename': name,
        'mode': mode, 'options': raw_options, 'location': {'project': request.project, 'project_id': request.project_id,
        'folder': request.folder, 'folder_id': request.folder_id}, 'tags': tags,
        'datalake': request.datalake.model_dump(mode='json') if request.datalake else None})
    # purge_source is deliberately not part of request_hash: a replay of the key
    # returns the existing attempt unchanged, whatever purge_source it carries (it
    # neither turns purging on nor off for that job: DELETE /jobs/{id}/source does)
    previous = lookup(db, current_user.id, key_hash, request_hash)
    if previous is not None and not previous.failed:
        return previous.job_id, previous.attempt
    face_models = []
    if standalone_faces or raw_options.get('profile') == 'image-full-v2':
        from api.face_routes import require_faces
        face_models = require_faces(raw_options['mode'] if standalone_faces else 'expressions')['models']
        if not standalone_faces:
            from api.image_routes import _read_capabilities_heartbeat
            try:
                native = _read_capabilities_heartbeat() or {}
            except Exception:
                native = {}
            if not native.get('dependencies_installed') or not native.get('model_downloaded'):
                raise HTTPException(503, 'Florence não está pronto para Full Analysis v2')
    try:
        destination = prepare_destination(db, current_user.id, request.datalake)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    location = _location_step(resolve_upload_location, db, current_user, plan, http_request.url.path)
    job_id = str(uuid4())
    storage = get_minio_client()
    source_path = f'images/{job_id}/source'
    options = dict(raw_options)
    if not standalone_faces:
        options['generation']['max_new_tokens'] = options['generation']['max_new_tokens'] or settings.vision_max_new_tokens
        options['generation']['num_beams'] = options['generation']['num_beams'] or settings.vision_num_beams
    now = datetime.utcnow()
    deadline_seconds = min(options['deadline_seconds'], 300 if standalone_faces else settings.vision_full_task_timeout_seconds, 300 if standalone_faces else 900)
    options['deadline_seconds'] = deadline_seconds
    configuration = {'mode': mode, ('face_options' if standalone_faces else 'full_options'): options, 'provider': settings.vision_provider,
                     'model': {'model_id': settings.vision_model_id, 'revision': settings.vision_model_revision,
                               'device': 'pending', 'dtype': 'pending'}}
    if face_models:
        configuration['face_models'] = face_models
    try:
        job = Job(id=job_id, user_id=current_user.id, filename=name, name=name, source_type='image',
            mime_type=mime, file_size_bytes=len(image_bytes), file_checksum=hashlib.sha256(image_bytes).hexdigest(),
            job_type='MAIN', status=JobStatus.PENDING, created_at=now,
            project_id=location.project_id, folder_id=location.folder_id)
        db.add(job)
        db.flush()
        set_job_tags(job, tags)
        save_configuration(db, job, operation='image', options=configuration, provider='facial' if standalone_faces else settings.vision_provider, model='enet_b0_8_best_afew' if standalone_faces else settings.vision_model_id)
        bind_destination(db, job, destination)
        if getattr(request, 'purge_source', False):
            # Durable on the job: finish() writes the report without the image and
            # the purge runs once the job settles (shared.job_source, "Image jobs")
            from shared.job_source import save_purge_option
            save_purge_option(db, job)
        if previous is None:
            attempt = 1
            db.add(Submission(user_id=current_user.id, key_hash=key_hash, request_hash=request_hash,
                              job_id=job_id, attempt=attempt))
        else:
            # Compare-and-set on the key's row: only one request moves it from the
            # failed attempt to the next one (the loser replays the winner's job)
            attempt = previous.attempt + 1
            moved = db.query(Submission).filter(
                Submission.id == previous.row.id, Submission.attempt == previous.attempt,
                Submission.job_id == previous.job_id,
            ).update({'attempt': attempt, 'job_id': job_id}, synchronize_session=False)
            if moved != 1:
                raise _AttemptRace()
        from shared.face_analysis import profile
        db.add(Run(job_id=job_id, profile=profile(configuration), options=configuration, source_path=source_path,
                   deadline_at=now+timedelta(seconds=deadline_seconds), dispatch_after=now))
        db.flush()  # Unique idempotency key owns this transaction before object write.
        if not storage.upload_file(bucket_name=storage.bucket_results, object_name=source_path,
            file_data=image_bytes, content_type=mime):
            raise RuntimeError('Source persistence unavailable')
        if hashlib.sha256(storage.download_file(storage.bucket_results, source_path)).hexdigest() != job.file_checksum:
            raise RuntimeError('Source checksum mismatch')
        db.commit()  # Source + key + configuration + outbox/run are ready together.
    except (IntegrityError, _AttemptRace):
        db.rollback()
        db.expire_all()
        previous = lookup(db, current_user.id, key_hash, request_hash)
        if previous is None or previous.failed:
            raise HTTPException(503, 'Conflito ao preservar a solicitação; tente novamente')
        return previous.job_id, previous.attempt
    except Exception as exc:
        db.rollback()
        storage.delete_folder(storage.bucket_results, f'images/{job_id}/')
        raise HTTPException(503, 'Não foi possível preservar a imagem e sua configuração') from exc
    from workers.image_full_tasks import dispatch
    try:
        dispatch(job_id)
    except Exception:
        # Durable outbox is recovered by beat. Never lose the owned request.
        pass
    return job_id, attempt


async def run_full(request, http_request, image_bytes, filename, user, db, tags, plan):
    job_id, attempt = await run_in_threadpool(submit, request, http_request, image_bytes, filename, user, db, tags, plan)
    if request.wait:
        deadline = asyncio.get_running_loop().time()+get_settings().vision_request_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            db.expire_all()
            job = db.get(Job, job_id)
            if job and job.status.value in TERMINAL and job.minio_result_path:
                storage = get_minio_client()
                payload = json.loads(await run_in_threadpool(storage.download_file, storage.bucket_results, job.minio_result_path))
                from shared.schemas import FaceAnalyzeResponse
                response = FaceAnalyzeResponse if hasattr(request, 'face_options') else ImageFullAnalyzeResponse
                return response(job_id=job_id, status=job.status.value, attempt=attempt, **payload)
            await asyncio.sleep(.25)
        raise HTTPException(504, {'error_code': 'VISION_TIMEOUT', 'message': 'Análise da imagem continua processando',
            'job_id': job_id, 'poll_url': f'/jobs/{job_id}', 'result_url': f'/jobs/{job_id}/result'})
    job = db.get(Job, job_id)
    return JSONResponse(status_code=202, content={'job_id': job_id, 'status': 'queued' if job.status == JobStatus.PENDING else job.status.value,
        'created_at': job.created_at.isoformat()+'Z', 'message': 'Análise da imagem enfileirada', 'attempt': attempt,
        'poll_url': f'/jobs/{job_id}', 'result_url': f'/jobs/{job_id}/result'})
