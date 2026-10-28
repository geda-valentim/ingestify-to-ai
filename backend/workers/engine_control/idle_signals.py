"""The idle policy's Redis signals (spec 0007, section 4.6). Each has a TTL, none authorizes
anything, and losing one only costs a tick or a wakeup a little later.

- `engine_idle:tick` (TICK_LOCK_SECONDS): one tick at a time, whatever the beat delivers to
  the control worker's threads. Without Redis there is no lock and no tick.
- `engine_idle:demand:<feature>` (DEMAND_TTL_SECONDS): a task of the feature was refused
  ENGINE_NOT_RUNNING. Legacy media reach the generic worker through the default queue,
  which the policy does not read; this tells it a standby service has work. The value
  is the engine the task named, or "local" (admission's default engine).
"""

from uuid import uuid4

TICK_LOCK = "engine_idle:tick"
TICK_LOCK_SECONDS = 60
DEMAND_TTL_SECONDS = 120
DEFAULT_ENGINE = "local"  # the slug admission falls back to when a task names no engine


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client().client


def demand_key(feature):
    return f"engine_idle:demand:{feature}"


def mark_demand(feature, engine_id=None):
    """Called on a refused admission. Never raises: the task goes on to its requeue."""
    try:
        _redis().set(demand_key(feature), engine_id or DEFAULT_ENGINE, ex=DEMAND_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - a lost hint, not a lost task
        pass


def demand(feature):
    """The engine named by the latest refused task of `feature`, or None."""
    try:
        value = _redis().get(demand_key(feature))
    except Exception:  # noqa: BLE001
        return None
    return value.decode() if isinstance(value, bytes) else value


def demanded(engine, marked):
    return marked is not None and marked in (engine.id, engine.slug)


def acquire_tick():
    """A token when this tick may run, else None (another tick holds it, or no Redis)."""
    token = uuid4().hex
    try:
        return token if _redis().set(TICK_LOCK, token, nx=True, ex=TICK_LOCK_SECONDS) else None
    except Exception:  # noqa: BLE001 - fail closed: no lock, no tick
        return None


def release_tick(token):
    try:
        client = _redis()
        if client.get(TICK_LOCK) in (token, token.encode()):
            client.delete(TICK_LOCK)  # a lock taken over after expiry is left alone (bar a tiny race)
    except Exception:  # noqa: BLE001 - it expires on its own
        pass
