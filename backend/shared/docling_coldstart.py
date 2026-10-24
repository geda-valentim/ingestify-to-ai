"""
Docling cold-start telemetry.

Every DoclingConverter build loads the layout/table weights (CUDA init included,
~10 s on the GPU worker). This module classifies why a build happened, logs it, and
keeps an hourly per-worker aggregate in Redis so `GET /admin/docling/cold-starts` and
`workers.monitoring.check_docling_cold_starts` can tell a healthy worker from one
that is being recycled (`--max-memory-per-child`) or thrashing its converter cache.

CONTRACT: pure observability. Redis is a TTL cache (see shared/redis_client.py): every
key expires after COLDSTART_TTL_SECONDS, and every failure here is swallowed - a Redis
outage must never break a conversion.

Key (HASH, one per UTC hour and worker hostname):
    docling:coldstart:{YYYYMMDDHH}:{hostname}
Fields:
    cold:{reason}          count of converter builds (process_start|new_options|evicted)
    seconds:{reason}       summed build seconds (float)
    processes_started      pool children started (worker_process_init)
    processes_stopped      pool children that exited (worker_process_shutdown)
    rss_kb_max             highest RSS seen at a child's shutdown, in KB
    conversions            get_converter() calls = converter requests (one per page job)
"""

import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY_PREFIX = "docling:coldstart"
COLDSTART_TTL_SECONDS = 48 * 3600
REASONS = ("process_start", "new_options", "evicted")

_WARN_EVERY_SECONDS = 60.0
_last_warn = 0.0


def hostname() -> str:
    return socket.gethostname()


def hour_bucket(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H")


def key_for(bucket: str, host: str) -> str:
    return f"{KEY_PREFIX}:{bucket}:{host}"


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client().client


def _warn_throttled(message: str, exc: Exception) -> None:
    global _last_warn
    now = time.monotonic()
    if now - _last_warn >= _WARN_EVERY_SECONDS:
        _last_warn = now
        logger.warning(f"{message}: {exc!r}")
    else:
        logger.debug(f"{message}: {exc!r}")


def _write(client, field_ops: List[tuple]) -> None:
    """field_ops: ("i", field, int) -> HINCRBY, ("f", field, float) -> HINCRBYFLOAT,
    ("max", field, int) -> keep the larger value (shutdown only, so not atomic)."""
    key = key_for(hour_bucket(), hostname())
    pipe = client.pipeline()
    for kind, field, value in field_ops:
        if kind == "i":
            pipe.hincrby(key, field, value)
        elif kind == "f":
            pipe.hincrbyfloat(key, field, value)
    pipe.expire(key, COLDSTART_TTL_SECONDS)
    pipe.execute()
    for kind, field, value in field_ops:
        if kind == "max":
            current = client.hget(key, field)
            if current is None or int(float(current)) < value:
                client.hset(key, field, value)


def _safe(field_ops: List[tuple]) -> None:
    try:
        _write(_redis(), field_ops)
    except Exception as exc:  # never break a conversion over telemetry
        _warn_throttled("docling coldstart telemetry not recorded", exc)


def record_cold_start(reason: str, seconds: float, cache_size: int) -> None:
    logger.info(
        f"docling.cold_start reason={reason} seconds={seconds:.2f} pid={os.getpid()} "
        f"hostname={hostname()} cache_size={cache_size}"
    )
    _safe([("i", f"cold:{reason}", 1), ("f", f"seconds:{reason}", float(seconds))])


def record_conversion_request() -> None:
    _safe([("i", "conversions", 1)])


def record_process_start() -> None:
    _safe([("i", "processes_started", 1)])


def current_rss_kb() -> Optional[int]:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)  # peak, KB on Linux
    except Exception:
        return None


def record_process_shutdown() -> None:
    rss = current_rss_kb()
    ops: List[tuple] = [("i", "processes_stopped", 1)]
    if rss is not None:
        ops.append(("max", "rss_kb_max", rss))
        logger.info(f"docling.process_shutdown pid={os.getpid()} hostname={hostname()} rss_kb={rss}")
    _safe(ops)


class BuildTracker:
    """Why is this converter being built? State is per PID (a forked child starts clean)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._pid = os.getpid()
        self._built_any = False
        self._seen: set = set()

    def classify(self, key) -> str:
        if self._pid != os.getpid():
            self.reset()
        if not self._built_any:
            reason = "process_start"
        elif key in self._seen:
            reason = "evicted"
        else:
            reason = "new_options"
        self._built_any = True
        self._seen.add(key)
        return reason


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_hours(hours: int = 24, now: Optional[datetime] = None, client=None) -> List[Dict[str, Any]]:
    """Buckets of the last `hours` UTC hours (oldest first), one entry per worker."""
    client = client or _redis()
    now = now or datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for back in range(hours - 1, -1, -1):
        bucket = hour_bucket(now - timedelta(hours=back))
        start = datetime.strptime(bucket, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        for key in sorted(client.scan_iter(match=f"{KEY_PREFIX}:{bucket}:*", count=200)):
            data = client.hgetall(key)
            by_reason = {r: int(_num(data.get(f"cold:{r}"))) for r in REASONS}
            total = sum(by_reason.values())
            conversions = int(_num(data.get("conversions")))
            rss = data.get("rss_kb_max")
            rows.append({
                "hour": start.isoformat(),
                "worker": key.split(":", 3)[3],
                "cold_starts": total,
                "by_reason": by_reason,
                "seconds_total": round(sum(_num(data.get(f"seconds:{r}")) for r in REASONS), 2),
                "processes_started": int(_num(data.get("processes_started"))),
                "processes_stopped": int(_num(data.get("processes_stopped"))),
                "rss_kb_max": int(_num(rss)) if rss is not None else None,
                "conversions": conversions,
                "cold_starts_per_100_conversions": round(100 * total / conversions, 2) if conversions else None,
            })
    return rows
