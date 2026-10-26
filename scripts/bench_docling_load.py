#!/usr/bin/env python3
"""Docling load script (spec 0022 S1): two concurrent clients over a fixed corpus.
(this layer: arguments, corpus, output guard and the HTTP client)
Results go to /data/ingestify-to-ai/benchmarks (customer data). API keys: env only.
"""
import argparse
import hashlib
import math
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ALLOWED_ROOT = "/data/ingestify-to-ai/benchmarks"
ROOT_DEVICE_PATH = "/"

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
