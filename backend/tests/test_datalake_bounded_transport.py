"""A user-supplied S3 endpoint cannot make the API buffer an unbounded response."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from shared.datalake.adapters import BoundedPoolManager, S3Adapter, ResponseTooLarge

CAP = 64 * 1024
SMALL = (b'<?xml version="1.0" encoding="UTF-8"?><ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
         b"<Owner><ID>x</ID></Owner><Buckets><Bucket><Name>alpha</Name><CreationDate>2024-01-01T00:00:00.000Z</CreationDate>"
         b"</Bucket></Buckets></ListAllMyBucketsResult>")


@pytest.fixture
def server():
    state = {"mode": "small", "sent": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            mode = state["mode"]
            if mode == "small":
                self.send_header("Content-Length", str(len(SMALL)))
                self.end_headers()
                self.wfile.write(SMALL)
            elif mode == "declared":
                self.send_header("Content-Length", str(10 * 1024 * 1024 * 1024))
                self.end_headers()
                self.wfile.flush()
                try:
                    self.wfile.write(b"x" * 1024)
                except OSError:
                    pass
            else:  # streamed until the client goes away, no Content-Length
                self.send_header("Connection", "close")
                self.end_headers()
                block = b"<a>" + b"x" * 16 * 1024
                try:
                    for _ in range(4096):  # 64 MiB at most
                        self.wfile.write(block)
                        state["sent"] += len(block)
                except OSError:
                    pass

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
    assert a.client._http.max_response_bytes == 4 * 1024 * 1024


def test_a_normal_listing_works(server):
    assert adapter(server).buckets() == ["alpha"]


def test_a_streamed_body_without_content_length_stops_at_the_cap(server):
    server["mode"] = "stream"
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()
    assert server["sent"] < 16 * CAP  # socket buffers allow some overshoot, never the 64 MiB


def test_a_declared_huge_content_length_fails_fast(server):
    server["mode"] = "declared"
    with pytest.raises(ResponseTooLarge):
        adapter(server).buckets()
