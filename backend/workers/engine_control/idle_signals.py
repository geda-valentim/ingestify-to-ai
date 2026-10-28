"""The idle policy's Redis signals (spec 0007, section 4.6). Each has a TTL, none authorizes
anything, and losing one only costs a wakeup a little later.

- `engine_idle:demand:<feature>` (DEMAND_TTL_SECONDS): a task of the feature was refused
  ENGINE_NOT_RUNNING. Legacy media reach the generic worker through the default queue,
  which the policy does not read; this tells it a standby service has work. The value
  is the engine the task named, or "local" (admission's default engine).
"""

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
