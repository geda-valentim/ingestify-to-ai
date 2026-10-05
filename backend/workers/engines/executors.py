"""
Who runs a placed item, per adapter type.

Only `local` exists in this slice: its `execute` is today's task, published with
the reservation it must claim (spec 0003, 4.10). An engine whose adapter has no
executor here is never placeable - which keeps every remote engine out until
slice 4a registers one. Tests register fake executors to exercise the remote
rules (budget, admin-only, fill_first) without a provider.
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


_EXECUTORS: Dict[str, Executor] = {"local": LocalExecutor()}


def get(adapter_type: str) -> Optional[Executor]:
    return _EXECUTORS.get(adapter_type)


def register(adapter_type: str, executor: Optional[Executor]) -> None:
    """Add (or with None remove) an executor; used by tests and, from slice 4a, by remote adapters"""
    if executor is None:
        _EXECUTORS.pop(adapter_type, None)
    else:
        _EXECUTORS[adapter_type] = executor
