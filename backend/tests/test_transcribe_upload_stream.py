"""/transcribe streams uploads to disk with a size limit instead of reading them into memory."""
import asyncio
import hashlib
import io

import pytest
from fastapi import HTTPException, UploadFile

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes


def upload(data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename="clip.mp4")


def stream(data, destination, max_size_mb=1):
    return asyncio.run(routes._stream_upload_to_file(upload(data), destination, max_size_mb))


def test_writes_file_and_returns_size_and_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "UPLOAD_CHUNK_SIZE", 1000)  # force several chunks
    data = bytes(range(256)) * 20
    destination = tmp_path / "staging" / "x.mp4"

    size, checksum = stream(data, destination)

    assert size == len(data)
    assert checksum == hashlib.sha256(data).hexdigest()
    assert destination.read_bytes() == data


def test_rejects_files_over_the_limit_and_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "UPLOAD_CHUNK_SIZE", 64 * 1024)
    destination = tmp_path / "x.mp4"
    with pytest.raises(HTTPException) as exc:
        stream(b"x" * (1024 * 1024 + 1), destination, max_size_mb=1)
    assert exc.value.status_code == 413
    assert not destination.exists()


def test_rejects_empty_upload(tmp_path):
    destination = tmp_path / "x.mp4"
    with pytest.raises(HTTPException) as exc:
        stream(b"", destination)
    assert exc.value.status_code == 400
    assert not destination.exists()
