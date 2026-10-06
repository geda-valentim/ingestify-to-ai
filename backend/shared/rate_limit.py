"""
Fixed-window rate limiting backed by Redis

Used to slow down online password guessing / credential stuffing on the
authentication endpoints. If Redis is unavailable, protected operations return
503 with Retry-After; independent process-local counters cannot safely replace
the shared budget across replicas. Existing authenticated sessions remain usable.
"""
import logging
import hashlib
import ipaddress
from typing import Optional

from fastapi import HTTPException, Request, status

from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

KEY_PREFIX = "ratelimit"


def client_ip(request: Request) -> str:
    """Use the ASGI peer, normalized after Uvicorn trusted-proxy processing.

    Never read forwarding headers here. Configure Uvicorn with an explicit
    trusted ingress IP; requests from other peers retain their socket address.
    """
    try:
        address = ipaddress.ip_address(request.client.host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return str(address)
    except (AttributeError, ValueError):
        raise _unavailable()


def _redis():
    return get_redis_client().client


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Autenticação temporariamente indisponível. Tente novamente mais tarde.",
        headers={"Retry-After": "30"},
    )


def _key(bucket: str, identity: str) -> str:
    # Avoid persisting attempted emails/usernames in Redis key names.
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}:{bucket}:{digest}"


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def _increment(redis, key: str, window_seconds: int) -> int:
    """
    Atomically create the counter with its TTL (if missing) and increment it.

    SET NX EX + INCR run in one MULTI/EXEC transaction, so a counter can never be
    left without an expiry (which would lock an IP/account out permanently).
    """
    pipe = redis.pipeline(transaction=True)
    pipe.set(key, 0, ex=window_seconds, nx=True)
    pipe.incr(key)
    _, count = pipe.execute()
    return count


def hit(bucket: str, identity: str, limit: int, window_seconds: int) -> None:
    """Count one request for (bucket, identity); raise 429 once `limit` is exceeded in the window"""
    key = _key(bucket, identity)
    try:
        redis = _redis()
        count = _increment(redis, key, window_seconds)
        if count > limit:
            ttl = redis.ttl(key)
            raise _too_many(ttl if ttl and ttl > 0 else window_seconds, "Muitas tentativas. Tente novamente mais tarde.")
    except HTTPException:
        raise
    except Exception:
        logger.warning("Rate limiter unavailable (%s)", bucket)
        raise _unavailable() from None


def check_failures(bucket: str, identity: str, limit: int) -> None:
    """Raise 429 if `identity` already has `limit` recorded failures (e.g. account lockout)"""
    key = _key(bucket, identity)
    try:
        redis = _redis()
        failures = int(redis.get(key) or 0)
        if failures >= limit:
            ttl = redis.ttl(key)
            raise _too_many(ttl if ttl and ttl > 0 else 60, "Muitas tentativas de login. Tente novamente mais tarde.")
    except HTTPException:
        raise
    except Exception:
        logger.warning("Rate limiter unavailable (%s)", bucket)
        raise _unavailable() from None


def record_failure(bucket: str, identity: str, window_seconds: int) -> None:
    """Record one failure for `identity`; the counter expires `window_seconds` after the first failure"""
    try:
        _increment(_redis(), _key(bucket, identity), window_seconds)
    except Exception:
        logger.warning("Rate limiter unavailable (%s)", bucket)
        raise _unavailable() from None


def reset(bucket: str, identity: str) -> None:
    try:
        _redis().delete(_key(bucket, identity))
    except Exception:
        logger.warning("Rate limiter unavailable (%s)", bucket)
        raise _unavailable() from None


def normalize_identity(value: Optional[str]) -> str:
    return (value or "").strip().lower()
