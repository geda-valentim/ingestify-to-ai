"""
Messages the Celery Redis broker holds as delivered-but-unacknowledged.

With task_acks_late, kombu moves every message a worker takes into the `unacked`
hash (delivery tag -> [payload, exchange, routing_key]) and scores it by delivery
time in `unacked_index`. Acking deletes it; only after `visibility_timeout` does a
consumer push it back to its queue. A message whose worker died (container
recreated, OOM kill) therefore sits there, invisible, for the whole timeout.

This module reads those entries, tells which ones no live worker is holding, and
puts one back on its queue - what an operator would otherwise do by hand.
Pure Redis: the caller supplies the task ids that workers report as live.
"""

import ast
import json
import time
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional

import redis

UNACKED_KEY = "unacked"
UNACKED_INDEX_KEY = "unacked_index"
REPORT_KEY = "monitoring:broker_unacked"


@dataclass
class UnackedMessage:
    delivery_tag: str
    task_id: Optional[str]
    task_name: Optional[str]
    queue: Optional[str]
    job_id: Optional[str]
    retries: Optional[int]
    delivered_at: Optional[float]
    age_seconds: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


def _job_id(headers: dict) -> Optional[str]:
    """job_id from the task kwargs, as Celery's protocol 2 renders them in `kwargsrepr`"""
    try:
        kwargs = ast.literal_eval(headers.get("kwargsrepr") or "{}")
        return kwargs.get("job_id") if isinstance(kwargs, dict) else None
    except (ValueError, SyntaxError):
        return None


def list_unacked(client: redis.Redis, now: Optional[float] = None) -> List[UnackedMessage]:
    """Every message the broker holds unacknowledged, oldest first"""
    now = time.time() if now is None else now
    messages = []
    for tag, raw in client.hgetall(UNACKED_KEY).items():
        tag = tag.decode() if isinstance(tag, bytes) else tag
        try:
            payload, _exchange, routing_key = json.loads(raw)
            headers = payload.get("headers") or {}
        except (ValueError, TypeError, AttributeError):
            payload, routing_key, headers = {}, None, {}
        delivered_at = client.zscore(UNACKED_INDEX_KEY, tag)
        messages.append(UnackedMessage(
            delivery_tag=tag,
            task_id=headers.get("id"),
            task_name=headers.get("task"),
            queue=routing_key,
            job_id=_job_id(headers),
            retries=headers.get("retries"),
            delivered_at=delivered_at,
            age_seconds=round(now - delivered_at, 1) if delivered_at is not None else None,
        ))
    return sorted(messages, key=lambda m: m.delivered_at or 0)


def find_orphans(
    messages: Iterable[UnackedMessage],
    live_task_ids: Iterable[str],
    min_age_seconds: float,
) -> List[UnackedMessage]:
    """
    Messages no live worker holds (not active, reserved or scheduled for a retry)
    that are older than min_age_seconds - the grace keeps a message that was just
    delivered, and not yet reported by its worker, from looking orphaned.
    """
    live = set(live_task_ids)
    return [
        m for m in messages
        if m.task_id not in live and m.age_seconds is not None and m.age_seconds >= min_age_seconds
    ]


def requeue(client: redis.Redis, delivery_tag: str, attempts: int = 5) -> bool:
    """
    Put one unacked message back at the head of its queue, atomically.

    Returns False if the message is no longer unacked (acked, or already restored
    by kombu or a concurrent call). Consumers BRPOP from the right, so RPUSH makes
    it the next message taken - it has waited longest.
    """
    for _ in range(attempts):
        with client.pipeline() as pipe:
            try:
                pipe.watch(UNACKED_KEY)
                raw = pipe.hget(UNACKED_KEY, delivery_tag)
                if raw is None:
                    pipe.unwatch()
                    return False
                payload, exchange, routing_key = json.loads(raw)
                if exchange:
                    # Only the default exchange maps a routing key straight to a
                    # queue list; anything else needs kombu's own binding lookup
                    pipe.unwatch()
                    return False
                pipe.multi()
                pipe.hdel(UNACKED_KEY, delivery_tag)
                pipe.zrem(UNACKED_INDEX_KEY, delivery_tag)
                pipe.rpush(routing_key, json.dumps(payload))
                pipe.execute()
                return True
            except redis.WatchError:
                continue  # the hash changed (another ack); look again
    return False


def broker_client() -> redis.Redis:
    """Redis client on the Celery broker database (not the app cache database)"""
    from shared.config import get_settings, redis_url_with_password

    settings = get_settings()
    return redis.Redis.from_url(
        redis_url_with_password(settings.celery_broker_url, settings.redis_password),
        **({"ssl_cert_reqs": "required", "ssl_check_hostname": True,
            "ssl_ca_certs": settings.redis_ssl_ca_certs or None}
           if settings.celery_broker_url.startswith("rediss://") else {}),
    )


def live_task_ids(inspect) -> Optional[set]:
    """
    Task ids the workers report as running, prefetched or scheduled for a retry
    (a retry's countdown keeps its message unacked in the worker), from a Celery
    `app.control.inspect()`. None when no worker answered: nothing can be judged.
    """
    ids = set()
    answered = False
    for method in (inspect.active, inspect.reserved, inspect.scheduled):
        replies = method()
        if not replies:
            continue
        answered = True
        for tasks in replies.values():
            for task in tasks or []:
                # scheduled() nests the task under "request"
                request = task.get("request", task)
                if request.get("id"):
                    ids.add(request["id"])
    return ids if answered else None
