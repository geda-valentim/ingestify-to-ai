"""Docling load script tests against a fake server only (never a real API)."""
import csv
import importlib.util
import json
import os
import re
import signal
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/bench_docling_load.py"
if not SCRIPT.exists():
    pytest.skip("scripts/ not mounted (backend-only container)", allow_module_level=True)
spec = importlib.util.spec_from_file_location("bench_load", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

KEYS = {"key-a-secret": "A", "key-b-secret": "B", "key-admin-secret": "admin"}
PAGES = [[("processing", 0), ("pending", 0), ("pending", 0)], [("completed", 0), ("processing", 0), ("processing", 0)], [("completed", 0), ("completed", 1), ("failed", 1)]]

now = lambda: datetime.utcnow().isoformat()

class Fake(BaseHTTPRequestHandler):
    jobs, flags, projects, cold = {}, set(), {}, 0  # flags: dup, flap, stuck, slow, drop, cold_fail

    log_message = lambda self, *a: None

    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code), self.send_header("Content-Length", str(len(data))), self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if "drop" in Fake.flags:  # connection closed without an answer: the upload outcome is unknown
            return setattr(self, "close_connection", True)
        if KEYS.get(self.headers.get("X-API-Key")) not in ("A", "B"):
            return self.send(401, {})
        Fake.projects[KEYS[self.headers["X-API-Key"]]] = re.search(rb'name="project"\r\n\r\n(.*?)\r\n', body).group(1).decode()
        jid = str(uuid.uuid4())
        Fake.jobs[jid] = {"multi": b"MULTI" in body, "polls": 0, "created": now()}
        self.send(200, {"job_id": jid, "status": "queued", "created_at": Fake.jobs[jid]["created"], "duplicate": "dup" in Fake.flags})

    def do_GET(self):
        if self.path == "/admin/docling/cold-starts":
            Fake.cold += 1
            row = {"hour": "h", "worker": "w", "conversions": 10 if Fake.cold == 1 else 24, "peak_rss_kb": 100 * Fake.cold, "by_reason": {"process_start": Fake.cold}}
            return self.send(403, {}) if "cold_fail" in Fake.flags else self.send(200, {"rows": [row]})
        job = Fake.jobs[self.path.rsplit("/", 1)[1]]
        "slow" in Fake.flags and time.sleep(0.3)
        job["polls"] += 1
        p, multi = job["polls"], job["multi"]
        st = {"created_at": job["created"], "started_at": now(), "completed_at": None, "total_pages": 3 if multi else None,
              "status": "processing" if p < (3 if multi else 2) else ("partial" if multi else "completed")}
        if multi:
            st.update(pages_completed=2 * (p >= 3), pages_failed=int(p >= 3), pages=[
                {"page_number": i + 1, "status": s, "retry_count": r} for i, (s, r) in enumerate(PAGES[min(p, 3) - 1])])
        if "flap" in Fake.flags and multi:  # partial at poll 3, requeued at 4, completed from 5
            st["status"] = "processing" if p in (1, 2, 4) else "partial" if p == 3 else "completed"
        if "stuck" in Fake.flags:
            st["status"] = "processing"
        st["completed_at"] = now() if st["status"] in ("completed", "partial") else None
        self.send(200, st)

@pytest.fixture
def server():
    Fake.jobs, Fake.flags, Fake.cold = {}, set(), 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()

@pytest.fixture
def env(tmp_path, monkeypatch):
    corpus, root = tmp_path / "corpus", tmp_path / "bench"
    corpus.mkdir(), root.mkdir()
    (corpus / "a-single.pdf").write_bytes(b"%PDF- single")
    (corpus / "b-multi.pdf").write_bytes(b"%PDF- MULTI")
    monkeypatch.setattr(bench, "ALLOWED_ROOT", str(root))
    monkeypatch.setattr(bench, "ROOT_DEVICE_PATH", "/proc")  # another st_dev, like a mounted /data
    monkeypatch.setenv("BENCH_API_KEY_A", "key-a-secret")
    monkeypatch.setenv("BENCH_API_KEY_B", "key-b-secret")
    monkeypatch.setenv("BENCH_ADMIN_API_KEY", "key-admin-secret")
    return corpus, root

def argv(url, corpus, root, *extra):
    return ["--api-url", url, "--corpus", str(corpus), "--out-root", str(root / "runs"), "--label", "t",
            "--phase", "cold", "--repetition", "1", "--poll-interval", "0.01", "--partial-grace", "0", *extra]

def run(url, corpus, root, *extra, rc=0):
    assert bench.main(argv(url, corpus, root, *extra)) == rc
    (run_dir,) = (root / "runs").iterdir()
    return run_dir, [json.loads(x) for x in (run_dir / "jobs.jsonl").read_text().splitlines()]

def test_percentile_and_coldstart_delta():
    assert bench.percentile([], .5) is None and bench.percentile([4], .99) == 4
    assert bench.percentile([1, 2, 3, 4], .5) == 2.5
    row = lambda h, conv, rss, r=0: {"hour": h, "worker": "w", "conversions": conv, "peak_rss_kb": rss, "by_reason": {"process_start": r}}
    d = bench.coldstart_delta({"rows": [row("h1", 10, 500, 1), row("old", 5, 1)]}, {"rows": [row("h1", 14, 300, 3), row("h2", 7, 900, 2)]})
    assert d["delta"] == {"conversions": 11} and d["by_reason"] == {"process_start": 4}
    assert d["absolute_after"]["peak_rss_kb"] == 900 and d["dropped_keys"] == ["old|w"]

def test_end_to_end(server, env):
    run_dir, rows = run(server, *env)
    assert len(rows) == 4 and next(csv.reader(open(run_dir / "jobs.csv")))[:3] == ["client", "seq", "rel_path"]
    summary = json.loads((run_dir / "summary.json").read_text())
    for c in "AB":
        s = summary["by_client"][c]
        assert (s["n_jobs"], s["valid_pages"], s["page_retries"], s["partial"]) == (2, 3, 2, 1)
        assert s["wait_s"]["p95"] is not None and s["service_s"]["n"] == 2 and s["page_service_s"]["n"] == 2
    assert summary["all"]["valid_pages_per_min"] > 0 and summary["coldstarts_delta"]["delta"]["conversions"] == 14
    assert summary["foreign_conversions_estimate"] == 2  # 14 - (4 pages + 2 retries) per client
    assert summary["foreign_conversions_exact"] is False and "upper bound" in summary["foreign_conversions_note"]
    multi = next(r for r in rows if r["rel_path"] == "b-multi.pdf")
    assert multi["service_start_source"] == "first_page_processing_observed" and len(multi["pages"]) == 3
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["projects"] == Fake.projects and len(set(Fake.projects.values())) == 2  # a project per client: dedup is per user+project
    assert len(manifest["job_ids"]) == 4 and manifest["t_start"] and manifest["corpus"][0]["sha256"]
    for f in run_dir.iterdir():
        assert f.stat().st_mode & 0o777 == 0o600 and not any(k in f.read_text() for k in KEYS)
    assert run_dir.stat().st_mode & 0o777 == 0o700

def test_duplicate_is_excluded(server, env):
    Fake.flags = {"dup"}
    run_dir, rows = run(server, *env)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert {r["error"] for r in rows} == {"duplicate"} and summary["all"]["n_jobs"] == 0
    assert summary["foreign_conversions_estimate"] == 14  # duplicates convert nothing: all 14 are foreign

def test_keys_label_inflight_and_existing_run_dir(server, env, monkeypatch, capsys):
    corpus, root = env
    for value in ("key-a-secret", None, "bad\nsecret-key"):  # equal keys, missing key, key that is not a single token
        monkeypatch.setenv("BENCH_API_KEY_B", value) if value else monkeypatch.delenv("BENCH_API_KEY_B")
        assert bench.main(argv(server, corpus, root)) == 2
    assert "secret-key" not in capsys.readouterr().err  # the value is never echoed
    monkeypatch.setenv("BENCH_API_KEY_B", "key-b-secret")
    for extra in (["--label", "x/../../escape"], ["--label", ".."], ["--inflight", "2"], ["--poll-interval", "nan"],
                  ["--job-timeout", "0"], ["--partial-grace", "-1"], ["--partial-grace", "inf"]):
        with pytest.raises(SystemExit) as e:
            bench.main(argv(server, corpus, root) + extra)
        assert e.value.code == 2
    assert not (root / "runs").exists() and not (root.parent / "escape").exists()
    monkeypatch.setattr(bench, "datetime", type("F", (datetime,), {"now": classmethod(lambda c, tz=None: datetime(2026, 1, 1, tzinfo=tz))}))
    (root / "runs" / "20260101T000000Z-t-r1").mkdir(parents=True)  # a run dir is never overwritten
    assert bench.main(argv(server, corpus, root)) == 2

@pytest.mark.parametrize("flag,extra,statuses", [
    ("flap", ["--partial-grace", "0.05"], ["completed"] * 4),  # partial is not final until the grace passes
    ("stuck", ["--job-timeout", "0.05"], ["timeout", "timeout"]),  # timeout stops each client after one job
    ("stuck", ["--job-timeout", "0.3", "--poll-interval", "60"], ["timeout", "timeout"]),  # sleep capped at the deadline
    ("drop", [], ["error", "error"]),  # ambiguous upload failure (no answer): one attempt per client
    ("slow", ["--job-timeout", "0.1"], ["timeout", "timeout"])])  # 0.3 s answers vs a 0.1 s deadline bound
def test_failure_modes(server, env, flag, extra, statuses):
    Fake.flags, t0 = {flag}, time.time()
    run_dir, rows = run(server, *env, *extra, rc=int(flag == "drop"))  # nothing accepted: exit 1
    assert [r["status"] for r in rows] == statuses and time.time() - t0 < 5
    assert len((run_dir / "submitted.jsonl").read_text().splitlines()) == (0 if flag == "drop" else len(rows))

def test_upload_failure_has_terminal_time_and_interrupted_run_keeps_manifest(server, env, monkeypatch):
    corpus, root = env
    monkeypatch.setenv("BENCH_API_KEY_A", "unknown-key")
    real, calls = bench.write_json, []
    monkeypatch.setattr(bench, "write_json", lambda *a: real(*a) if not calls.append(1) and len(calls) == 1 else 1 / 0)  # dies after the first manifest
    with pytest.raises(ZeroDivisionError):
        bench.main(argv(server, corpus, root))
    (run_dir,) = (root / "runs").iterdir()
    rows = [json.loads(x) for x in (run_dir / "jobs.jsonl").read_text().splitlines()]
    assert all(r["observed_terminal_at"] for r in rows if r["client"] == "A") and len(rows) == 4
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["t_end"] is None and "MONITORING_AUTO_RETRY_ENABLED" in manifest["operator_note"]
    assert len((run_dir / "submitted.jsonl").read_text().splitlines()) == 2  # B's two jobs

def test_dead_client_thread_fails_the_run(server, env, monkeypatch):
    monkeypatch.setattr(bench, "run_client", lambda *a: 1 / 0)
    assert bench.main(argv(server, *env)) == 1
    (run_dir,) = (env[1] / "runs").iterdir()
    assert json.loads((run_dir / "manifest.json").read_text())["t_end"] is None  # incomplete run: manifest kept without t_end
    assert not list((env[1] / "runs").glob("*/summary.json"))  # and no summary

def test_ctrl_c_stops_both_clients_and_keeps_the_journal(server, env):
    Fake.flags = {"stuck"}
    old = signal.signal(signal.SIGINT, signal.default_int_handler)  # background runs may ignore SIGINT
    threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGINT)).start()  # a real signal wakes join()
    t0 = time.time()
    try:
        assert bench.main(argv(server, *env)) == 1 and time.time() - t0 < 5
    finally:
        signal.signal(signal.SIGINT, old)
    (run_dir,) = (env[1] / "runs").iterdir()
    rows = [json.loads(x) for x in (run_dir / "jobs.jsonl").read_text().splitlines()]
    assert sorted((r["client"], r["error"]) for r in rows) == [("A", "interrupted"), ("B", "interrupted")] and len((run_dir / "submitted.jsonl").read_text().splitlines()) == 2
    assert json.loads((run_dir / "manifest.json").read_text())["t_end"] is None

def test_project_name_over_the_api_limit_is_refused_before_any_artifact(server, env):
    assert bench.main(argv(server, *env, "--label", "x" * 80)) == 2 and not list((env[1] / "runs").glob("*"))

def test_failed_poll_keeps_the_last_snapshot(server, env, monkeypatch):
    real, multi = bench.Api.get_json, lambda path: Fake.jobs[path.rsplit("/", 1)[1]]
    flaky = lambda self, path, dl: 1 / 0 if multi(path)["multi"] and multi(path)["polls"] >= 2 else real(self, path, dl)
    monkeypatch.setattr(bench.Api, "get_json", flaky)
    rows = [r for r in run(server, *env)[1] if r["rel_path"] == "b-multi.pdf"]
    assert [(r["status"], r["total_pages"], r["pages_failed"]) for r in rows] == [("error", 3, 0)] * 2 and all(r["started_at"] for r in rows)

def test_errors_never_carry_a_key(server, env, monkeypatch):
    def leaky(self, *a):
        raise RuntimeError(f"Invalid header value {self.session.headers['X-API-Key']!r} / {self.secrets}")
    monkeypatch.setattr(bench.Api, "upload", leaky)
    run_dir, rows = run(server, *env, rc=1)
    assert {r["error"].startswith("upload: ") for r in rows} == {True}
    assert not any(k in f.read_text() for f in run_dir.iterdir() for k in KEYS)

def test_snapshot_failure_keeps_the_results(server, env):
    Fake.flags = {"cold_fail"}
    run_dir, rows = run(server, *env)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert len(rows) == 4 and "failed" in summary["coldstarts_delta"]["skipped"] and (run_dir / "jobs.csv").exists()
