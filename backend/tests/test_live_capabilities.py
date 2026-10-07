"""Session controls: validation, model forwarding, durability and rolling upgrades."""
import json
from types import SimpleNamespace

import pytest
from shared.models import Job, JobConfiguration
from shared.job_configuration import job_configuration
from shared.live.capabilities import LiveOptions, MANAGED
from tests.test_live_transcription import world, FakeWorkerSocket, frame  # noqa: F401
from workers.live.decoder import OnlineWhisper, Word


def upgraded(world, languages=None):
    worker = world.store.readiness()
    worker.update(options_protocol=1, languages=languages or ['pt', 'en', 'es'])
    world.store.ready(worker)


def test_live_catalog_does_not_advertise_old_workers_as_options_ready(world):
    catalog = world.client.get('/transcribe/live/sessions/capabilities').json()
    assert catalog['ready'] and not catalog['options_supported'] and catalog['languages'] == ['pt']
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p', 'options': {'decoding': {'beam_size': 3}}})
    assert response.status_code == 503 and response.json()['detail']['code'] == 'LIVE_OPTIONS_UPGRADE_REQUIRED'
    with world.db() as db:
        assert db.query(Job).count() == 0
    assert world.store.reserve('still-free')[0]


@pytest.mark.parametrize('payload', [
    {'language': 'zz'}, {'language': None},
    {'options': {'decoding': {'task': 'translate'}}},
    {'options': {'decoding': {'word_timestamps': False}}},
    {'options': {'decoding': {'without_timestamps': True}}},
    {'options': {'decoding': {'condition_on_previous_text': True}}},
    {'options': {'decoding': {'clip_timestamps': [1, 2]}}},
    {'options': {'decoding': {'beam_size': 0}}},
    {'options': {'decoding': {'initial_prompt': [1, 2]}}},
    {'options': {'decoding': {'suppress_tokens': [-2]}}},
    {'options': {'decoding': {'hotwords': 'x' * 1025}}},
    {'options': {'interval_seconds': 6}},
    {'options': {'interval_seconds': 5, 'max_context_seconds': 4}},
])
def test_invalid_options_leave_no_job_or_lease(world, payload):
    upgraded(world)
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p', **payload})
    assert response.status_code == 422, response.text
    with world.db() as db:
        assert db.query(Job).count() == 0 and db.query(JobConfiguration).count() == 0
    assert world.store.reserve('still-free')[0]


def test_options_and_language_survive_websocket_handoff_and_cache_expiry(world, monkeypatch):
    import websockets
    upgraded(world)
    class CapturingWorker(FakeWorkerSocket):
        hello = None
        async def send(self, payload):
            if isinstance(payload, str) and 'generation' in json.loads(payload):
                self.hello = json.loads(payload)
            return await super().send(payload)
    worker = CapturingWorker()
    monkeypatch.setattr(websockets, 'connect', lambda *a, **k: worker)
    options = {'decoding': {'beam_size': 3, 'initial_prompt': 'Ingestify vocabulary', 'hotwords': 'lakehouse',
                            'vad_parameters': {'threshold': .7}}, 'interval_seconds': 1, 'max_context_seconds': 12}
    response = world.client.post('/transcribe/live/sessions', json={'project_id': 'p', 'language': 'es', 'options': options})
    assert response.status_code == 201, response.text
    data = response.json()
    with world.db() as db:
        saved = job_configuration(db.get(Job, data['job_id']))
        assert saved['operation'] == 'live_transcribe'
        assert saved['options']['language'] == 'es'
        assert saved['options']['options']['decoding']['beam_size'] == 3
    with world.client.websocket_connect(f"/transcribe/live/sessions/{data['job_id']}/stream") as ws:
        ws.send_json({'type': 'authenticate', 'protocol': 1, 'ticket': data['ticket']})
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_bytes(frame(0, 0))
        ws.receive_json(); ws.receive_json()
        ws.send_json({'type': 'finish', 'last_seq': 0})
        assert ws.receive_json()['type'] == 'transcript.final'
        assert ws.receive_json()['type'] == 'session.completed'
    assert worker.hello['options'] == saved['options']['options']
    assert worker.hello['language'] == 'es'
    world.redis.client.flushall()
    assert world.client.get(f"/jobs/{data['job_id']}").json()['configuration'] == saved
    assert world.client.get(f"/transcribe/live/sessions/{data['job_id']}").json()['configuration'] == saved
    result = world.client.get(f"/jobs/{data['job_id']}/result?format=json").json()
    assert result['language'] == 'es'
    assert result['configuration'] == saved['options']


def test_controls_reach_each_decode_and_preserve_confirmed_context():
    calls = []
    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append(kwargs)
            return [], None
    decoder = OnlineWhisper(Model(), language='en', options={'interval_seconds': 1, 'max_context_seconds': 12,
        'decoding': {'beam_size': 3, 'initial_prompt': 'Names: Ingestify.', 'hotwords': 'Data Lake',
                     'vad_parameters': {'threshold': .7}, 'compression_ratio_threshold': None}})
    decoder.offset = 1
    decoder.confirmed_words = [Word(0, .9, ' Confirmed context.')]
    decoder.push(b'\0\0' * 16000)
    decoder.finish()
    assert len(calls) == 2
    for call in calls:
        assert call['language'] == 'en' and call['beam_size'] == 3
        assert call['initial_prompt'] == 'Names: Ingestify. Confirmed context.'
        assert call['hotwords'] == 'Data Lake' and call['vad_parameters']['threshold'] == .7
        assert 'neg_threshold' not in call['vad_parameters']
        assert all(call[key] == value for key, value in MANAGED.items())
    assert decoder.max_context == 12 and decoder.interval == 1


def test_schema_exposes_only_protocol_compatible_controls(world):
    upgraded(world, ['en'])
    catalog = world.client.get('/transcribe/live/sessions/capabilities').json()
    assert catalog['options_supported'] and catalog['languages'] == ['en']
    controls = catalog['options_schema']['$defs']['LiveDecodingOptions']['properties']
    assert {'beam_size', 'best_of', 'initial_prompt', 'hotwords', 'vad_filter', 'vad_parameters', 'temperature'} <= controls.keys()
    assert not set(MANAGED).intersection(controls)
    assert world.client.post('/transcribe/live/sessions', json={'project_id': 'p', 'language': 'pt'}).status_code == 422
