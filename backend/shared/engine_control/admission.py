"""Admission and maintenance use the same SQL resource locks. No fail-open."""

from uuid import uuid4

from sqlalchemy import or_
from shared.config import get_settings
from shared.engine_control.local_services import admission_services, is_service_key
from shared.engine_control.models import (
    ControlResource,
    ControlAdmission,
    EngineOperation,
    OperationPlan,
    RuntimeProfile,
)
from shared.engine_control.service import ControlError, locked_engine, now
from shared.models import Engine


def resource_rows(db, engine, feature, lock=True):
    # Canonical service keys plus GPU shared by the lane; profile can still be desired.
    from shared.engine_control import registry
    from shared.engine_control.service import latest_profile

    p = latest_profile(db, engine.id, feature)
    if not p:
        # Without a profile, only the feature's own services (any host): a document conversion is
        # not refused because transcription's dedicated service is draining (spec 0007 §4.6).
        if engine.adapter_type != "local":
            return []
        services = admission_services(feature)
        rows = db.query(ControlResource).filter(ControlResource.owner_engine_id == engine.id)
        if services is None:  # a feature without a service of its own: every row, as before
            return _lockable(rows.order_by(ControlResource.key), lock).all()
        like = or_(*(ControlResource.key.like(f"local:%:service:{s}") for s in sorted(services)))
        return [r for r in _lockable(  # the LIKE narrows in SQL; the exact match is below
            rows.filter(like).order_by(ControlResource.key),
            lock,
        ).all() if is_service_key(r.key, services)]
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
    return _lockable(
        db.query(ControlResource)
        .filter(ControlResource.key.in_(sorted(keys)))
        .order_by(ControlResource.key),
        lock,
    ).all()


def _lockable(query, lock):
    return query.with_for_update() if lock else query


def _find_engine(db, engine_id):
    return (
        db.query(Engine).filter_by(id=engine_id).first()
        if engine_id
        else db.query(Engine).filter_by(slug="local").first()
    )


def _refusal(rows, feature):
    """The code admission refuses with for these resources, or None. Shared by acquire and admission_refusal."""
    if any(r.gate_closed for r in rows):
        return "ENGINE_MAINTENANCE"
    if any(
        (r.applied or {}).get("feature_modes", {}).get(feature) in ("standby", "stopped")
        for r in rows
    ):
        return "ENGINE_NOT_RUNNING"
    return None


def admission_refusal(db, feature, engine_id=None):
    """What acquire would refuse with right now (None = admitted), by plain SELECTs: no row locks, no ticket."""
    if not get_settings().engine_control_enabled:
        return None
    e = _find_engine(db, engine_id)
    if not e:
        return "ADMISSION_AUTHORITY_UNAVAILABLE"
    return _refusal(resource_rows(db, e, feature, lock=False), feature)


def acquire(feature, holder, engine_id=None, session_factory=None):
    if not get_settings().engine_control_enabled:
        return []
    if session_factory is None:
        from shared.database import SessionLocal

        session_factory = SessionLocal
    with session_factory() as db:
        e = _find_engine(db, engine_id)
        if not e:
            raise ControlError("ADMISSION_AUTHORITY_UNAVAILABLE", 503)
        e = locked_engine(db, e.id)
        rows = resource_rows(db, e, feature)
        refusal = _refusal(rows, feature)
        if refusal:
            raise ControlError(refusal, 503)
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
    held = {}
    return any(
        r.gate_closed
        or (r.operation_id and _holds_placement(db, r.operation_id, feature, held))
        or (r.applied or {}).get("feature_modes", {}).get(feature)
        in ("standby", "stopped")
        for r in rows
    )


def _holds_placement(db, operation_id, feature, held):
    """An automatic operation (a plan with `trigger`) of another feature only locks the shared keys:
    its effect acts on its own dedicated service (spec 0007 §4.6). One primary-key read per
    operation, only for a locked row; a missing plan keeps blocking."""
    if operation_id not in held:
        body = (
            db.query(OperationPlan.body)
            .join(EngineOperation, EngineOperation.plan_id == OperationPlan.id)
            .filter(EngineOperation.id == operation_id)
            .scalar()
        ) or {}
        held[operation_id] = not (body.get("trigger") and body.get("feature") not in (None, feature))
    return held[operation_id]
