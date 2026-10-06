"""Provider downloads obey the same projected input allowance as admission."""
import asyncio
import sys
from types import SimpleNamespace

import pytest
from shared.config import get_settings
from workers.sources import DropboxHandler, GoogleDriveHandler


@pytest.mark.parametrize('provider', ['gdrive', 'dropbox'])
@pytest.mark.parametrize('oversized', [False, True])
def test_cloud_sources_stream_bounded_chunks_and_remove_partial_files(tmp_path, monkeypatch, provider, oversized):
    monkeypatch.setattr(get_settings(), 'max_file_size_mb', 1)
    chunks = [b'x' * 600_000, b'y' * 600_000] if oversized else [b'first', b'second']
    observed = {}
    if provider == 'gdrive':
        monkeypatch.setitem(sys.modules, 'google.oauth2', SimpleNamespace())
        monkeypatch.setitem(sys.modules, 'google.oauth2.credentials', SimpleNamespace(Credentials=lambda **kw: object()))
        service = SimpleNamespace(files=lambda: SimpleNamespace(get_media=lambda **kw: object()))
        monkeypatch.setitem(sys.modules, 'googleapiclient', SimpleNamespace())
        monkeypatch.setitem(sys.modules, 'googleapiclient.discovery', SimpleNamespace(build=lambda *a, **kw: service))
        class Downloader:
            def __init__(self, writer, request, chunksize):
                self.writer, self.index = writer, 0
                observed['chunk_size'] = chunksize
            def next_chunk(self):
                self.writer.write(chunks[self.index])
                self.index += 1
                return None, self.index == len(chunks)
        monkeypatch.setitem(sys.modules, 'googleapiclient.http', SimpleNamespace(MediaIoBaseDownload=Downloader))
        handler, source = GoogleDriveHandler(), 'file-id'
    else:
        class Response:
            @property
            def content(self):
                raise AssertionError('provider response must never be buffered whole')
            def iter_content(self, chunk_size):
                observed['chunk_size'] = chunk_size
                yield from chunks
            def close(self):
                observed['closed'] = True
        monkeypatch.setitem(sys.modules, 'dropbox', SimpleNamespace(
            Dropbox=lambda token: SimpleNamespace(files_download=lambda source: (object(), Response()))))
        handler, source = DropboxHandler(), '/folder/file.pdf'
    if oversized:
        with pytest.raises(Exception, match='SOURCE_FILE_SIZE_LIMIT_EXCEEDED'):
            asyncio.run(handler.download(source, tmp_path, auth_token='test-only-provider-token'))
        assert list(tmp_path.iterdir()) == []
    else:
        path = asyncio.run(handler.download(source, tmp_path, auth_token='test-only-provider-token'))
        assert path.read_bytes() == b''.join(chunks)
    assert observed['chunk_size'] == 1024 * 1024
    if provider == 'dropbox':
        assert observed['closed']
