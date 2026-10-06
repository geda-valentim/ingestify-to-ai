"""Release gate for audited ML runtimes that cannot yet resolve patched dependencies.

Standard library only: also shipped in the remote image. Qualification is local
and explicitly ENVIRONMENT=development; no production override exists.
"""
import os


class RuntimeSecurityBlocked(RuntimeError):
    code = "ML_RUNTIME_SECURITY_BLOCKED"


def require_safe_runtime(provider: str, *, environment=None) -> None:
    provider = str(provider).strip().lower()
    if provider not in {"whisperx", "diart"}:
        return
    environment = os.environ.get("ENVIRONMENT", "production") if environment is None else environment
    if str(environment).strip().lower() != "development":
        raise RuntimeSecurityBlocked(
            f"{provider} is unavailable in production: its qualified dependency set "
            "contains unresolved security advisories. Use faster-whisper until a "
            "patched runtime is available and qualified."
        )
