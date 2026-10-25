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
    recycle:{reason}       why a child exited: memory_limit (exitcode 155 and peak RSS above
                           --max-memory-per-child) | max_tasks (155 otherwise, with a task limit) |
                           shutdown (exitcode 0 or a signal handler) | unknown (anything else)
    last_exitcode          exitcode of the last child that exited, as billiard reported it
    max_memory_per_child_kb|max_tasks_per_child   the limits the worker runs with (0/unset: absent)
    processes_vanished     children that disappeared without running worker_process_shutdown
                           (SIGKILL: cgroup OOM, hard time limit, docker kill). Seen by the next child
                           to start, through the registry below, so counted a few seconds late
    cgroup_oom_kill        memory.events oom_kill of the container's cgroup, absolute (compare hour
                           with hour: it resets when the cgroup is recreated)
    cgroup_memory_peak_kb|cgroup_memory_max_kb   memory.peak (max seen) and memory.max of the cgroup
    rss_kb_max             highest current RSS seen at a child's shutdown, in KB
    peak_rss_kb            highest peak RSS (ru_maxrss, what --max-memory-per-child compares), KB
    conversions            get_converter() calls = converter requests (one per page job)
    conv:first|conv:warm   convert() calls, split by the converter's first call in this process
                           (weights load inside it) vs later ones; failed calls included. Differs
                           from `conversions` when convert() never runs (missing file, no Docling)
    conv_seconds:first|warm  summed convert() seconds of those calls (the export to markdown is out)
    conv:first_process     convert() calls that were the first of the whole pool child
    conv:failed            convert() calls that raised
    wrapper_seconds:{reason}  build seconds without the pipeline load (== seconds:{reason} when
                           DOCLING_INIT_PIPELINE is off)
    pipeline_init_seconds:{reason}  seconds of initialize_pipeline (DOCLING_INIT_PIPELINE on only)
    pipeline_init:{ok|failed|unavailable}  count of those loads, by outcome (flag on only)
    pages_ok|pages_failed  pages converted / not converted (PARTIAL_SUCCESS counts the pages whose
                           backend failed to open; a document_timeout partial would show 0 failed)
    docling_version        installed docling, written by the last writer

Child registry (HASH, per worker hostname, same TTL; deliberately outside KEY_PREFIX so the
reader's scan does not see it):
    docling:children:{hostname}    pid -> /proc starttime of each live pool child
A clean shutdown removes its own pid. If Redis was down at that moment the next start counts
one false "vanished"; the registry is observability, not a source of truth.
"""

import functools
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
RECYCLE_REASONS = ("memory_limit", "max_tasks", "shutdown", "unknown")
CHILDREN_PREFIX = "docling:children"
CGROUP_ROOT = "/sys/fs/cgroup"
try:  # billiard returns this exitcode for both --max-memory-per-child and --max-tasks-per-child
    from billiard.pool import EX_RECYCLE
except Exception:  # pragma: no cover - billiard is always there under celery
    EX_RECYCLE = 0x9B

# The pool limits, recorded by the parent (worker_init) before it forks: children inherit them.
_limits: Dict[str, Optional[int]] = {"max_memory_kb": None, "max_tasks": None}

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


def _write(client, field_ops: List[tuple], extra=None) -> None:
    """field_ops: ("i", field, int) -> HINCRBY, ("f", field, float) -> HINCRBYFLOAT,
    ("set", field, value) -> HSET, ("max", field, int) -> keep the larger value (shutdown only, so not atomic)."""
    key = key_for(hour_bucket(), hostname())
    pipe = client.pipeline()
    if extra is not None:
        extra(pipe)
    for kind, field, value in field_ops:
        if kind == "i":
            pipe.hincrby(key, field, value)
        elif kind == "f":
            pipe.hincrbyfloat(key, field, value)
        elif kind == "set":
            pipe.hset(key, field, value)
    pipe.expire(key, COLDSTART_TTL_SECONDS)
    pipe.execute()
    for kind, field, value in field_ops:
        if kind == "max":
            current = client.hget(key, field)
            if current is None or int(float(current)) < value:
                client.hset(key, field, value)


# Circuit breaker: after a failed write the writers skip Redis for this long, so a hung
# Redis costs one 0.5 s timeout per window instead of one or two per page. Per PID.
_BREAKER_SECONDS = 30.0
_skip_until = 0.0
_skip_pid = None


def _guarded(fn) -> None:
    """Run fn(client) behind the breaker; any failure is swallowed and arms it."""
    global _skip_until, _skip_pid
    if _skip_pid != os.getpid():
        _skip_until, _skip_pid = 0.0, os.getpid()
    if time.monotonic() < _skip_until:
        return
    try:
        fn(_redis())
    except Exception as exc:  # never break a conversion over telemetry
        _skip_until = time.monotonic() + _BREAKER_SECONDS
        _warn_throttled("docling coldstart telemetry not recorded", exc)


def _safe(field_ops: List[tuple], extra=None) -> None:
    _guarded(lambda client: _write(client, field_ops, extra))


def record_cold_start(reason: str, seconds: float, cache_size: int, wrapper_seconds: Optional[float] = None,
                      pipeline_init_seconds: Optional[float] = None, pipeline_init: str = "off") -> None:
    """`seconds` is the whole build; with DOCLING_INIT_PIPELINE on it includes the weight load."""
    def fmt(v):
        return "none" if v is None else f"{v:.2f}"

    logger.info(
        f"docling.cold_start reason={reason} seconds={seconds:.2f} wrapper_seconds={fmt(wrapper_seconds)} "
        f"pipeline_init_seconds={fmt(pipeline_init_seconds)} pipeline_init={pipeline_init} "
        f"pid={os.getpid()} hostname={hostname()} cache_size={cache_size}"
    )
    ops = [("i", f"cold:{reason}", 1), ("f", f"seconds:{reason}", float(seconds))]
    if wrapper_seconds is not None:
        ops.append(("f", f"wrapper_seconds:{reason}", float(wrapper_seconds)))
    if pipeline_init != "off":
        ops.append(("i", f"pipeline_init:{pipeline_init}", 1))
        if pipeline_init_seconds is not None:
            ops.append(("f", f"pipeline_init_seconds:{reason}", float(pipeline_init_seconds)))
    _safe(ops)


def record_conversion_request() -> None:
    _safe([("i", "conversions", 1)])


@functools.lru_cache(maxsize=1)
def docling_version() -> str:
    try:
        from importlib.metadata import version

        return version("docling")
    except Exception:
        return "unknown"


def label_converter(converter, key: tuple, reason: str) -> None:
    """Hang cheap labels on a converter at build time, so the hot path computes none."""
    try:
        ocr, tables, images, pictures = (int(bool(v)) for v in (tuple(key) + (False,) * 4)[:4])
        converter.telemetry = {"key": f"ocr{ocr}-tab{tables}-img{images}-pic{pictures}", "build_reason": reason}
    except Exception:  # an object that takes no attributes just reports key=uncached
        pass


_process_converted_pid = None


def _value(obj: Any) -> Any:
    return getattr(obj, "value", obj)


def record_conversion(conv, seconds: float, result, fmt: str, probe: bool = False) -> None:
    """One docling.conversion log line and the hourly counters for one convert() call.

    `result` is the docling ConversionResult, or None when convert() raised (a PDF that
    reaches convert() is one page: the split comes first). Never raises. With `probe`
    only the log line is emitted; the first-call flags still flip, they are physical."""
    global _process_converted_pid
    try:
        pid = os.getpid()
        first_key = getattr(conv, "_converted_pid", None) != pid
        first_process = _process_converted_pid != pid
        conv._converted_pid = _process_converted_pid = pid
        labels = getattr(conv, "telemetry", None) or {"key": "uncached", "build_reason": "none"}

        if result is None:
            outcome, pages, ok, failed = "failed", 1, 0, 1
        else:
            status = str(_value(getattr(result, "status", None)))
            pages = int(getattr(getattr(result, "input", None), "page_count", 0) or 1)
            bad = 0
            if status == "partial_success":
                bad = min(pages, sum(
                    1 for e in (getattr(result, "errors", None) or [])
                    if _value(getattr(e, "component_type", None)) == "document_backend"
                ))
            outcome = "partial" if status == "partial_success" else "ok"
            ok, failed = pages - bad, bad
        version = docling_version()
        logger.info(
            f"docling.conversion result={outcome} first_process={str(first_process).lower()} "
            f"first_key={str(first_key).lower()} build_reason={labels['build_reason']} "
            f"seconds={seconds:.2f} pages={'unknown' if result is None else pages} pages_ok={ok} "
            f"pages_failed={failed} key={labels['key']} accelerator={getattr(conv, 'accelerator', 'default')} "
            f"docling={version} format={fmt} probe={str(probe).lower()} pid={pid} hostname={hostname()}"
        )
        if probe:
            return
        warmth = "first" if first_key else "warm"
        ops: List[tuple] = [
            ("i", f"conv:{warmth}", 1), ("f", f"conv_seconds:{warmth}", float(seconds)),
            ("i", "pages_ok", ok), ("i", "pages_failed", failed), ("set", "docling_version", version),
        ]
        if first_process:
            ops.append(("i", "conv:first_process", 1))
        if result is None:
            ops.append(("i", "conv:failed", 1))
        # keep the child registry alive while the worker converts: same pipeline, no round trip
        _safe(ops, extra=_register_self)
    except Exception as exc:
        _warn_throttled("docling conversion telemetry not recorded", exc)


def set_recycle_limits(max_memory_kb, max_tasks) -> None:
    """Remember the pool limits (parent, before the fork). 0, empty or None mean no limit."""
    for name, value in (("max_memory_kb", max_memory_kb), ("max_tasks", max_tasks)):
        try:
            _limits[name] = int(value) or None
        except (TypeError, ValueError):
            _limits[name] = None


def classify_exit(exitcode, peak_kb, max_memory_kb, max_tasks) -> str:
    """Why did a pool child exit? billiard returns 155 for a memory and for a task recycle and
    checks memory first, so a peak above the memory limit settles it."""
    if exitcode == EX_RECYCLE:
        if max_memory_kb and peak_kb is not None and peak_kb > max_memory_kb:
            return "memory_limit"
        if max_tasks:
            return "max_tasks"
        return "unknown"
    if exitcode == 0 or (isinstance(exitcode, int) and exitcode < 0):
        return "shutdown"  # sentinel at warm shutdown, or billiard's signal handler (-(256-signum))
    return "unknown"


def _proc_start_time(pid) -> Optional[str]:
    """Field 22 of /proc/{pid}/stat: tells a live process from a reused pid. Never raises."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[19]
    except Exception:
        return None


def _read_int(path: str) -> Optional[int]:
    try:
        with open(path) as fh:
            raw = fh.read().strip()
        return int(raw) if raw != "max" else None
    except Exception:
        return None


def _cgroup_memory() -> Dict[str, int]:
    """oom_kill, peak and max (KB) of this container's cgroup v2; absent fields are left out."""
    out: Dict[str, int] = {}
    try:
        with open(f"{CGROUP_ROOT}/memory.events") as fh:
            for line in fh:
                name, _, value = line.partition(" ")
                if name == "oom_kill":
                    out["oom_kill"] = int(value)
    except Exception:
        pass
    for field, name in (("peak_kb", "memory.peak"), ("max_kb", "memory.max")):
        value = _read_int(f"{CGROUP_ROOT}/{name}")
        if value is not None:
            out[field] = value // 1024
    return out


def _children_key() -> str:
    return f"{CHILDREN_PREFIX}:{hostname()}"


_own_start: Dict[int, Optional[str]] = {}


def _register_self(pipe) -> None:
    """Queue our registry entry (re-created if the key expired or was evicted) and its TTL on a
    transactional pipeline: HSET and EXPIRE go together, so the key never lives without a TTL."""
    pid = os.getpid()
    if pid not in _own_start:
        _own_start.clear()
        _own_start[pid] = _proc_start_time(pid)
    key, started = _children_key(), _own_start[pid]
    if started is not None:
        pipe.hset(key, str(pid), started)
    pipe.expire(key, COLDSTART_TTL_SECONDS)


def record_process_start() -> None:
    """A pool child started. It also notices the siblings that vanished without a shutdown
    (SIGKILL never runs worker_process_shutdown): registered pids whose /proc starttime
    changed. The parent has no public hook for that, but its replacement always comes after."""
    me = os.getpid()
    cgroup = _cgroup_memory()
    seen: Dict[str, Any] = {}

    def work(client) -> None:
        import redis

        key = _children_key()
        mine = _proc_start_time(me)
        removed: List[str] = []
        # Optimistic transaction: the registry is read and the stale entries are deleted in one
        # MULTI, retried if another child touched it in between. So a stale entry is claimed by exactly one child, and a live entry another child
        # just wrote is never deleted by a reader that saw the old state.
        for _ in range(3):
            with client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    # our own pid too: a restarted container (same hostname) can hand us a dead child's pid
                    gone = [
                        pid for pid, started in pipe.hgetall(key).items()
                        if (pid != str(me) or mine is not None)
                        and (mine if pid == str(me) else _proc_start_time(pid)) != started
                    ]
                    pipe.multi()
                    for pid in gone:
                        pipe.hdel(key, pid)
                    pipe.execute()
                    removed = gone
                    break
                except redis.WatchError:
                    continue
        # Our own entry never depends on the cleanup above (it can lose every retry when the
        # pool starts together): only the vanished count is skipped then.
        with client.pipeline() as pipe:
            _register_self(pipe)
            pipe.execute()
        seen["removed"] = removed
        ops: List[tuple] = [("i", "processes_started", 1)]
        if removed:
            ops.append(("i", "processes_vanished", len(removed)))
        if "oom_kill" in cgroup:
            ops.append(("max", "cgroup_oom_kill", cgroup["oom_kill"]))
        _write(client, ops)

    _guarded(work)
    removed = seen.get("removed")
    if removed:
        logger.warning(
            f"docling.process_vanished count={len(removed)} pids={','.join(removed)} "
            f"cgroup_oom_kill={cgroup.get('oom_kill', 'none')} hostname={hostname()}"
        )


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


def record_process_shutdown(exitcode=None) -> None:
    rss = current_rss_kb()
    peak = peak_rss_kb()
    limit, tasks = _limits["max_memory_kb"], _limits["max_tasks"]
    reason = classify_exit(exitcode, peak, limit, tasks)
    cgroup = _cgroup_memory()
    ops: List[tuple] = [("i", "processes_stopped", 1)]
    if rss is not None:
        ops.append(("max", "rss_kb_max", rss))
    if peak is not None:
        ops.append(("max", "peak_rss_kb", peak))
    ops.append(("i", f"recycle:{reason}", 1))
    if exitcode is not None:
        ops.append(("set", "last_exitcode", exitcode))
    if limit:
        ops.append(("set", "max_memory_per_child_kb", limit))
    if tasks:
        ops.append(("set", "max_tasks_per_child", tasks))
    if "peak_kb" in cgroup:
        ops.append(("max", "cgroup_memory_peak_kb", cgroup["peak_kb"]))
    if "max_kb" in cgroup:
        ops.append(("set", "cgroup_memory_max_kb", cgroup["max_kb"]))
    pct = f"{100 * peak / limit:.1f}" if limit and peak is not None else "none"
    logger.info(
        f"docling.process_shutdown pid={os.getpid()} hostname={hostname()} exitcode={exitcode} "
        f"reason={reason} rss_kb={rss} peak_rss_kb={peak} max_memory_kb={limit or 'none'} "
        f"peak_pct_of_limit={pct} max_tasks={tasks or 'none'} "
        f"cgroup_memory_peak_kb={cgroup.get('peak_kb', 'none')} cgroup_oom_kill={cgroup.get('oom_kill', 'none')}"
    )
    me = str(os.getpid())
    _safe(ops, extra=lambda pipe: pipe.hdel(_children_key(), me))


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

            def opt(field):
                return int(_num(data[field])) if data.get(field) is not None else None

            limit = opt("max_memory_per_child_kb")
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
                "conversions_first": int(_num(data.get("conv:first"))),
                "conversions_warm": int(_num(data.get("conv:warm"))),
                "conversions_first_process": int(_num(data.get("conv:first_process"))),
                "conversions_failed": int(_num(data.get("conv:failed"))),
                "convert_seconds_first": round(_num(data.get("conv_seconds:first")), 2),
                "convert_seconds_warm": round(_num(data.get("conv_seconds:warm")), 2),
                "wrapper_seconds_total": round(sum(_num(data.get(f"wrapper_seconds:{r}")) for r in REASONS), 2),
                "pipeline_init_seconds_total": round(
                    sum(_num(data.get(f"pipeline_init_seconds:{r}")) for r in REASONS), 2),
                **{f"pipeline_init_{s}": int(_num(data.get(f"pipeline_init:{s}")))
                   for s in ("ok", "failed", "unavailable")},
                "pages_ok": int(_num(data.get("pages_ok"))),
                "pages_failed": int(_num(data.get("pages_failed"))),
                "docling_version": data.get("docling_version"),
                **{f"recycle_{r}": int(_num(data.get(f"recycle:{r}"))) for r in RECYCLE_REASONS},
                "processes_vanished": int(_num(data.get("processes_vanished"))),
                "last_exitcode": opt("last_exitcode"),
                "max_memory_per_child_kb": limit,
                "max_tasks_per_child": opt("max_tasks_per_child"),
                "peak_rss_pct_of_limit": round(100 * int(_num(peak)) / limit, 1) if limit and peak is not None else None,
                "cgroup_oom_kill": opt("cgroup_oom_kill"),
                "cgroup_memory_peak_kb": opt("cgroup_memory_peak_kb"),
                "cgroup_memory_max_kb": opt("cgroup_memory_max_kb"),
            })
    return rows
