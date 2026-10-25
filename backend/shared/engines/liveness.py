"""
Reading the local workers' heartbeats (written by workers/engines/heartbeat.py).

Used for health, the "configured X, alive Y" view and the S3 readiness hook
(unused until admission is wired) - never for capacity.
"""

import threading
import time
from typing import Dict, List, NamedTuple, Optional, Tuple

KEY = "engines:local:{feature}:{hostname}"
TTL_SECONDS = 30


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def alive(feature: str, client) -> List[Dict[str, str]]:
    """Heartbeats currently alive for a feature, one per worker hostname"""
    workers = []
    for key in client.scan_iter(match=KEY.format(feature=feature, hostname="*")):
        data = client.hgetall(key)
        if data:
            entry = {_text(k): _text(v) for k, v in data.items()}
            entry["hostname"] = _text(key).split(":", 3)[3]
            workers.append(entry)
    return sorted(workers, key=lambda w: w["hostname"])


READY_CACHE_SECONDS = 10


class ReadySlots(NamedTuple):
    slots: int
    observed: int  # live worker entries behind the number
    reason: Optional[str]  # internal only; not a queue_reason, never sent to the API


_ready_cache: Dict[str, Tuple[float, ReadySlots]] = {}
_ready_lock = threading.Lock()


def observed_ready_slots(feature: str, client=None, *, clock=time.monotonic) -> ReadySlots:
    """Sum of the `concurrency` of the live workers of a feature (cached 10 s).

    Never below 1: an unreadable or empty observation reports 1 with a reason.
    Nothing calls this yet."""
    now = clock()
    with _ready_lock:
        hit = _ready_cache.get(feature)
        if hit and hit[0] > now:
            return hit[1]
    try:
        if client is None:
            from shared.redis_client import get_redis_client
            client = get_redis_client().client
        workers = alive(feature, client)
        if not workers:
            result = ReadySlots(1, 0, "no_ready_workers")
        else:
            total, unreported = 0, False
            for w in workers:
                try:
                    n = int(w.get("concurrency", ""))
                    if n < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    n, unreported = 1, True
                total += n
            result = ReadySlots(total, len(workers), "concurrency_unreported" if unreported else None)
    except Exception:
        result = ReadySlots(1, 0, "observation_failed")
    with _ready_lock:
        _ready_cache[feature] = (now + READY_CACHE_SECONDS, result)
    return result


def reset_cache() -> None:
    with _ready_lock:
        _ready_cache.clear()


# worker-remote announces itself every 10 s (workers/engines/remote_tasks.py); a route
# with a remote step is refused while it is silent (spec 0003, Appendix I)
REMOTE_KEY = "engines:remote:heartbeat"
REMOTE_TTL_SECONDS = 30


def remote_worker(client) -> Dict[str, str]:
    """The live worker-remote's heartbeat ({} when none is alive)"""
    data = client.hgetall(REMOTE_KEY) or {}
    return {_text(k): _text(v) for k, v in data.items()}
