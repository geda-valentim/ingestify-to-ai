"""
A transcription's outputs, end to end through process_conversion.

Spec 0003 slice 1a moved everything after the transcriber returns - formats,
MinIO, the Redis result, Elasticsearch, MySQL completion, file cleanup - into
workers.engines.pipeline.finish_transcription, so a remote engine's result can
finish the same way. These tests pin what that path produces, so the move (and
any later change) is checked against the observable behaviour, not the code.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.models import Job, JobStatus, User
from shared.redis_client import RedisClient
from shared.transcripts import transcript_object_name, transcript_result_object_name
from workers import tasks
from workers.engines import pipeline

JOB_ID = "11111111-2222-4333-8444-555555555555"

RESULT = {
    "text": "Olá, turma. Hoje: termodinâmica.",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": " Olá, turma."},
        {"start": 2.5, "end": 61.2, "text": " Hoje: termodinâmica."},
    ],
    "language": "pt",
    "language_probability": 0.99,
    "duration": 61.2,
    "word_count": 4,
    "char_count": 32,
    "provider": "faster-whisper",
    "model": "turbo",
    "device": "cuda",
}


class FakeMinio:
    bucket_audio = "ingestify-audio"

    def __init__(self):
        self.objects = {}
        self.deleted = []

    def upload_file(self, bucket_name, object_name, file_data, content_type):
        self.objects[(bucket_name, object_name)] = (file_data.decode("utf-8"), content_type)
        return object_name

    def download_file(self, bucket_name, object_name):
        return self.objects[(bucket_name, object_name)][0].encode()

    def delete_file(self, bucket_name, object_name):
        self.deleted.append((bucket_name, object_name))
        return True


@pytest.fixture
def world(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(User(id="u1", username="u", email="u@example.com", hashed_password="x"))
        db.add(Job(id=JOB_ID, user_id="u1", filename="aula.mp3", job_type="main",
                   status=JobStatus.PENDING, minio_upload_path=f"audio/{JOB_ID}/aula.mp3"))
        db.commit()

    audio_dir = tmp_path / "audio" / JOB_ID
    audio_dir.mkdir(parents=True)
    audio = audio_dir / "aula.mp3"
    audio.write_bytes(b"ID3" + b"\0" * 997)

    redis_client = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    redis_client.append_partial_transcript(JOB_ID, [{"start": 0.0, "end": 2.5, "text": "Olá"}])
    es = MagicMock()
    es.store_job_result.return_value = True
    minio = FakeMinio()
    transcriber = SimpleNamespace(compute_type="float16")

    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    for module in (tasks, pipeline):
        monkeypatch.setattr(module, "SessionLocal", Session)
    monkeypatch.setattr(pipeline, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)

    import workers.audio as audio_pkg
    monkeypatch.setattr(
        audio_pkg, "transcribe_with_gpu_fallback", lambda *a, **k: (dict(RESULT), transcriber)
    )

    def run(**options):
        tasks.process_conversion.run(
            job_id=JOB_ID, source_type="file", source=str(audio),
            options={"is_audio": True, "media_kind": "audio", **options},
        )

    return SimpleNamespace(run=run, Session=Session, redis=redis_client, es=es, minio=minio, audio=audio)


def test_the_job_completes_with_every_output(world):
    world.run(output_format="srt", include_timestamps=True)

    stored = world.redis.get_job_result(JOB_ID)
    assert stored["markdown"] == (
        "# Audio Transcription\n\n**Language:** pt\n**Duration:** 61.20s\n**Word Count:** 4\n"
        "\n---\n\n[00:00] Olá, turma.\n[00:02] Hoje: termodinâmica."
    )
    assert stored["transcript"]["vtt"] == (
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.500\nOlá, turma.\n\n"
        "2\n00:00:02.500 --> 00:01:01.200\nHoje: termodinâmica.\n"
    )
    assert stored["transcript"]["srt"].startswith("1\n00:00:00,000 --> 00:00:02,500\nOlá, turma.\n")
    assert stored["transcript"]["txt"] == "Olá, turma.\nHoje: termodinâmica."
    transcript = json.loads(stored["transcript"]["json"])
    assert all(transcript[key] == value for key, value in RESULT.items())
    assert transcript['configuration'] == {"is_audio": True, "media_kind": "audio", "output_format": "srt", "include_timestamps": True}

    metadata = stored["metadata"]
    assert metadata == {
        "format": "mp3", "size_bytes": 1000, "words": 4, "language": "pt", "duration": 61.2,
        "word_count": 4, "char_count": 32, "provider": "faster-whisper", "model": "turbo",
        "device": "cuda", "compute_type": "float16", "language_probability": 0.99,
        "processing_seconds": metadata["processing_seconds"], "output_format": "srt",
        "available_formats": ["markdown", "vtt", "srt", "txt", "json"],
        "configuration": transcript['configuration'],
    }


def test_formats_are_kept_in_minio_and_indexed_in_elasticsearch(world):
    world.run()

    for fmt in ("vtt", "srt", "txt", "json"):
        assert ("ingestify-audio", transcript_object_name(JOB_ID, fmt)) in world.minio.objects
    payload = json.loads(world.minio.objects[("ingestify-audio", transcript_result_object_name(JOB_ID))][0])
    assert payload == world.redis.get_job_result(JOB_ID)

    call = world.es.store_job_result.call_args.kwargs
    assert call["job_id"] == JOB_ID and call["user_id"] == "u1" and call["filename"] == "aula.mp3"
    assert call["total_pages"] is None
    assert call["markdown_content"].startswith("# Audio Transcription")


def test_the_job_is_marked_completed_everywhere_and_cleaned_up(world):
    world.run()

    with world.Session() as db:
        job = db.get(Job, JOB_ID)
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 100
        assert job.char_count == 32 and job.has_elasticsearch_result is True
        assert job.minio_upload_path is not None  # kept without purge_source

    status = world.redis.get_job_status(JOB_ID)
    assert status["status"] == "completed" and status["progress"] == 100
    assert world.redis.get_partial_transcript(JOB_ID) == ([], 0)  # live text dropped
    assert not world.audio.exists()  # local files removed
    assert world.minio.deleted == []


def test_purge_source_deletes_the_media_and_keeps_the_transcripts(world):
    world.run(purge_source=True)

    assert world.minio.deleted == [("ingestify-audio", f"audio/{JOB_ID}/aula.mp3")]
    with world.Session() as db:
        assert db.get(Job, JOB_ID).minio_upload_path is None
    assert ("ingestify-audio", transcript_object_name(JOB_ID, "txt")) in world.minio.objects


def test_without_timestamps_the_markdown_is_the_plain_text(world):
    world.run(include_timestamps=False)

    assert world.redis.get_job_result(JOB_ID)["markdown"].endswith("\n---\n\nOlá, turma. Hoje: termodinâmica.")


def test_the_old_helper_names_still_work():
    assert tasks._store_transcript_outputs is pipeline.store_transcript_outputs
    assert tasks._purge_audio_source is pipeline.purge_audio_source


def finish(world, **options):
    pipeline.finish_transcription(JOB_ID, dict(RESULT), options=options, file_path=world.audio,
                                 processing_seconds=0.5, compute_type="float16",
                                 redis_client=world.redis, es_client=world.es)


@pytest.mark.parametrize("failed_object", ["transcript.srt", "result.json"])
@pytest.mark.parametrize("failure", ["exception", "false"])
def test_storage_failure_never_completes_or_purges_source(world, monkeypatch, failed_object, failure):
    upload = world.minio.upload_file
    def fail(**kwargs):
        if kwargs['object_name'].endswith(failed_object):
            if failure == "exception":
                raise OSError("storage unavailable")
            return None
        return upload(**kwargs)
    monkeypatch.setattr(world.minio, "upload_file", fail)
    with pytest.raises((OSError, RuntimeError)):
        finish(world, purge_source=True)
    with world.Session() as db:
        assert db.get(Job, JOB_ID).status != JobStatus.COMPLETED
        assert db.get(Job, JOB_ID).minio_upload_path is not None
    assert world.audio.exists()
    assert not world.minio.deleted
    assert world.redis.get_job_result(JOB_ID) is None
    assert not world.es.store_job_result.called


def test_minio_unavailable_never_completes(world, monkeypatch):
    monkeypatch.setattr(pipeline, 'get_minio_client', lambda: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(OSError):
        finish(world)
    with world.Session() as db:
        assert db.get(Job, JOB_ID).status != JobStatus.COMPLETED
    assert world.audio.exists()


@pytest.mark.parametrize('index_failure', ['false', 'exception'])
def test_index_failure_keeps_exact_result_after_all_cache_entries_expire(world, monkeypatch, index_failure):
    if index_failure == 'false':
        world.es.store_job_result.return_value = False
    else:
        world.es.store_job_result.side_effect = OSError('index offline')
    finish(world, include_timestamps=False, output_format='srt')
    from api import routes
    monkeypatch.setattr(routes, 'get_redis_client', lambda: world.redis)
    monkeypatch.setattr(routes, 'get_minio_client', lambda: world.minio)
    monkeypatch.setattr(routes, 'get_es_client', lambda: (_ for _ in ()).throw(AssertionError('index must not be needed')))
    import asyncio
    world.redis.client.flushdb()
    with world.Session() as db:
        job = db.get(Job, JOB_ID)
        assert job.status == JobStatus.COMPLETED
        assert job.has_elasticsearch_result is False
        response = asyncio.run(routes.get_job_result(JOB_ID, format_='markdown', owned_job=job, db=db))
        assert '[00:00]' not in response.result.markdown
        assert response.result.markdown.endswith(RESULT['text'])
        assert response.result.metadata.device == 'cuda'
        default = asyncio.run(routes.get_job_result(JOB_ID, format_=None, owned_job=job, db=db))
        assert default.media_type.startswith('application/x-subrip')


def test_mysql_commit_failure_cannot_publish_cache_completion(world, monkeypatch):
    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, 'commit', lambda self: (_ for _ in ()).throw(OSError('SQL unavailable')))
    with pytest.raises(OSError):
        finish(world, purge_source=True)
    with world.Session() as db:
        assert db.get(Job, JOB_ID).status != JobStatus.COMPLETED
    assert (world.redis.get_job_status(JOB_ID) or {}).get('status') != 'completed'
    assert world.audio.exists()
    assert not world.minio.deleted
