"""
Engine alerts (spec 0003, 4.8): always a log line, and - when
ENGINE_ALERT_WEBHOOK_URL is set - a small generic JSON POST:

    {"source": "ingestify", "event": "budget_soft", "engine": "modal_1",
     "message": "...", "details": {...numbers...}, "at": "2026-10-05T12:00:00"}

Only engine slugs, periods and money/second figures go out: never credentials,
user ids, file names or transcript text (messages pass through redact()). A
webhook that is down never fails the caller; each alert tries once, briefly.

Deduplication is the caller's: budget alerts fire once per period (the engine's
alerted_soft_period / alerted_hard_period columns), the watchdog throttles its own.
"""

import json
import logging
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from shared.engines.redact import redact

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0

# Events callers send
BUDGET_SOFT = "budget_soft"
BUDGET_EXHAUSTED = "budget_exhausted"
QUOTA_EXHAUSTED = "quota_exhausted"
BILLING_DEGRADED = "billing_degraded"
DISPATCHER_DOWN = "dispatcher_down"
COST_DIVERGENCE = "cost_divergence"
ENGINE_PROBE_FAILED = "engine_probe_failed"

# Replaced in tests: (url, body bytes) -> None
_post: Optional[Callable[[str, bytes], None]] = None
sent: List[Dict[str, Any]] = []  # the last alerts of this process (tests, debugging); bounded
MAX_KEPT = 50


def _webhook_url() -> str:
    try:
        from shared.config import get_settings
        return get_settings().engine_alert_webhook_url or ""
    except Exception:
        return ""


def _default_post(url: str, body: bytes) -> None:
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "ingestify-alerts"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (operator's URL)
        response.read(1024)


def _clean(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for key, value in (details or {}).items():
        if isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = redact(str(value))[:200]
    return out


def alert(event: str, engine: Optional[str], message: str, details: Optional[Dict[str, Any]] = None,
          now: Optional[datetime] = None) -> Dict[str, Any]:
    """Log the alert and, if configured, POST it; returns the payload"""
    payload = {
        "source": "ingestify",
        "event": event,
        "engine": engine,
        "message": redact(message)[:500],
        "details": _clean(details),
        "at": (now or datetime.utcnow()).replace(microsecond=0).isoformat(),
    }
    logger.warning(f"[ENGINES] ALERT {event}{' ' + engine if engine else ''}: {payload['message']}")
    sent.append(payload)
    del sent[:-MAX_KEPT]
    url = _webhook_url()
    if url:
        try:
            (_post or _default_post)(url, json.dumps(payload).encode())
        except Exception as e:  # an alert channel must never break what raised the alert
            logger.warning(f"[ENGINES] Alert webhook failed: {type(e).__name__}")
    return payload
