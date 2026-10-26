"""Docling load script, foundation layer: arguments, corpus, output guard and the HTTP client (fake servers only)."""
import importlib.util
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/bench_docling_load.py"
if not SCRIPT.exists():
    pytest.skip("scripts/ not mounted (backend-only container)", allow_module_level=True)
spec = importlib.util.spec_from_file_location("bench_api", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

def test_guards(tmp_path, monkeypatch):
    for d in (tmp_path / "missing", tmp_path, None):
        with pytest.raises(bench.UsageError, match="BENCH_CORPUS_DIR"):
            bench.load_corpus(d)
    monkeypatch.setattr(bench, "ALLOWED_ROOT", str(tmp_path / "ok"))
    monkeypatch.setattr(bench, "ROOT_DEVICE_PATH", "/proc")
    assert bench.check_output_root(str(tmp_path / "ok" / "runs"))
    for bad in (tmp_path / "other", tmp_path / "ok" / ".." / "x"):
        with pytest.raises(bench.UsageError, match="outside"):
            bench.check_output_root(str(bad))
    monkeypatch.setattr(bench, "ROOT_DEVICE_PATH", str(tmp_path))
    with pytest.raises(bench.UsageError, match="system disk"):
        bench.check_output_root(str(tmp_path / "ok"))

def test_order():
    o = lambda c, r: [f["rel_path"] for f in bench.client_order([{"rel_path": str(i)} for i in range(20)], 22, c, r)]
    assert o("A", 1) == o("A", 1) != o("A", 2) and sorted(o("A", 1)) == sorted(o("B", 1))

class Trickle(BaseHTTPRequestHandler):  # a small JSON reply that arrives one byte at a time: in the headers or in the body
    log_message = lambda self, *a: None
    where = "body"

    def drip(self, data):
        try:
            for i in range(len(data)):
                self.wfile.write(data[i:i + 1]), self.wfile.flush(), time.sleep(0.4)
        except OSError:  # the client gave up
            pass

    def do_GET(self):
        body = b'{"status": "completed"}'
        head = b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body)
        self.drip(head + body) if Trickle.where == "head" else (self.wfile.write(head), self.drip(body))

@pytest.mark.parametrize("where", ["head", "body"])
def test_get_json_never_outlives_the_deadline_on_a_trickling_reply(where):
    Trickle.where = where
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api, t0 = bench.Api(f"http://127.0.0.1:{srv.server_address[1]}", "k"), time.time()
    try:
        with pytest.raises(RuntimeError):
            api.get_json("/j", time.time() + 0.6)  # the whole reply would take ~15 s; each read is within the socket timeout
        assert time.time() - t0 < 2 and api.http_retries >= 1
    finally:
        srv.shutdown()

def test_get_json_returns_promptly_when_stop_is_set_during_a_stalled_reply():
    Trickle.where = "head"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api, stop, got = bench.Api(f"http://127.0.0.1:{srv.server_address[1]}", "k"), threading.Event(), []
    def call():
        try:
            api.get_json("/j", time.time() + 30, stop)
        except BaseException as e:
            got.append(e)
    t, t0 = threading.Thread(target=call), time.time()
    try:
        t.start(), time.sleep(0.3), stop.set(), t.join(5)  # without the fix the call waits out its 30 s deadline
        assert not t.is_alive() and time.time() - t0 < 2
        assert len(got) == 1 and isinstance(got[0], InterruptedError)
    finally:
        srv.shutdown()
