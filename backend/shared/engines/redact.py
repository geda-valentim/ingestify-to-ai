"""
Keep provider tokens out of logs and persisted error messages.

`redact(text)` masks anything shaped like a credential (Modal token ids and
secrets, OpenAI-style keys, bearer tokens, JWTs) plus any exact value registered
with `register_secret` - e.g. the credentials an engine just opened.
`install_log_redaction()` applies it to every log record of the process, through
the record factory, so it covers records from every logger, their arguments and
their tracebacks, whatever handlers Celery or uvicorn install later.
"""

import logging
import re
import threading
from typing import Set

MASK = "[REDACTED]"

_PATTERNS = [
    re.compile(r"\b(?:ak|as|wk|ws)-[A-Za-z0-9]{10,}"),  # Modal token id / secret
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),  # OpenAI-style API keys
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)((?:token|secret|api[_-]?key|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{6,}"),
]

_registered: Set[str] = set()
_lock = threading.Lock()
_installed = False


def register_secret(value: str) -> None:
    """Redact this exact value from now on (ignored when too short to be a secret)"""
    if value and len(value) >= 8:
        with _lock:
            _registered.add(value)


def redact(text) -> str:
    if text is None:
        return text
    text = str(text)
    for secret in list(_registered):
        if secret in text:
            text = text.replace(secret, MASK)
    for pattern in _PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + MASK, text)
        else:
            text = pattern.sub(MASK, text)
    return text


def _redact_arg(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value  # keeps %d / %f working
    if isinstance(value, str):
        return redact(value)
    # Exceptions, dicts, objects: what %s would print, redacted
    return redact(str(value))


def _redact_args(args):
    if isinstance(args, tuple):
        return tuple(_redact_arg(a) for a in args)
    if isinstance(args, dict):
        return {k: _redact_arg(v) for k, v in args.items()}
    return args


def install_log_redaction() -> None:
    """Redact every log record created in this process from now on (idempotent)"""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True

    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        # Redact the template and each argument in place, keeping their structure:
        # formatters such as uvicorn's access log unpack record.args themselves
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        record.args = _redact_args(record.args)
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        return record

    logging.setLogRecordFactory(factory)
