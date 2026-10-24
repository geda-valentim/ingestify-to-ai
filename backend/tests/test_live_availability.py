"""GET /transcribe/live/sessions/availability: the page asks before opening the microphone."""
import pytest
from api import live_routes
from tests.test_live_transcription import world  # noqa: F401

PATH = '/transcribe/live/sessions/availability'


def get(world):
    response = world.client.get(PATH)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def test_ready_worker_with_a_free_slot_is_available(world):
    body = get(world)
    assert body['available'] is True and body['code'] is None and body['message'] is None
    assert body['diarization']['available'] is False
    assert body['diarization']['code'] == 'LIVE_DIARIZATION_NOT_READY'


def test_asking_reserves_nothing(world):
    get(world)
    get(world)
    lease, _ = world.store.reserve('one')  # the only slot is still free
    assert lease['job_id'] == 'one'


def test_full_capacity_is_reported_before_the_post(world):
    world.store.reserve('one')
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_CAPACITY_FULL')
    assert body['message']
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert (response.status_code, response.json()['detail']['code']) == (503, 'LIVE_CAPACITY_FULL')


def test_worker_down_is_not_ready(world):
    world.redis.client.delete(world.store.worker_key)
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_NOT_READY')
    assert body['message'] == 'The live transcription service is not available right now. Try again in a moment.'


def test_worker_warming_up_is_not_ready(world):
    world.store.ready({'ready': False, 'capacity': 1, 'incarnation': 'warming'})
    assert get(world)['code'] == 'LIVE_NOT_READY'


def test_disabled_server_says_so(world, monkeypatch):
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', False)
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_DISABLED')
    assert body['diarization']['code'] == 'LIVE_DISABLED'


def test_redis_down_is_not_ready(world, monkeypatch):
    def boom(protocol=1):
        raise ConnectionError('redis down')

    monkeypatch.setattr(world.store, 'availability', boom)
    assert get(world)['code'] == 'LIVE_NOT_READY'


def test_qualified_diarization_with_capability_is_available(world, monkeypatch):
    settings = live_routes.get_settings()
    monkeypatch.setattr(settings, 'live_diarization_enabled', True)
    monkeypatch.setattr(settings, 'live_diarization_qualified', True)
    world.store.ready({'ready': True, 'capacity': 1, 'incarnation': 'v2', 'backend': 'whisper', 'model': 'turbo',
                       'capabilities': ['online_diarization'], 'diarization_capacity': 1})
    assert get(world)['diarization'] == {'available': True, 'code': None, 'message': None}


def test_the_post_503_carries_a_message(world, monkeypatch):
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', False)
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert response.status_code == 503
    assert response.json()['detail'] == {'code': 'LIVE_DISABLED', 'message': 'Live transcription is turned off on this server.'}


def test_messages_follow_accept_language(world, monkeypatch):
    from shared.i18n import LanguageMiddleware

    from fastapi.testclient import TestClient

    client = TestClient(LanguageMiddleware(world.client.app), headers=dict(world.client.headers))
    world.store.reserve('one')
    headers = {'Accept-Language': 'pt-BR'}
    body = client.get(PATH, headers=headers).json()
    assert (body['code'], body['message']) == ('LIVE_CAPACITY_FULL', 'Todas as vagas de transcrição ao vivo estão em uso. Tente de novo em instantes.')
    assert client.get(PATH).json()['message'] == 'All live transcription slots are in use. Try again in a moment.'
    monkeypatch.setattr(live_routes.get_settings(), 'live_transcription_enabled', False)
    response = client.post('/transcribe/live/sessions', json={'project_id': 'p'}, headers=headers)
    assert response.json()['detail'] == {'code': 'LIVE_DISABLED', 'message': 'A transcrição ao vivo está desligada neste servidor.'}
    assert response.headers['retry-after'] == '5'


def ready_diarization(world, monkeypatch, **worker):
    settings = live_routes.get_settings()
    monkeypatch.setattr(settings, 'live_diarization_enabled', True)
    monkeypatch.setattr(settings, 'live_diarization_qualified', True)
    world.store.ready({'ready': True, 'capacity': 2, 'incarnation': 'v2', 'backend': 'whisper', 'model': 'turbo',
                       'capabilities': ['online_diarization'], 'diarization_capacity': 1, **worker})


def test_expired_lease_of_an_active_job_is_capacity_full(world):
    world.store.ready({'ready': True, 'capacity': 1, 'incarnation': 'test', 'backend': 'whisper', 'model': 'turbo',
                       'active_jobs': ['still-inside-cuda']})
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_CAPACITY_FULL')
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert (response.status_code, response.json()['detail']['code']) == (503, 'LIVE_CAPACITY_FULL')


def test_exhausted_diarization_capacity_leaves_protocol_one_available(world, monkeypatch):
    ready_diarization(world, monkeypatch)
    world.store.reserve('speakers', protocol=2)
    body = get(world)
    assert (body['available'], body['code']) == (True, None)
    assert (body['diarization']['available'], body['diarization']['code']) == (False, 'LIVE_DIARIZATION_NOT_READY')


def test_database_failure_is_not_ready_not_500(world, monkeypatch):
    def boom(db):
        raise RuntimeError('database down')

    monkeypatch.setattr(live_routes, 'available', boom)
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_NOT_READY')


def test_common_inputs_are_read_once_per_request(world, monkeypatch):
    calls = []
    monkeypatch.setattr(live_routes, 'available', lambda db: calls.append(1) or True)
    get(world)
    assert len(calls) == 1


def engine_control(world, monkeypatch, *, gate_closed=False, modes=None, engine=True):
    from shared.engine_control.models import ControlResource
    from shared.models import Engine
    monkeypatch.setattr(live_routes.get_settings(), 'engine_control_enabled', True)
    with world.db() as db:
        if engine:
            db.add(Engine(id='local', slug='local', display_name='Local', adapter_type='local', config={'features': {}},
                          deployments={}, limit_usd=10, min_remaining_usd=0, version=0))
            db.add(ControlResource(key='live-gpu', owner_engine_id='local', gate_closed=gate_closed,
                                   applied={'feature_modes': modes or {}}))
        db.commit()


def test_engine_control_off_does_not_consult_admission(world, monkeypatch):
    monkeypatch.setattr(live_routes.get_settings(), 'engine_control_enabled', False)
    assert get(world)['available'] is True


def test_engine_control_open_gate_is_available(world, monkeypatch):
    engine_control(world, monkeypatch)
    assert get(world)['available'] is True


@pytest.mark.parametrize('kwargs', [
    {'gate_closed': True},
    {'modes': {'live-transcription': 'standby'}},
    {'modes': {'live-transcription': 'stopped'}},
    {'engine': False},
])
def test_engine_control_refusal_matches_the_post(world, monkeypatch, kwargs):
    engine_control(world, monkeypatch, **kwargs)
    body = get(world)
    assert (body['available'], body['code']) == (False, 'LIVE_NOT_READY')
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p'})
    assert (response.status_code, response.json()['detail']['code']) == (503, 'LIVE_NOT_READY')


def test_availability_takes_no_row_locks(world, monkeypatch):
    from shared.engine_control import admission
    locks = []
    real = admission.resource_rows
    monkeypatch.setattr(admission, 'resource_rows',
                        lambda db, engine, feature, lock=True: locks.append(lock) or real(db, engine, feature, lock))
    engine_control(world, monkeypatch)
    get(world)
    assert locks == [False]
