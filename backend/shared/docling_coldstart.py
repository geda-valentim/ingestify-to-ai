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
    rss_kb_max             highest current RSS seen at a child's shutdown, in KB
    peak_rss_kb            highest peak RSS (ru_maxrss, what --max-memory-per-child compares), KB
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


# Telemetry must never hold a conversion (or a pool child's start/exit) hostage to a
# hung Redis: its own client, with a short connect/socket timeout (the shared client
# waits up to 5 s per command). redis-py pools are fork-safe, but the cached client is
# keyed by PID anyway so a child never reuses its parent's sockets.
TELEMETRY_TIMEOUT_SECONDS = 0.5
_telemetry_client = None
_telemetry_client_pid = None


def _redis():
    """Short-timeout client for the writers (conversion path, pool signals)."""
    global _telemetry_client, _telemetry_client_pid
    if _telemetry_client is None or _telemetry_client_pid != os.getpid():
        import redis
        from shared.config import get_settings

        settings = get_settings()
        _telemetry_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
            socket_connect_timeout=TELEMETRY_TIMEOUT_SECONDS,
            socket_timeout=TELEMETRY_TIMEOUT_SECONDS,
        )
        _telemetry_client_pid = os.getpid()
    return _telemetry_client


def _redis_read():
    """Regular client for the readers (admin endpoint, monitoring task): they scan."""
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


def peak_rss_kb() -> Optional[int]:
    """Peak RSS of this process, in KB on Linux: what billiard compares with
    --max-memory-per-child (not the current RSS)."""
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return None


def record_process_shutdown() -> None:
    rss = current_rss_kb()
    peak = peak_rss_kb()
    ops: List[tuple] = [("i", "processes_stopped", 1)]
    if rss is not None:
        ops.append(("max", "rss_kb_max", rss))
    if peak is not None:
        ops.append(("max", "peak_rss_kb", peak))
    logger.info(f"docling.process_shutdown pid={os.getpid()} hostname={hostname()} rss_kb={rss} peak_rss_kb={peak}")
    _safe(ops)


class BuildTracker:
    """Why is this converter being built? State is per PID (a forked child starts clean).

    `peek` names the reason without recording anything; `commit` marks the key as built
    and is called only after the build succeeded, so a build that raises (CUDA OOM, say)
    does not turn its retry into a bogus `evicted`/`new_options`."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._pid = os.getpid()
        self._built_any = False
        self._seen: set = set()

    def peek(self, key) -> str:
        if self._pid != os.getpid():
            self.reset()
        if not self._built_any:
            return "process_start"
        return "evicted" if key in self._seen else "new_options"

    def commit(self, key) -> None:
        self._built_any = True
        self._seen.add(key)


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_hours(hours: int = 24, now: Optional[datetime] = None, client=None) -> List[Dict[str, Any]]:
    """Buckets of the last `hours` UTC hours (oldest first), one entry per worker."""
    client = client or _redis_read()
    now = now or datetime.now(timezone.utc)
    wanted = [hour_bucket(now - timedelta(hours=back)) for back in range(hours - 1, -1, -1)]
    by_bucket: Dict[str, set] = {b: set() for b in wanted}
    for key in client.scan_iter(match=f"{KEY_PREFIX}:*", count=1000):
        parts = key.split(":", 3)
        if len(parts) == 4 and parts[2] in by_bucket:
            by_bucket[parts[2]].add(key)

    rows: List[Dict[str, Any]] = []
    for bucket in wanted:
        start = datetime.strptime(bucket, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        for key in sorted(by_bucket[bucket]):
            data = client.hgetall(key)
            by_reason = {r: int(_num(data.get(f"cold:{r}"))) for r in REASONS}
            total = sum(by_reason.values())
            conversions = int(_num(data.get("conversions")))
            rss, peak = data.get("rss_kb_max"), data.get("peak_rss_kb")
            rows.append({
                "hour": start.isoformat(),
                "worker": key.split(":", 3)[3],
                "cold_starts": total,
                "by_reason": by_reason,
                "seconds_total": round(sum(_num(data.get(f"seconds:{r}")) for r in REASONS), 2),
                "processes_started": int(_num(data.get("processes_started"))),
                "processes_stopped": int(_num(data.get("processes_stopped"))),
                "rss_kb_max": int(_num(rss)) if rss is not None else None,
                "peak_rss_kb": int(_num(peak)) if peak is not None else None,
                "conversions": conversions,
                "cold_starts_per_100_conversions": round(100 * total / conversions, 2) if conversions else None,
            })
    return rows
