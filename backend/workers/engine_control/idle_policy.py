"""Local idle cooldown and standby wakeup (spec 0007, section 4.6).

Every tick, for each `local` engine whose applied profile opted in with
`idle_cooldown`, one of three things happens per feature:

- running and idle for `idle_timeout_seconds` -> a `cooldown` operation, so the
  desired state becomes `standby` (the model leaves the GPU);
- standby with work waiting for it -> a `start` operation (the wakeup);
- anything else -> nothing. A stopped feature stays stopped: only the admin
  started that, and only the admin undoes it.

Both go through the same plan/enqueue path as the admin's button, as the admin
who applied the opted-in revision, so the drain, the resource lock, the
authorization and the operation history apply unchanged. The idempotency key is
derived from the applied state: repeated ticks find the operation already
created, and a refused one is not retried until the applied state changes (a new
revision or a new opt-in). A cooldown that fails stays in the history. A wakeup
that fails for a transient reason is retried with backoff, at most
WAKEUP_MAX_ATTEMPTS times; after that the policy stops and says so on the
operation that applied the opt-in (idle_notes), with the work still waiting, so
a queue never stalls in silence. Jobs in standby wait in the queue or the
dispatcher backlog for readiness; nothing falls back to CPU.

Only dedicated services take part: the generic worker also serves the default
queue (webhooks, figure finalize), so it never goes to standby on its own, and
live sessions are admitted by HTTP, not by a queue.
"""

import logging
import time
from datetime import timedelta

from sqlalchemy import func, or_

from shared.config import get_settings
from shared.database import SessionLocal
from shared.engine_control import service
from shared.engine_control.contracts import TriggeredPlanRequest
from shared.engine_control.models import (
    ControlAdmission,
    ControlResource,
    EngineOperation,
    OperationEvent,
    RuntimeProfile,
)
from shared.models import Engine, FeatureRoute, JobDispatch
from workers.engine_control import idle_notes, idle_signals
from workers.engine_control.local import SERVICES, LocalControlAdapter

logger = logging.getLogger(__name__)

ADAPTER = "local"
KOMBU_PRIORITY_SEP = "\x06\x16"
# Dispatch rows placed on an engine and not finished yet.
PLACED_STATES = ("assigned", "running")
# Wait before wakeup attempt 2, 3, 4 and 5, counted from the previous one's end.
WAKEUP_BACKOFF_MINUTES = (1, 5, 15, 15)
WAKEUP_MAX_ATTEMPTS = 5
# Outcomes a wakeup may be retried after. needs_attention keeps its locks for recovery.
# A cancel is only ever asked by an admin (the API): not transient, it ends the cycle
# (see _cancel_asked).
RETRYABLE = ("failed", "cancelled")
CANCEL_ASKED = "cancel.requested"
# A lost permission refused by the server's own authorization, or an opt-in no longer in
# force (at claim or before the effect): retrying cannot succeed. A host agent's report
# with the same code is an ordinary failure (see _server_code).
NOT_RETRIED_CODES = ("ACCESS_DENIED", "ACCESS_REVOKED", "IDLE_POLICY_NOT_OPTED_IN")
TRIGGER = {"cooldown": "idle_policy", "start": "wakeup"}


def feature_queues():
    """The Celery queue whose consumer is the dedicated service of each feature."""
    settings = get_settings()
    return {"transcription": settings.transcription_queue, "vision": settings.vision_queue}


def queue_depth(queue):
    """Messages waiting on a Celery queue, every priority. None when Redis cannot tell."""
    try:
        from shared.redis_client import get_redis_client

        pipe = get_redis_client().client.pipeline(transaction=False)
        for name in [queue] + [f"{queue}{KOMBU_PRIORITY_SEP}{step}" for step in range(1, 10)]:
            pipe.llen(name)
        return sum(int(n or 0) for n in pipe.execute())  # one round trip
    except Exception:  # noqa: BLE001 - unknown, never "empty"
        return None


def default_opt_in(db, engine_id, feature):
    """(actor, revision) of the applied opt-in, or None (then the policy does nothing)."""
    from shared.engine_control.idle_opt_in import opt_in

    return opt_in(db, engine_id, feature)


def applied_profile(db, engine_id, feature):
    return (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine_id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )


def _mode(rows, service_key, feature):
    row = next((r for r in rows if r.key == service_key), None)
    return ((row.applied or {}).get("feature_modes") or {}).get(feature, "running") if row else "running"


def _open_tickets(db, keys):
    return (
        db.query(func.count(ControlAdmission.id))
        .filter(ControlAdmission.resource_key.in_(keys), ControlAdmission.released_at.is_(None))
        .scalar()
    )


def _last_release(db, keys):
    return (
        db.query(func.max(ControlAdmission.released_at))
        .filter(ControlAdmission.resource_key.in_(keys))
        .scalar()
    )


def _placed(db, engine_id, feature):
    return (
        db.query(JobDispatch.id)
        .filter(
            JobDispatch.feature == feature,
            JobDispatch.state.in_(PLACED_STATES),
            JobDispatch.engine_id == engine_id,
        )
        .first()
        is not None
    )


def _backlog(db, engine_id, feature, due_at=None, states=("waiting",)):
    """Items waiting for a route that can place them on this engine; with `due_at`, only
    those placeable by then (not in a dispatcher backoff)."""
    route = db.get(FeatureRoute, feature)
    if not route or route.state != "active":
        return None
    if not any(engine_id in (step.get("engine_ids") or []) for step in route.steps or []):
        return None
    return db.query(JobDispatch.id).filter(
        JobDispatch.feature == feature, JobDispatch.state.in_(states),
        *([or_(JobDispatch.not_before.is_(None), JobDispatch.not_before <= due_at)] if due_at else []))


def _has_backlog(db, engine_id, feature, due_at=None, states=("waiting",)):
    found = _backlog(db, engine_id, feature, due_at, states)
    return found is not None and found.first() is not None


def _routed_backlog(db, engine_id, feature, due_at=None):
    """How many, for the give-up note."""
    found = _backlog(db, engine_id, feature, due_at)
    return found.with_entities(func.count(JobDispatch.id)).scalar() if found is not None else 0


def _standby_is_ours(db, row, profile, actor):
    """The last change of the applied state was this opt-in's own idle cooldown.

    A later human operation (drain_stop, a manual cooldown, start, apply_profile)
    ends the automatic cycle: the wakeup never undoes what an admin did. A row
    applied before the operation was recorded does not qualify either.
    """
    applied = (row.applied if row else None) or {}
    if applied.get("type") != "cooldown" or applied.get("trigger") != "idle_policy":
        return False
    if applied.get("revision") != profile.revision or not actor:
        return False
    op = db.get(EngineOperation, applied.get("operation_id")) if applied.get("operation_id") else None
    return op is not None and op.actor_id == actor


def decide(db, engine, feature, profile, depth, at, actor=None, demand=False):
    """'cooldown', 'start' or None for one feature of one local engine. `demand`: a task of
    the feature was just refused ENGINE_NOT_RUNNING (legacy media on the default queue)."""
    settings = profile.profile
    if not settings.get("idle_cooldown"):
        return None
    keys = LocalControlAdapter().resource_keys(engine, feature, settings)
    rows = db.query(ControlResource).filter(ControlResource.key.in_(keys)).all()
    if any(r.operation_id or r.gate_closed for r in rows):
        return None  # an operation owns it right now
    host = (settings.get("provider_settings") or {}).get("host_id", "unregistered")
    # Every ticket of this feature carries its dedicated service key; the generic
    # worker's key also counts unrelated document work, so activity is read here only.
    service_key = f"local:{host}:service:{SERVICES[feature]}"
    mode = _mode(rows, service_key, feature)
    if mode == "standby":
        row = next((r for r in rows if r.key == service_key), None)
        if not _standby_is_ours(db, row, profile, actor):
            return None
        if (depth or 0) > 0 or demand or _has_backlog(db, engine.id, feature, at):
            return "start"
        return None
    if mode != "running" or settings.get("min_ready_replicas"):
        return None
    if depth is None or depth > 0 or _open_tickets(db, [service_key]) or _placed(db, engine.id, feature):
        return None
    if _has_backlog(db, engine.id, feature, states=("probing", "waiting")):
        return None  # arriving or waiting for this engine, even in a backoff: not idle (else a loop)
    quiet_since = at - timedelta(seconds=int(settings.get("idle_timeout_seconds") or 60))
    last = _last_release(db, [service_key])
    if profile.applied_at > quiet_since or (last is not None and last > quiet_since):
        return None
    return "cooldown"


def idempotency_key(action, engine_id, feature, profile):
    """One operation per applied state; a new revision or a new apply gives a new key."""
    return f"idle:{action}:{engine_id}:{feature}:{profile.revision}:{profile.applied_at:%Y%m%dT%H%M%S%f}"


def _wakeup_attempts(db, actor, base):
    """[(attempt number, operation)] of this applied state's wakeups, oldest first: the
    exact keys on the (actor_id, idempotency_key) unique index, never a history scan."""
    keys = {f"{base}:{n}": n for n in range(1, WAKEUP_MAX_ATTEMPTS + 1)}
    rows = (
        db.query(EngineOperation)
        .filter(EngineOperation.actor_id == actor, EngineOperation.idempotency_key.in_(list(keys)))
        .all()
    )
    return sorted(((keys[op.idempotency_key], op) for op in rows), key=lambda pair: pair[0])


def _cancel_asked(db, attempts):
    """An admin asked to cancel one of these attempts. Read from the append-only event,
    not from the operation's flag, which a later recovery clears."""
    ids = [op.id for _, op in attempts]
    return db.query(OperationEvent.seq).filter(
        OperationEvent.operation_id.in_(ids), OperationEvent.type == CANCEL_ASKED
    ).first() is not None


def _server_code(op):
    """The operation's error code when the server's own authorization gave it (plan, enqueue,
    claim, before the effect); None for the host agent's report, which only says the host's
    call was refused: an ordinary failure, never the actor's lost permission."""
    error = op.error or {}
    return None if error.get("source") == "host" else error.get("code")


def _refused_later(db, engine_id, feature, profile, actor, action, op):
    """A permission lost after the enqueue (at claim, before the effect) is noted like one
    refused at the plan, and suppressed the same way."""
    code = _server_code(op)
    if op.state != "failed" or code not in NOT_RETRIED_CODES or code == "IDLE_POLICY_NOT_OPTED_IN":
        return
    idle_notes.remember_refusal(idle_notes.refusal_key(engine_id, feature, profile, actor))
    idle_notes.announce_refusal(db, engine_id, feature, profile, actor, action, code)


def _next_wakeup(db, engine_id, feature, profile, actor, base, at, waiting):
    """(key to create, None) for a new attempt, (None, existing id) or (None, None) to wait."""
    attempts = _wakeup_attempts(db, actor, base)
    if not attempts:
        return f"{base}:1", None
    number, last = attempts[-1]
    if last.state not in RETRYABLE:
        return None, last.id  # running, succeeded or needs_attention: nothing to add
    if _server_code(last) in NOT_RETRIED_CODES:
        _refused_later(db, engine_id, feature, profile, actor, "start", last)
        return None, None
    if _cancel_asked(db, attempts):
        return None, None
    if number >= WAKEUP_MAX_ATTEMPTS:
        idle_notes.give_up(db, engine_id, feature, profile, actor, WAKEUP_MAX_ATTEMPTS, waiting)
        # Only an admin or a new applied state resumes it: later ticks skip this state at once.
        idle_notes.remember_refusal(idle_notes.refusal_key(engine_id, feature, profile, actor))
        return None, None
    ended = last.finished_at or last.created_at
    if at < ended + timedelta(minutes=WAKEUP_BACKOFF_MINUTES[number - 1]):
        return None, None
    return f"{base}:{number + 1}", None


def _enqueue(session_factory, engine_id, feature, action, actor, at=None, waiting=0, revision=None,
             applied_at=None):
    with session_factory() as db:
        engine = db.get(Engine, engine_id)
        if engine is None or engine.adapter_type != ADAPTER:
            return None  # never anything paid, even if the row changed under us
        profile = applied_profile(db, engine_id, feature)
        if profile is None or (revision is not None and profile.revision != revision) or (
            applied_at is not None and profile.applied_at != applied_at
        ):
            return None  # applied state moved since the tick looked; the next tick decides again
        refused = idle_notes.refusal_key(engine_id, feature, profile, actor)
        if idle_notes.refusal_known(refused):
            return None
        key = idempotency_key(action, engine_id, feature, profile)
        if action == "start":
            key, existing_id = _next_wakeup(db, engine_id, feature, profile, actor, key, at or service.now(), waiting)
            if key is None:
                return existing_id
        else:
            existing = db.query(EngineOperation).filter_by(actor_id=actor, idempotency_key=key).first()
            if existing:
                _refused_later(db, engine_id, feature, profile, actor, action, existing)
                return existing.id  # a cooldown is tried once per applied state
        # Always the opted-in revision: left out, create_plan would take the newest
        # desired one, which may not be applied or opted in at all.
        request = TriggeredPlanRequest(type=action, feature=feature, engine_version=engine.version,
                                       profile_revision=profile.revision, trigger=TRIGGER[action])
        try:
            plan = service.create_plan(db, engine, request, actor)
            return service.enqueue(db, plan["plan_id"], plan["plan_hash"], key, actor)["operation_id"]
        except service.ControlError as exc:
            # The opt-in moved since the tick read it: not a lost permission; the next tick re-reads it.
            lost = exc.status == 403 and exc.code != "IDLE_POLICY_NOT_OPTED_IN"
            if lost:  # noted once per applied state by the database, whether Redis is up or not
                idle_notes.remember_refusal(refused)
                db.rollback()
                idle_notes.announce_refusal(db, engine_id, feature, profile, actor, action, exc.code)
            raise


# A tick gives up (until the next one) once it has run this long: a slow Redis or a
# locked engine never ties up the control worker's threads, which humans' operations use.
TICK_BUDGET_SECONDS = 10
_warned = {}  # (engine, feature) -> applied state already warned about; logs only


def _warn_no_opt_in(engine_id, feature, profile, action):
    state = idle_notes.state_tag(profile)
    if _warned.get((engine_id, feature)) != state:
        _warned[(engine_id, feature)] = state
        logger.warning("engine idle policy: %s/%s has no opt-in for the applied revision; %s skipped "
                       "(apply the profile again to opt in)", engine_id, feature, action)


def tick(session_factory=SessionLocal, depth_of=queue_depth, opt_in_of=default_opt_in, now=None,
         demand_of=idle_signals.demand, clock=time.monotonic):
    """One pass over the local engines, one at a time and within TICK_BUDGET_SECONDS.
    Returns [(engine_id, feature, action, operation_id)]."""
    token = idle_signals.acquire_tick()
    if token is None:
        return []
    try:
        return _tick(session_factory, depth_of, opt_in_of, now or service.now(), demand_of,
                     clock, clock() + TICK_BUDGET_SECONDS)
    finally:
        idle_signals.release_tick(token)


def _tick(session_factory, depth_of, opt_in_of, at, demand_of, clock, deadline):
    # Redis first, with no database session open while it answers.
    signals = {feature: (depth_of(queue), demand_of(feature)) for feature, queue in feature_queues().items()}
    candidates = []
    with session_factory() as db:
        for engine in db.query(Engine).filter(Engine.adapter_type == ADAPTER).all():
            if clock() > deadline:
                logger.warning("engine idle policy: tick over its %ss budget; the next one goes on",
                               TICK_BUDGET_SECONDS)
                return []
            for feature, (depth, marked) in signals.items():
                profile = applied_profile(db, engine.id, feature)
                if profile is None or not profile.profile.get("idle_cooldown"):
                    continue
                opt = opt_in_of(db, engine.id, feature)
                action = decide(db, engine, feature, profile, depth, at, opt.actor if opt else None,
                                idle_signals.demanded(engine, marked))
                if not action:
                    continue
                if not opt or opt.revision != profile.revision:
                    _warn_no_opt_in(engine.id, feature, profile, action)
                    continue
                waiting = (depth or 0) + _routed_backlog(db, engine.id, feature, at)
                candidates.append((engine.id, feature, action, opt.actor, opt.revision, profile.applied_at, waiting))
    done = []
    for engine_id, feature, action, actor, revision, applied_at, waiting in candidates:
        if clock() > deadline:
            break
        try:
            operation_id = _enqueue(session_factory, engine_id, feature, action, actor, at, waiting, revision,
                                    applied_at)
        except service.ControlError as exc:
            # Busy resource, stale version, host not ready: the next tick looks again.
            logger.info("engine idle policy: %s %s/%s refused: %s", action, engine_id, feature, exc)
            continue
        except Exception:  # noqa: BLE001 - a lock wait on one engine never skips the others
            logger.exception("engine idle policy: %s %s/%s failed", action, engine_id, feature)
            continue
        if operation_id:
            done.append((engine_id, feature, action, operation_id))
    return done
