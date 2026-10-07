"""Provider validation, durable requests and local/remote decoding parity."""
import inspect
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from api import routes
from shared.audio_capabilities import AudioDecodingOptions, audio_capabilities, validate_audio_options
from shared.job_configuration import job_configuration
from shared.models import Job, JobConfiguration
from workers.audio.decoding_options import FASTER_WHISPER_OPTIONS, PROVIDER_OPTIONS
from workers.engines import whisper_core
from workers.engines.modal_apps import protocol
from tests.test_upload_projects import db, env, jwt  # noqa: F401: shared authenticated upload harness


@pytest.fixture(autouse=True)
def audio_model(monkeypatch):
    monkeypatch.setattr(routes.settings, 'audio_transcriber_provider', 'faster-whisper')
    monkeypatch.setattr(routes.settings, 'whisper_model', 'turbo')


def upload(env, options=None, **fields):
    return env.client.post('/transcribe', headers=jwt(), files={'file': ('recording.wav', b'RIFF-audio', 'audio/wav')},
        data={'project': 'Audio checks', **({'decoding_options': json.dumps(options)} if options is not None else {}), **fields})


def test_catalog_requires_authentication_and_lists_the_installed_parameters(env, monkeypatch):
    monkeypatch.setattr('shared.engines.routing.get_route', lambda *args, **kwargs: None)
    assert env.client.get('/audio/capabilities').status_code == 401
    response = env.client.get('/audio/capabilities', headers=jwt())
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['model'] == 'turbo' and catalog['tasks'] == ['transcribe']
    assert catalog['operations'] == ['transcribe', 'detect_language', 'inspect']
    assert catalog['workers_running'] is False and 'fila' in catalog['execution_reason']
    from faster_whisper import WhisperModel
    parameters = set(inspect.signature(WhisperModel.transcribe).parameters) - {'self', 'audio'}
    assert FASTER_WHISPER_OPTIONS == parameters
    assert set(catalog['parameters_schema']['properties']) == parameters - {'word_timestamps'}


def test_language_catalog_matches_the_native_tokenizer():
    from faster_whisper.tokenizer import _LANGUAGE_CODES
    from shared.audio_capabilities import WHISPER_LANGUAGE_CODES, local_whisper_languages
    assert WHISPER_LANGUAGE_CODES == _LANGUAGE_CODES
    assert local_whisper_languages('base.en') == ('en',)
    assert 'yue' not in local_whisper_languages('large-v2')
    assert 'yue' in local_whisper_languages('large-v3-turbo')


@pytest.mark.parametrize('provider', ['faster-whisper', 'openai-whisper'])
def test_language_validation_matches_model_and_catalog(provider):
    settings = SimpleNamespace(audio_transcriber_provider=provider, whisper_model='large-v2', enable_audio_transcription=True,
        max_audio_file_size_mb=50, max_video_file_size_mb=500)
    languages = audio_capabilities(settings).parameters_schema['properties']['language']['enum']
    assert None in languages and 'pt' in languages and 'yue' not in languages and 'zz' not in languages
    with pytest.raises(ValueError, match='Idioma'):
        validate_audio_options({'language': 'yue'}, provider=provider, model='large-v2')
    with pytest.raises(ValueError, match='Idioma'):
        validate_audio_options({'language': 'zz'}, provider=provider, model='turbo')
    assert validate_audio_options({'language': 'pt'}, provider=provider, model='large-v2')['language'] == 'pt'


@pytest.mark.parametrize('provider', list(PROVIDER_OPTIONS))
def test_catalog_excludes_unsupported_provider_controls(provider):
    settings = SimpleNamespace(audio_transcriber_provider=provider, whisper_model='medium', enable_audio_transcription=True,
        max_audio_file_size_mb=50, max_video_file_size_mb=500)
    catalog = audio_capabilities(settings)
    assert set(catalog.parameters_schema['properties']) == PROVIDER_OPTIONS[provider] - {'word_timestamps'}
    assert catalog.tasks == ['transcribe', 'translate']
    if provider == 'openai-api':
        assert catalog.model == 'whisper-1' and catalog.max_video_size_mb == 25


@pytest.mark.parametrize('options', [
    {'task': 'translate'}, {'beam_size': 0}, {'beam_size': 21}, {'temperature': []},
    {'temperature': [0, 2]}, {'vad_parameters': {'unknown': True}}, {'clip_timestamps': '1,0'},
    {'clip_timestamps': 'nan'}, {'unknown': True}, {'prefix': [1, 2]}, {'suppress_tokens': '-1'},
    {'language': 'zz'}, {'language': 'por'},
])
def test_invalid_options_leave_no_job_file_or_dispatch(env, options):
    response = upload(env, options)
    assert response.status_code == 422, response.text
    assert env.db.query(Job).count() == 0 and env.db.query(JobConfiguration).count() == 0
    assert env.enqueued == [] and list(env.tmp.iterdir()) == []


def test_request_is_stored_before_dispatch_and_different_settings_create_new_jobs(env):
    requested = {'language': 'pt', 'hotwords': 'Ingestify', 'temperature': [0, .2],
                 'clip_timestamps': [0, 2], 'vad_parameters': {'threshold': .4}, 'beam_size': 2}
    first = upload(env, requested, include_word_timestamps='true')
    assert first.status_code == 200, first.text
    first_id = first.json()['job_id']
    persisted = job_configuration(env.db.get(Job, first_id))
    assert persisted['model'] == 'turbo' and persisted['provider'] == 'faster-whisper'
    assert all(persisted['options'][key] == value for key, value in requested.items() if key != 'vad_parameters')
    assert persisted['options']['vad_parameters']['threshold'] == .4
    assert persisted['options']['vad_parameters']['min_silence_duration_ms'] == 500
    queued = env.enqueued[0]['kwargs']['options']
    assert all(queued[key] == value for key, value in requested.items() if key != 'vad_parameters')
    assert protocol.clean_options(queued)['hotwords'] == 'Ingestify'
    repeated = upload(env, requested, include_word_timestamps='true')
    assert repeated.json()['job_id'] == first_id and len(env.enqueued) == 1
    changed = upload(env, {**requested, 'language': 'en'}, include_word_timestamps='true')
    assert changed.json()['job_id'] != first_id and len(env.enqueued) == 2
    env.db.expire_all()
    status = env.client.get('/jobs/' + first_id, headers=jwt())
    assert status.status_code == 200, status.text
    assert status.json()['configuration'] == persisted


@pytest.mark.parametrize('source_type', ['url', 'gdrive', 'dropbox'])
@pytest.mark.parametrize('operation', ['transcribe', 'detect_language', 'inspect'])
def test_external_audio_sources_keep_options_configuration_and_queue(env, source_type, operation):
    requested = {'operation': operation, 'decoding': {'beam_size': 2, 'hotwords': 'Ingestify'},
        'include_timestamps': False, 'include_word_timestamps': operation == 'transcribe',
        'output_format': 'json', 'purge_source': True}
    response = env.client.post('/convert', headers={**jwt(), 'X-Source-Token': 'external-provider-token'}, data={
        'source_type': source_type, 'source': 'https://example.test/opaque-source',
        'project': 'Audio sources', 'name': 'Named conversation', 'audio_options': json.dumps(requested)})
    assert response.status_code == 200, response.text
    job_id = response.json()['job_id']
    saved = job_configuration(env.db.get(Job, job_id))
    assert saved['operation'] == 'transcription' and saved['provider'] == 'faster-whisper'
    assert saved['options']['operation'] == operation and saved['options']['hotwords'] == 'Ingestify'
    assert saved['options']['include_timestamps'] is False and saved['options']['purge_source'] is True
    queued = env.enqueued[0]
    assert queued['queue'] == routes.settings.transcription_queue
    assert queued['kwargs']['options'] == {**saved['options'], 'is_audio': True, 'transcriber_provider': 'faster-whisper'}
    assert 'external-provider-token' not in json.dumps(queued)
    status = env.client.get('/jobs/' + job_id, headers=jwt())
    assert status.json()['configuration'] == saved and status.json()['kind'] == 'transcription'
    listed = env.client.get('/jobs?kind=transcription', headers=jwt()).json()
    assert listed['total'] == 1 and listed['jobs'][0]['job_id'] == job_id
    assert env.client.get('/jobs?kind=document', headers=jwt()).json()['total'] == 0
    assert routes._is_transcription_job(job_id, env.db.get(Job, job_id))


@pytest.mark.parametrize('options', [
    {'decoding': {'task': 'translate'}}, {'decoding': {'beam_size': 0}},
    {'unknown': True}, {'operation': 'detect_language', 'decoding': {'language': 'pt'}},
    {'include_word_timestamps': True, 'decoding': {'without_timestamps': True}}, {'output_format': 'html'},
])
def test_external_audio_validation_precedes_job_location_and_queue(env, options):
    response = env.client.post('/convert', headers=jwt(), data={
        'source_type': 'url', 'source': 'https://example.test/audio.wav',
        'project': 'Audio sources', 'audio_options': json.dumps(options)})
    assert response.status_code == 422, response.text
    assert env.db.query(Job).count() == 0 and env.db.query(JobConfiguration).count() == 0
    assert not env.enqueued and list(env.tmp.iterdir()) == []


def test_convert_audio_file_uses_transcribe_limits_and_configuration_deduplication(env):
    options = {'decoding': {'language': 'pt', 'hotwords': 'Ingestify'}, 'output_format': 'json'}
    first = env.client.post('/convert', headers=jwt(), files={'file': ('recording.wav', b'RIFF-audio', 'audio/wav')},
        data={'source_type': 'file', 'project': 'Audio checks', 'audio_options': json.dumps(options)})
    assert first.status_code == 200, first.text
    repeated = upload(env, options['decoding'], output_format='json')
    assert repeated.json()['job_id'] == first.json()['job_id'] and len(env.enqueued) == 1


def test_audio_and_document_controls_cannot_be_combined(env):
    response = env.client.post('/convert', headers=jwt(), data={'source_type': 'url',
        'source': 'https://example.test/file', 'project': 'Mixed options', 'audio_options': '{}', 'conversion_options': '{}'})
    assert response.status_code == 422 and not env.enqueued and env.db.query(Job).count() == 0


@pytest.mark.parametrize('source_type,source', [('url', 'https://example.test/recording.wav?token=fixture'),
    ('dropbox', '/recordings/lecture.mp4')])
def test_implicit_external_media_saves_audio_defaults_before_queue(env, source_type, source):
    response = env.client.post('/convert', headers={**jwt(), 'X-Source-Token': 'fixture'},
        data={'source_type': source_type, 'source': source, 'project': 'Audio defaults'})
    assert response.status_code == 200, response.text
    configuration = job_configuration(env.db.get(Job, response.json()['job_id']))
    assert configuration['operation'] == 'transcription' and configuration['provider'] == 'faster-whisper'
    assert configuration['options']['output_format'] == 'markdown'
    assert env.enqueued[0]['kwargs']['options']['is_audio'] is True
    assert env.enqueued[0]['queue'] == routes.settings.transcription_queue


@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
@pytest.mark.parametrize('name,mime', [('recording.wav', 'audio/wav'), ('lecture.m4v', 'video/x-m4v')])
def test_implicit_media_upload_matches_explicit_transcription_configuration(env, endpoint, name, mime):
    response = env.client.post(endpoint, headers=jwt(), files={'file': (name, b'RIFF-audio', mime)},
        data={'project': 'Audio checks', **({'source_type': 'file'} if endpoint == '/convert' else {})})
    assert response.status_code == 200, response.text
    configuration = job_configuration(env.db.get(Job, response.json()['job_id']))
    assert configuration['operation'] == 'transcription' and configuration['provider'] == 'faster-whisper'
    repeated = upload(env)
    assert repeated.json()['job_id'] == response.json()['job_id'] and len(env.enqueued) == 1


@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
def test_document_controls_on_known_media_rejected_before_upload(env, endpoint):
    response = env.client.post(endpoint, headers=jwt(), files={'file': ('recording.wav', b'RIFF-audio', 'audio/wav')},
        data={'project': 'Wrong model', 'conversion_options': '{"formats":["html"],"output_format":"html"}',
            **({'source_type': 'file'} if endpoint == '/convert' else {})})
    assert response.status_code == 422 and 'Docling' in response.json()['detail']
    assert env.db.query(Job).count() == 0 and env.enqueued == [] and list(env.tmp.iterdir()) == []


def test_document_controls_on_known_external_media_rejected_before_queue(env):
    response = env.client.post('/convert', headers=jwt(), data={'source_type': 'url',
        'source': 'https://example.test/recording.wav', 'project': 'Wrong model', 'docling_preset': 'quality'})
    assert response.status_code == 422 and 'Docling' in response.json()['detail']
    assert env.db.query(Job).count() == 0 and env.enqueued == []


def test_discovered_audio_replaces_document_configuration_before_inference(env, monkeypatch):
    from workers import tasks
    response = env.client.post('/convert', headers={**jwt(), 'X-Source-Token': 'fixture'},
        data={'source_type': 'gdrive', 'source': 'opaque-file-id', 'project': 'Discovery'})
    job_id = response.json()['job_id']
    assert job_configuration(env.db.get(Job, job_id))['operation'] == 'document'
    monkeypatch.setattr(tasks, 'SessionLocal', lambda: env.db)
    options = tasks._resolve_discovered_audio_options(job_id, env.enqueued[0]['options'])
    saved = job_configuration(env.db.get(Job, job_id))
    assert saved['operation'] == 'transcription' and saved['provider'] == 'faster-whisper'
    assert options == {**saved['options'], 'is_audio': True, 'transcriber_provider': 'faster-whisper'}
    env.db.expire_all()
    status = env.client.get('/jobs/'+job_id, headers=jwt()).json()
    assert status['kind'] == 'transcription' and status['configuration'] == saved


def test_explicit_document_controls_on_discovered_audio_are_not_ignored(env, monkeypatch):
    from workers import tasks
    response = env.client.post('/convert', headers={**jwt(), 'X-Source-Token': 'fixture'},
        data={'source_type': 'gdrive', 'source': 'opaque-file-id', 'project': 'Discovery', 'conversion_options': '{}'})
    job_id = response.json()['job_id']
    with pytest.raises(ValueError, match='não aceita opções Docling'):
        tasks._resolve_discovered_audio_options(job_id, env.enqueued[0]['options'])
    assert job_configuration(env.db.get(Job, job_id))['operation'] == 'document'
    env.db.expire_all()
    # Retry recovers the same processing intent from SQL, even without the
    # original task message or its Redis cache.
    saved = job_configuration(env.db.get(Job, job_id))['options']
    assert saved['processing_mode'] == 'document'
    with pytest.raises(ValueError, match='não aceita opções Docling'):
        tasks._resolve_discovered_audio_options(job_id, saved)
    with pytest.raises(ValueError, match='não aceita opções Docling'):
        tasks._resolve_discovered_audio_options(job_id, {'_document_requested': True})


def test_discovered_audio_persistence_failure_prevents_inference_options(monkeypatch):
    from workers import tasks
    from shared.models import JobConfiguration
    job = SimpleNamespace(configuration_row=JobConfiguration(operation='document', options={}, fingerprint='old'))
    session = MagicMock(); session.query.return_value.filter.return_value.first.return_value = job
    session.commit.side_effect = RuntimeError('database unavailable')
    monkeypatch.setattr(tasks, 'SessionLocal', lambda: session)
    with pytest.raises(RuntimeError, match='database unavailable'):
        tasks._resolve_discovered_audio_options('controlled-fixture', {})
    session.rollback.assert_called_once(); session.close.assert_called_once()


@pytest.mark.parametrize('provider,options', [
    ('openai-api', {'beam_size': 3}), ('openai-api', {'temperature': [0, .2]}),
    ('openai-api', {'initial_prompt': [1]}), ('openai-whisper', {'hotwords': 'term'}),
    ('openai-whisper', {'initial_prompt': [1]}),
])
def test_provider_restrictions_reject_before_execution(provider, options):
    with pytest.raises(ValueError):
        validate_audio_options(options, provider=provider, model='medium')


def test_all_public_decoding_controls_survive_the_remote_protocol_and_reach_the_model(tmp_path):
    options = validate_audio_options({}, provider='faster-whisper', model='medium')
    options.update(task='translate', language='pt', initial_prompt='technical lecture', hotwords='Ingestify',
                   clip_timestamps='0,2', temperature=[0, .4], vad_parameters={'threshold': .4},
                   include_word_timestamps=True)
    portable = protocol.clean_options(options)
    assert portable == {k: v for k, v in options.items() if k != 'language' or v is not None}
    model = MagicMock()
    model.transcribe.return_value = (iter([]), SimpleNamespace(language='pt', language_probability=.99, duration=2))
    whisper_core.transcribe(model, tmp_path / 'audio.wav', portable, model_name='medium')
    kwargs = model.transcribe.call_args.kwargs
    assert kwargs['word_timestamps'] is True
    assert kwargs == {**{k: v for k, v in portable.items() if k != 'include_word_timestamps'}, 'word_timestamps': True}


def test_language_detection_does_not_decode_segments(tmp_path):
    def segments():
        raise AssertionError('Language detection must not decode the full recording')
        yield
    model = MagicMock()
    model.transcribe.return_value = (segments(), SimpleNamespace(language='pt', language_probability=.97, duration=2))
    result = whisper_core.transcribe(model, tmp_path / 'audio.wav', {'operation': 'detect_language'}, model_name='turbo')
    assert result['operation'] == 'detect_language' and result['language_probability'] == .97
    assert result['segments'] == [] and result['language'] == 'pt'


def test_file_inspection_returns_stream_metadata_without_inference(tmp_path):
    import wave
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as recording:
        recording.setnchannels(1); recording.setsampwidth(2); recording.setframerate(16000)
        recording.writeframes(b'\0\0' * 16000)
    model = MagicMock()
    result = whisper_core.transcribe(model, path, {'operation': 'inspect'}, model_name='turbo')
    model.transcribe.assert_not_called()
    assert result['operation'] == 'inspect' and result['duration'] == 1
    assert result['media_info']['channels'] == 1 and result['media_info']['sample_rate'] == 16000


@pytest.mark.parametrize('options', [
    {'temperature': [0] * 101}, {'initial_prompt': [-2]},
    {'initial_prompt': [1] * 10001}, {'prefix': 'x' * 10001},
    {'suppress_tokens': [-2]}, {'clip_timestamps': [0] * 10001},
    {'clip_timestamps': '1000000001'}, {'vad_parameters': {'speech_pad_ms': 1000000001}},
])
def test_requests_outside_portable_worker_limits_are_rejected_at_the_api(env, options):
    response = upload(env, options)
    assert response.status_code == 422, response.text
    assert env.db.query(Job).count() == 0 and env.enqueued == []


def test_modal_artifact_can_import_shared_audio_contract_in_isolation(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from workers.engines.modal_apps.files import BACKEND_DIR, SOURCE_FILES
    for source in SOURCE_FILES:
        destination = tmp_path / source.relative_to(BACKEND_DIR)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    result = subprocess.run([sys.executable, '-c',
        'from workers.audio.decoding_options import clean_remote_options; '
        'assert clean_remote_options({"beam_size": 3}) == {"beam_size": 3}'],
        cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(tmp_path)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_configuration_persistence_failure_cannot_dispatch_an_unrecorded_request(env, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('configuration storage unavailable')
    monkeypatch.setattr(routes, 'save_configuration', unavailable)
    response = upload(env, {'language': 'pt'})
    assert response.status_code == 503
    assert env.enqueued == []
    assert env.db.query(Job).count() == 0 and env.db.query(JobConfiguration).count() == 0
    assert not any(path.is_file() for path in env.tmp.rglob('*'))


def test_cloud_provider_forwards_prompt_temperature_and_preserves_word_timestamps(tmp_path):
    from workers.audio.openai_api_transcriber import OpenAIAPITranscriber
    transcriber = object.__new__(OpenAIAPITranscriber)
    transcriber.client = MagicMock()
    transcriber.client.audio.transcriptions.create.return_value = SimpleNamespace(
        text='Olá mundo', language='portuguese', duration=2,
        segments=[{'start': 0, 'end': 2, 'text': 'Olá mundo'}],
        words=[{'start': 0, 'end': .5, 'word': 'Olá'}, {'start': 1, 'end': 2, 'word': 'mundo'}])
    path = tmp_path / 'recording.wav'
    path.write_bytes(b'RIFF-fixture')
    options = validate_audio_options({'initial_prompt': 'technical lecture', 'language': 'pt', 'temperature': .2},
                                     provider='openai-api', model='whisper-1')
    result = transcriber.transcribe(path, {**options, 'include_word_timestamps': True})
    sent = transcriber.client.audio.transcriptions.create.call_args.kwargs
    assert sent['prompt'] == 'technical lecture' and sent['temperature'] == .2
    assert sent['language'] == 'pt' and sent['timestamp_granularities'] == ['segment', 'word']
    assert [word['word'] for word in result['segments'][0]['words']] == ['Olá', 'mundo']


def test_cloud_translation_uses_translation_endpoint_without_language_or_word_arguments(tmp_path):
    from workers.audio.openai_api_transcriber import OpenAIAPITranscriber
    transcriber = object.__new__(OpenAIAPITranscriber)
    transcriber.client = MagicMock()
    transcriber.client.audio.translations.create.return_value = SimpleNamespace(
        text='Hello world', language='english', duration=2, segments=[])
    path = tmp_path / 'recording.wav'
    path.write_bytes(b'RIFF-fixture')
    options = validate_audio_options({'task': 'translate', 'initial_prompt': 'Technical lecture', 'language': 'pt'},
                                     provider='openai-api', model='whisper-1')
    result = transcriber.transcribe(path, options)
    transcriber.client.audio.transcriptions.create.assert_not_called()
    sent = transcriber.client.audio.translations.create.call_args.kwargs
    assert sent['prompt'] == 'Technical lecture'
    assert 'language' not in sent and 'timestamp_granularities' not in sent
    assert result['text'] == 'Hello world'


def test_local_whisper_receives_its_own_supported_controls(tmp_path):
    from workers.audio.openai_whisper_transcriber import OpenAIWhisperTranscriber
    transcriber = object.__new__(OpenAIWhisperTranscriber)
    transcriber.model_size = 'medium'
    transcriber.model = MagicMock()
    transcriber.model.transcribe.return_value = {'text': 'Hello world', 'language': 'en',
        'segments': [{'start': 0, 'end': 1, 'text': 'Hello world', 'avg_logprob': -.1}]}
    path = tmp_path / 'recording.wav'
    path.write_bytes(b'RIFF-fixture')
    options = validate_audio_options({'task': 'translate', 'carry_initial_prompt': True, 'initial_prompt': 'lecture',
                                     'fp16': False, 'sample_len': 64}, provider='openai-whisper', model='medium')
    result = transcriber.transcribe(path, options)
    sent = transcriber.model.transcribe.call_args.kwargs
    assert sent['task'] == 'translate' and sent['sample_len'] == 64 and sent['fp16'] is False
    assert sent['carry_initial_prompt'] and sent['initial_prompt'] == 'lecture'
    assert sent['best_of'] is None and sent['patience'] is None
    assert 'vad_filter' not in sent and 'hotwords' not in sent
    assert result['segments'][0]['avg_logprob'] == -.1
