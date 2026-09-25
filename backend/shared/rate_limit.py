"""
Fixed-window rate limiting backed by Redis

Used to slow down online password guessing / credential stuffing on the
authentication endpoints. If Redis is unavailable the limiter fails open
(requests are allowed and a warning is logged) so an outage does not lock
everyone out.
"""
import logging
from typing import Optional

from fastapi import HTTPException, Request, status

from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

KEY_PREFIX = "ratelimit"


def client_ip(request: Request) -> str:
    """IP of the direct peer (X-Forwarded-For is client-controlled, so it is not trusted)"""
    return request.client.host if request.client else "unknown"


def _redis():
    return get_redis_client().client


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def _increment(redis, key: str, window_seconds: int) -> int:
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, window_seconds)
    return count


def hit(bucket: str, identity: str, limit: int, window_seconds: int) -> None:
    """Count one request for (bucket, identity); raise 429 once `limit` is exceeded in the window"""
    key = f"{KEY_PREFIX}:{bucket}:{identity}"
    try:
        redis = _redis()
        count = _increment(redis, key, window_seconds)
        if count > limit:
            ttl = redis.ttl(key)
            raise _too_many(ttl if ttl and ttl > 0 else window_seconds, "Muitas tentativas. Tente novamente mais tarde.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limiter unavailable ({bucket}), allowing request: {e}")


def check_failures(bucket: str, identity: str, limit: int) -> None:
    """Raise 429 if `identity` already has `limit` recorded failures (e.g. account lockout)"""
    key = f"{KEY_PREFIX}:{bucket}:{identity}"
    try:
        redis = _redis()
        failures = int(redis.get(key) or 0)
        if failures >= limit:
            ttl = redis.ttl(key)
            raise _too_many(ttl if ttl and ttl > 0 else 60, "Muitas tentativas de login. Tente novamente mais tarde.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limiter unavailable ({bucket}), allowing request: {e}")


def record_failure(bucket: str, identity: str, window_seconds: int) -> None:
    """Record one failure for `identity`; the counter expires `window_seconds` after the first failure"""
    try:
        _increment(_redis(), f"{KEY_PREFIX}:{bucket}:{identity}", window_seconds)
    except Exception as e:
        logger.warning(f"Rate limiter unavailable ({bucket}), failure not recorded: {e}")


def reset(bucket: str, identity: str) -> None:
    try:
        _redis().delete(f"{KEY_PREFIX}:{bucket}:{identity}")
    except Exception as e:
        logger.warning(f"Rate limiter unavailable ({bucket}), could not reset: {e}")


def normalize_identity(value: Optional[str]) -> str:
    return (value or "").strip().lower()
