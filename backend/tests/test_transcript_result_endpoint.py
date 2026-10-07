"""GET /jobs/{id}/result?format=... for transcription jobs."""
import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes
from shared.models import Job, JobStatus

JOB_ID = "3f1c9a2e-0000-4000-8000-000000000001"
USER = SimpleNamespace(id="user-1")
VTT = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nOlá\n"

METADATA = {
    "format": "mp4", "size_bytes": 1024, "words": 1, "language": "pt", "duration": 1.0,
    "device": "cuda", "available_formats": ["markdown", "vtt", "srt", "txt", "json"],
}


class FakeRedis:
    def __init__(self, result, output_format=None, expired_status=False):
        self.result = result
        self.output_format = output_format
        self.expired_status = expired_status

    def get_job_output_format(self, job_id):
        return self.output_format

    def get_job_status(self, job_id):
        if self.expired_status:
            return None
        return {"status": "completed", "type": "main", "completed_at": "2026-09-25T12:00:00"}

    def get_job_pages_total(self, job_id):
        return None

    def get_partial_transcript(self, job_id, since):
        return [], 0

    def verify_job_ownership(self, job_id, user_id):
        return True

    def get_job_result(self, job_id):
        return self.result


class FakeMinio:
    bucket_audio = "ingestify-audio"

    def __init__(self, objects):
        self.objects = objects

    def download_file(self, bucket_name, object_name):
        if object_name not in self.objects:
            raise FileNotFoundError(object_name)
        return self.objects[object_name]


class FakeDB:
    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return None


@pytest.fixture
def backend(monkeypatch):
    def setup(redis_result, minio_objects=None, es_result=None, output_format=None, expired_status=False):
        monkeypatch.setattr(routes, "get_redis_client", lambda: FakeRedis(redis_result, output_format, expired_status))
        monkeypatch.setattr(routes, "get_es_client", lambda: SimpleNamespace(get_job_result=lambda job_id: es_result))
        monkeypatch.setattr(routes, "get_minio_client", lambda: FakeMinio(minio_objects or {}))
        monkeypatch.setattr("shared.live.lifecycle.available", lambda db: False)
        monkeypatch.setattr(routes.engine_dispatch, "job_signal", lambda db, job_id: (None, None))
    return setup


def get_result(fmt=None, owned_job=None):
    return asyncio.run(routes.get_job_result(JOB_ID, format_=fmt, current_user=USER, owned_job=owned_job, db=FakeDB()))


def durable_job(status=JobStatus.COMPLETED, job_id=JOB_ID):
    return Job(id=job_id, user_id=USER.id, job_type="MAIN", status=status, progress=0,
               filename="recording.mp3", mime_type="audio/mpeg", file_size_bytes=1024,
               created_at=datetime(2026, 9, 25, 11), completed_at=datetime(2026, 9, 25, 12))


def test_vtt_from_redis(backend):
    backend({"markdown": "# t", "metadata": METADATA, "transcript": {"vtt": VTT}})
    response = get_result("vtt")
    assert response.body.decode() == VTT
    assert response.media_type.startswith("text/vtt")
    assert f'filename="{JOB_ID}.vtt"' in response.headers["content-disposition"]


def test_vtt_from_minio_after_redis_expired(backend):
    backend(
        None,
        minio_objects={f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode()},
        es_result={"markdown_content": "# t", "metadata": METADATA},
    )
    assert get_result("vtt").body.decode() == VTT


def test_vtt_from_minio_when_elasticsearch_has_no_result(backend):
    backend(None, minio_objects={f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode()}, es_result=None)
    assert get_result("vtt").body.decode() == VTT


def test_empty_srt_is_served_from_minio(backend):
    backend(None, minio_objects={f"transcripts/{JOB_ID}/transcript.srt": b""})
    response = get_result("srt")
    assert response.body == b""
    assert response.media_type.startswith("application/x-subrip")


def test_latest_requested_default_format_wins(backend):
    # e.g. the same file re-submitted (deduplicated) with output_format=vtt
    backend({"markdown": "# t", "metadata": {**METADATA, "output_format": "markdown"}, "transcript": {"vtt": VTT}},
            output_format="vtt")
    assert get_result().body.decode() == VTT


def test_markdown_query_overrides_default(backend):
    backend({"markdown": "# t", "metadata": METADATA, "transcript": {"vtt": VTT}}, output_format="vtt")
    assert get_result("markdown").result.markdown == "# t"


def test_output_format_chosen_at_upload_is_the_default(backend):
    backend({"markdown": "# t", "metadata": {**METADATA, "output_format": "srt"}, "transcript": {"srt": "1\n"}})
    assert get_result().media_type.startswith("application/x-subrip")


def test_default_is_json_with_transcription_metadata(backend):
    backend({"markdown": "# t", "metadata": METADATA, "transcript": {"vtt": VTT}})
    response = get_result()
    assert response.result.markdown == "# t"
    assert response.result.metadata.device == "cuda"
    assert "vtt" in response.result.metadata.available_formats


def test_document_job_has_no_subtitles(backend):
    backend({"markdown": "# doc", "metadata": {"format": "pdf", "size_bytes": 10}})
    with pytest.raises(HTTPException) as exc:
        get_result("vtt")
    assert exc.value.status_code == 404


def test_invalid_format_is_rejected(backend):
    backend({"markdown": "# t", "metadata": METADATA})
    with pytest.raises(HTTPException) as exc:
        get_result("docx")
    assert exc.value.status_code == 422


def test_durable_status_after_cache_expiry(backend):
    backend(None, expired_status=True)
    response = asyncio.run(routes.get_job_status(
        JOB_ID, current_user=USER, owned_job=durable_job(), db=FakeDB()))
    assert response.status == "completed"
    assert response.progress == 100
    assert response.created_at == datetime(2026, 9, 25, 11)
    assert response.completed_at == datetime(2026, 9, 25, 12)


@pytest.mark.parametrize("fmt", ["vtt", "srt", "txt", "json"])
def test_durable_formats_after_status_and_result_expire(backend, fmt):
    content = {"vtt": VTT, "srt": "1\n", "txt": "Olá", "json": '{"text":"Olá"}'}[fmt]
    backend(None, expired_status=True, minio_objects={f"transcripts/{JOB_ID}/transcript.{fmt}": content.encode()})
    assert get_result(fmt, durable_job()).body.decode() == content


def test_durable_default_format_after_cache_expiry(backend):
    backend(None, expired_status=True, output_format="vtt",
            minio_objects={f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode()})
    assert get_result(owned_job=durable_job()).body.decode() == VTT


def test_display_recovers_from_minio_without_elasticsearch_or_redis(backend):
    transcript = {"text": "Olá mundo", "language": "pt", "duration": 1.0,
                  "segments": [{"start": 0.0, "end": 1.0, "text": "Olá mundo"}]}
    backend(None, expired_status=True, output_format="json",
            minio_objects={f"transcripts/{JOB_ID}/transcript.json": json.dumps(transcript).encode()})
    response = get_result("markdown", durable_job())
    assert "[00:00] Olá mundo" in response.result.markdown
    assert response.result.metadata.language == "pt"
    assert response.result.metadata.duration == 1.0
    assert response.result.metadata.size_bytes == 1024
    assert response.result.metadata.device is None
    assert "vtt" in response.result.metadata.available_formats


@pytest.mark.parametrize("status,code", [(JobStatus.PENDING, 400), (JobStatus.PROCESSING, 400),
                                        (JobStatus.CANCELLED, 400), (JobStatus.FAILED, 500)])
def test_unfinished_durable_job_cannot_publish_stored_transcript(backend, status, code):
    backend(None, expired_status=True, minio_objects={f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode()})
    with pytest.raises(HTTPException) as exc:
        get_result("vtt", durable_job(status))
    assert exc.value.status_code == code


def test_parent_status_is_not_used_for_expired_child(backend):
    backend(None, expired_status=True)
    with pytest.raises(HTTPException) as exc:
        get_result("vtt", durable_job(job_id="parent-job"))
    assert exc.value.status_code == 404


def test_completed_partial_after_cache_expiry(backend):
    backend(None, expired_status=True)
    response = asyncio.run(routes.get_partial_transcript(JOB_ID, since=0, current_user=USER, owned_job=durable_job()))
    assert response.status == "completed"
    assert response.segments == []


def test_terminal_mysql_status_overrides_stale_cache(backend):
    backend(None)  # Redis incorrectly says completed.
    job = durable_job(JobStatus.FAILED)
    job.error_message = "Storage failed"
    with pytest.raises(HTTPException) as exc:
        get_result("json", job)
    assert exc.value.status_code == 500
    assert "Storage failed" in exc.value.detail


def test_durable_result_preserves_markdown_metadata_and_default_without_any_cache(backend, monkeypatch):
    payload = {"markdown": "Custom original text without timestamps", "metadata": {
        **METADATA, "output_format": "vtt", "provider": "faster-whisper", "processing_seconds": 2.5}}
    backend(None, expired_status=True, minio_objects={
        f"transcripts/{JOB_ID}/result.json": json.dumps(payload).encode(),
        f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode(),
    })
    monkeypatch.setattr(routes, "get_es_client", lambda: (_ for _ in ()).throw(AssertionError("Index must not be needed")))
    response = get_result("markdown", durable_job())
    assert response.result.markdown == payload["markdown"]
    assert response.result.metadata.device == "cuda"
    assert get_result(owned_job=durable_job()).body.decode() == VTT


def test_subtitles_do_not_require_initializing_elasticsearch(backend, monkeypatch):
    backend(None, expired_status=True, minio_objects={f"transcripts/{JOB_ID}/transcript.vtt": VTT.encode()})
    monkeypatch.setattr(routes, "get_es_client", lambda: (_ for _ in ()).throw(OSError("Index offline")))
    assert get_result("vtt", durable_job()).body.decode() == VTT
