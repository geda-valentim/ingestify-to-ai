"""Independent of the runner: expires paid overrides even when no jobs exist."""

import time
from datetime import datetime
from sqlalchemy import func
from shared.database import SessionLocal
from shared.engine_control.models import EngineOperation, ControlResource
from shared.engine_control import registry
from shared.engine_control.contracts import utc_deadline
from shared.models import Engine
from shared.engines.redact import install_log_redaction


def round_(session_factory=SessionLocal):
    from shared.redis_client import get_redis_client

    get_redis_client().client.set("engine-control:watchdog", str(time.time()), ex=30)
    with session_factory() as db:
        rows = [
            (op.id, op.engine_id, op.handles)
            for op in db.query(EngineOperation).filter(EngineOperation.reserved_usd > 0)
        ]
    for op_id, engine_id, handles in rows:
        maintenance = (handles or {}).get("maintenance") or {}
        if not maintenance.get("cleanup_required"):
            continue
        with session_factory() as db:
            owner = (
                db.query(ControlResource)
                .filter_by(maintenance_operation_id=op_id)
                .first()
            )
            if owner is None:
                # A newer canonical policy owns this same pool. Never undo its override.
                old = db.get(EngineOperation, op_id)
                old.handles = dict(
                    old.handles or {},
                    maintenance=dict(maintenance, cleanup_required=False),
                )
                db.commit()
                continue
        until = maintenance.get("warm_until")
        expired = not until or utc_deadline(until) <= datetime.utcnow()
        with session_factory() as db:
            engine = db.get(Engine, engine_id)
            if not expired and engine.limit_usd is not None:
                from shared.engines import budget

                room = budget.headroom(
                    db,
                    engine,
                    budget.period_start(engine, datetime.utcnow()),
                    include_reserved=False,
                )
                expired = room is None or room <= 0
            db.expunge(engine)
        if not expired:
            continue
        # Cleanup does not claim the operator's execution lease or repeat a deploy.
        driver = registry.create(engine.adapter_type)
        try:
            driver.expire_maintenance(engine, op_id, session_factory)
        except Exception:
            with session_factory() as db:
                op = (
                    db.query(EngineOperation)
                    .filter_by(id=op_id)
                    .with_for_update()
                    .one()
                )
                op.error = {
                    "code": "BUDGET_STOP_UNCONFIRMED",
                    "message": "Override pago não confirmado; exposição preservada.",
                }
                db.commit()


def loop():
    install_log_redaction()
    while True:
        try:
            round_()
        except Exception:
            pass  # Remains visible as stale watchdog health; no log of credentials.
        time.sleep(5)


if __name__ == "__main__":
    loop()
