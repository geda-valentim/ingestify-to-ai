"""Private resident model service. One bounded audio/output channel per session."""
import asyncio
import hmac
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from shared.config import get_settings
from shared.redis_client import get_redis_client
from shared.live.protocol import AudioClock, LiveError, control, RATE
from shared.live.store import LiveStore
from workers.live.decoder import OnlineWhisper

app = FastAPI(docs_url=None, redoc_url=None)
settings = get_settings()
model = None
compute_type = None
cold_start_seconds = None
active = set()
incarnation = secrets.token_hex(16)
executor = ThreadPoolExecutor(max_workers=settings.live_max_sessions, thread_name_prefix='live-inference')
heartbeat_task = None


def get_store():
    return LiveStore(get_redis_client().client, settings.live_worker_id)


def load_resident():
    global model, compute_type
    if len(settings.live_internal_token) < 32:
        raise RuntimeError('LIVE_INTERNAL_TOKEN must contain at least 32 characters')
    from shared.device import resolve_whisper_device, resolve_whisper_compute_type
    from workers.engines.whisper_core import load_model
    from workers.engines.benchmark import gpu_memory
    from shared.engines.capacity import VramUse
    device = resolve_whisper_device()
    if not device.startswith('cuda'):
        raise RuntimeError('Live transcription requires CUDA; CPU fallback is disabled')
    memory = gpu_memory()
    if not memory:
        raise RuntimeError('GPU memory measurement is required for live admission')
    # Guard current usage + declared resident footprint + reserve before loading.
    total = memory['total_gb']
    used = memory['used_gb']
    budget = VramUse('live shared GPU', total, settings.live_vram_reserve_gb,
                     ['current resident workloads', 'live resident model'],
                     used + settings.live_vram_footprint_gb)
    if not budget.fits:
        raise RuntimeError('Live resident model does not fit the GPU VRAM budget')
    if settings.environment == 'production':
        from shared.database import SessionLocal
        from shared.live.capacity import require_production_budget
        with SessionLocal() as db:
            require_production_budget(db, settings, memory)
    compute_type = resolve_whisper_compute_type(device)
    model = load_model(settings.whisper_model, device, compute_type)
    import numpy as np
    segments, _ = model.transcribe(np.zeros(RATE, dtype=np.float32), language='pt', beam_size=1)
    list(segments)  # Warm lazy decoder before readiness.


async def heartbeat():
    from workers.engines.benchmark import gpu_memory
    while True:
        gpu = await asyncio.to_thread(gpu_memory)
        await asyncio.to_thread(get_store().ready, {
            'ready': model is not None, 'capacity': settings.live_max_sessions,
            'incarnation': incarnation, 'backend': 'whisper', 'model': settings.whisper_model,
            'device': 'cuda', 'resident_vram_gb': settings.live_vram_footprint_gb,
            'gpu_ref': settings.live_gpu_ref, 'gpu': gpu,
            'compute_type': compute_type, 'cold_start_seconds': cold_start_seconds,
            'active_jobs': sorted(active),
        })
        await asyncio.sleep(2)


@app.on_event('startup')
async def startup():
    global heartbeat_task, cold_start_seconds
    started = time.monotonic()
    await asyncio.get_running_loop().run_in_executor(executor, load_resident)
    cold_start_seconds = time.monotonic() - started
    heartbeat_task = asyncio.create_task(heartbeat())


@app.on_event('shutdown')
async def shutdown():
    if heartbeat_task:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
    get_store().redis.delete(get_store().worker_key)
    executor.shutdown(wait=False, cancel_futures=True)


@app.get('/health')
def health():
    return {'ready': model is not None, 'active': len(active), 'capacity': settings.live_max_sessions,
            'runtime_revision':os.environ.get('INGESTIFY_RUNTIME_REVISION'),
            'model_profile_id':os.environ.get('INGESTIFY_MODEL_PROFILE'),'model':settings.whisper_model}


@app.websocket('/internal/stream')
async def stream(ws: WebSocket):
    if len(settings.live_internal_token) < 32 or not hmac.compare_digest(
        ws.headers.get('x-live-token', ''), settings.live_internal_token):
        await ws.close(4401)
        return
    await ws.accept()
    tasks = []
    job_id = None
    output = asyncio.Queue(maxsize=32)
    audio = asyncio.Queue(maxsize=10)
    queued_samples = 0
    clock = AudioClock(settings.live_max_duration_seconds)
    store = get_store()
    generation = None
    acquired = False
    inference_future = None

    async def emit(event):
        try:
            output.put_nowait(event)
        except asyncio.QueueFull:
            raise LiveError('LIVE_BACKPRESSURE', 4429)

    async def send():
        while True:
            event = await output.get()
            await asyncio.wait_for(ws.send_json(event), timeout=5)
            if event['type'] == 'decoder.completed':
                return

    async def receive():
        nonlocal queued_samples
        while True:
            frame = await asyncio.wait_for(ws.receive(), timeout=20)
            if frame['type'] == 'websocket.disconnect':
                raise LiveError('LIVE_INTERRUPTED', 1011)
            if frame.get('bytes') is not None:
                pcm = clock.accept(frame['bytes'])
                queued_samples += len(pcm) // 2
                if queued_samples > settings.live_max_audio_backlog_seconds * RATE:
                    raise LiveError('LIVE_BACKPRESSURE', 4429)
                try:
                    audio.put_nowait(pcm)
                except asyncio.QueueFull:
                    raise LiveError('LIVE_BACKPRESSURE', 4429)
            else:
                message = control(frame.get('text'))
                if message.get('type') == 'cancel':
                    raise LiveError('LIVE_CANCELLED', 4404)
                clock.finish(message)
                await audio.put(None)
                return

    async def decode():
        nonlocal queued_samples, inference_future
        decoder = OnlineWhisper(model)
        loop = asyncio.get_running_loop()
        while True:
            pcm = await audio.get()
            if not await asyncio.to_thread(store.valid, job_id, generation):
                raise LiveError('LIVE_LEASE_LOST', 1011)
            operation = decoder.finish if pcm is None else lambda: decoder.push(pcm)
            # Do not release the process-local slot until a cancelled CUDA call
            # actually returns; a Python cancellation cannot stop CTranslate2.
            inference_future = loop.run_in_executor(executor, operation)
            events = await asyncio.shield(inference_future)
            inference_future = None
            if pcm is not None:
                queued_samples -= len(pcm) // 2
            if not await asyncio.to_thread(store.valid, job_id, generation):
                raise LiveError('LIVE_LEASE_LOST', 1011)
            for event in events:
                await emit(event)
            await emit({'type': 'decoder.progress', 'samples': decoder.received,
                        'inference_seconds': decoder.inference_seconds})
            if pcm is None:
                # Avoid unbounded giant JSON results on the socket; API already
                # owns the final segments and constructs the normalized result.
                await emit({'type': 'decoder.completed', 'samples': decoder.received,
                            'inference_seconds': decoder.inference_seconds})
                return

    try:
        hello = control(await asyncio.wait_for(ws.receive_text(), 5))
        job_id, generation = hello.get('job_id'), hello.get('generation')
        if not isinstance(job_id, str) or type(generation) is not int or not store.valid(job_id, generation, 'streaming'):
            raise LiveError('LIVE_INVALID_RESERVATION', 4401)
        lease = store.lease(job_id)
        if lease['incarnation'] != incarnation or len(active) >= settings.live_max_sessions or job_id in active:
            raise LiveError('LIVE_CAPACITY_FULL', 1013)
        active.add(job_id)
        acquired = True
        await emit({'type': 'session.ready', 'backend': 'whisper', 'model': settings.whisper_model,
                    'compute_type': compute_type, 'policy': 'local-agreement-2',
                    'cold_start_seconds': cold_start_seconds})
        tasks = [asyncio.create_task(receive()), asyncio.create_task(decode()), asyncio.create_task(send())]
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()

    except Exception as exc:
        error = exc if isinstance(exc, LiveError) else LiveError('LIVE_DECODER_FAILED', 1011)
        with suppress(Exception):
            await asyncio.wait_for(ws.send_json({'type': 'session.error', 'code': error.code}), 1)
            await ws.close(error.close)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if inference_future is not None:
            with suppress(Exception, asyncio.CancelledError):
                await asyncio.shield(inference_future)
        if acquired:
            active.discard(job_id)
        with suppress(Exception):
            await ws.close()
