"""Forced cancel of admission tickets (spec 0007 §4.5).

The way out for an admission ticket whose holder cannot be proven dead (the drain's G1
reconciliation and the ledger sweeper only act on positive evidence). The plan freezes the open
tickets of a feature's resources, with what the holder looks like right now and the ledger rows
it seems to hold; executing it only releases those tickets, in one transaction, recording why.
It kills no process, changes no job and has no ledger effect: a usage whose holder is dead is
settled by the sweeper, and one with a live heartbeat is real work.
"""

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from shared.engine_control.contracts import FORCE_CANCEL
from shared.engine_control.models import (
    ControlAdmission,
    ControlResource,
    EngineOperation,
    OperationPlan,
)

PERMISSION = "engine_operations.execute." + FORCE_CANCEL
LIVE_WORK_SECONDS = 90  # a heartbeat younger than the sweeper's stale limit looks like live work
IN_FLIGHT = ("reserved", "spawning", "running")
MAX_TICKETS = 100  # oldest first; the plan stores at most this many (another plan takes the rest)
# A prefork child may not be in `inspect active` yet: below the drain's acceptance grace an
# "absent" holder is shown as unknown (workers/engine_control/orphan_tickets.ACCEPT_GRACE_SECONDS).
ACCEPT_GRACE_SECONDS = 30

_probe = None


def set_holder_probe(probe):
    """`probe(holders) -> {holder: {"verdict", "pid", "host"}}`, registered by the API process
    (it asks the Celery nodes; this layer cannot). Verdicts: alive, absent, node_silent,
    legacy_holder, unknown."""
    global _probe
    _probe = probe


def parse_holder(holder):
    """(task_id, pid, node) of a `task:<id>|<pid>|<node>` holder, else None: the format
    workers/engine_control/orphan_tickets writes (a test keeps the two parsers equal)."""
    if not holder.startswith("task:"):
        return None
    parts = holder[len("task:"):].split("|", 2)
    if len(parts) != 3 or not parts[0] or not parts[1].isdecimal() or not parts[2]:
        return None
    return parts[0], int(parts[1]), parts[2]


def _unknown(holder):
    """Unknown verdict, but the process the holder names (so its ledger rows are still listed)."""
    p = parse_holder(holder)
    return {"verdict": "unknown", "pid": p[1] if p else None, "host": p[2].split("@", 1)[-1] if p else None}


def _verdicts(holders):
    unknown = {h: _unknown(h) for h in holders}
    if _probe is None:
        return unknown
    try:
        return {**unknown, **(_probe(holders) or {})}
    except Exception:  # no answer is "unknown", never a reason to refuse or to release
        return unknown


def _authorize(db, engine, feature, actor):
    from shared.access import policy

    if policy.enabled():
        policy.authorize(db, actor, PERMISSION, engine=engine, feature=feature, lock=True)


def _open_tickets(db, keys):
    return (
        db.query(ControlAdmission)
        .filter(ControlAdmission.resource_key.in_(keys), ControlAdmission.released_at.is_(None))
        .order_by(ControlAdmission.created_at, ControlAdmission.id)
        .limit(MAX_TICKETS)
        .all()
    ) if keys else []


def _usages(db, engine_id, holder, seen, now):
    """Ledger rows the holder seems to hold: by job for a live session, else by (pid, host)
    against the usage holder `host:pid[:thread]` (a heuristic, said so in the plan)."""
    from shared.models import EngineUsage

    q = db.query(EngineUsage).filter(EngineUsage.engine_id == engine_id, EngineUsage.status.in_(IN_FLIGHT))
    if holder.startswith("live:"):
        q = q.filter(EngineUsage.job_id == holder[len("live:"):])
    elif seen.get("pid") is not None and seen.get("host"):
        own = f"{seen['host']}:{seen['pid']}"
        escaped = own.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.filter((EngineUsage.holder == own) | EngineUsage.holder.like(escaped + ":%", escape="\\"))
    else:
        return []
    rows = []
    for u in q.order_by(EngineUsage.id).limit(20):
        age = (now - u.heartbeat_at).total_seconds() if u.heartbeat_at else None
        rows.append(dict(usage_id=u.id, status=u.status, job_id=u.job_id, subject_type=u.subject_type,
                         subject_id=u.subject_id, heartbeat_age_seconds=age,
                         looks_alive=age is not None and age < LIVE_WORK_SECONDS))
    return rows


def _require_schema(db):
    """Until the additive 0007 migration adds release_reason, only force_cancel is unavailable."""
    from shared.engine_control.migration import has_added_columns
    from shared.engine_control.service import ControlError

    if not has_added_columns(db.get_bind(), "engine_control_admissions"):
        raise ControlError("ENGINE_CONTROL_MIGRATION_REQUIRED", 503)


def create_plan(db, engine, req, actor):
    from shared.access import policy
    from shared.engine_control import admission
    from shared.engine_control.service import ControlError, clean, digest, locked_engine, now

    _require_schema(db)
    # Ask the Celery nodes (up to 2 s) before taking any lock, and only for someone who may
    # force-cancel at all; a ticket seen only after the locks gets "unknown".
    if policy.enabled() and not policy.allowed(db, actor, PERMISSION, engine=engine, feature=req.feature):
        raise ControlError("ACCESS_DENIED", 403)
    first = _open_tickets(db, sorted(r.key for r in admission.resource_rows(db, engine, req.feature, lock=False)))
    seen = _verdicts(sorted({t.holder for t in first}))
    engine_id = engine.id
    db.rollback()
    if policy.enabled():
        policy.epoch(db, True)
    engine = locked_engine(db, engine_id)
    if engine.version != req.engine_version:
        raise ControlError("VERSION_CONFLICT")
    _authorize(db, engine, req.feature, actor)
    rows = admission.resource_rows(db, engine, req.feature, lock=False)
    if any(r.operation_id for r in rows):
        raise ControlError("OPERATION_CONFLICT")
    keys = sorted(r.key for r in rows)
    tickets = _open_tickets(db, keys)
    if not tickets:
        raise ControlError("FORCE_CANCEL_NOTHING_TO_RELEASE", 422, feature=req.feature)
    at = now()
    listed = []
    for t in tickets:
        s = seen.get(t.holder) or _unknown(t.holder)
        age = int((at - t.created_at).total_seconds())
        verdict = "unknown" if s["verdict"] == "absent" and age < ACCEPT_GRACE_SECONDS else s["verdict"]
        listed.append(dict(
            ticket_id=t.id, resource_key=t.resource_key, holder=t.holder, age_seconds=age, verdict=verdict,
            job_id=t.holder[len("live:"):] if t.holder.startswith("live:") else None,
            usages=_usages(db, engine.id, t.holder, s, at),
        ))
    body = clean(dict(
        type=FORCE_CANCEL, feature=req.feature, engine_id=engine.id, adapter_type=engine.adapter_type,
        resources=keys, tickets=listed, ledger_effect="none", usage_link="heuristic: (pid, host)",
        looks_like_live_work=any(u["looks_alive"] for t in listed for u in t["usages"]),
        confirmation=f"{engine.slug}:{len(listed)}",
    ))
    plan = OperationPlan(engine_id=engine.id, actor_id=actor, engine_version=engine.version, profile_id=None,
                         body=body, hash=digest(body), expires_at=at + timedelta(minutes=5))
    db.add(plan)
    db.commit()
    return dict(plan_id=plan.id, plan_hash=plan.hash, expires_at=plan.expires_at, **body)


def enqueue(db, plan, plan_hash, key, actor, confirm):
    """Release the plan's frozen tickets that are still open, in one transaction; the
    operation is born finished (there is nothing to cancel)."""
    from shared.access import policy
    from shared.engine_control.service import (
        ControlError, append_event, digest, locked_engine, now, operation_view,
    )
    from shared.models import AdminAudit, Engine

    _require_schema(db)
    if policy.enabled():
        policy.epoch(db, True)
    if not key or len(key) > 128:
        raise ControlError("IDEMPOTENCY_KEY_REQUIRED", 422)
    request_hash = digest(dict(plan_id=plan.id, plan_hash=plan_hash, confirm=confirm))
    e = locked_engine(db, plan.engine_id)
    existing = (
        db.query(EngineOperation).filter_by(actor_id=actor, idempotency_key=key).with_for_update().first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise ControlError("IDEMPOTENCY_CONFLICT")
        return operation_view(existing)
    if plan.actor_id != actor:
        raise ControlError("PLAN_NOT_FOUND", 404)
    if plan.expires_at <= now() or plan.hash != plan_hash or e.version != plan.engine_version:
        raise ControlError("PLAN_STALE")
    if confirm != plan.body["confirmation"]:
        raise ControlError("FORCE_CANCEL_CONFIRMATION_REQUIRED", 422)
    _authorize(db, db.get(Engine, plan.engine_id), plan.body["feature"], actor)
    resources = (
        db.query(ControlResource).filter(ControlResource.key.in_(plan.body["resources"]))
        .order_by(ControlResource.key).with_for_update().all()
    )
    if any(r.operation_id for r in resources):
        raise ControlError("OPERATION_CONFLICT")
    at = now()
    op = EngineOperation(engine_id=e.id, actor_id=actor, plan_id=plan.id, idempotency_key=key,
                         request_hash=request_hash, state="succeeded", stage="done", started_at=at,
                         finished_at=at, deadline=at, reserved_usd=0, actual_usd=0, cost_confirmed=True)
    db.add(op)
    db.flush()
    frozen = [t["ticket_id"] for t in plan.body["tickets"]]
    open_now = [
        t.id for t in db.query(ControlAdmission)
        .filter(ControlAdmission.id.in_(frozen), ControlAdmission.released_at.is_(None))
        .with_for_update()
    ]
    if open_now:
        t = ControlAdmission.__table__
        db.execute(update(t).where(t.c.id.in_(open_now), t.c.released_at.is_(None))
                   .values(released_at=at, release_reason=f"{FORCE_CANCEL}:{op.id}"))
    released = [i for i in frozen if i in set(open_now)]
    already = [i for i in frozen if i not in set(open_now)]
    op.result = {"released": released, "already_released": already, "ledger_effect": "none"}
    append_event(db, op, "operation.accepted", {"message": "Operação aceita"})
    append_event(db, op, "operation.succeeded", {"result": op.result, "error": None})
    db.add(AdminAudit(actor_user_id=actor, auth_method="jwt", action="engine.force_cancel", target_type="engine",
                      target_id=e.id, before=None,
                      after={"operation_id": op.id, "tickets": plan.body["tickets"], "confirmation": confirm,
                             "released": released, "already_released": already}))
    try:
        db.commit()
    except IntegrityError:  # the same key raced on another engine's lock
        db.rollback()
        raise ControlError("IDEMPOTENCY_CONFLICT") from None
    return operation_view(op)
