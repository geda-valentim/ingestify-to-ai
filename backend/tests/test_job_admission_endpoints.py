"""Public routes share the same authenticated identity and durable slot."""
import base64
import pytest
from api import routes
from shared.models import Job, JobStatus
from tests.test_upload_projects import db, env, jwt, api_key, add_key, ALICE, PNG


@pytest.mark.parametrize('endpoint', ['/upload', '/transcribe', '/convert'])
def test_all_multipart_routes_return_429_before_stream(env, monkeypatch, endpoint):
    monkeypatch.setattr(routes.settings, 'job_max_active', 1)
    env.db.add(Job(id='existing', user_id=ALICE, status=JobStatus.PROCESSING, job_type='MAIN'))
    env.db.commit()
    async def forbidden(*args):
        raise AssertionError('quota must reject before reading/staging upload')
    monkeypatch.setattr(routes, '_stream_upload_to_file', forbidden)
    response = env.client.post(endpoint, headers=jwt(), files={'file': ('a.mp3', b'audio', 'audio/mpeg')},
                               data={'project': 'Quota', **({'source_type': 'file'} if endpoint == '/convert' else {})})
    assert response.status_code == 429
    assert not env.enqueued


@pytest.mark.parametrize('endpoint', ['/images/describe', '/images/ocr', '/images/describe/upload', '/images/ocr/upload'])
def test_all_image_routes_share_active_quota(env, monkeypatch, endpoint):
    monkeypatch.setattr(routes.settings, 'job_max_active', 1)
    env.db.add(Job(id='existing', user_id=ALICE, status=JobStatus.PROCESSING, job_type='MAIN'))
    env.db.commit()
    if endpoint.endswith('/upload'):
        response = env.client.post(endpoint, headers=jwt(), files={'file': ('a.png', PNG, 'image/png')}, data={'project':'Quota'})
    else:
        response = env.client.post(endpoint, headers=jwt(), json={'image_base64':base64.b64encode(PNG).decode(), 'project':'Quota'})
    assert response.status_code == 429


def test_jwt_and_api_keys_share_user_quota(env, monkeypatch):
    monkeypatch.setattr(routes.settings, 'job_max_active', 1)
    add_key(env.db, 'quota-key', ALICE)
    first = env.client.post('/upload', headers=jwt(), files={'file': ('a.pdf', b'pdf', 'application/pdf')}, data={'project':'Quota'})
    assert first.status_code == 200, first.text
    response = env.client.post('/upload', headers=api_key('quota-key'), files={'file': ('b.pdf', b'different', 'application/pdf')}, data={'project':'Quota'})
    assert response.status_code == 429


def test_cannot_delete_active_job_to_reset_budget(env):
    env.db.add(Job(id='active', user_id=ALICE, status=JobStatus.PROCESSING, job_type='MAIN'))
    env.db.commit()
    response = env.client.delete('/jobs/active', headers=jwt())
    assert response.status_code == 409
    assert env.db.get(Job, 'active') is not None


def test_remote_convert_reserves_unknown_input_before_enqueue(env, monkeypatch):
    monkeypatch.setattr(routes.settings, 'job_max_storage_mb', routes.settings.max_file_size_mb - 1)
    response = env.client.post('/convert', headers=jwt(), data={
        'source_type':'url', 'source':'https://example.invalid/unknown.pdf', 'project':'Quota'})
    assert response.status_code == 429
    assert not env.enqueued


def test_retry_of_terminal_parent_consumes_active_page_slot(env, monkeypatch):
    from shared.models import Page
    monkeypatch.setattr(routes.settings, 'job_max_active', 1)
    env.db.add(Job(id='parent', user_id=ALICE, status=JobStatus.COMPLETED, job_type='MAIN', filename='doc.pdf'))
    env.db.flush()
    env.db.add_all([Page(id='active-page', job_id='parent', page_number=1, status=JobStatus.PROCESSING),
                    Page(id='failed-page', job_id='parent', page_number=2, status=JobStatus.FAILED)])
    env.db.commit()
    response = env.client.post('/jobs/parent/pages/2/retry', headers=jwt())
    assert response.status_code == 429
    assert env.client.delete('/jobs/parent', headers=jwt()).status_code == 409


def test_retry_missing_pdf_releases_active_slot(env, monkeypatch):
    from shared.models import Page
    monkeypatch.setattr(routes.settings, 'job_max_active', 1)
    env.db.add(Job(id='parent', user_id=ALICE, status=JobStatus.COMPLETED, job_type='MAIN', filename='doc.pdf'))
    env.db.flush()
    env.db.add(Page(id='failed-page', job_id='parent', page_number=2, status=JobStatus.FAILED))
    env.db.commit()
    assert env.client.post('/jobs/parent/pages/2/retry', headers=jwt()).status_code == 404
    env.db.expire_all()
    assert env.db.get(Page, 'failed-page').status == JobStatus.FAILED
    response = env.client.post('/upload', headers=jwt(), files={'file': ('a.pdf', b'pdf', 'application/pdf')}, data={'project':'Quota'})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('source_type,bucket', [('file', 'uploads'), ('audio', 'audio')])
@pytest.mark.parametrize('fail_raises', [False, True])
def test_delete_input_failure_keeps_storage_ledger(env, monkeypatch, source_type, bucket, fail_raises):
    from types import SimpleNamespace
    monkeypatch.setattr(routes.settings, 'job_max_storage_mb', 1)
    env.db.add(Job(id='retained', user_id=ALICE, status=JobStatus.COMPLETED,
                  job_type='MAIN', source_type=source_type, minio_upload_path='source',
                  file_size_bytes=1024 * 1024))
    env.db.commit()
    calls = []
    def remove(actual_bucket, key):
        calls.append((actual_bucket, key))
        if fail_raises:
            raise RuntimeError('offline')
        return False
    monkeypatch.setattr(routes, 'get_minio_client', lambda: SimpleNamespace(
        bucket_audio='audio', bucket_uploads='uploads', delete_file=remove))
    response = env.client.delete('/jobs/retained', headers=jwt())
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'JOB_INPUT_CLEANUP_FAILED'
    env.db.expire_all()
    assert env.db.get(Job, 'retained').file_size_bytes == 1024 * 1024
    assert calls == [(bucket, 'source')]
    assert env.client.post('/upload', headers=jwt(), files={
        'file': ('a.pdf', b'pdf', 'application/pdf')}, data={'project':'Quota'}).status_code == 429


@pytest.mark.parametrize('already_absent', [False, True])
def test_delete_document_confirms_input_removal_before_freeing_ledger(env, monkeypatch, already_absent):
    from types import SimpleNamespace
    env.db.add(Job(id='retained', user_id=ALICE, status=JobStatus.COMPLETED,
                   job_type='MAIN', source_type='file', minio_upload_path='source', file_size_bytes=123))
    env.db.commit()
    objects = set() if already_absent else {'source'}
    calls = []
    def remove(bucket, key):
        calls.append((bucket, key))
        objects.discard(key)
        return True
    monkeypatch.setattr(routes, 'get_minio_client', lambda: SimpleNamespace(
        bucket_audio='audio', bucket_uploads='uploads', delete_file=remove))
    response = env.client.delete('/jobs/retained', headers=jwt())
    assert response.status_code == 200, response.text
    env.db.expire_all()
    assert env.db.get(Job, 'retained') is None
    assert not objects
    assert calls == [('uploads', 'source')]
