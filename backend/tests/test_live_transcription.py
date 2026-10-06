"""Protocol, privacy, lease fencing and durable publication under failure/races."""
import json
import struct
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base, get_db
from shared.models import User, Job, JobStatus, LiveSession, Project
from shared.redis_client import RedisClient
from shared.live.store import LiveStore
from shared.live.protocol import AudioClock, LiveError
from shared.live import lifecycle, persistence
from workers.live.decoder import OnlineWhisper
from api import live_routes, routes
from shared.auth import get_current_active_user
from shared.transcripts import transcript_object_name


@pytest.fixture
def world(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([User(id='u', username='u', email='u@example.com', hashed_password='x'),
                    User(id='other', username='other', email='o@example.com', hashed_password='x')])
        db.add(Project(id='p', user_id='u', name='Aulas', name_key='aulas'))
        db.commit()
    redis = RedisClient(fakeredis.FakeRedis(decode_responses=True))
    store = LiveStore(redis.client)
    store.ready({'ready': True, 'capacity': 1, 'incarnation': 'test', 'backend': 'whisper', 'model': 'turbo'})
    for module in (live_routes, lifecycle, persistence):
        monkeypatch.setattr(module, 'SessionLocal', Session)
    monkeypatch.setattr(live_routes, 'get_store', lambda: store)
    monkeypatch.setattr(live_routes, 'get_redis_client', lambda: redis)
    monkeypatch.setattr(routes, 'get_redis_client', lambda: redis)
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', True)
    monkeypatch.setattr(live_routes.get_settings(), 'environment', 'development')
    monkeypatch.setattr(live_routes.get_settings(), 'live_internal_token', 'test-' + 'x' * 40)
    es = MagicMock()
    es.store_job_result.return_value = True
    es.get_job_result.return_value = None
    monkeypatch.setattr(routes, 'get_es_client', lambda: es)
    monkeypatch.setattr(live_routes, 'get_es_client', lambda: es)
    minio = SimpleNamespace(bucket_audio='audio', objects={})
    def upload(bucket_name, object_name, file_data, content_type):
        minio.objects[object_name] = file_data
        return object_name
    def delete(bucket, name):
        minio.objects.pop(name, None)
        return True
    minio.upload_file, minio.delete_file = upload, delete
    minio.download_file = lambda bucket_name, object_name: minio.objects.get(object_name)
    minio.delete_folder = lambda bucket, prefix: [minio.objects.pop(k) for k in list(minio.objects) if k.startswith(prefix)]
    monkeypatch.setattr(persistence, 'get_minio_client', lambda: minio)
    monkeypatch.setattr(routes, 'get_minio_client', lambda: minio)
    app = FastAPI()
    app.include_router(live_routes.router)
    app.include_router(routes.router)
    def dbdep():
        with Session() as db:
            yield db
    def auth():
        with Session() as db:
            return db.get(User, 'u')
    app.dependency_overrides[get_db] = dbdep
    app.dependency_overrides[get_current_active_user] = auth
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=Session, store=store, redis=redis, minio=minio, es=es, app=app)


def frame(seq, offset, count=3200):
    return struct.pack('<IQ', seq, offset) + b'\0\0' * count


def test_pcm_clock_counts_silence_tail_and_rejects_order_size_rate():
    clock = AudioClock(max_seconds=1)
    assert len(clock.accept(frame(0, 0), now=1)) == 6400
    with pytest.raises(LiveError, match='LIVE_INVALID_SEQUENCE'):
        clock.accept(frame(0, 3200), now=1.2)
    with pytest.raises(LiveError, match='LIVE_INVALID_FRAME'):
        clock.accept(frame(1, 3200, 8001), now=1.2)
    clock.accept(frame(1, 3200, 3), now=1.2)
    assert clock.samples == 3203
    clock.finish({'type': 'finish', 'last_seq': 1})
    with pytest.raises(LiveError, match='LIVE_INVALID_FINISH'):
        clock.finish({'type': 'finish', 'last_seq': True})
    burst = AudioClock()
    for n in range(10): burst.accept(frame(n, n * 3200), now=1)
    with pytest.raises(LiveError, match='LIVE_FRAME_RATE'):
        burst.accept(frame(10, 32000), now=1)


def test_atomic_capacity_single_use_ticket_and_orphan_expiry(world):
    lease, _ = world.store.reserve('one')
    ticket = world.store.ticket(lease, 'u')
    with pytest.raises(LiveError, match='LIVE_CAPACITY_FULL'):
        world.store.reserve('two')
    world.store.consume(ticket, 'one')
    with pytest.raises(LiveError, match='LIVE_INVALID_TICKET'):
        world.store.consume(ticket, 'one')
    world.redis.client.delete(lease['slot'], 'live:lease:one')
    replacement, _ = world.store.reserve('two')
    world.store.release('one', lease['generation'])
    assert world.store.valid('two', replacement['generation'])


def test_worker_restart_invalidates_generation(world):
    lease, _ = world.store.reserve('one')
    world.store.ready({'ready': True, 'capacity': 1, 'incarnation': 'restarted', 'backend': 'whisper', 'model': 'turbo'})
    assert not world.store.valid('one', lease['generation'])
    assert not world.store.renew('one', lease['generation'])


def test_admission_reuses_location_tags_and_exact_mysql_owner(world):
    assert world.client.post('/transcribe/live/sessions', json={}).status_code == 422
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p', 'tags': ['Live', 'live']})
    assert response.status_code == 201
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert 'ticket' not in data['ws_url']
    with world.db() as db:
        job = db.get(Job, data['job_id'])
        assert job.project_id == 'p' and job.tags == ['live'] and job.file_checksum is None
        assert db.get(LiveSession, job.id).state == 'created'
        job.user_id = 'other'; db.commit()
    assert world.client.get('/transcribe/live/sessions/' + data['job_id']).status_code == 404


def test_bad_project_does_not_consume_capacity(world):
    assert world.client.post('/transcribe/live/sessions', json={'project_id': 'foreign'}).status_code == 404
    assert world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).status_code == 201
    assert world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).status_code == 503


def create_finalizing(world):
    data = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).json()
    job_id = data['job_id']
    lease = world.store.consume(data['ticket'], job_id)
    gen = lease['generation']
    assert world.store.renew(job_id, gen, activate=True)
    lifecycle.transition(job_id, gen, ['created'], 'streaming')
    lifecycle.transition(job_id, gen, ['streaming'], 'finalizing', 16000)
    return job_id, gen


RESULT = {'text': 'Olá, turma.', 'segments': [{'start': .2, 'end': .8, 'text': 'Olá, turma.'}],
          'language': 'pt', 'duration': 1, 'word_count': 2, 'char_count': 11,
          'model': 'turbo', 'provider': 'faster-whisper', 'device': 'cuda'}


def finish(world, job_id, gen):
    return persistence.finish_live(job_id, gen, RESULT, world.store, world.redis, world.es, .1, 'float16')


def test_durable_formats_and_reads_after_cache_expiry(world):
    job_id, gen = create_finalizing(world)
    finish(world, job_id, gen)
    assert len(world.minio.objects) == 4
    assert world.client.get(f'/jobs/{job_id}/result?format=json').json()['segments'] == RESULT['segments']
    world.redis.client.delete(f'job:{job_id}:status', f'job:{job_id}:result')
    assert world.client.get(f'/jobs/{job_id}').json()['status'] == 'completed'
    for fmt in ['json', 'txt', 'vtt', 'srt']:
        assert world.client.get(f'/jobs/{job_id}/result?format={fmt}').status_code == 200
    world.es.get_job_result.return_value = {'markdown_content': '# Transcrição', 'metadata': {'format': 'pcm', 'size_bytes': 32000}}
    assert world.client.get(f'/jobs/{job_id}/result').status_code == 200


def test_storage_error_never_completes_or_leaves_generation_objects(world):
    job_id, gen = create_finalizing(world)
    original = world.minio.upload_file
    def fail(bucket_name, object_name, file_data, content_type):
        original(bucket_name, object_name, file_data, content_type)
        if object_name.endswith('.srt'): raise RuntimeError('write then lose ack')
        return object_name
    world.minio.upload_file = fail
    with pytest.raises(RuntimeError): finish(world, job_id, gen)
    assert not world.minio.objects
    with world.db() as db:
        assert db.get(LiveSession, job_id).state == 'finalizing'
        assert db.get(Job, job_id).status != JobStatus.COMPLETED


def test_cancel_during_upload_fences_publication_and_cleans_late_objects(world):
    job_id, gen = create_finalizing(world)
    original = world.minio.upload_file
    def cancel(bucket_name, object_name, file_data, content_type):
        original(bucket_name, object_name, file_data, content_type)
        lifecycle.terminate(job_id, 'cancelled', 'LIVE_CANCELLED', world.store, world.redis)
        return object_name
    world.minio.upload_file = cancel
    with pytest.raises(LiveError): finish(world, job_id, gen)
    assert not world.minio.objects
    assert world.client.get(f'/jobs/{job_id}/result?format=json').status_code == 400


def test_delete_cleanup_before_late_upload_cannot_resurrect_job(world):
    job_id, gen = create_finalizing(world)
    original = world.minio.upload_file
    def delete_then_write(bucket_name, object_name, file_data, content_type):
        assert world.client.delete(f'/jobs/{job_id}').status_code == 200
        original(bucket_name, object_name, file_data, content_type)
        return object_name
    world.minio.upload_file = delete_then_write
    with pytest.raises(LiveError): finish(world, job_id, gen)
    assert not world.minio.objects
    assert world.redis.get_job_result(job_id) is None
    with world.db() as db:
        assert db.get(Job, job_id) is None and db.get(LiveSession, job_id) is None


def test_sweeper_failure_keeps_confirmed_partial_and_releases_slot(world):
    job_id, gen = create_finalizing(world)
    world.store.append_confirmed(job_id, gen, RESULT['segments'])
    world.redis.client.delete(f'live:lease:{job_id}')
    lifecycle.sweep(world.store, world.redis)
    with world.db() as db:
        assert db.get(Job, job_id).status == JobStatus.FAILED
    assert world.redis.get_partial_transcript(job_id)[0] == RESULT['segments']


class Model:
    def __init__(self, hypotheses):
        self.hypotheses = iter(hypotheses)
    def transcribe(self, audio, **kwargs):
        words = [SimpleNamespace(start=a, end=b, word=t) for a, b, t in next(self.hypotheses)]
        return iter([SimpleNamespace(words=words, no_speech_prob=0, end=words[-1].end if words else len(audio)/16000)]), None


def test_online_agreement_revision_context_and_tail_without_file():
    model = Model([[(.1,.3,' Olá'),(.3,.8,' turma')],[(.1,.3,' Olá'),(.3,.8,' turma')],
                   [(0,.3,' Olá'),(.3,.8,' turma'),(.8,1.1,' hoje')]])
    decoder = OnlineWhisper(model)
    first = decoder.push(b'\0\0' * 16000)
    assert not any(e['type'] == 'transcript.final' for e in first)
    second = decoder.push(b'\0\0' * 16000)
    assert [e['text'] for e in second if e['type'] == 'transcript.final'] == ['Olá turma']
    tail = decoder.finish()
    assert [e['text'] for e in tail if e['type'] == 'transcript.final'] == ['hoje']
    assert decoder.result('turbo')['text'] == 'Olá turma hoje'


def test_live_schema_explicit_create_and_downgrade_guard(world):
    import importlib.util
    spec = importlib.util.spec_from_file_location('migration', __import__('pathlib').Path(__file__).resolve().parents[2] / 'scripts/migrate_0005_live.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    job_id, _ = create_finalizing(world)
    with world.db() as db:
        bind = db.get_bind()
        with pytest.raises(RuntimeError, match='Drain'): module.migrate(bind, True)
    lifecycle.terminate(job_id, 'cancelled', 'LIVE_CANCELLED', world.store, world.redis)
    module.migrate(bind, True)
    assert not inspect(bind).has_table('live_sessions')
    module.migrate(bind)
    assert inspect(bind).has_table('live_sessions')


def test_legitimate_repetition_is_not_deleted_by_overlap_dedup():
    model = Model([[(.1,.3,' sim,')],[(.1,.3,' sim,')],
                   [(.1,.3,' sim,'),(.3,.5,' sim,')],
                   [(.1,.3,' sim,'),(.3,.5,' sim,')]])
    decoder = OnlineWhisper(model)
    for _ in range(4):
        decoder.push(b'\0\0' * 16000)
    assert decoder.result('turbo')['text'] == 'sim, sim,'


def test_source_timestamps_include_silence_and_context_trimming():
    # Decoder times are relative to each bounded window; advancing offset must
    # preserve the original capture timeline, even with VAD and overlap.
    model = Model([[(3,3.3,' ola')],[(3,3.3,' ola')],[(3.3,4,' mundo')]])
    decoder = OnlineWhisper(model, max_context=3)
    decoder.push(b'\0\0' * (4 * 16000))
    decoder.push(b'\0\0' * 16000)
    events = decoder.finish()
    assert decoder.segments[0]['start'] == 3
    assert decoder.segments[0]['end'] == 3.3
    assert decoder.segments[-1]['end'] == 4
    assert all(a['end'] <= b['start'] for a,b in zip(decoder.segments, decoder.segments[1:]))


def test_real_jwt_api_key_precedence_and_bound_project(world):
    from shared.auth import create_access_token, hash_api_key
    from shared.models import APIKey
    world.app.dependency_overrides.pop(get_current_active_user)
    with world.db() as db:
        db.add(APIKey(id='test-key', user_id='u', key_hash=hash_api_key('test-live-key'),
                      project_id='p', is_active=True))
        db.commit()
    assert world.client.post('/transcribe/live/sessions', json={}).status_code == 401
    # JWT wins, so a key-bound project does not resolve the missing JWT location.
    jwt = create_access_token({'sub': 'u'})
    assert world.client.post('/transcribe/live/sessions', json={},
        headers={'Authorization': 'Bearer ' + jwt, 'X-API-Key': 'test-live-key'}).status_code == 422
    response = world.client.post('/transcribe/live/sessions', json={}, headers={'X-API-Key': 'test-live-key'})
    assert response.status_code == 201
    with world.db() as db:
        assert db.get(Job, response.json()['job_id']).project_id == 'p'


def test_disabled_and_existing_database_without_live_table(world, monkeypatch):
    with world.db() as db:
        LiveSession.__table__.drop(db.get_bind())
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', False)
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert response.status_code == 503 and response.json()['detail']['code'] == 'LIVE_DISABLED'
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', True)
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert response.status_code == 503 and response.json()['detail']['code'] == 'LIVE_NOT_READY'


class FakeWorkerSocket:
    """Controlled private hop: actual public WS/API/persistence, fake inference."""
    def __init__(self):
        import asyncio
        self.events = asyncio.Queue()
        self.clock = AudioClock()
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    def __aiter__(self):
        return self
    async def __anext__(self):
        return json.dumps(await self.events.get())
    async def send(self, payload):
        if isinstance(payload, bytes):
            self.clock.accept(payload)
            await self.events.put({'type': 'transcript.partial', 'utterance_id': 0, 'revision': self.clock.seq,
                                   'text': 'Olá' if self.clock.seq == 1 else 'Olá, turma.'})
            await self.events.put({'type': 'decoder.progress', 'samples': self.clock.samples, 'inference_seconds': .01})
        else:
            value = json.loads(payload)
            if 'generation' in value:
                await self.events.put({'type': 'session.ready', 'backend': 'whisper', 'model': 'turbo'})
            else:
                self.clock.finish(value)
                await self.events.put({'type': 'transcript.final', 'segment_id': 0, 'utterance_id': 0,
                    'start': 0, 'end': self.clock.samples / 16000, 'text': 'Olá, turma.'})
                await self.events.put({'type': 'decoder.completed', 'samples': self.clock.samples, 'inference_seconds': .03})


def test_public_ws_streams_revisions_before_eof_and_persists_finals(world, monkeypatch):
    import websockets
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: FakeWorkerSocket())
    from starlette.websockets import WebSocket
    original_send = WebSocket.send_json
    async def assert_terminal_cleanup(socket, event, *args, **kwargs):
        if event.get('type') == 'session.completed':
            # Assert ordering at publication, before the consumer or finally
            # can run; this deterministically exposes the original race.
            assert world.store.lease(event['job_id']) is None
        return await original_send(socket, event, *args, **kwargs)
    monkeypatch.setattr(WebSocket, 'send_json', assert_terminal_cleanup)
    data = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).json()
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type': 'authenticate', 'protocol': 1, 'ticket': data['ticket']})
        ready = ws.receive_json()
        assert ready['type'] == 'session.ready' and ready['event_seq'] == 1
        ws.send_bytes(frame(0, 0))
        assert ws.receive_json()['text'] == 'Olá'
        assert ws.receive_json()['type'] == 'session.progress'
        ws.send_bytes(frame(1, 3200))
        assert ws.receive_json()['text'] == 'Olá, turma.'
        assert ws.receive_json()['type'] == 'session.progress'
        ws.send_json({'type': 'finish', 'last_seq': 1})
        final, completed = ws.receive_json(), ws.receive_json()
        assert final['type'] == 'transcript.final' and completed['type'] == 'session.completed'
        assert completed['event_seq'] == 7
    assert world.client.get(f"/jobs/{data['job_id']}/result?format=json").json()['text'] == 'Olá, turma.'
    assert world.store.lease(data['job_id']) is None


def test_public_ws_consumed_ticket_and_wrong_job_are_denied(world, monkeypatch):
    import websockets
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: FakeWorkerSocket())
    data = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).json()
    # Wrong path consumes the bearer ticket but cannot authorize a different job.
    with world.client.websocket_connect('/transcribe/live/sessions/foreign/stream') as ws:
        ws.send_json({'type': 'authenticate', 'protocol': 1, 'ticket': data['ticket']})
        assert ws.receive_json()['code'] == 'LIVE_INVALID_TICKET'
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type': 'authenticate', 'protocol': 1, 'ticket': data['ticket']})
        assert ws.receive_json()['code'] == 'LIVE_INVALID_TICKET'


def test_public_ws_out_of_order_fails_and_frees_capacity(world, monkeypatch):
    import websockets
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: FakeWorkerSocket())
    data = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).json()
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type': 'authenticate', 'protocol': 1, 'ticket': data['ticket']})
        ws.receive_json()
        ws.send_bytes(frame(1, 0))
        assert ws.receive_json()['code'] == 'LIVE_INVALID_SEQUENCE'
    with world.db() as db:
        assert db.get(Job, data['job_id']).status == JobStatus.FAILED
    assert world.store.lease(data['job_id']) is None
    assert world.client.post('/transcribe/live/sessions', json={'project_id': 'p'}).status_code == 201


def test_cancel_cache_mutations_happen_before_sql_commit(world, monkeypatch):
    job_id, gen = create_finalizing(world)
    operations = []
    original_status = world.redis.set_job_status
    original_delete = world.redis.delete_partial_transcript
    from sqlalchemy import event
    event.listen(world.db.class_, 'before_commit', lambda db: operations.append('commit'))
    def status(*a, **k):
        operations.append('cache-status')
        return original_status(*a, **k)
    def partial(*a, **k):
        operations.append('cache-partial-delete')
        return original_delete(*a, **k)
    monkeypatch.setattr(world.redis, 'set_job_status', status)
    monkeypatch.setattr(world.redis, 'delete_partial_transcript', partial)
    lifecycle.terminate(job_id, 'cancelled', 'LIVE_CANCELLED', world.store, world.redis)
    assert operations == ['cache-status', 'cache-partial-delete', 'commit']


def test_live_resident_budget_reuses_bindings_and_requires_matching_uuid(world):
    from shared.live.capacity import require_production_budget
    from shared.models import Engine
    settings = SimpleNamespace(live_gpu_ref='gpu0', live_vram_footprint_gb=3,
                               live_vram_reserve_gb=3.2, vision_model_id='florence-community/Florence-2-base-ft')
    config = {'gpus': [{'ref': 'gpu0', 'uuid': 'GPU-test', 'vram_gb': 16, 'vram_reserve_gb': 2}],
              'features': {'transcription': {'gpu_ref': 'gpu0', 'workers': 2, 'executions_per_worker': 1}}}
    with world.db() as db:
        db.add(Engine(id='engine', slug='local', display_name='Local', adapter_type='local', config=config))
        db.commit()
        use = require_production_budget(db, settings, {'uuid': 'GPU-test'})
        assert use.used_gb == 9 and use.reserve_gb == 3.2 and use.fits
        with pytest.raises(RuntimeError, match='UUID'):
            require_production_budget(db, settings, {'uuid': 'wrong'})
        settings.live_vram_footprint_gb = 8
        with pytest.raises(RuntimeError, match='does not fit'):
            require_production_budget(db, settings, {'uuid': 'GPU-test'})


def test_admin_inventory_includes_live_without_fake_celery_binding(world, monkeypatch):
    import asyncio
    from api import engine_admin_routes
    from shared.models import Engine
    world.store.ready({'ready': True, 'capacity': 1, 'incarnation': 'test', 'backend': 'whisper', 'model': 'turbo',
        'resident_vram_gb': 3, 'gpu': {'uuid': 'GPU-test', 'total_gb': 16, 'used_gb': 6}})
    monkeypatch.setattr(engine_admin_routes, 'get_redis_client', lambda: world.redis)
    monkeypatch.setattr(engine_admin_routes, '_alive_by_feature', lambda: {})
    with world.db() as db:
        db.add(Engine(id='engine', slug='local', display_name='Local', adapter_type='local', config={
            'gpus': [{'ref': 'gpu0', 'uuid': 'GPU-test', 'vram_gb': 16, 'vram_reserve_gb': 2}], 'features': {}}))
        db.commit()
        response = asyncio.run(engine_admin_routes.list_gpus(admin_user=None, db=db))
    assert response['declared'][0]['live_reserved_gb'] == 3
    assert response['declared'][0]['budgeted_gb'] == 6.2
    assert response['declared'][0]['bindings'] == []
    assert response['live_worker']['ready']


def test_worker_cuda_tail_blocks_capacity_after_lease_release(world):
    world.store.ready({'ready': True, 'capacity': 1, 'incarnation': 'test', 'backend': 'whisper', 'model': 'turbo',
                       'active_jobs': ['still-inside-cuda']})
    with pytest.raises(LiveError, match='LIVE_CAPACITY_FULL'):
        world.store.reserve('new-job')


def test_shared_resident_model_has_private_context_per_session():
    class ContentModel:
        def transcribe(self, audio, **kwargs):
            text = ' um' if float(np.mean(audio)) < .05 else ' dois'
            word = SimpleNamespace(start=.1, end=.3, word=text)
            return iter([SimpleNamespace(words=[word], no_speech_prob=0, end=.3)]), None
    model = ContentModel()
    one, two = OnlineWhisper(model), OnlineWhisper(model)
    for _ in range(2):
        one.push((np.ones(16000, dtype='<i2') * 1000).tobytes())
        two.push((np.ones(16000, dtype='<i2') * 10000).tobytes())
    assert one.result('turbo')['text'] == 'um'
    assert two.result('turbo')['text'] == 'dois'
    assert one.confirmed_words is not two.confirmed_words


def test_redis_outage_cannot_prevent_sql_termination_or_publish_later(world, monkeypatch):
    job_id, gen = create_finalizing(world)
    def unavailable(*args, **kwargs):
        raise ConnectionError('test store unavailable')
    monkeypatch.setattr(world.store, 'valid', unavailable)
    monkeypatch.setattr(world.store, 'release', unavailable)
    lifecycle.sweep(world.store, world.redis)
    with world.db() as db:
        assert db.get(Job, job_id).status == JobStatus.FAILED
        assert db.get(LiveSession, job_id).state == 'failed'
    with pytest.raises(LiveError, match='LIVE_SESSION_GONE'):
        finish(world, job_id, gen)
    # Even a stale PROCESSING cache must not override the terminal SQL state.
    world.redis.set_job_status(job_id, 'main', 'processing')
    assert world.client.get(f'/jobs/{job_id}').json()['status'] == 'failed'


@pytest.mark.parametrize('state', ['finalizing', 'failed', 'cancelled', 'deleted'])
def test_search_never_publishes_uncommitted_cancelled_or_deleted_live(world, state):
    job_id, gen = create_finalizing(world)
    world.es.search_jobs.return_value = [{'job_id': job_id, 'markdown_content': 'private live text',
        'metadata': {'input_mode': 'live', 'generation': gen}},
        {'job_id': 'batch-job-without-cache', 'markdown_content': 'existing batch text'}]
    if state in ('failed', 'cancelled'):
        lifecycle.terminate(job_id, state, 'TEST_INTERRUPTED', world.store, world.redis)
    elif state == 'deleted':
        assert world.client.delete(f'/jobs/{job_id}').status_code == 200
    result = world.client.get('/search', params={'query': 'text'}).json()
    assert [hit['job_id'] for hit in result['results']] == ['batch-job-without-cache']


def test_search_publishes_only_completed_owned_matching_generation(world):
    job_id, gen = create_finalizing(world)
    finish(world, job_id, gen)
    world.es.search_jobs.return_value = [
        {'job_id': job_id, 'markdown_content': 'valid generation', 'metadata': {'input_mode': 'live', 'generation': gen}},
        {'job_id': job_id, 'markdown_content': 'stale generation', 'metadata': {'input_mode': 'live', 'generation': gen + 1}},
        {'job_id': job_id, 'markdown_content': 'unversioned live', 'metadata': {'input_mode': 'live'}},
    ]
    response = world.client.get('/search', params={'query': 'generation'}).json()
    assert response['total'] == 1 and response['results'][0]['preview'] == 'valid generation...'
    with world.db() as db:
        db.get(Job, job_id).user_id = 'other'; db.commit()
    assert world.client.get('/search', params={'query': 'generation'}).json()['total'] == 0


@pytest.mark.parametrize('stale_read', [False, True])
def test_heartbeat_waits_for_committed_finalization_thread(world, monkeypatch, stale_read):
    import asyncio
    import threading
    import websockets
    committed, observed = threading.Event(), threading.Event()
    stale_remaining = [stale_read]
    original_finish = live_routes.finish_live
    original_sleep = asyncio.sleep
    original_transition = live_routes.transition
    original_session = live_routes.SessionLocal
    def finish(*args, **kwargs):
        result = original_finish(*args, **kwargs)
        committed.set()
        assert observed.wait(5), 'heartbeat must observe the SQL/thread gap'
        return result
    async def heartbeat_tick(delay, *args, **kwargs):
        if delay == 5:
            assert await asyncio.to_thread(committed.wait, 5)
            return
        return await original_sleep(delay, *args, **kwargs)
    class HeartbeatSession:
        def __enter__(self):
            self.db = original_session()
            return self
        def __exit__(self, *args):
            self.db.close()
        def __getattr__(self, name):
            return getattr(self.db, name)
        def get(self, model, key):
            value = self.db.get(model, key)
            if model is LiveSession and committed.is_set() and value.state == 'completed':
                if stale_remaining[0]:
                    stale_remaining[0] = False
                    return SimpleNamespace(state='finalizing', generation=value.generation)
                observed.set()
            return value
    def transition(*args, **kwargs):
        if committed.is_set() and args[2:4] == (['finalizing'], 'finalizing'):
            observed.set()
            raise LiveError('LIVE_SESSION_GONE', 4404)
        return original_transition(*args, **kwargs)
    monkeypatch.setattr(live_routes, 'finish_live', finish)
    monkeypatch.setattr(live_routes, 'SessionLocal', HeartbeatSession)
    monkeypatch.setattr(live_routes, 'transition', transition)
    monkeypatch.setattr(asyncio, 'sleep', heartbeat_tick)
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: FakeWorkerSocket())
    data = world.client.post('/transcribe/live/sessions', json={'project_id':'p'}).json()
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type':'authenticate', 'protocol':1, 'ticket':data['ticket']})
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_bytes(frame(0, 0))
        ws.receive_json()
        ws.receive_json()
        ws.send_json({'type':'finish', 'last_seq':0})
        assert ws.receive_json()['type'] == 'transcript.final'
        assert ws.receive_json()['type'] == 'session.completed'
        assert world.store.lease(data['job_id']) is None
    assert observed.is_set()


def test_heartbeat_keeps_renewing_after_active_state_race(world, monkeypatch):
    import asyncio
    import threading
    import websockets
    uploading, renewed_again = threading.Event(), threading.Event()
    original_finish, original_transition = live_routes.finish_live, live_routes.transition
    original_sleep, original_renew = asyncio.sleep, world.store.renew
    renewals = []
    raced = []
    def finish(*args, **kwargs):
        uploading.set()
        assert renewed_again.wait(5), 'active finalization must retain heartbeat renewal'
        return original_finish(*args, **kwargs)
    async def tick(delay, *args, **kwargs):
        if delay == 5:
            assert await asyncio.to_thread(uploading.wait, 5)
            return
        return await original_sleep(delay, *args, **kwargs)
    def renew(*args, **kwargs):
        result = original_renew(*args, **kwargs)
        if len(args) == 2 and uploading.is_set():
            renewals.append(result)
            if len(renewals) == 2:
                renewed_again.set()
        return result
    def transition(*args, **kwargs):
        if uploading.is_set() and args[3] in ('streaming', 'finalizing') and not raced:
            raced.append(True)
            raise LiveError('LIVE_SESSION_GONE', 4404)
        return original_transition(*args, **kwargs)
    monkeypatch.setattr(live_routes, 'finish_live', finish)
    monkeypatch.setattr(live_routes, 'transition', transition)
    monkeypatch.setattr(asyncio, 'sleep', tick)
    monkeypatch.setattr(world.store, 'renew', renew)
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: FakeWorkerSocket())
    data = world.client.post('/transcribe/live/sessions', json={'project_id':'p'}).json()
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type':'authenticate', 'protocol':1, 'ticket':data['ticket']})
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_bytes(frame(0, 0))
        ws.receive_json()
        ws.receive_json()
        ws.send_json({'type':'finish', 'last_seq':0})
        assert ws.receive_json()['type'] == 'transcript.final'
        assert ws.receive_json()['type'] == 'session.completed'
    assert raced and renewed_again.is_set() and renewals[:2] == [True, True]
