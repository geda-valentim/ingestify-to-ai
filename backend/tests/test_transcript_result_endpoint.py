"""GET /jobs/{id}/result?format=... for transcription jobs."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes

JOB_ID = "3f1c9a2e-0000-4000-8000-000000000001"
USER = SimpleNamespace(id="user-1")
VTT = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nOlá\n"

METADATA = {
    "format": "mp4", "size_bytes": 1024, "words": 1, "language": "pt", "duration": 1.0,
    "device": "cuda", "available_formats": ["markdown", "vtt", "srt", "txt", "json"],
}


class FakeRedis:
    def __init__(self, result):
        self.result = result

    def get_job_status(self, job_id):
        return {"status": "completed", "type": "main", "completed_at": "2026-09-25T12:00:00"}

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
    def setup(redis_result, minio_objects=None, es_result=None):
        monkeypatch.setattr(routes, "get_redis_client", lambda: FakeRedis(redis_result))
        monkeypatch.setattr(routes, "get_es_client", lambda: SimpleNamespace(get_job_result=lambda job_id: es_result))
        monkeypatch.setattr(routes, "get_minio_client", lambda: FakeMinio(minio_objects or {}))
    return setup


def get_result(fmt=None):
    return asyncio.run(routes.get_job_result(JOB_ID, format_=fmt, current_user=USER, db=FakeDB()))


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
