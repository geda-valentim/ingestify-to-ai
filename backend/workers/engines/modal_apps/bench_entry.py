"""
The benchmark's ephemeral app (spec 0003, Appendix H): the production Whisper app
definition (whisper_app.py, built from INGESTIFY_MODAL_DEPLOY = the combination's
deploy spec) plus a local entrypoint, run by `modal run` - so Modal creates an
ephemeral app for exactly that decorator and stops it when the run ends or the
CLI interrupts it. Never deployed.

    INGESTIFY_MODAL_DEPLOY=<spec> INGESTIFY_MODAL_BENCH=<samples, E> \\
        python -m modal run -m workers.engines.modal_apps.bench_entry::bench

Each sample is sent E times at once (E inputs sharing one container when E > 1),
one sample after the other; the first input pays the cold start. Run by
workers/engines/benchmark.py in a subprocess with a from-scratch environment.
This file is not shipped into the image (the container imports whisper_app), so
it does not enter the deploy fingerprint.
"""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

from workers.engines.modal_apps import bench_protocol, protocol
from workers.engines.modal_apps.whisper_app import WhisperRunner, app


@app.local_entrypoint()
def bench():
    config = json.loads(os.environ[bench_protocol.BENCH_ENV])
    executions = int(config.get("executions") or 1)
    deadline_seconds = float(config.get("deadline_seconds") or 3600)
    started = time.time()
    print(bench_protocol.started_line(started), flush=True)
    runner = WhisperRunner()
    items, first, last = [], None, None
    for path in config["samples"]:
        media = Path(path).read_bytes()
        calls = []
        for _ in range(executions):
            request = protocol.build_request(attempt_key=str(uuid4()), media=media, suffix=Path(path).suffix.lower(),
                                             options=config.get('options', {}), deadline_unix=started + deadline_seconds)
            calls.append((time.time(), runner.transcribe.spawn(request)))
        for spawned, call in calls:
            result, usage = protocol.parse_response(call.get())
            ended = time.time()
            first = usage["exec_started_unix"] if first is None else min(first, usage["exec_started_unix"])
            last = usage["exec_ended_unix"] if last is None else max(last, usage["exec_ended_unix"])
            items.append({"media_seconds": result["duration"], "exec_seconds": usage["exec_seconds"],
                          "cold_start_seconds": usage["cold_start_seconds"], "wall_seconds": ended - spawned})
    window = (last - first) if first is not None and last is not None else 0.0
    print(bench_protocol.done_line(started, time.time(), window, items), flush=True)
