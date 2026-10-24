"""A user-supplied S3 endpoint cannot make the API buffer an unbounded response."""
import gzip
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from shared.datalake.adapters import BoundedPoolManager, S3Adapter, ResponseTooLarge

CAP = 64 * 1024
SMALL = (b'<?xml version="1.0" encoding="UTF-8"?><ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
         b"<Owner><ID>x</ID></Owner><Buckets><Bucket><Name>alpha</Name><CreationDate>2024-01-01T00:00:00.000Z</CreationDate>"
         b"</Bucket></Buckets></ListAllMyBucketsResult>")
BLOCK = b"<a>" + b"x" * 16 * 1024
TOTAL = 4096 * len(BLOCK)  # ~64 MiB a hostile server is willing to send


@pytest.fixture
def server():
    state = {"mode": "small", "sent": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def stream(self, status, headers=()):
            # Close-delimited body (no Content-Length) until the client goes away.
            self.send_response(status)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Connection", "close")
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            try:
                for _ in range(4096):
                    self.wfile.write(BLOCK)
                    state["sent"] += len(BLOCK)
            except OSError:
                pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(10 * 1024 * 1024))
            self.end_headers()

        def do_GET(self):
            mode = state["mode"]
            if mode == "small":
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(SMALL)))
                self.end_headers()
                self.wfile.write(SMALL)
            elif mode == "gzip":
                body = gzip.compress(SMALL)
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif mode == "declared":
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(10 * 1024 * 1024 * 1024))
                self.end_headers()
                self.wfile.flush()
                try:
                    self.wfile.write(b"x" * 1024)
                except OSError:
                    pass
            elif mode == "redirect":
                self.stream(302, [("Location", "/elsewhere")])
            elif mode == "retry":
                self.stream(503, [("Retry-After", "1")])
            elif mode == "error":
                self.stream(500)
            else:
                self.stream(200)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state["endpoint"] = f"http://127.0.0.1:{httpd.server_port}"
    yield state
    httpd.shutdown()
    httpd.server_close()


def adapter(state):
    a = S3Adapter({"endpoint": state["endpoint"]}, {"access_key": "k", "secret_key": "s"})
    a.client._http = BoundedPoolManager(max_response_bytes=CAP)
    return a


def test_the_adapter_uses_the_bounded_transport():
    a = S3Adapter({"endpoint": "http://127.0.0.1:1"}, {"access_key": "k", "secret_key": "s"})
    assert isinstance(a.client._http, BoundedPoolManager)
    assert a.client._http.max_response_bytes == 8 * 1024 * 1024


def test_a_normal_listing_works(server):
    assert adapter(server).buckets() == ["alpha"]


def test_a_streamed_body_without_content_length_stops_at_the_cap(server):
    server["mode"] = "stream"
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()
    assert server["sent"] < TOTAL / 2  # loopback buffers allow overshoot, never the whole body


def test_a_declared_huge_content_length_fails_fast(server):
    server["mode"] = "declared"
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()


@pytest.mark.parametrize("mode", ["redirect", "retry"])
def test_redirect_and_retry_after_bodies_are_bounded(server, mode):
    # urllib3 would drain a 3xx body and honor Retry-After before the cap sees them.
    server["mode"] = mode
    started = time.monotonic()
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()
    assert server["sent"] < TOTAL / 2
    assert time.monotonic() - started < 0.9  # no Retry-After sleep


def test_head_with_a_large_content_length_is_not_refused(server):
    # stat_object of an object bigger than the cap: HEAD has no body to buffer.
    response = BoundedPoolManager(max_response_bytes=CAP).urlopen("HEAD", server["endpoint"] + "/b/k")
    assert response.status == 200
    assert response.headers["Content-Length"] == str(10 * 1024 * 1024)


def test_a_compressed_response_is_refused(server):
    server["mode"] = "gzip"
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()


def test_a_huge_error_body_is_bounded_even_when_the_caller_streams(server):
    server["mode"] = "error"
    with pytest.raises(ResponseTooLarge):
        BoundedPoolManager(max_response_bytes=CAP).urlopen("GET", server["endpoint"] + "/b/k", preload_content=False)
    assert server["sent"] < TOTAL / 2


def test_a_streamed_success_passes_through_unbuffered(server):
    server["mode"] = "stream"
    response = BoundedPoolManager(max_response_bytes=CAP).urlopen(
        "GET", server["endpoint"] + "/b/k", preload_content=False)
    try:
        assert response.status == 200
        assert len(response.read(1024)) == 1024  # the body is still on the wire
        assert server["sent"] < TOTAL
    finally:
        response.close()
