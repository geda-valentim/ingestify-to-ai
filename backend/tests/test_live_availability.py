"""GET /transcribe/live/sessions/availability: the page asks before opening the microphone."""
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
    assert 'não está disponível' in body['message']


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
    assert response.json()['detail'] == {'code': 'LIVE_DISABLED', 'message': live_routes.UNAVAILABLE_MESSAGES['LIVE_DISABLED']}
