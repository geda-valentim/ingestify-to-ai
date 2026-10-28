"""How an engine operation is shown by the API (spec 0007)."""

from sqlalchemy.orm import object_session

from shared import error_catalog
from shared.engine_control.contracts import TERMINAL
from shared.engine_control.models import EngineOperation, OperationPlan

SOURCE = "_source"  # key of `observed` naming the operation that observed it


def _facts(body):
    body = body or {}
    return {"feature": body.get("feature"), "type": body.get("type"), "trigger": body.get("trigger")}


def plan_facts(op):
    """What the operation's plan says about it: feature, type and the trigger of an automatic
    operation. Read through the operation's session (every caller passes an attached row); a
    detached row shows them as None."""
    db = object_session(op)
    plan = db.get(OperationPlan, op.plan_id) if db is not None else None
    return _facts(plan.body if plan is not None else None)


def observation(result, op, body):
    """What a finished operation stores as a resource's observation: its result, tagged with
    the operation, feature and type it came from (a shared resource serves several features,
    and a test of one must not read as the state of another)."""
    return dict(result or {}, **{SOURCE: {"operation_id": op.id, "feature": (body or {}).get("feature"),
                                          "type": (body or {}).get("type")}})


def resource_views(db, resources):
    """Resources for the runtime status: who observed them last and which operation locks
    them, by feature and type. A value nobody recorded (an observation stored before the
    source was kept) is None: unknown, never guessed."""
    locking = {r.operation_id for r in resources if r.operation_id}
    plans = dict(
        db.query(EngineOperation.id, OperationPlan.body)
        .join(OperationPlan, OperationPlan.id == EngineOperation.plan_id)
        .filter(EngineOperation.id.in_(locking))
        .all()
    ) if locking else {}
    out = []
    for r in resources:
        observed = dict(r.observed or {})
        source = observed.pop(SOURCE, None) or {}
        lock = _facts(plans.get(r.operation_id)) if r.operation_id else {}
        out.append(dict(
            key=r.key,
            maintenance=r.gate_closed,
            operation_id=r.operation_id,
            operation_feature=lock.get("feature"),
            operation_type=lock.get("type"),
            applied=r.applied,
            observed=observed,
            observed_at=r.observed_at,
            observed_feature=source.get("feature"),
            observed_operation_type=source.get("type"),
            observed_operation_id=source.get("operation_id"),
        ))
    return out


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
