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
from shared.transcripts import transcript_object_name
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
    assert json.loads(stored["transcript"]["json"]) == {
        k: RESULT[k] for k in ("language", "duration", "text", "segments")
    }

    metadata = stored["metadata"]
    assert metadata == {
        "format": "mp3", "size_bytes": 1000, "words": 4, "language": "pt", "duration": 61.2,
        "word_count": 4, "char_count": 32, "provider": "faster-whisper", "model": "turbo",
        "device": "cuda", "compute_type": "float16", "language_probability": 0.99,
        "processing_seconds": metadata["processing_seconds"], "output_format": "srt",
        "available_formats": ["markdown", "vtt", "srt", "txt", "json"],
    }


def test_formats_are_kept_in_minio_and_indexed_in_elasticsearch(world):
    world.run()

    for fmt in ("vtt", "srt", "txt", "json"):
        assert ("ingestify-audio", transcript_object_name(JOB_ID, fmt)) in world.minio.objects

    call = world.es.store_job_result.call_args.kwargs
    assert call["job_id"] == JOB_ID and call["user_id"] == "u1" and call["filename"] == "aula.mp3"
    assert call["total_pages"] is None
    assert call["markdown_content"].startswith("# Audio Transcription")


def test_the_job_is_marked_completed_everywhere_and_cleaned_up(world):
    world.run()

    with world.Session() as db:
        job = db.get(Job, JOB_ID)
        assert job.status == JobStatus.COMPLETED
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
