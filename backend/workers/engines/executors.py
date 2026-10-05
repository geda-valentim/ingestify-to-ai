"""
Who runs a placed item, per adapter type.

`local`: its `execute` is today's task, published with the reservation it must
claim (spec 0003, 4.10). `modal` (slice 4a): execute_remote on the worker-remote
lane (workers/engines/remote.py); this side holds no provider code and never
imports `modal`. An engine whose adapter has no executor here is never
placeable. Tests register fake executors to exercise the remote rules.

Optional executor methods the dispatcher uses when present:
    deploy_state(engine, feature, binding)          deployed | not_deployed | needs_redeploy
    reservation_values(engine, binding, feature)    rate, price snapshot, fingerprint of the row
"""

from decimal import Decimal
from typing import Dict, Optional, Protocol

from shared.engines import dispatch
from shared.engines.capacity import Binding
from shared.models import Engine, JobDispatch


class Executor(Protocol):
    remote: bool

    def estimate(self, engine: Engine, binding: Binding, item: JobDispatch) -> Decimal:
        """Money to reserve for one attempt (rounded up)"""

    def publish(self, celery, engine: Engine, item: JobDispatch, usage_id: int) -> None:
        """Send the item to the engine, after the placement committed"""


class LocalExecutor:
    remote = False

    def estimate(self, engine, binding, item) -> Decimal:
        return Decimal("0")

    def publish(self, celery, engine, item, usage_id) -> None:
        dispatch.publish_local(celery, item.feature, item.payload, usage_id)


def _remote_executor():
    from workers.engines.remote import RemoteExecutor
    return RemoteExecutor()


_EXECUTORS: Dict[str, Executor] = {"local": LocalExecutor(), "modal": _remote_executor()}


def get(adapter_type: str) -> Optional[Executor]:
    return _EXECUTORS.get(adapter_type)


def register(adapter_type: str, executor: Optional[Executor]) -> None:
    """Add (or with None remove) an executor; used by tests"""
    if executor is None:
        _EXECUTORS.pop(adapter_type, None)
    else:
        _EXECUTORS[adapter_type] = executor
