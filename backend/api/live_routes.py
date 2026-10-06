"""Authenticated live admission and bounded public/private WebSocket relay."""
import asyncio
import math
import time
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db, SessionLocal
from shared.models import Job, JobStatus, LiveSession, User
from shared.redis_client import get_redis_client
from shared.elasticsearch_client import get_es_client
from shared.tags import set_job_tags
from shared.live.protocol import AudioClock, LiveError, control, RATE, TERMINAL
from shared.live.store import LiveStore
from shared.live.lifecycle import available, transition, terminate, sweep
from shared.live.persistence import finish_live
from api.deps import get_owned_job
from api.projects_api import LocationFields, prepare_upload_location, resolve_upload_location
from api.tag_routes import parse_tags_or_422

router = APIRouter(prefix='/transcribe/live/sessions', tags=['Live transcription'])
handshakes = 0
MAX_HANDSHAKES = 32


class AudioFormat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    encoding: Literal['pcm_s16le'] = 'pcm_s16le'
    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1


class CreateSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: Optional[str] = None
    project_id: Optional[str] = None
    folder: Optional[str] = None
    folder_id: Optional[str] = None
    name: str = Field('Transcrição ao vivo', min_length=1, max_length=1000)
    tags: list[str] = Field(default_factory=list)
    language: Literal['pt'] = 'pt'
    audio: AudioFormat = Field(default_factory=AudioFormat)


def get_store():
    return LiveStore(get_redis_client().client, get_settings().live_worker_id)


def live_owned(job_id, owned_job, db):
    if owned_job is None or owned_job.id != job_id or not available(db):
        raise HTTPException(404, detail='Sessão não encontrada')
    live = db.get(LiveSession, job_id)
    if live is None:
        raise HTTPException(404, detail='Sessão não encontrada')
    return live


def unavailable(code):
    raise HTTPException(503, detail={'code': code}, headers={'Retry-After': '5'})


@router.post('', status_code=201)
def create_session(body: CreateSession, request: Request, response: Response,
                   user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settings = get_settings()
    fields = LocationFields(body.project, body.project_id, body.folder, body.folder_id)
    plan = prepare_upload_location(db, user, request, fields)
    tags = parse_tags_or_422(body.tags)
    if not settings.live_transcription_enabled:
        unavailable('LIVE_DISABLED')
    if len(settings.live_internal_token) < 32 or not available(db):
        unavailable('LIVE_NOT_READY')
    store, cache = get_store(), get_redis_client()
    job_id, committed = str(uuid.uuid4()), False
    generation = None
    admission_tickets = []
    try:
        from shared.engine_control.admission import acquire
        admission_tickets = acquire('live-transcription', 'live:' + job_id)
        lease, worker = store.reserve(job_id)
        generation = lease['generation']
        location = resolve_upload_location(db, user, plan, '/transcribe/live/sessions')
        job = Job(id=job_id, user_id=user.id, project_id=location.project_id, folder_id=location.folder_id,
            name=body.name, filename='live.pcm', source_type='audio', job_type='MAIN',
            mime_type='application/octet-stream', status=JobStatus.PENDING)
        db.add(job)
        db.flush()
        set_job_tags(job, tags)
        db.add(LiveSession(job_id=job_id, state='created', backend=worker['backend'], model=worker['model'],
            language=body.language, worker_id=lease['worker_id'], generation=generation, audio_samples=0))
        db.commit()
        committed = True
        if not cache.set_job_status(job_id, 'main', 'pending', name=body.name):
            raise LiveError('LIVE_STORE_UNAVAILABLE', 1011)
        cache.set_job_owner(job_id, user.id)
        ticket = store.ticket(lease, user.id)
        response.headers['Cache-Control'] = 'no-store'
        ws_url = str(request.url_for('live_stream', job_id=job_id))
        return {'job_id': job_id, 'status': 'pending', 'ws_url': ws_url, 'ticket': ticket,
                'ticket_expires_in': 60, 'audio': body.audio.model_dump(), 'chunk_ms': 200,
                'max_duration_seconds': settings.live_max_duration_seconds}
    except Exception as exc:
        db.rollback()
        from shared.engine_control.admission import release
        release(admission_tickets)
        if generation is not None:
            if committed:
                terminate(job_id, 'failed', 'LIVE_ADMISSION_FAILED', store, cache, generation)
            else:
                store.release(job_id, generation)
        if isinstance(exc, HTTPException):
            raise
        unavailable(exc.code if isinstance(exc, LiveError) else 'LIVE_NOT_READY')


@router.get('/{job_id}')
def session_status(job_id: str, user: User = Depends(get_current_active_user),
                   owned_job: Job = Depends(get_owned_job), db: Session = Depends(get_db)):
    live = live_owned(job_id, owned_job, db)
    return {'job_id': job_id, 'state': live.state, 'duration_seconds': live.audio_samples / RATE,
            'backend': live.backend, 'model': live.model, 'language': live.language,
            'error_code': live.error_code, 'ended_at': live.ended_at}


@router.delete('/{job_id}')
def cancel_session(job_id: str, user: User = Depends(get_current_active_user),
                   owned_job: Job = Depends(get_owned_job), db: Session = Depends(get_db)):
    live_owned(job_id, owned_job, db)
    db.rollback()
    terminate(job_id, 'cancelled', 'LIVE_CANCELLED', get_store(), get_redis_client())
    return {'job_id': job_id, 'state': db.get(LiveSession, job_id).state}


async def sweeper_loop():
    while True:
        try:
            await asyncio.to_thread(sweep, get_store(), get_redis_client())
        except Exception:
            # No connection contents or exception parameters in logs.
            import logging
            logging.getLogger(__name__).warning('Live sweeper unavailable; admission remains lease-fenced')
        await asyncio.sleep(5)


@router.websocket('/{job_id}/stream', name='live_stream')
async def live_stream(ws: WebSocket, job_id: str):
    global handshakes
    settings = get_settings()
    if not settings.live_transcription_enabled or handshakes >= MAX_HANDSHAKES:
        await ws.close(1013)
        return
    origin = ws.headers.get('origin')
    if origin and origin not in settings.cors_origins:
        await ws.close(4403)
        return
    if settings.environment == 'production' and ws.scope.get('scheme') != 'wss':
        await ws.close(4403)
        return
    handshakes += 1
    try:
        await ws.accept()
    except BaseException:
        handshakes -= 1
        raise
    tasks = []
    store, cache = get_store(), get_redis_client()
    generation = None
    event_seq = 0
    output_lock = asyncio.Lock()
    clock = AudioClock(settings.live_max_duration_seconds)
    processed_samples = 0
    segments = []
    inference_seconds = 0.0
    persistence = None
    completed = False
    worker_compute_type = None
    handshake_pending = True

    async def emit(event):
        nonlocal event_seq
        async with output_lock:
            event_seq += 1
            await asyncio.wait_for(ws.send_json({**event, 'event_seq': event_seq, 'job_id': job_id}), 5)

    async def periodic():
        while True:
            await asyncio.sleep(5)
            if not await asyncio.to_thread(store.renew, job_id, generation):
                raise LiveError('LIVE_LEASE_LOST', 1011)
            # Reload short-lived transaction; never hold a read view across WS awaits.
            with SessionLocal() as db:
                live = db.get(LiveSession, job_id)
                state = live.state if live else None
            if state not in ('streaming', 'finalizing'):
                raise LiveError('LIVE_SESSION_GONE', 4404)
            await asyncio.to_thread(transition, job_id, generation, [state], state, clock.samples)

    try:
        auth = control(await asyncio.wait_for(ws.receive_text(), 5))
        if auth.get('type') != 'authenticate' or type(auth.get('protocol')) is not int or auth.get('protocol') != 1:
            raise LiveError('LIVE_INVALID_TICKET', 4401)
        binding = await asyncio.to_thread(store.consume, auth.get('ticket'), job_id)
        generation = binding['generation']
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            owner = db.get(User, binding['user_id'])
            live = db.get(LiveSession, job_id) if available(db) else None
            if not job or not owner or not owner.is_active or job.user_id != binding['user_id'] or not live or live.generation != generation or live.state != 'created':
                raise LiveError('LIVE_SESSION_GONE', 4404)
            model_name, language = live.model, live.language
        if not await asyncio.to_thread(store.renew, job_id, generation, True):
            raise LiveError('LIVE_INVALID_TICKET', 4401)
        await asyncio.to_thread(transition, job_id, generation, ['created'], 'streaming')
        cache.set_job_status(job_id, 'main', 'processing')
        handshakes -= 1
        handshake_pending = False
        import websockets
        async with websockets.connect(settings.live_worker_url,
            additional_headers={'X-Live-Token': settings.live_internal_token},
            max_size=65536, max_queue=10, write_limit=16384, open_timeout=5,
            ping_interval=10, ping_timeout=10) as worker:
            await worker.send(__import__('json').dumps({'job_id': job_id, 'generation': generation}))

            async def client_input():
                while True:
                    try:
                        frame = await asyncio.wait_for(ws.receive(), 20)
                    except asyncio.TimeoutError:
                        raise LiveError('LIVE_AUDIO_TIMEOUT', 1011) from None
                    if frame['type'] == 'websocket.disconnect':
                        raise LiveError('LIVE_INTERRUPTED', 1011)
                    if frame.get('bytes') is not None:
                        clock.accept(frame['bytes'])
                        if clock.samples - processed_samples > settings.live_max_audio_backlog_seconds * RATE:
                            raise LiveError('LIVE_BACKPRESSURE', 4429)
                        await asyncio.wait_for(worker.send(frame['bytes']), 2)
                        if clock.samples >= (settings.live_max_duration_seconds - 10) * RATE:
                            await emit({'type': 'session.limit', 'remaining_seconds':
                                max(0, settings.live_max_duration_seconds - clock.samples / RATE)})
                    else:
                        message = control(frame.get('text'))
                        if message.get('type') == 'cancel':
                            raise LiveError('LIVE_CANCELLED', 4404)
                        clock.finish(message)
                        await asyncio.to_thread(transition, job_id, generation, ['streaming'], 'finalizing', clock.samples)
                        await asyncio.wait_for(worker.send(frame['text']), 2)
                        return

            async def worker_output():
                nonlocal processed_samples, inference_seconds, persistence, completed, worker_compute_type
                ready = False
                async for text in worker:
                    event = control(text, 65536)
                    kind = event.get('type')
                    if not await asyncio.to_thread(store.valid, job_id, generation):
                        raise LiveError('LIVE_LEASE_LOST', 1011)
                    if kind == 'session.ready':
                        ready = True
                        worker_compute_type = event.get('compute_type')
                        await emit(event)
                    elif kind == 'decoder.progress':
                        processed_samples = event['samples']
                        inference_seconds = event['inference_seconds']
                        await emit({'type': 'session.progress', 'duration_seconds': clock.samples / RATE,
                            'backlog_seconds': max(0, clock.samples - processed_samples) / RATE})
                    elif kind == 'transcript.final':
                        start, end = event.get('start'), event.get('end')
                        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                            or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start
                            or end > clock.samples / RATE + .01 or (segments and start < segments[-1]['end'])
                            or event.get('segment_id') != len(segments) or not isinstance(event.get('text'), str)):
                            raise LiveError('LIVE_DECODER_PROTOCOL', 1011)
                        segment = {key: event[key] for key in ('start', 'end', 'text')}
                        await asyncio.to_thread(store.append_confirmed, job_id, generation, [segment])
                        segments.append(segment)
                        await emit(event)
                    elif kind == 'transcript.partial':
                        await emit(event)
                    elif kind == 'session.error':
                        raise LiveError(event.get('code', 'LIVE_DECODER_FAILED'), 1011)
                    elif kind == 'decoder.completed':
                        if not ready or event.get('samples') != clock.samples:
                            raise LiveError('LIVE_DECODER_PROTOCOL', 1011)
                        text_result = ' '.join(s['text'] for s in segments)
                        result = {'text': text_result, 'segments': segments, 'language': language,
                            'duration': clock.samples / RATE, 'word_count': len(text_result.split()),
                            'char_count': len(text_result), 'model': model_name,
                            'provider': 'faster-whisper', 'device': 'cuda'}
                        persistence = asyncio.create_task(asyncio.to_thread(finish_live, job_id, generation, result,
                            store, cache, get_es_client(), event['inference_seconds'], worker_compute_type))
                        try:
                            await asyncio.shield(persistence)
                        except LiveError:
                            raise
                        except Exception:
                            raise LiveError('LIVE_STORAGE_FAILED', 1011) from None
                        completed = True
                        await emit({'type': 'session.completed', 'result_url': f'/jobs/{job_id}/result',
                                    'inference_seconds': event['inference_seconds']})
                        return
                    else:
                        raise LiveError('LIVE_DECODER_PROTOCOL', 1011)
                raise LiveError('LIVE_INTERRUPTED', 1011)

            input_task = asyncio.create_task(client_input())
            output_task = asyncio.create_task(worker_output())
            lease_task = asyncio.create_task(periodic())
            tasks = [input_task, output_task, lease_task]
            pending = set(tasks)
            while output_task in pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
    except Exception as exc:
        error = exc if isinstance(exc, LiveError) else LiveError('LIVE_INTERRUPTED', 1011)
        if generation is not None and not completed:
            with suppress(Exception):
                await asyncio.to_thread(terminate, job_id,
                    'cancelled' if error.code == 'LIVE_CANCELLED' else 'failed', error.code, store, cache, generation)
        with suppress(Exception):
            await emit({'type': 'session.error', 'code': error.code})
            await ws.close(error.close)
    finally:
        if handshake_pending:
            handshakes -= 1
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if persistence:
            with suppress(Exception, asyncio.CancelledError):
                await asyncio.shield(persistence)
        if generation is not None:
            with suppress(Exception):
                await asyncio.to_thread(store.release, job_id, generation)
        with suppress(Exception):
            await ws.close()
