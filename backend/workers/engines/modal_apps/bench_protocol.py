"""
What the benchmark CLI and its ephemeral Modal app say to each other (spec 0003,
Appendix H). Standard library only: the CLI side must not import `modal`.

The CLI starts `modal run -m workers.engines.modal_apps.bench_entry::bench` with
BENCH_ENV = {"samples": [paths], "executions": E, "deadline_seconds": s}. The
entrypoint prints one STARTED line once the app is up (the GPU deadline counts
from there), then one RESULT line:

    INGESTIFY_BENCH {"event": "done", "started": unix, "ended": unix,
                     "window_seconds": s, "items": [{media_seconds, exec_seconds,
                     cold_start_seconds, wall_seconds}, ...]}

Not part of the deployed app's files: changing this never changes a fingerprint.
"""

import json
from typing import Any, Dict, Optional

BENCH_ENV = "INGESTIFY_MODAL_BENCH"
PREFIX = "INGESTIFY_BENCH "
STARTED = PREFIX + '{"event": "started"'
ITEM_FIELDS = ("media_seconds", "exec_seconds", "cold_start_seconds", "wall_seconds")


def started_line(at: float) -> str:
    return PREFIX + json.dumps({"event": "started", "at": at})


def done_line(started: float, ended: float, window_seconds: float, items) -> str:
    return PREFIX + json.dumps({"event": "done", "started": started, "ended": ended,
                                "window_seconds": window_seconds, "items": list(items)})


def parse_output(output: str) -> Optional[Dict[str, Any]]:
    """The `done` record of a benchmark run's output, validated; None when it never finished"""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith(PREFIX):
            continue
        try:
            record = json.loads(line[len(PREFIX):])
        except ValueError:
            continue
        if record.get("event") != "done":
            continue
        items = []
        for raw in record.get("items") or []:
            if not isinstance(raw, dict):
                return None
            try:
                items.append({k: max(float(raw.get(k) or 0.0), 0.0) for k in ITEM_FIELDS})
            except (TypeError, ValueError):
                return None
        try:
            return {"started": float(record["started"]), "ended": float(record["ended"]),
                    "window_seconds": max(float(record.get("window_seconds") or 0.0), 0.0), "items": items}
        except (KeyError, TypeError, ValueError):
            return None
    return None
