"""/upload and /convert stream files to disk (size limit + checksum) instead of reading them into memory."""
import asyncio
from datetime import datetime
import hashlib
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes
from workers import tasks

USER = SimpleNamespace(id="user-1", username="alice")
DATA = b"%PDF-1.4 " + bytes(range(256)) * 50


class FakeRedis:
    def __getattr__(self, name):
        return lambda *args, **kwargs: True


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, existing=None):
        self.existing = existing

    def query(self, model):
        return FakeQuery(self.existing)

    def add(self, obj):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeMinio:
    bucket_uploads = "ingestify-uploads"

    def __init__(self):
        self.uploads = []

    def upload_file(self, **kwargs):
        assert "file_data" not in kwargs, "upload must be streamed from disk, not from memory"
        self.uploads.append(kwargs)


@pytest.fixture
def env(tmp_path, monkeypatch):
    minio = FakeMinio()
    enqueued = []
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(routes.settings, "max_file_size_mb", 1)
    monkeypatch.setattr(routes, "get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(routes, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kwargs: enqueued.append(kwargs))
    return SimpleNamespace(tmp=tmp_path, minio=minio, enqueued=enqueued)


def upload_file(data=DATA, name="report.pdf"):
    return UploadFile(file=io.BytesIO(data), filename=name, headers={"content-type": "application/pdf"})


def upload(data=DATA, db=None):
    return asyncio.run(routes.upload_and_convert(
        file=upload_file(data), name=None, docling_preset="fast", current_user=USER, db=db or FakeDB(),
    ))


def staging_files(tmp):
    staging = tmp / "uploads" / ".staging"
    return list(staging.iterdir()) if staging.exists() else []


def test_upload_is_moved_to_job_dir_and_streamed_to_minio(env):
    response = upload()
    job_dir = env.tmp / "uploads" / str(response.job_id)
    saved = job_dir / "report.pdf"

    assert saved.read_bytes() == DATA
    assert env.minio.uploads[0]["file_path"] == str(saved)
    assert env.enqueued[0]["source"] == str(saved)
    assert staging_files(env.tmp) == []


def test_upload_over_limit_is_rejected_without_leftovers(env):
    with pytest.raises(HTTPException) as exc:
        upload(b"x" * (1024 * 1024 + 1))
    assert exc.value.status_code == 413
    assert staging_files(env.tmp) == []
    assert env.enqueued == []


def test_duplicate_upload_discards_staged_file(env):
    existing = SimpleNamespace(id="3f1c9a2e-0000-4000-8000-00000000000a", created_at=datetime.utcnow())
    response = upload(db=FakeDB(existing=existing))
    assert str(response.job_id) == existing.id
    assert staging_files(env.tmp) == []
    assert env.enqueued == []


def test_convert_streams_the_uploaded_file(env):
    response = asyncio.run(routes.convert_document(
        source_type="file", source=None, file=upload_file(), name=None,
        authorization=None, current_user=USER, db=FakeDB(),
    ))
    saved = env.tmp / "uploads" / str(response.job_id) / "report.pdf"
    assert saved.read_bytes() == DATA
    assert env.enqueued[0]["source"] == str(saved)
    assert env.minio.uploads[0]["file_path"] == str(saved)


def test_checksum_matches_content(tmp_path):
    size, checksum = asyncio.run(routes._stream_upload_to_file(upload_file(), tmp_path / "x.pdf", 1))
    assert (size, checksum) == (len(DATA), hashlib.sha256(DATA).hexdigest())


class BrokenDB(FakeDB):
    def query(self, model):
        raise RuntimeError("database unavailable")


def test_staged_file_removed_when_setup_fails_before_enqueue(env):
    with pytest.raises(RuntimeError):
        upload(db=BrokenDB())
    assert staging_files(env.tmp) == []
    assert env.enqueued == []


def test_convert_staged_file_removed_when_setup_fails(env):
    with pytest.raises(RuntimeError):
        asyncio.run(routes.convert_document(
            source_type="file", source=None, file=upload_file(), name=None,
            authorization=None, current_user=USER, db=BrokenDB(),
        ))
    assert staging_files(env.tmp) == []


def test_staging_name_stays_short_for_long_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    long_name = "a." + "b" * 220  # valid sanitized name (< 255 bytes), huge "extension"
    staged = routes._upload_staging_path(long_name)
    assert len(staged.name.encode()) <= 36 + routes.STAGING_MAX_SUFFIX_BYTES
    assert routes._upload_staging_path("report.pdf").suffix == ".pdf"
    assert routes._upload_staging_path("clip.mp4", "audio").parent == tmp_path / "audio" / ".staging"
