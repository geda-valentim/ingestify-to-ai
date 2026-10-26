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

class Trickle(BaseHTTPRequestHandler):  # a small JSON body (Content-Length) that arrives one byte at a time
    log_message = lambda self, *a: None

    def do_GET(self):
        body = b'{"status": "completed"}'
        self.send_response(200), self.send_header("Content-Length", str(len(body))), self.end_headers()
        try:
            for i in range(len(body)):
                self.wfile.write(body[i:i + 1]), self.wfile.flush(), time.sleep(0.4)
        except OSError:  # the client gave up
            pass

def test_get_json_never_outlives_the_deadline_on_a_trickling_body():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api, t0 = bench.Api(f"http://127.0.0.1:{srv.server_address[1]}", "k"), time.time()
    try:
        with pytest.raises(RuntimeError):
            api.get_json("/j", time.time() + 0.6)  # the whole body would take ~9 s; each read is within the socket timeout
        assert time.time() - t0 < 2 and api.http_retries >= 1
    finally:
        srv.shutdown()
