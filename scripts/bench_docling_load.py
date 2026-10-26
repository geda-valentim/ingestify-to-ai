#!/usr/bin/env python3
"""Docling load script (spec 0022 S1): two concurrent clients over a fixed corpus.
Results go to /data/ingestify-to-ai/benchmarks (customer data). API keys: env only.
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ALLOWED_ROOT = "/data/ingestify-to-ai/benchmarks"
ROOT_DEVICE_PATH = "/"
TERMINAL = {"completed", "failed", "partial", "cancelled"}
VALID_JOB = {"completed", "partial"}
JOB_FIELDS = ["client", "seq", "rel_path", "sha256", "job_id", "status", "duplicate", "error",
              "submitted_at", "created_at", "started_at", "completed_at", "observed_terminal_at",
              "total_pages", "pages_ok", "pages_failed", "page_retries", "wait_s",
              "service_s", "total_s", "service_start_source"]

class UsageError(Exception): pass

def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name, kw in [("--api-url", {"required": True}), ("--corpus", {"default": os.environ.get("BENCH_CORPUS_DIR")}),
                     ("--out-root", {"default": ALLOWED_ROOT + "/runs"}), ("--label", {"required": True}),
                     ("--phase", {"required": True, "choices": ["cold", "warm"]}),
                     ("--repetition", {"required": True, "type": int}), ("--seed", {"type": int, "default": 22}),
                     ("--inflight", {"type": int, "default": 1}), ("--poll-interval", {"type": float, "default": .5}),
                     ("--job-timeout", {"type": float, "default": 3600}),
                     ("--partial-grace", {"type": float, "default": 120})]:
        p.add_argument(name, **kw)
    a = p.parse_args(argv)
    # --inflight > 1 would let the synchronous upload stall the polling of jobs in flight
    ok = lambda lo, *vs: all(math.isfinite(v) and v > lo for v in vs)
    if (a.repetition < 1 or a.inflight != 1 or not re.fullmatch(r"[A-Za-z0-9._-]+", a.label) or a.label in (".", "..")
            or not ok(0, a.poll_interval, a.job_timeout) or not ok(-1e-9, a.partial_grace)):
        p.error("need --repetition >= 1, --inflight 1, --label [A-Za-z0-9._-]+, finite positive --poll-interval/--job-timeout, finite --partial-grace >= 0")
    return a

def load_corpus(directory):
    root = Path(directory or "/nonexistent")
    if not root.is_dir() or not any(root.rglob("*.pdf")):
        raise UsageError(f"corpus not found or without *.pdf: {directory!r}. Set --corpus or BENCH_CORPUS_DIR; "
                         "the corpus holds customer data and needs the authorization recorded in spec 0022 S1")
    files = sorted(root.rglob("*.pdf"), key=lambda x: x.relative_to(root).as_posix())
    return [{"rel_path": f.relative_to(root).as_posix(), "path": str(f), "size": f.stat().st_size,
             "sha256": hashlib.sha256(f.read_bytes()).hexdigest()} for f in files]

def check_output_root(path):
    real, allowed = os.path.realpath(path), os.path.realpath(ALLOWED_ROOT)
    if real != allowed and not real.startswith(allowed + os.sep):
        raise UsageError(f"output {real} is outside {allowed}")
    probe = real
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    if os.stat(probe).st_dev == os.stat(ROOT_DEVICE_PATH).st_dev:
        raise UsageError(f"{probe} is on the system disk (is /data mounted?)")
    return real

def client_order(files, seed, client, rep):
    order = list(files)
    random.Random(f"{seed}|{client}|{rep}").shuffle(order)
    return order

def epoch(iso):
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")) if iso else None
    return dt and (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()

def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None

class Api:
    def __init__(self, base, key, secrets=()):
        self.base, self.session, self.http_retries, self.secrets = base.rstrip("/"), requests.Session(), 0, (key, *secrets)
        self.session.headers["X-API-Key"] = key

    def redact(self, text):  # errors reach jobs.jsonl: no key value may go with them
        for k in self.secrets:
            text = str(text).replace(k, "***")
        return str(text)

    def get_json(self, path, deadline):  # every wait is bounded by the job deadline
        for attempt in range(3):
            left = deadline - time.time()
            if left <= 0:
                break
            box, done = {}, threading.Event()  # the worker writes only to its own box; only this caller records anything
            threading.Thread(target=self._attempt, args=(path, min(60, left), box, done), daemon=True).start()
            if not done.wait(left):  # a socket timeout alone lets a server that trickles headers or body hold us: abandon the worker
                r = box.get("r")  # close() waits for the reader's buffer lock, so it never runs in the caller
                r is None or threading.Thread(target=r.close, daemon=True).start()
            elif "json" in box:
                return box["json"]
            elif box.get("exc") and not isinstance(box["exc"], (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)):
                raise box["exc"]  # a bad body is the server's answer, not a transport failure
            self.http_retries += 1
            time.sleep(max(0, min(0.2 * 2 ** attempt, deadline - time.time())))
        raise RuntimeError(f"GET {path} failed (3 attempts or deadline)")

    def _attempt(self, path, timeout, box, done):  # GET + full body read + JSON parse
        try:
            with self.session.get(self.base + path, timeout=timeout, stream=True) as r:
                box["r"] = r
                if r.status_code < 500 and r.status_code != 429:
                    r.raise_for_status()
                    box["json"] = r.json()
        except Exception as e:
            box["exc"] = e
        finally:
            done.set()

    def upload(self, rec_path, project):
        r = self.session.post(self.base + "/upload", files={"file": open(rec_path, "rb")},
                              data={"project": project, "docling_preset": "fast"}, timeout=300)
        r.raise_for_status()
        return r.json()

def observe(state, status_json, now):  # page transitions seen at poll time (+-poll interval)
    for page in status_json.get("pages") or []:
        st = state["pages"].setdefault(page["page_number"], {"n": page["page_number"]})
        st["status"], st["retry_count"] = page.get("status"), page.get("retry_count") or 0
        if page.get("status") == "processing":
            st.setdefault("first_processing_at", now)
        if page.get("status") == "completed":
            st.setdefault("first_completed_at", now)

def job_metrics(rec, pages, status_json):
    created, started, completed = epoch(rec["created_at"]), epoch(rec["started_at"]), epoch(rec["completed_at"])
    multi = (rec["total_pages"] or 1) > 1
    seen = [p["first_processing_at"] for p in pages if p.get("first_processing_at")]
    start, rec["service_start_source"] = (min(seen), "first_page_processing_observed") if multi and seen else (started, "main_started_at")
    sub = lambda a, b: round(a - b, 4) if a is not None and b is not None else None
    rec["wait_s"], rec["service_s"], rec["total_s"] = sub(start, created), sub(completed, start), sub(completed, created)
    for p in pages:
        p["wait_s"] = sub(p.get("first_processing_at"), created)
        p["service_s"] = sub(p.get("first_completed_at"), p.get("first_processing_at"))
    rec["pages"] = pages
    rec["page_retries"] = sum(p["retry_count"] for p in pages)
    rec["pages_ok"] = ((status_json.get("pages_completed") or 0) if multi else int(rec["status"] == "completed")) if rec["status"] in VALID_JOB else 0

def run_client(client, api, files, args, project, barrier, out, lock):
    barrier.wait()
    for seq, f in enumerate(client_order(files, args.seed, client, args.repetition), 1):  # one job at a time
        if out["stop"].is_set():
            break
        rec, stop = {k: None for k in JOB_FIELDS}, False
        rec.update(client=client, seq=seq, rel_path=f["rel_path"], sha256=f["sha256"], duplicate=False,
                   submitted_at=iso(time.time()), page_retries=0, pages_ok=0, pages_failed=0)
        try:
            created = api.upload(f["path"], project)
            rec["job_id"], rec["created_at"] = created["job_id"], created["created_at"]
            if created.get("duplicate"):
                rec.update(duplicate=True, status="error", error="duplicate")
        except Exception as e:  # upload has no retry: the failure is the job's
            rec.update(status="error", error=api.redact(f"upload: {e}"))
            # anything but a 4xx answer is ambiguous: the job may exist and still run, so stop this client
            stop = not (isinstance(e, requests.HTTPError) and e.response.status_code < 500)
        if rec["status"] == "error":
            rec["observed_terminal_at"] = iso(time.time())
            emit(rec, out, lock)
            if stop:
                break
            continue
        emit({"client": client, "seq": seq, "job_id": rec["job_id"]}, out, lock, "journal")
        job, t0 = {"pages": {}}, time.time()
        deadline = t0 + args.job_timeout
        while True:
            out["stop"].wait(min(args.poll_interval, max(0, deadline - time.time())))  # never sleep past the deadline
            try:
                if out["stop"].is_set():
                    raise InterruptedError("interrupted")
                js, now = api.get_json(f"/jobs/{rec['job_id']}", deadline), time.time()
                observe(job, js, now)
                sig = (js["status"], js.get("pages_completed"), js.get("pages_failed"),
                       [(q["status"], q["retry_count"]) for q in js.get("pages") or []])
                if sig != job.get("sig"):
                    job["sig"], job["sig_at"] = sig, now
                # partial is final only after --partial-grace s unchanged: auto-retry may requeue pages
                done = js["status"] in TERMINAL and (js["status"] != "partial" or now - job["sig_at"] >= args.partial_grace)
                job["last"] = js  # validated: it survives a failed poll
            except Exception as e:
                js, now, done, rec["error"] = {**job.get("last", {}), "status": "error"}, time.time(), True, api.redact(e)
            if now > deadline:  # also a terminal answer that arrives after the deadline
                js, done, rec["error"] = {**js, "status": "timeout"}, True, "timeout"
            if done:
                break
        rec.update(status=js.get("status", "error"), started_at=js.get("started_at"),
                   completed_at=js.get("completed_at"), total_pages=js.get("total_pages"),
                   pages_failed=js.get("pages_failed") or 0, observed_terminal_at=iso(now),
                   error=rec["error"] or js.get("error"))
        job_metrics(rec, sorted(job["pages"].values(), key=lambda p: p["n"]), js)
        emit(rec, out, lock)
        if rec["error"] and rec["status"] in ("timeout", "error"):
            break  # the job may still run in the backend: stop submitting, never overlap jobs

def guard(done, fn, *a):  # is_alive()/join() lie after SIGINT on 3.10-3.12: this event is the only proof a client ended
    try:
        fn(*a)
    finally:
        done.set()

def emit(rec, out, lock, kind="jsonl"):
    with lock:
        if kind == "jsonl":
            out["records"].append(rec)
        out[kind].write(json.dumps(rec, default=str) + "\n")
        out[kind].flush()

def new_file(path, **kw):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", **kw)

def write_json(path, obj):  # atomic, so a crash never leaves a half-written file
    with new_file(path + ".tmp") as fh:
        json.dump(obj, fh, indent=2, default=str)
    os.replace(path + ".tmp", path)

def main(argv=None):
    args = parse_args(argv)
    try:
        keys = {c: os.environ.get(f"BENCH_API_KEY_{c}") for c in "AB"}
        # single printable token: requests echoes an invalid header value in its error, and errors reach the disk
        if not all(re.fullmatch(r"[\x21-\x7e]+", v or "") for v in keys.values()) or keys["A"] == keys["B"]:
            raise UsageError("set BENCH_API_KEY_A and BENCH_API_KEY_B (two different single-token keys; values are never shown)")
        files = load_corpus(args.corpus)
        t_start = datetime.now(timezone.utc)
        run_id = f"{t_start:%Y%m%dT%H%M%SZ}-{args.label}-r{args.repetition}"
        projects = {c: f"bench-0022-{run_id}-{c}" for c in "AB"}  # dedup is per user+project: one project per client
        if any(len(n) > 100 for n in projects.values()):  # the API's MAX_NAME_LENGTH (shared/projects.py); charset is label-safe
            raise UsageError(f"project name {projects['A']!r} exceeds 100 characters: use a shorter --label")
        run_dir = check_output_root(os.path.join(check_output_root(args.out_root), run_id))
        if os.path.exists(run_dir):
            raise UsageError(f"{run_dir} already exists; runs are never overwritten")
        os.makedirs(run_dir, mode=0o700)
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    manifest = {"run_id": run_id, "args": vars(args), "projects": projects,
                "t_start": t_start.isoformat(), "t_end": None,
                "operator_note": "set MONITORING_AUTO_RETRY_ENABLED=false on the API/workers during the run",
                "corpus": [{k: f[k] for k in ("rel_path", "size", "sha256")} for f in files],
                "job_ids": "see submitted.jsonl (journal, written at upload) until the run ends"}
    write_json(os.path.join(run_dir, "manifest.json"), manifest)
    jsonl, journal = (new_file(os.path.join(run_dir, n)) for n in ("jobs.jsonl", "submitted.jsonl"))
    out = {"records": [], "jsonl": jsonl, "journal": journal, "stop": threading.Event()}
    barrier, lock, apis = threading.Barrier(2), threading.Lock(), {c: Api(args.api_url, keys[c], keys.values()) for c in "AB"}
    t_run = time.time()
    errors, old_hook = [], threading.excepthook
    threading.excepthook = lambda a: errors.append(a.exc_value)  # join() does not propagate a dead client
    done = {c: threading.Event() for c in "AB"}
    threads = [threading.Thread(target=guard, args=(done[c], run_client, c, apis[c], files, args, projects[c], barrier, out, lock)) for c in "AB"]
    [t.start() for t in threads]
    while not all(e.is_set() for e in done.values()):
        try:
            [e.wait(0.5) for e in done.values()]
        except KeyboardInterrupt:  # stop both clients, keep waiting until they really end, exit non-zero
            out["stop"].set()
            errors.append(KeyboardInterrupt())
    [t.join() for t in threads]
    threading.excepthook, t_end, _ = old_hook, time.time(), (jsonl.close(), journal.close())
    if errors:
        print(f"error: run incomplete, a client died or Ctrl-C: {errors[0]!r} (manifest kept without t_end)", file=sys.stderr)
        return 1
    if not any(r["job_id"] for r in out["records"]):  # nothing was benchmarked: never look successful
        print("error: no job was accepted by the API (manifest kept without t_end)", file=sys.stderr)
        return 1
    manifest.update(t_end=iso(t_end), job_ids=[r["job_id"] for r in out["records"] if r["job_id"]])
    write_json(os.path.join(run_dir, "manifest.json"), manifest)
    print(run_dir)
    return 0

if __name__ == "__main__":
    sys.exit(main())
