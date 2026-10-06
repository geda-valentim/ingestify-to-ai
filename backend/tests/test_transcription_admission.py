"""Public multipart admission and durable publication contracts of spec 0006."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.test_upload_projects import db, env, add_project, jwt, ALICE
from api import routes
from shared.models import Job
from shared.transcription import options_from_profile


@pytest.fixture
def whisperx(monkeypatch):
    monkeypatch.setattr(routes.settings, 'audio_transcriber_provider', 'whisperx')
    monkeypatch.setattr(routes.settings, 'whisperx_diarization_default', True)
    monkeypatch.setattr(routes.settings, 'whisperx_diarization_ready', True)


def request(env, endpoint, **fields):
    return env.client.post(endpoint, headers=jwt(),
        files={'file': ('meeting.mp4', b'video-fixture-bytes', 'video/mp4')},
        data={'project': 'Meetings', **({'source_type':'file'} if endpoint == '/convert' else {}), **fields})


@pytest.mark.parametrize('endpoint', ['/upload', '/transcribe', '/convert'])
def test_public_options_survive_enqueue_and_changed_defaults(env, whisperx, monkeypatch, endpoint):
    response = request(env, endpoint, language='pt', diarize='true', min_speakers=2,
                       max_speakers=3, include_word_timestamps='true')
    assert response.status_code == 200, response.text
    job = env.db.get(Job, response.json()['job_id'])
    assert job.transcription_profile_hash and len(job.transcription_profile_hash) == 64
    profile = job.transcription_profile
    assert (profile['language'], profile['diarize'], profile['min_speakers'], profile['max_speakers'], profile['include_word_timestamps']) == ('pt', True, 2, 3, True)
    queued = env.enqueued[-1]
    assert queued['queue'] == routes.settings.transcription_queue
    queued = queued.get('kwargs', queued)
    assert queued['options']['transcription_profile'] == profile
    assert queued['options']['diarization_explicit'] is True
    monkeypatch.setattr(routes.settings, 'audio_transcriber_provider', 'faster-whisper')
    assert options_from_profile(profile)['transcriber_provider'] == 'whisperx'


@pytest.mark.parametrize('endpoint', ['/upload', '/transcribe', '/convert'])
@pytest.mark.parametrize('options', [{'min_speakers':0}, {'min_speakers':4,'max_speakers':2}, {'diarize':'false','max_speakers':2}])
def test_invalid_options_have_no_job_or_enqueue(env, whisperx, endpoint, options):
    assert request(env, endpoint, **options).status_code == 422
    assert env.db.query(Job).count() == 0 and env.enqueued == []


@pytest.mark.parametrize('endpoint', ['/upload', '/transcribe', '/convert'])
def test_unready_returns_503_before_upload(env, whisperx, monkeypatch, endpoint):
    monkeypatch.setattr(routes.settings, 'whisperx_diarization_ready', False)
    response = request(env, endpoint)
    assert response.status_code == 503 and response.json()['detail']['code'] == 'DIARIZATION_NOT_READY'
    assert env.db.query(Job).count() == 0 and env.enqueued == []


def test_profile_changes_prevent_dedupe_and_identical_request_reuses_job(env, whisperx):
    first = request(env, '/transcribe', language='pt', diarize='true')
    same = request(env, '/transcribe', language='pt', diarize='true')
    different = request(env, '/transcribe', language='pt', diarize='false')
    assert same.json()['job_id'] == first.json()['job_id']
    assert different.json()['job_id'] != first.json()['job_id']
    assert len(env.enqueued) == 2


@pytest.mark.parametrize('endpoint', ['/upload', '/convert'])
def test_documents_ignore_unready_default_but_reject_explicit_diarization(env, whisperx, monkeypatch, endpoint):
    monkeypatch.setattr(routes.settings, 'whisperx_diarization_ready', False)
    def post(**extra):
        return env.client.post(endpoint, headers=jwt(),
            files={'file':('notes.pdf', b'%PDF-test', 'application/pdf')},
            data={'project':'Notes', **({'source_type':'file'} if endpoint == '/convert' else {}), **extra})
    assert post(diarize='true').status_code == 422
    assert env.enqueued == []
    response = post()
    assert response.status_code == 200, response.text
    assert env.db.get(Job, response.json()['job_id']).transcription_profile is None


def test_status_exposes_alignment_phase(env, whisperx, fake_redis):
    response = request(env, '/transcribe')
    job_id = response.json()['job_id']
    fake_redis.set_job_status(job_id, 'main', 'processing', progress=70)
    fake_redis.update_job_progress(job_id, 70, phase='aligning')
    response = env.client.get(f'/jobs/{job_id}', headers=jwt())
    assert response.status_code == 200, response.text
    assert response.json()['phase'] == 'aligning'


@pytest.mark.parametrize('endpoint', ['/upload', '/transcribe', '/convert'])
def test_sql_failure_never_enqueues_or_keeps_orphan_cache(env, whisperx, monkeypatch, fake_redis, endpoint):
    add_project(env.db, ALICE, 'Meetings')
    def fail_job_commit():
        raise RuntimeError('SQL unavailable')
    monkeypatch.setattr(env.db, 'commit', fail_job_commit)
    response = request(env, endpoint, diarize='true')
    assert response.status_code == 503
    assert env.enqueued == [] and env.db.query(Job).count() == 0
    assert not list(fake_redis.client.scan_iter('job:*'))


def test_unknown_url_keeps_candidate_profile_without_downloading(env, whisperx):
    response = env.client.post('/convert', headers=jwt(), data={
        'project':'Meetings', 'source_type':'url', 'source':'https://example.com/resource', 'language':'pt'})
    assert response.status_code == 200, response.text
    job = env.db.get(Job, response.json()['job_id'])
    assert job.transcription_profile['provider'] == 'whisperx'
    assert job.transcription_profile['diarize'] is True
    assert env.enqueued[-1]['options']['diarization_explicit'] is False


def test_migration_preserves_legacy_rows_and_prevents_active_downgrade():
    script = Path(__file__).resolve().parents[2] / 'scripts/migrate_0006_transcription_profiles.py'
    if not script.exists():
        script = Path('/scripts/migrate_0006_transcription_profiles.py')
    spec = importlib.util.spec_from_file_location('migration_0006', script)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE jobs (id VARCHAR(36) PRIMARY KEY, status VARCHAR(20), filename TEXT)'))
        conn.execute(text("INSERT INTO jobs VALUES ('old', 'COMPLETED', 'old.mp3')"))
    migration.migrate(engine)
    migration.migrate(engine)
    with engine.begin() as conn:
        row = conn.execute(text('SELECT filename, transcription_profile FROM jobs')).one()
        assert tuple(row) == ('old.mp3', None)
        conn.execute(text("INSERT INTO jobs VALUES ('new', 'PROCESSING', 'new.mp3', '{}', 'hash', NULL)"))
    with pytest.raises(RuntimeError, match='Drain'):
        migration.migrate(engine, downgrade=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET status='COMPLETED' WHERE id='new'"))
    migration.migrate(engine, downgrade=True)
    migration.migrate(engine, downgrade=True)
    assert {c['name'] for c in inspect(engine).get_columns('jobs')} == {'id','status','filename'}
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM jobs')).scalar() == 2
