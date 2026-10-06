"""Admission and maintenance use the same SQL resource locks. No fail-open."""

from uuid import uuid4
from shared.config import get_settings
from shared.engine_control.models import (
    ControlResource,
    ControlAdmission,
    RuntimeProfile,
)
from shared.engine_control.service import ControlError, locked_engine, now
from shared.models import Engine


def resource_rows(db, engine, feature):
    # Canonical service keys plus GPU shared by the lane; profile can still be desired.
    from shared.engine_control import registry
    from shared.engine_control.service import latest_profile

    p = latest_profile(db, engine.id, feature)
    if not p:
        # Generic tasks can execute multiple features in the same managed service.
        if engine.adapter_type == "local":
            return (
                db.query(ControlResource)
                .filter_by(owner_engine_id=engine.id)
                .order_by(ControlResource.key)
                .with_for_update()
                .all()
            )
        return []
    driver = registry.create(engine.adapter_type)
    keys = set(driver.resource_keys(engine, feature, p.profile))
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine.id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    if applied:
        keys.update(driver.resource_keys(engine, feature, applied.profile))
    return (
        db.query(ControlResource)
        .filter(ControlResource.key.in_(sorted(keys)))
        .order_by(ControlResource.key)
        .with_for_update()
        .all()
    )


def acquire(feature, holder, engine_id=None, session_factory=None):
    if not get_settings().engine_control_enabled:
        return []
    if session_factory is None:
        from shared.database import SessionLocal

        session_factory = SessionLocal
    with session_factory() as db:
        e = (
            db.query(Engine).filter_by(id=engine_id).first()
            if engine_id
            else db.query(Engine).filter_by(slug="local").first()
        )
        if not e:
            raise ControlError("ADMISSION_AUTHORITY_UNAVAILABLE", 503)
        e = locked_engine(db, e.id)
        rows = resource_rows(db, e, feature)
        if any(r.gate_closed for r in rows):
            raise ControlError("ENGINE_MAINTENANCE", 503)
        if any(
            (r.applied or {}).get("feature_modes", {}).get(feature)
            in ("standby", "stopped")
            for r in rows
        ):
            raise ControlError("ENGINE_NOT_RUNNING", 503)
        tickets = []
        for r in rows:
            ticket = ControlAdmission(
                id=str(uuid4()), resource_key=r.key, holder=holder[:128]
            )
            db.add(ticket)
            tickets.append(ticket.id)
        db.commit()
        return tickets


def release(tickets, session_factory=None):
    if not tickets:
        return
    if session_factory is None:
        from shared.database import SessionLocal

        session_factory = SessionLocal
    with session_factory() as db:
        db.query(ControlAdmission).filter(
            ControlAdmission.id.in_(tickets), ControlAdmission.released_at.is_(None)
        ).update({"released_at": now()}, synchronize_session=False)
        db.commit()


def placement_blocked(db, engine, feature):
    if not get_settings().engine_control_enabled:
        return False
    rows = resource_rows(db, engine, feature)
    return any(
        r.gate_closed
        or r.operation_id
        or (r.applied or {}).get("feature_modes", {}).get(feature)
        in ("standby", "stopped")
        for r in rows
    )
