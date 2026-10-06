from api import live_routes
from shared.models import Job, JobStatus
from tests.test_live_transcription import world


def test_live_and_batch_share_identity_quota_before_worker_reservation(world, monkeypatch):
    monkeypatch.setattr(live_routes.get_settings(), 'job_max_active', 1)
    with world.db() as db:
        db.add(Job(id='batch', user_id='u', status=JobStatus.PROCESSING, job_type='MAIN'))
        db.commit()
    response = world.client.post('/transcribe/live/sessions', json={'project_id':'p'})
    assert response.status_code == 429


def test_live_cancellation_releases_sql_quota(world, monkeypatch):
    monkeypatch.setattr(live_routes.get_settings(), 'job_max_active', 1)
    first = world.client.post('/transcribe/live/sessions', json={'project_id':'p'})
    assert first.status_code == 201
    assert world.client.post('/transcribe/live/sessions', json={'project_id':'p'}).status_code == 429
    assert world.client.delete('/transcribe/live/sessions/' + first.json()['job_id']).status_code == 200
    assert world.client.post('/transcribe/live/sessions', json={'project_id':'p'}).status_code == 201


def test_live_reserves_entire_allowed_pcm_duration(world, monkeypatch):
    settings = live_routes.get_settings()
    monkeypatch.setattr(settings, 'live_max_duration_seconds', 1800)
    monkeypatch.setattr(settings, 'job_max_storage_mb', 54)
    # 1,800 s * 16,000 samples/s * two bytes is 57.6 MB, larger than
    # the default 50 MiB file allowance and the configured 54 MiB ledger.
    assert world.client.post('/transcribe/live/sessions', json={'project_id':'p'}).status_code == 429
