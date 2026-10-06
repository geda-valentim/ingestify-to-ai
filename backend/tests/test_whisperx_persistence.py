"""Fault injection at every durable write; old attempts cannot publish or purge."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from shared.models import User, Job, JobStatus
from shared.redis_client import RedisClient
from workers.engines import pipeline
from tests.test_whisperx_contract import sample


@pytest.fixture
def setup(monkeypatch, tmp_path):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    with session() as db:
        db.add(User(id='u', username='speaker', email='speaker@example.com', hashed_password='x'))
        db.add(Job(id='j', user_id='u', filename='audio.wav', status=JobStatus.PROCESSING,
                   transcript_attempt_id='a', minio_upload_path='source'))
        db.commit()
    monkeypatch.setattr(pipeline, 'SessionLocal', session)
    minio = MagicMock(bucket_audio='audio')
    minio.upload_file.return_value = 'written'
    monkeypatch.setattr(pipeline, 'get_minio_client', lambda: minio)
    import workers.tasks
    monkeypatch.setattr(workers.tasks, '_remove_job_files', MagicMock())
    redis = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    es = MagicMock()
    es.store_job_result.return_value = True
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'fixture')
    options = {'_transcript_attempt_id': 'a', 'purge_source': True}
    def run():
        pipeline.finish_transcription('j', sample(), options=options, file_path=source,
            processing_seconds=1, compute_type='int8', redis_client=redis, es_client=es)
    return SimpleNamespace(run=run, db=session, minio=minio, redis=redis, es=es, options=options)


@pytest.mark.parametrize('index', [0, 1, 2, 3])
def test_failed_format_never_completes_or_purges(setup, index):
    setup.minio.upload_file.side_effect = ['ok'] * index + [RuntimeError('storage fault')]
    with pytest.raises(RuntimeError):
        setup.run()
    with setup.db() as db:
        row = db.get(Job, 'j')
        assert row.status == JobStatus.PROCESSING and row.minio_upload_path == 'source'
    assert setup.redis.get_job_result('j') is None
    assert all('/attempts/a/' in c.args[1] for c in setup.minio.delete_file.call_args_list)


def test_es_failure_preserves_source(setup):
    setup.es.store_job_result.return_value = False
    with pytest.raises(RuntimeError, match='INDEX_FAILED'):
        setup.run()
    assert setup.minio.delete_file.call_count == 4
    with setup.db() as db:
        assert db.get(Job, 'j').status != JobStatus.COMPLETED
        assert db.get(Job, 'j').minio_upload_path == 'source'


def test_superseded_attempt_cannot_publish(setup):
    with setup.db() as db:
        db.get(Job, 'j').transcript_attempt_id = 'new'
        db.commit()
    with pytest.raises(RuntimeError, match='CANCELLED'):
        setup.run()
    setup.minio.upload_file.assert_not_called()
    setup.es.store_job_result.assert_not_called()


def test_cancel_after_last_upload_prevents_index_and_publish(setup):
    calls = []
    def write(**kwargs):
        calls.append(kwargs)
        if len(calls) == 4:
            with setup.db() as db:
                db.get(Job, 'j').status = JobStatus.CANCELLED
                db.commit()
        return 'ok'
    setup.minio.upload_file.side_effect = write
    with pytest.raises(RuntimeError, match='CANCELLED'):
        setup.run()
    setup.es.store_job_result.assert_not_called()
    assert setup.redis.get_job_result('j') is None


def test_success_publishes_all_formats_before_purge(setup):
    setup.run()
    with setup.db() as db:
        assert db.get(Job, 'j').status == JobStatus.COMPLETED
        assert db.get(Job, 'j').minio_upload_path is None
    assert setup.minio.upload_file.call_count == 4
    assert setup.redis.get_job_result('j')['metadata']['schema_version'] == 2
    assert setup.redis.get_job_status('j')['status'] == 'completed'


def test_commit_failure_does_not_erase_a_retry_published_after_rollback(setup, monkeypatch):
    """Rollback releases the DB lock; cleanup must address only attempt objects."""
    real_factory = setup.db
    class FailingCommit:
        def __init__(self):
            self.db = real_factory()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.db.close()
        def __getattr__(self, name):
            return getattr(self.db, name)
        def commit(self):
            raise RuntimeError('commit lost')
        def rollback(self):
            self.db.rollback()
            # Another attempt publishes immediately after the lock is released.
            setup.redis.set_job_result('j', {'winner': 'new'})
    monkeypatch.setattr(pipeline, 'SessionLocal', FailingCommit)
    with pytest.raises(RuntimeError, match='commit lost'):
        setup.run()
    setup.es.delete_job_result.assert_not_called()
    assert setup.redis.get_job_result('j') == {'winner': 'new'}
    assert all('/attempts/a/' in call.args[1] for call in setup.minio.delete_file.call_args_list)
