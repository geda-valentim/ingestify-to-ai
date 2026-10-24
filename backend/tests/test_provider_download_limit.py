"""Drive and Dropbox downloads stream to disk and honour MAX_FILE_SIZE_MB."""
import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from workers import sources
from workers.sources import DropboxHandler, GoogleDriveHandler, SourceFileTooLarge

MB = 1024 * 1024
CHUNK = 64 * 1024


@pytest.fixture(autouse=True)
def limit_1mb(monkeypatch):
    monkeypatch.setattr(sources, "get_settings", lambda: SimpleNamespace(max_file_size_mb=1))
    monkeypatch.setattr(sources, "DOWNLOAD_CHUNK_BYTES", CHUNK)


def _run(handler, tmp_path, source, token="tok"):
    return asyncio.run(handler.download(source, tmp_path, auth_token=token))


# ---------- Google Drive ----------

class _FakeDrive:
    """Stands in for googleapiclient: records the token, the chunk size and what was produced."""

    def __init__(self, monkeypatch, *, declared, total):
        self.token = None
        self.chunksize = None
        self.pulled = 0  # bytes the "network" produced
        self.max_chunk = 0
        fake = self

        class Creds:
            def __init__(self, token):
                fake.token = token

        class Files:
            def get(self, fileId, fields):
                return SimpleNamespace(execute=lambda: {} if declared is None else {"size": str(declared)})

            def get_media(self, fileId):
                return object()

        class Service:
            def files(self):
                return Files()

        class Download:
            def __init__(self, fh, request, chunksize):
                fake.chunksize = chunksize
                self.fh = fh

            def next_chunk(self):
                size = min(CHUNK, total - fake.pulled)
                fake.pulled += size
                fake.max_chunk = max(fake.max_chunk, size)
                self.fh.write(b"x" * size)
                return SimpleNamespace(progress=lambda: fake.pulled / total), fake.pulled >= total

        modules = {
            "google": types.ModuleType("google"),
            "google.oauth2": types.ModuleType("google.oauth2"),
            "google.oauth2.credentials": SimpleNamespace(Credentials=Creds),
            "googleapiclient": types.ModuleType("googleapiclient"),
            "googleapiclient.discovery": SimpleNamespace(build=lambda *a, **k: Service()),
            "googleapiclient.http": SimpleNamespace(MediaIoBaseDownload=Download),
        }
        for name, module in modules.items():
            monkeypatch.setitem(sys.modules, name, module)


def test_drive_under_limit_streams_to_disk(monkeypatch, tmp_path):
    drive = _FakeDrive(monkeypatch, declared=300 * 1024, total=300 * 1024)
    path = _run(GoogleDriveHandler(), tmp_path, "file-id-123456")
    assert path.read_bytes() == b"x" * (300 * 1024)
    assert drive.token == "tok"
    assert drive.chunksize == CHUNK  # never the library's 100 MB default


def test_drive_declared_size_over_limit_fails_before_download(monkeypatch, tmp_path):
    drive = _FakeDrive(monkeypatch, declared=5 * MB, total=5 * MB)
    with pytest.raises(SourceFileTooLarge) as exc:
        _run(GoogleDriveHandler(), tmp_path, "file-id-123456")
    assert exc.value.max_mb == 1
    assert drive.pulled == 0
    assert list(tmp_path.iterdir()) == []


def test_drive_unknown_size_aborts_mid_stream_and_removes_partial(monkeypatch, tmp_path):
    drive = _FakeDrive(monkeypatch, declared=None, total=50 * MB)
    with pytest.raises(SourceFileTooLarge):
        _run(GoogleDriveHandler(), tmp_path, "file-id-123456")
    assert drive.pulled <= MB + CHUNK  # stopped right after crossing the limit
    assert drive.max_chunk <= CHUNK  # incremental, never the whole body
    assert list(tmp_path.iterdir()) == []


def test_drive_lying_declared_size_aborts_mid_stream(monkeypatch, tmp_path):
    drive = _FakeDrive(monkeypatch, declared=1000, total=20 * MB)
    with pytest.raises(SourceFileTooLarge):
        _run(GoogleDriveHandler(), tmp_path, "file-id-123456")
    assert drive.pulled <= MB + CHUNK
    assert list(tmp_path.iterdir()) == []


def test_drive_requires_token(tmp_path):
    with pytest.raises(ValueError):
        asyncio.run(GoogleDriveHandler().download("file-id-123456", tmp_path, auth_token=None))


# ---------- Dropbox ----------

class _FakeDropbox:
    def __init__(self, monkeypatch, *, declared, total):
        self.token = None
        self.pulled = 0
        self.closed = False
        self.chunk_size = None
        fake = self

        class Response:
            @property
            def content(self):  # reading the whole body is what this fix removes
                raise AssertionError("response.content must not be used")

            def iter_content(self, chunk_size):
                fake.chunk_size = chunk_size
                while fake.pulled < total:
                    size = min(CHUNK, total - fake.pulled)
                    fake.pulled += size
                    yield b"y" * size

            def close(self):
                fake.closed = True

        class Dropbox:
            def __init__(self, token):
                fake.token = token

            def files_download(self, path):
                return SimpleNamespace(size=declared), Response()

        monkeypatch.setitem(sys.modules, "dropbox", SimpleNamespace(Dropbox=Dropbox))


def test_dropbox_under_limit_streams_to_disk(monkeypatch, tmp_path):
    dbx = _FakeDropbox(monkeypatch, declared=300 * 1024, total=300 * 1024)
    path = _run(DropboxHandler(), tmp_path, "/docs/report.pdf")
    assert path.name == "report.pdf"
    assert path.read_bytes() == b"y" * (300 * 1024)
    assert dbx.token == "tok"
    assert dbx.chunk_size == CHUNK
    assert dbx.closed


def test_dropbox_declared_size_over_limit_fails_before_download(monkeypatch, tmp_path):
    dbx = _FakeDropbox(monkeypatch, declared=5 * MB, total=5 * MB)
    with pytest.raises(SourceFileTooLarge):
        _run(DropboxHandler(), tmp_path, "/docs/report.pdf")
    assert dbx.pulled == 0
    assert dbx.closed
    assert list(tmp_path.iterdir()) == []


def test_dropbox_lying_size_aborts_mid_stream_and_removes_partial(monkeypatch, tmp_path):
    dbx = _FakeDropbox(monkeypatch, declared=10, total=50 * MB)
    with pytest.raises(SourceFileTooLarge):
        _run(DropboxHandler(), tmp_path, "/docs/report.pdf")
    assert dbx.pulled <= MB + CHUNK
    assert dbx.closed
    assert list(tmp_path.iterdir()) == []


def test_dropbox_requires_token(tmp_path):
    with pytest.raises(ValueError):
        asyncio.run(DropboxHandler().download("/a.pdf", tmp_path, auth_token=None))


def test_file_too_large_message_is_the_catalog_one():
    from shared.error_catalog import render

    assert "1 MB" in render("FILE_TOO_LARGE", lang="en", max_size_mb=SourceFileTooLarge(1).max_mb)
