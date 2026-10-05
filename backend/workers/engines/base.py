"""
The contract of a remote engine adapter (spec 0003, 4.10 and Appendix F) -
provisional, with the one implementation slice 4a needs (Modal).

An adapter is built per engine with that engine's opened credentials, held only
in the object. It never touches the database: the executor (remote_runner.py)
owns claims, heartbeats and settles, and hands the adapter an ExecutionContext
whose callbacks persist what must survive a crash (the provider call id) before
waiting on it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional


class ErrorCode:
    """What went wrong, as the backlog understands it (spec 0003, Appendix J)"""
    AUTH = "AUTH"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    CAPACITY = "CAPACITY"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_DEPLOYED = "NOT_DEPLOYED"
    COLD_START_FAILED = "COLD_START_FAILED"
    TRANSIENT = "TRANSIENT"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"
    INPUT_REJECTED = "INPUT_REJECTED"
    LOST = "LOST"  # the call finished but its output expired at the provider

    # Engine errors: the item goes elsewhere, nothing counts toward max_attempts
    ENGINE = frozenset({AUTH, QUOTA_EXHAUSTED, CAPACITY, RATE_LIMITED, NOT_DEPLOYED, COLD_START_FAILED, TRANSIENT})
    # The job's own failures: counted
    COUNTED = frozenset({TIMEOUT, INTERNAL})


@dataclass
class Usage:
    """What one attempt used, as measured by the executor and reported by the container"""
    measured_seconds: float = 0.0  # spawned -> result, by the executor's clock
    reported_seconds: Optional[float] = None  # the container's exec interval
    container_id: Optional[str] = None
    exec_started_at: Optional[datetime] = None
    exec_ended_at: Optional[datetime] = None
    cold_start_seconds: Optional[float] = None
    shared_seconds: Optional[float] = None  # E > 1 (slice 4d)
    units: Dict[str, Any] = field(default_factory=dict)


class EngineError(Exception):
    """A classified failure, with what was used until then (the container id even on failure)"""

    def __init__(self, code: str, detail: str = "", usage: Optional[Usage] = None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.usage = usage or Usage()


@dataclass
class ExecResult:
    output: Dict[str, Any]  # the feature's result (whisper_core's dict for transcription), validated
    usage: Usage


@dataclass
class HealthReport:
    ok: bool
    code: Optional[str] = None  # ErrorCode when not ok
    detail: str = ""
    deployed: Optional[bool] = None
    deployed_fingerprint: Optional[str] = None
    checked_at: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "detail": self.detail, "deployed": self.deployed,
                "deployed_fingerprint": self.deployed_fingerprint, "checked_at": self.checked_at}


@dataclass
class ExecutionContext:
    """
    What the executor gives the adapter for one attempt. `record_call_id(call id,
    spawned_at, deadline_at)` persists the provider's call id and the attempt's
    ceiling (with E = 1, spawned_at + reserved / rate) BEFORE the adapter waits on
    the call; `heartbeat` renews the usage row and returns False once the row is
    no longer ours.
    """
    usage_id: int
    attempt_key: str
    record_call_id: Callable[[str, datetime, datetime], None]
    heartbeat: Callable[[], bool]
    on_progress: Optional[Callable[[float], None]] = None  # seconds elapsed since spawn
    deadline_at: Optional[datetime] = None  # set once known (resume)
    poll_seconds: float = 15.0
