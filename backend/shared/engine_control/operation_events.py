"""The event log of an engine operation, as the API pages it (spec 0007)."""

from shared.engine_control.models import EngineOperation, OperationEvent


def events(db, op_id, after=0, limit=100):
    from shared.engine_control.service import ControlError
    op = db.get(EngineOperation, op_id)
    if not op:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    rows = (
        db.query(OperationEvent)
        .filter(OperationEvent.operation_id == op_id, OperationEvent.seq > after)
        .order_by(OperationEvent.seq)
        .limit(limit + 1)
        .all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    return dict(
        events=[
            dict(
                seq=x.seq,
                type=x.type,
                stage=x.stage,
                payload=x.payload,
                at=x.created_at,
            )
            for x in rows
        ],
        next=rows[-1].seq if rows else after,
        has_more=more,
        state=op.state,
    )
