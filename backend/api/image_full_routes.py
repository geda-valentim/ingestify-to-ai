"""Full image submission and cancellation; native image endpoints stay intact."""
import asyncio
import hashlib
import json
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


def replay(db, user_id, key_hash, request_hash):
    row = db.query(Submission).filter_by(user_id=user_id, key_hash=key_hash).first()
    if row is None:
        return None
    if row.deleted_at or not db.get(Job, row.job_id):
        if row.deleted_at and row.purged_at and row.deleted_at < datetime.utcnow()-timedelta(hours=24):
            db.delete(row)
            db.commit()
            return None
        raise HTTPException(410, 'Job excluído; use nova Idempotency-Key para outra solicitação')
    if row.request_hash != request_hash:
        raise HTTPException(409, 'Idempotency-Key já utilizada com outra solicitação')
    return row.job_id


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
    previous = replay(db, current_user.id, key_hash, request_hash)
    if previous:
        return previous
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
        db.add(Submission(user_id=current_user.id, key_hash=key_hash, request_hash=request_hash, job_id=job_id))
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
    except IntegrityError:
        db.rollback()
        previous = replay(db, current_user.id, key_hash, request_hash)
        if not previous:
            raise HTTPException(503, 'Conflito ao preservar a solicitação; tente novamente')
        return previous
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
    return job_id


async def run_full(request, http_request, image_bytes, filename, user, db, tags, plan):
    job_id = await run_in_threadpool(submit, request, http_request, image_bytes, filename, user, db, tags, plan)
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
                return response(job_id=job_id, status=job.status.value, **payload)
            await asyncio.sleep(.25)
        raise HTTPException(504, {'error_code': 'VISION_TIMEOUT', 'message': 'Análise da imagem continua processando',
            'job_id': job_id, 'poll_url': f'/jobs/{job_id}', 'result_url': f'/jobs/{job_id}/result'})
    job = db.get(Job, job_id)
    return JSONResponse(status_code=202, content={'job_id': job_id, 'status': 'queued' if job.status == JobStatus.PENDING else job.status.value,
        'created_at': job.created_at.isoformat()+'Z', 'message': 'Análise da imagem enfileirada',
        'poll_url': f'/jobs/{job_id}', 'result_url': f'/jobs/{job_id}/result'})
