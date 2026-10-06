"""Task-level fault injection: terminal state, retries and takeover are fenced."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from shared.models import Job, JobStatus, User
from shared.redis_client import RedisClient
from workers import tasks
from workers.engines import pipeline
from tests.test_whisperx_contract import sample


@pytest.fixture
def world(monkeypatch, tmp_path):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    with session() as db:
        db.add(User(id='u', username='speaker', email='speaker@example.com', hashed_password='x'))
        db.add(Job(id='j', user_id='u', filename='audio.wav', status=JobStatus.PENDING,
                   transcript_attempt_id='old', minio_upload_path='source'))
        db.commit()
    audio = tmp_path / 'j' / 'audio.wav'
    audio.parent.mkdir()
    audio.write_bytes(b'source')
    redis = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    for module in (tasks, pipeline):
        monkeypatch.setattr(module, 'SessionLocal', session)
    monkeypatch.setattr(tasks, 'get_redis_client', lambda: redis)
    monkeypatch.setattr(tasks, 'get_es_client', MagicMock())
    monkeypatch.setattr(tasks, 'get_source_handler', MagicMock())
    monkeypatch.setattr(tasks, '_resolve_uploaded_file', lambda *args: audio)
    monkeypatch.setattr(tasks, '_divert_audio_to_backlog', lambda *args: (False, audio))
    monkeypatch.setattr(tasks.settings, 'temp_storage_path', str(tmp_path))
    retry = MagicMock(side_effect=RuntimeError('RETRY'))
    monkeypatch.setattr(tasks.process_conversion, 'retry', retry)
    def run(**options):
        return tasks.process_conversion.run('j', 'file', str(audio),
            {'is_audio': True, 'transcriber_provider': 'whisperx', **options})
    return SimpleNamespace(session=session, audio=audio, redis=redis, retry=retry, run=run)


@pytest.mark.parametrize('winner', [JobStatus.COMPLETED, JobStatus.CANCELLED])
def test_stale_error_does_not_overwrite_terminal_winner(world, monkeypatch, winner):
    def old_fails(*args):
        with world.session() as db:
            job = db.get(Job, 'j')
            job.status, job.transcript_attempt_id = winner, 'winner'
            db.commit()
        world.redis.set_job_status('j', 'main', winner.value, progress=100)
        raise RuntimeError('TRANSCRIPTION_ATTEMPT_CANCELLED')
    monkeypatch.setattr(tasks, '_transcribe_audio', old_fails)
    assert world.run()['status'] == 'discarded'
    with world.session() as db:
        assert db.get(Job, 'j').status == winner
        assert db.get(Job, 'j').transcript_attempt_id == 'winner'
    assert world.redis.get_job_status('j')['status'] == winner.value
    assert world.audio.exists()
    world.retry.assert_not_called()


@pytest.mark.parametrize('state', [JobStatus.COMPLETED, JobStatus.CANCELLED])
def test_redelivery_never_restarts_terminal_job(world, monkeypatch, state):
    with world.session() as db:
        db.get(Job, 'j').status = state
        db.commit()
    infer = MagicMock()
    monkeypatch.setattr(tasks, '_transcribe_audio', infer)
    assert world.run()['status'] == 'discarded'
    infer.assert_not_called()
    assert world.redis.get_job_status('j') is None


def test_retry_message_with_obsolete_fence_is_discarded(world, monkeypatch):
    infer = MagicMock()
    monkeypatch.setattr(tasks, '_transcribe_audio', infer)
    assert world.run(_expected_attempt_id='older')['status'] == 'discarded'
    infer.assert_not_called()


def test_current_failure_retries_with_fence_and_preserves_source(world, monkeypatch):
    def fail(job_id, file_path, options, *args):
        pipeline.begin_transcription_attempt(job_id, options)
        raise RuntimeError('temporary storage error')
    monkeypatch.setattr(tasks, '_transcribe_audio', fail)
    with pytest.raises(RuntimeError, match='RETRY'):
        world.run()
    retry_options = world.retry.call_args.kwargs['kwargs']['options']
    with world.session() as db:
        assert db.get(Job, 'j').status == JobStatus.PENDING
        assert db.get(Job, 'j').transcript_attempt_id == retry_options['_expected_attempt_id']
    assert '_transcript_attempt_id' not in retry_options
    assert world.audio.exists()


def test_superseded_progress_cannot_mutate_new_attempt(world):
    stale = {'_transcript_attempt_id': 'old'}
    current = {}
    pipeline.begin_transcription_attempt('j', current)
    callback = MagicMock()
    assert not pipeline.with_transcription_attempt('j', stale, callback)
    callback.assert_not_called()


def test_takeover_publication_prefix_does_not_share_provider_attempt(world, monkeypatch):
    """New holder publishes while the previous holder is still uploading."""
    objects, calls = {}, []
    minio = MagicMock(bucket_audio='audio')
    es = MagicMock()
    es.store_job_result.return_value = True
    monkeypatch.setattr(pipeline, 'get_minio_client', lambda: minio)
    monkeypatch.setattr(tasks, '_remove_job_files', lambda *args: None)
    old, new = {}, {}
    pipeline.begin_transcription_attempt('j', old)
    def finish(options):
        pipeline.finish_transcription('j', sample(), options=options, file_path=world.audio,
            processing_seconds=1, compute_type='int8', redis_client=world.redis, es_client=es)
    def upload(**kwargs):
        name = kwargs['object_name']
        objects[name] = kwargs['file_data']
        calls.append(name)
        if len(calls) == 1:
            pipeline.begin_transcription_attempt('j', new)
            assert new['_transcript_attempt_id'] != old['_transcript_attempt_id']
            finish(new)
        return name
    minio.upload_file.side_effect = upload
    minio.delete_file.side_effect = lambda bucket, name: objects.pop(name, None)
    with pytest.raises(RuntimeError, match='CANCELLED'):
        finish(old)
    assert len(objects) == 4
    assert all(f"/attempts/{new['_transcript_attempt_id']}/" in name for name in objects)
    with world.session() as db:
        assert db.get(Job, 'j').status == JobStatus.COMPLETED
        assert db.get(Job, 'j').transcript_attempt_id == new['_transcript_attempt_id']


def test_gpu_retry_clears_unflushed_partial_batch(monkeypatch, tmp_path):
    from workers.audio import factory
    redis = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    redis.set_job_status('j', 'main', 'processing', progress=30)
    clock = [0.0]
    progress = tasks._transcription_progress(redis, 'j', clock=lambda: clock[0])
    class GPU:
        device = 'cuda'
        def transcribe(self, path, options, on_progress):
            on_progress(1, 10, {'start': 0, 'end': 1, 'text': 'gpu partial'})
            raise RuntimeError('CUDA out of memory')
    class CPU:
        device = 'cpu'
        def transcribe(self, path, options, on_progress):
            clock[0] = 3
            on_progress(1, 10, {'start': 0, 'end': 1, 'text': 'cpu only'})
            return {'text': 'cpu only'}
    providers = iter([GPU(), CPU()])
    monkeypatch.setattr(factory, 'get_audio_transcriber', lambda **kwargs: next(providers))
    monkeypatch.setattr(factory, 'mark_gpu_unavailable', lambda *args: None)
    monkeypatch.setattr(factory, 'reset_audio_transcriber', lambda: None)
    factory.transcribe_with_gpu_fallback(tmp_path / 'audio.wav', {'_reset_progress': lambda: progress(0, 0)}, on_progress=progress)
    segments, _ = redis.get_partial_transcript('j')
    assert [segment['text'] for segment in segments] == ['cpu only']
