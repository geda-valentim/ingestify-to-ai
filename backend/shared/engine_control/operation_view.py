"""How an engine operation is shown by the API (spec 0007)."""

from sqlalchemy.orm import object_session

from shared import error_catalog
from shared.engine_control.contracts import TERMINAL
from shared.engine_control.models import OperationPlan


def plan_facts(op):
    """What the operation's plan says about it: the trigger of an automatic operation.
    Read through the operation's session (every caller passes an attached row); a detached
    row shows no trigger."""
    db = object_session(op)
    plan = db.get(OperationPlan, op.plan_id) if db is not None else None
    body = (plan.body if plan is not None else None) or {}
    return {"trigger": body.get("trigger")}


def operation_view(op):
    """The operation as the API shows it. Plan facts (who triggered it) come from its plan."""
    return dict(
        operation_id=op.id,
        engine_id=op.engine_id,
        plan_id=op.plan_id,
        state=op.state,
        can_recover=op.state == "needs_attention"
        and bool((op.handles or {}).get("executor_exited")),
        stage=op.stage,
        can_cancel=op.state not in TERMINAL,
        cancel_requested=op.cancel_requested,
        generation=op.generation,
        last_seq=op.seq,
        result=op.result,
        error=error_catalog.operation_error(op.error),
        reserved_usd=str(op.reserved_usd),
        actual_usd=str(op.actual_usd) if op.actual_usd is not None else None,
        cost_confirmed=op.cost_confirmed,
        created_at=op.created_at,
        started_at=op.started_at,
        finished_at=op.finished_at,
        events_url=f"/admin/engine-operations/{op.id}/events",
        **plan_facts(op),
    )
