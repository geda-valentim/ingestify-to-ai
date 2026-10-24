"""
Completion webhook of a job (`callback_url` on /upload, /convert and /transcribe).

When a MAIN job reaches COMPLETED, FAILED or PARTIAL and carries a `callback_url`,
the platform POSTs a small signed JSON event to it (`job.completed`, `job.failed`,
`job.partial`; docs/features/webhooks.md). The event has the job's metadata, never
the markdown: the receiver fetches `GET /jobs/{id}/result` with its own credentials.

A MAIN job becomes terminal in many places (the single-document path, the merge of
a split PDF, the describe-figures stage, the stuck-job monitor, the engine ledger,
every transcription failure path...). Instead of a call in each one, a Session
listener watches every flush: a MAIN job whose `status` moved to a terminal value
gets its `webhook_state` written *in the same transaction* (state "pending" and a
delivery id), and once that transaction commits the delivery task is queued. So a
rolled-back write sends nothing, a future terminal path is covered without a
change, and nothing here can raise into the job code (enqueue errors are logged).

The delivery id is deterministic (`job`, `status`, `completed_at`): a redelivered
task that settles the job again writes the same id, and a later transition (a
PARTIAL job that finishes after an automatic page retry) gets a new one. Receivers
dedupe on `X-Ingestify-Delivery`.

The per-user signing secret is derived (HMAC) from a server key, so there is no
table of secrets and users cannot read each other's.
"""

from __future__ import annotations

import calendar
import hashlib
import hmac
import ipaddress
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.models import Job, JobStatus

logger = logging.getLogger(__name__)

MAX_CALLBACK_URL_LENGTH = 2048
SIGNATURE_VERSION = "v1"
_DELIVERY_NAMESPACE = uuid.UUID("5b1f3f0e-6d0a-4b7e-9d52-1c1d6c7e04a9")

EVENTS = {
    JobStatus.COMPLETED: "job.completed",
    JobStatus.FAILED: "job.failed",
    JobStatus.PARTIAL: "job.partial",
}

# What `GET /jobs/{id}` shows of the latest delivery; `webhook_state` has more
_PUBLIC_STATE_KEYS = ("status", "attempts", "last_http_status", "last_error",
                      "last_attempt_at", "delivered_at", "delivery_id", "event")


class InvalidCallbackUrl(ValueError):
    """A `callback_url` the platform will not deliver to (the API answers 422 INVALID_CALLBACK_URL)"""


# ---------------------------------------------------------------------------
# callback_url
# ---------------------------------------------------------------------------

_INTERNAL_SUFFIXES = (".local", ".internal", ".localhost", ".localdomain", ".lan", ".home.arpa")


def validate_callback_url(url: str) -> str:
    """
    The URL to store (stripped, fragment dropped) or `InvalidCallbackUrl`.

    Only what can be judged without the network: https (http with
    WEBHOOK_ALLOW_HTTP), a host, no credentials, no literal non-public IP, no
    single-label or internal-looking name (redis, minio, *.local...). The names
    that resolve to a private address are refused at delivery
    (`workers.sources._resolve_public_ips`), when DNS is looked up.
    """
    url = (url or "").strip()
    if not url:
        raise InvalidCallbackUrl("callback_url is empty")
    if len(url) > MAX_CALLBACK_URL_LENGTH:
        raise InvalidCallbackUrl(f"callback_url is longer than {MAX_CALLBACK_URL_LENGTH} characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise InvalidCallbackUrl("callback_url is not a valid URL")

    allowed = ("https", "http") if get_settings().webhook_allow_http else ("https",)
    if parts.scheme.lower() not in allowed:
        raise InvalidCallbackUrl("callback_url must use https")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise InvalidCallbackUrl("callback_url has no host")
    if parts.username is not None or parts.password is not None:
        raise InvalidCallbackUrl("callback_url must not contain credentials")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        from workers.sources import _is_public_ip
        if not _is_public_ip(literal):
            raise InvalidCallbackUrl("callback_url must not point to a private or reserved address")
    else:
        if "." not in host or host == "localhost" or host.endswith(_INTERNAL_SUFFIXES):
            raise InvalidCallbackUrl("callback_url must point to a public host name")

    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))


def url_host(url: Optional[str]) -> Optional[str]:
    """The host of a callback URL (the status endpoint never shows the path or query: they may hold a token)"""
    try:
        return urlsplit(url or "").hostname
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------

def _master_key() -> bytes:
    settings = get_settings()
    key = settings.webhook_signing_secret
    if not key and settings.webhook_signing_secret_file:
        with open(settings.webhook_signing_secret_file) as f:
            key = f.read().strip()
    if key:
        return key.encode()
    # Distinct label: the JWT key itself is never used as an HMAC key here
    return hmac.new(settings.jwt_secret_key.encode(), b"ingestify-webhook:master:v1", hashlib.sha256).digest()


def signing_secret(user_id: str) -> str:
    """The secret of one user, `whsec_...`: what the receiver verifies `X-Ingestify-Signature` with"""
    digest = hmac.new(_master_key(), b"ingestify-webhook:v1:" + str(user_id).encode(), hashlib.sha256)
    return "whsec_" + digest.hexdigest()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """Hex HMAC-SHA256 of `{timestamp}.{body}`"""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def signature_header(secret: str, timestamp: int, body: bytes) -> str:
    return f"t={timestamp},{SIGNATURE_VERSION}={sign(secret, timestamp, body)}"


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def event_for(status) -> Optional[str]:
    try:
        return EVENTS.get(JobStatus(getattr(status, "value", status)))
    except ValueError:
        return None


def delivery_id_for(job: Job) -> str:
    """Same job, status and completion time -> same id; a later transition -> another"""
    status = JobStatus(getattr(job.status, "value", job.status)).value
    return str(uuid.uuid5(_DELIVERY_NAMESPACE, f"{job.id}:{status}:{_iso(job.completed_at) or ''}"))


def build_payload(job: Job, delivery_id: str, event_name: str) -> bytes:
    """The event body: compact JSON, metadata only (never the markdown or any result)"""
    from shared.error_catalog import split

    error = None
    if job.error_message:
        code, detail = split(job.error_message)
        error = {"code": code, "message": str(detail if code else job.error_message)[:500]}
    status = getattr(job.status, "value", job.status)
    body = {
        "id": delivery_id,
        "event": event_name,
        "created": calendar.timegm((job.completed_at or datetime.utcnow()).utctimetuple()),
        "data": {
            "job_id": job.id,
            "status": status,
            "name": job.name,
            "type": "main",
            "project_id": job.project_id,
            "folder_id": job.folder_id,
            "created_at": _iso(job.created_at),
            "completed_at": _iso(job.completed_at),
            "total_pages": job.total_pages,
            "pages_completed": job.pages_completed,
            "pages_failed": job.pages_failed,
            "error": error,
            "result_url": f"/jobs/{job.id}/result",
        },
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()


def public_state(job: Job) -> Optional[dict]:
    """The `webhook` block of `GET /jobs/{id}`, or None when the job has no callback URL"""
    if not isinstance(job.callback_url, str) or not job.callback_url:
        return None
    state = job.webhook_state or {}
    block = {"url_host": url_host(job.callback_url)}
    block.update({key: state.get(key) for key in _PUBLIC_STATE_KEYS if key != "event"})
    block["status"] = state.get("status") or "pending"
    block["attempts"] = state.get("attempts") or 0
    return block


# ---------------------------------------------------------------------------
# Arming a delivery (the Session listener and the duplicate-upload path)
# ---------------------------------------------------------------------------

def _wants_delivery(job: Job) -> bool:
    return bool(job.callback_url and job.user_id and job.job_type == "MAIN")


def _arm(session: Session, job: Job) -> Optional[str]:
    """Write the pending state of this job's terminal event and register it for after the commit"""
    name = event_for(job.status)
    if not name:
        return None
    delivery_id = delivery_id_for(job)
    job.webhook_state = {
        "delivery_id": delivery_id,
        "event": name,
        "job_status": getattr(job.status, "value", job.status),
        "status": "pending",
        "attempts": 0,
        "armed_at": _iso(datetime.utcnow()),
    }
    pending = session.info.setdefault("webhooks", [])
    if (job.id, delivery_id) not in pending:
        pending.append((job.id, delivery_id))
    return delivery_id


def schedule_current(db: Session, job: Job, *, url_changed: bool = True) -> bool:
    """
    A request attached (or changed) the `callback_url` of a job that is already
    terminal (a duplicate upload of a finished conversion): the caller still gets
    its one event, once `db` commits. Nothing is sent again when this URL already
    has this terminal event.
    """
    if not _wants_delivery(job) or event_for(job.status) is None:
        return False
    state = job.webhook_state or {}
    if not url_changed and state.get("delivery_id") == delivery_id_for(job) \
            and state.get("status") in ("pending", "delivered"):
        return False
    _arm(db, job)
    return True


def _on_before_flush(session: Session, flush_context, instances) -> None:
    for job in list(session.dirty) + list(session.new):
        if not isinstance(job, Job):
            continue
        try:
            added = inspect(job).attrs.status.history.added
            if not added or event_for(added[0]) is None or not _wants_delivery(job):
                continue
            _arm(session, job)
        except Exception:  # never into the code that settles the job
            logger.exception("Could not arm the webhook of job %s", getattr(job, "id", None))


def _on_after_commit(session: Session) -> None:
    pending = session.info.pop("webhooks", None)
    for job_id, delivery_id in pending or ():
        try:
            from workers.webhook_tasks import deliver_webhook, DISPATCH_DELAY_SECONDS
            options = {"countdown": DISPATCH_DELAY_SECONDS}
            queue = get_settings().webhook_queue
            if queue:
                options["queue"] = queue
            deliver_webhook.apply_async((job_id, delivery_id), **options)
        except Exception:
            # The state stays "pending": GET /jobs/{id} shows it, nothing is retried by itself
            logger.exception("Could not queue the webhook of job %s", job_id)


def _on_after_transaction_end(session: Session, transaction) -> None:
    # After a commit the list was already consumed; after a rollback or a close it is dropped
    if transaction.parent is None:
        session.info.pop("webhooks", None)


def install() -> None:
    if not event.contains(Session, "before_flush", _on_before_flush):
        event.listen(Session, "before_flush", _on_before_flush)
        event.listen(Session, "after_commit", _on_after_commit)
        event.listen(Session, "after_transaction_end", _on_after_transaction_end)


install()
