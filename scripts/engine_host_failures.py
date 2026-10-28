"""What the host agent says about a failure: the operation's error code and the journal line."""
import json
import urllib.error

# What the operator should do for refusals that stop the agent (journalctl only).
FAILURE_HINTS = {
    "REGISTERED_MANIFEST_CHANGED": "compose files changed since registration; re-register the host "
    "(docs/runbooks/engine-control-bootstrap.md, 'Re-registrar o host')",
    "HOST_IDENTITY_REQUIRED": "the API does not know this host's token; check that "
    "secrets/engine_host_identities.json is readable by the API container and re-register if needed",
    "Registered images must be pinned by digest": "re-register after building the worker images",
}


def _api_code(exc):
    """The `detail.code` of an API refusal, or None. Reads the body: call once per error."""
    try:
        body = json.loads(exc.read().decode("utf-8", "replace") or "null")
        detail = body.get("detail") if isinstance(body, dict) else None
        return detail.get("code") if isinstance(detail, dict) else detail
    except Exception:
        return None


def failure_code(exc):
    """The code reported as the operation's error: the API's (ACCESS_REVOKED, ...), not "HTTP Error 403"."""
    if isinstance(exc, urllib.error.HTTPError):
        code = _api_code(exc)
        if isinstance(code, str) and code.isupper() and code.replace("_", "").isalnum():
            return code[:200]
        return f"HTTP_{exc.code}"
    return str(exc)[:200]


def describe_failure(exc, secret=None):
    """One log line for a failed cycle: type, code/message and a hint. Never the token."""
    kind = type(exc).__name__
    if isinstance(exc, urllib.error.HTTPError):
        code = _api_code(exc)
        text = f"HTTP {exc.code}" + (f" {code}" if code else "")
    elif isinstance(exc, urllib.error.URLError):
        text = f"API unreachable ({exc.reason})"
    else:
        text = str(exc)
    if secret:
        text = text.replace(secret, "***")
    text = " ".join(text.split())[:300]
    hint = next((h for key, h in FAILURE_HINTS.items() if text.startswith(key) or f" {key}" in text), None)
    return f"{kind}: {text}" + (f" — {hint}" if hint else "")
