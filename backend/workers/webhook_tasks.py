"""
Delivery of the completion webhook of a job (shared/webhooks.py, docs/features/webhooks.md).

`deliver_webhook(job_id, delivery_id)` is queued once the transaction that settled
the job committed. It POSTs the signed event to the job's `callback_url` through
the SSRF-pinned sender of the URL source (the host is resolved once, every address
must be public, and the connection goes to that address), follows no redirect and
reads at most 4 KB of the answer.

2xx: delivered. 3xx and 4xx (except 408 and 429): permanent, the receiver said no.
5xx, 408, 429, a timeout or a network error: retried with a growing delay, six
attempts in all (30 s, 2 min, 10 min, 30 min, 2 h between them, within the Celery
visibility timeout). The outcome is written to `Job.webhook_state` only while it
still belongs to this delivery; the job's own status, error and timestamps are
never touched, and nothing here raises into another task.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Tuple

import httpx
from sqlalchemy import update

from workers.celery_app import celery_app
from workers.sources import _send_pinned
from shared import webhooks
from shared.database import SessionLocal
from shared.models import Job

logger = logging.getLogger(__name__)

DISPATCH_DELAY_SECONDS = 2  # lets the settling transaction's readers see it
RETRY_COUNTDOWNS = (30, 120, 600, 1800, 7200)
MAX_RESPONSE_BYTES = 4096
USER_AGENT = "Ingestify-Webhook/1"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_RETRYABLE_STATUS = {408, 429}


def _record(job_id: str, delivery_id: str, **fields) -> bool:
    """Merge `fields` into the job's webhook_state if it still belongs to `delivery_id`"""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        state = (job.webhook_state if job else None) or {}
        if not job or state.get("delivery_id") != delivery_id:
            return False
        # Core update with updated_at pinned: a delivery is not a change of the job
        db.execute(
            update(Job).where(Job.id == job_id)
            .values(webhook_state={**state, **fields}, updated_at=Job.updated_at)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return True


async def _post(url: str, body: bytes, headers: dict) -> Tuple[int, str]:
    """POST and return (status, first bytes of the answer); redirects are not followed"""
    async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT) as client:
        response = await _send_pinned(client, url, method="POST", content=body, headers=headers)
        try:
            received = b""
            async for chunk in response.aiter_bytes():
                received += chunk
                if len(received) >= MAX_RESPONSE_BYTES:
                    break
            return response.status_code, received[:MAX_RESPONSE_BYTES].decode("utf-8", "replace")
        finally:
            await response.aclose()


def _classify_refusal(error: Exception) -> Tuple[bool, str]:
    """(retryable, last_error) of an exception raised before any answer"""
    if isinstance(error, httpx.TimeoutException):
        return True, "TIMEOUT"
    if isinstance(error, httpx.HTTPError):
        return True, f"NETWORK_ERROR: {type(error).__name__}"
    text = str(error)
    if "non-public" in text:
        return False, "CALLBACK_URL_NOT_PUBLIC"
    if "Could not resolve" in text:
        return True, "DNS_ERROR"
    return False, "INVALID_CALLBACK_URL"


@celery_app.task(bind=True, max_retries=len(RETRY_COUNTDOWNS), name="workers.webhook_tasks.deliver_webhook",
                 acks_late=True)
def deliver_webhook(self, job_id: str, delivery_id: str) -> Optional[str]:
    """Send one terminal event of a MAIN job; returns delivered | failed | superseded"""
    retry_in = None
    try:
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            state = (job.webhook_state if job else None) or {}
            if (not job or state.get("delivery_id") != delivery_id or not job.callback_url
                    or not job.user_id or state.get("job_status") != getattr(job.status, "value", job.status)):
                # Another terminal transition, or the job went back to work: that one has its own delivery
                return "superseded"
            event_name = state.get("event") or webhooks.event_for(job.status)
            body = webhooks.build_payload(job, delivery_id, event_name)
            url = job.callback_url
            secret = webhooks.signing_secret(job.user_id)

        attempt = int(self.request.retries or 0) + 1
        timestamp = int(time.time())  # fresh per attempt: the receiver may reject old timestamps
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Ingestify-Event": event_name,
            "X-Ingestify-Delivery": delivery_id,
            "X-Ingestify-Signature": webhooks.signature_header(secret, timestamp, body),
        }
        outcome = {"attempts": attempt, "last_attempt_at": datetime.utcnow().isoformat(),
                   "last_http_status": None, "last_error": None}
        try:
            status_code, _answer = asyncio.run(_post(url, body, headers))
        except Exception as error:
            retryable, outcome["last_error"] = _classify_refusal(error)
            logger.warning("Webhook of job %s attempt %s: %s (%s)", job_id, attempt,
                           outcome["last_error"], type(error).__name__)
        else:
            outcome["last_http_status"] = status_code
            if 200 <= status_code < 300:
                _record(job_id, delivery_id, status="delivered", delivered_at=datetime.utcnow().isoformat(),
                        **outcome)
                return "delivered"
            retryable = status_code in _RETRYABLE_STATUS or status_code >= 500
            outcome["last_error"] = f"HTTP_{status_code}"
            logger.warning("Webhook of job %s attempt %s answered %s", job_id, attempt, status_code)

        if retryable and attempt <= len(RETRY_COUNTDOWNS):
            _record(job_id, delivery_id, status="pending", **outcome)
            retry_in = RETRY_COUNTDOWNS[attempt - 1]
        else:
            _record(job_id, delivery_id, status="failed", **outcome)
            return "failed"
    except Exception as error:  # never into another task
        logger.exception("Webhook delivery of job %s failed unexpectedly", job_id)
        try:
            _record(job_id, delivery_id, status="failed", last_error=f"INTERNAL_ERROR: {type(error).__name__}",
                    last_attempt_at=datetime.utcnow().isoformat())
        except Exception:
            logger.exception("Could not record the webhook failure of job %s", job_id)
        return "failed"

    raise self.retry(countdown=retry_in)
