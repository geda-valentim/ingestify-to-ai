"""
Reading the local workers' heartbeats (written by workers/engines/heartbeat.py).

Used for health and the "configured X, alive Y" view only - never for capacity.
"""

from typing import Dict, List

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


# worker-remote announces itself every 10 s (workers/engines/remote_tasks.py); a route
# with a remote step is refused while it is silent (spec 0003, Appendix I)
REMOTE_KEY = "engines:remote:heartbeat"
REMOTE_TTL_SECONDS = 30


def remote_worker(client) -> Dict[str, str]:
    """The live worker-remote's heartbeat ({} when none is alive)"""
    data = client.hgetall(REMOTE_KEY) or {}
    return {_text(k): _text(v) for k, v in data.items()}
