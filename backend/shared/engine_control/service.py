"""SQL truth, short transactions, idempotent operations and fenced events."""

import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from shared.models import Engine, EngineUsage, AdminAudit
from shared.engine_control.models import (
    RuntimeProfile,
    ControlResource,
    OperationPlan,
    EngineOperation,
    OperationEvent,
    OperationOutbox,
    ControlHost,
)
from shared.engine_control.contracts import RuntimeSettings, TERMINAL
from shared.engine_control import registry, catalog
from shared.engines import budget
from shared.engines.redact import redact


class ControlError(Exception):
    def __init__(self, code, status=409, message=None):
        self.code, self.status = code, status
        super().__init__(message or code)


def now():
    return datetime.utcnow()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def clean(value):
    # Filter recursively BEFORE persistence, including structured errors/handles.
    if isinstance(value, str):
        return redact(
            re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]", "", value)
        )[:8192]
    if isinstance(value, dict):
        return {
            k: clean(v)
            for k, v in value.items()
            if not re.search(r"token|secret|password|credential", k, re.I)
        }
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value[:100]]
    return value


def locked_engine(db, engine_id):
    e = (
        db.query(Engine)
        .filter((Engine.id == engine_id) | (Engine.slug == engine_id))
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not e:
        raise ControlError("ENGINE_NOT_FOUND", 404)
    return e


def active_operation(db, engine_id):
    return (
        db.query(EngineOperation)
        .filter(
            EngineOperation.engine_id == engine_id, ~EngineOperation.state.in_(TERMINAL)
        )
        .with_for_update()
        .first()
    )


def latest_profile(db, engine_id, feature, revision=None):
    q = db.query(RuntimeProfile).filter_by(engine_id=engine_id, feature=feature)
    if revision is not None:
        q = q.filter_by(revision=revision)
    return q.order_by(RuntimeProfile.revision.desc()).first()


def profile_view(p):
    return (
        dict(
            id=p.id,
            feature=p.feature,
            revision=p.revision,
            profile=p.profile,
            applied_at=p.applied_at,
            created_at=p.created_at,
        )
        if p
        else None
    )


def capabilities(db, engine, feature=None):
    d = registry.descriptor(engine.adapter_type)
    from shared.config import get_settings

    if not get_settings().engine_control_enabled:
        return dict(
            d,
            managed=False,
            hosts=[],
            actions=[
                dict(
                    type=a, supported=True, enabled=False, reason="CONTROL_NOT_ENABLED"
                )
                for a in d["actions"]
            ],
        )
    actions = []
    latest = (
        latest_profile(db, engine.id, feature)
        if feature is not None
        else db.query(RuntimeProfile)
        .filter_by(engine_id=engine.id)
        .order_by(RuntimeProfile.created_at.desc(), RuntimeProfile.revision.desc())
        .first()
    )
    dependency = None
    if d["execution_mode"] == "queue":
        if latest is None:
            dependency = "RUNTIME_PROFILE_REQUIRED"
        else:
            host_id = (latest.profile.get("provider_settings") or {}).get("host_id")
            h = db.get(ControlHost, host_id) if host_id else None
            if not h or h.seen_at < now() - timedelta(seconds=30):
                dependency = "HOST_AGENT_NOT_READY"
    if (
        not __import__("shared.config", fromlist=["get_settings"])
        .get_settings()
        .engine_control_enabled
    ):
        dependency = "CONTROL_NOT_ENABLED"
    for a in d["actions"]:
        reason = dependency
        if (
            d.get("credential_fields")
            and a not in ("test", "reconcile")
            and not engine.credentials_sealed
        ):
            reason = "CREDENTIALS_REQUIRED"
        if d.get("requires_cleanup_watchdog") and a in (
            "start",
            "warmup",
            "deploy",
            "apply_profile",
            "restart",
        ):
            try:
                from shared.redis_client import get_redis_client

                stamp = get_redis_client().client.get("engine-control:watchdog")
                if stamp is None or time.time() - float(stamp) > 30:
                    reason = "CLEANUP_WATCHDOG_NOT_READY"
            except Exception:
                reason = "CLEANUP_WATCHDOG_NOT_READY"

        actions.append(
            dict(type=a, supported=True, enabled=reason is None, reason=reason)
        )
    return dict(
        d,
        actions=actions,
        managed=bool(latest),
        hosts=[
            dict(id=h.id, seen_at=h.seen_at, services=h.inventory.get("services", []))
            for h in db.query(ControlHost)
        ],
    )


def save_profile(db, engine, feature, raw, version, actor):
    engine = locked_engine(db, engine.id)
    if engine.version != version:
        raise ControlError("VERSION_CONFLICT")
    if active_operation(db, engine.id):
        raise ControlError("OPERATION_CONFLICT")
    if (
        db.query(ControlResource)
        .filter_by(owner_engine_id=engine.id)
        .filter(ControlResource.operation_id.isnot(None))
        .first()
    ):
        raise ControlError("RESOURCE_LOCKED")
    p = RuntimeSettings.model_validate(raw).model_dump(mode="json")
    driver = registry.create(engine.adapter_type, p["adapter_version"])
    p = driver.validate(engine, feature, p, db)
    old = latest_profile(db, engine.id, feature)
    row = RuntimeProfile(
        engine_id=engine.id,
        feature=feature,
        revision=(old.revision if old else 0) + 1,
        profile=p,
    )
    db.add(row)
    # Establish canonical ownership before management is enabled. Aliases cannot diverge.
    for key in sorted(driver.resource_keys(engine, feature, p)):
        r = db.get(ControlResource, key)
        if r and r.owner_engine_id != engine.id:
            raise ControlError("RESOURCE_OWNED_BY_ANOTHER_ENGINE")
        if r is None:
            db.add(ControlResource(key=key, owner_engine_id=engine.id))
    engine.version += 1
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="jwt",
            action="engine.profile_created",
            target_type="engine",
            target_id=engine.id,
            before=None,
            after={"feature": feature, "revision": row.revision},
        )
    )
    db.commit()
    return profile_view(row)


def create_plan(db, engine, req, actor):
    engine = locked_engine(db, engine.id)
    if engine.version != req.engine_version:
        raise ControlError("VERSION_CONFLICT")
    cap = next(
        (
            a
            for a in capabilities(db, engine, req.feature)["actions"]
            if a["type"] == req.type
        ),
        None,
    )
    if cap is None or not cap["enabled"]:
        raise ControlError(
            cap["reason"] if cap else "ACTION_UNSUPPORTED", 503 if cap else 422
        )
    p = latest_profile(db, engine.id, req.feature, req.profile_revision)
    if not p and req.type not in ("test", "reconcile"):
        raise ControlError("RUNTIME_PROFILE_REQUIRED", 422)
    driver = registry.create(engine.adapter_type)
    profile = p.profile if p else {}
    try:
        body = driver.plan(engine, req, profile, db)
    except ValueError as exc:
        raise ControlError("INVALID_OPERATION", 422, str(exc)) from None
    body.update(
        adapter_type=engine.adapter_type,
        adapter_version=1,
        engine_id=engine.id,
        feature=req.feature,
        type=req.type,
        profile=profile,
        profile_revision=p.revision if p else None,
        drain_timeout_seconds=req.drain_timeout_seconds,
        max_usd=str(req.max_usd),
    )
    body["resources"] = sorted(driver.resource_keys(engine, req.feature, profile))
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine.id, feature=req.feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    if applied:
        body["resources"] = sorted(
            set(body["resources"])
            | set(driver.resource_keys(engine, req.feature, applied.profile))
        )
    body["credentials_revision"] = str(engine.credentials_updated_at)
    body["engine_config_hash"] = digest(
        {"config": engine.config, "deployments": engine.deployments}
    )
    body = clean(body)
    plan = OperationPlan(
        engine_id=engine.id,
        actor_id=actor,
        engine_version=engine.version,
        profile_id=p.id if p else None,
        body=body,
        hash=digest(body),
        expires_at=now() + timedelta(minutes=5),
    )
    db.add(plan)
    db.commit()
    return dict(
        plan_id=plan.id, plan_hash=plan.hash, expires_at=plan.expires_at, **body
    )


def enqueue(db, plan_id, plan_hash, key, actor, confirm_paid=False):
    if not key or len(key) > 128:
        raise ControlError("IDEMPOTENCY_KEY_REQUIRED", 422)
    request_hash = digest(
        dict(plan_id=plan_id, plan_hash=plan_hash, confirm_paid=confirm_paid)
    )
    existing = (
        db.query(EngineOperation).filter_by(actor_id=actor, idempotency_key=key).first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise ControlError("IDEMPOTENCY_CONFLICT")
        return operation_view(existing)
    plan = db.get(OperationPlan, plan_id)
    if not plan or plan.actor_id != actor:
        raise ControlError("PLAN_NOT_FOUND", 404)
    e = locked_engine(db, plan.engine_id)
    # The first lookup may precede a concurrent commit. A locking read sees the
    # accepted request after waiting for the engine lock under InnoDB RR.
    existing = (
        db.query(EngineOperation)
        .filter_by(actor_id=actor, idempotency_key=key)
        .with_for_update()
        .first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise ControlError("IDEMPOTENCY_CONFLICT")
        return operation_view(existing)
    if (
        plan.expires_at <= now()
        or plan.hash != plan_hash
        or e.version != plan.engine_version
    ):
        raise ControlError("PLAN_STALE")
    if (
        digest({"config": e.config, "deployments": e.deployments})
        != plan.body["engine_config_hash"]
    ):
        raise ControlError("PLAN_STALE")
    if active_operation(db, e.id):
        raise ControlError("OPERATION_CONFLICT")
    estimate = Decimal(plan.body.get("estimated_max_usd", "0"))
    period = budget.period_start(e, now())
    if estimate:
        if not confirm_paid or Decimal(plan.body["max_usd"]) < estimate:
            raise ControlError("PAID_CONFIRMATION_REQUIRED", 422)
        if not budget.admits(db, e, estimate, period):
            raise ControlError("BUDGET_INSUFFICIENT")
    op_id = str(uuid4())
    for key_ in plan.body["resources"]:
        r = db.query(ControlResource).filter_by(key=key_).with_for_update().first()
        if not r:
            r = ControlResource(key=key_, owner_engine_id=e.id)
            db.add(r)
        elif r.owner_engine_id != e.id:
            raise ControlError("RESOURCE_OWNERSHIP_CONFLICT")
        if r.operation_id:
            raise ControlError("RESOURCE_LOCKED")
        r.operation_id = op_id
    op = EngineOperation(
        id=op_id,
        engine_id=e.id,
        actor_id=actor,
        plan_id=plan.id,
        idempotency_key=key,
        request_hash=request_hash,
        deadline=now() + timedelta(seconds=3600 + plan.body["drain_timeout_seconds"]),
        reserved_usd=estimate,
        period_start=period,
    )
    db.add(op)
    db.add(OperationOutbox(operation_id=op_id))
    db.flush()
    append_event(db, op, "operation.accepted", {"message": "Operação aceita"})
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="jwt",
            action="engine.operation_created",
            target_type="engine",
            target_id=e.id,
            before=None,
            after={"operation_id": op_id, "type": plan.body["type"]},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(EngineOperation)
            .filter_by(actor_id=actor, idempotency_key=key)
            .first()
        )
        if existing and existing.request_hash == request_hash:
            return operation_view(existing)
        raise ControlError("OPERATION_CONFLICT") from None
    return operation_view(op)


def operation_view(op):
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
        error=op.error,
        reserved_usd=str(op.reserved_usd),
        actual_usd=str(op.actual_usd) if op.actual_usd is not None else None,
        cost_confirmed=op.cost_confirmed,
        created_at=op.created_at,
        started_at=op.started_at,
        finished_at=op.finished_at,
        events_url=f"/admin/engine-operations/{op.id}/events",
    )


def append_event(db, op, kind, payload):
    payload = clean(payload)
    if kind == "log":
        size = len(json.dumps(payload).encode())
        if op.log_bytes >= 1048576:
            return
        if op.log_bytes + size > 1048576:
            payload = {
                "message": "Limite de logs atingido; etapas continuam disponíveis."
            }
            kind = "log.truncated"
        op.log_bytes += size
    op.seq += 1
    db.add(
        OperationEvent(
            operation_id=op.id, seq=op.seq, type=kind, stage=op.stage, payload=payload
        )
    )


def claim(db, op_id, holder):
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if not op or op.state in TERMINAL:
        return None
    if op.state in ("running", "reconciling"):
        # Expired lease does not authorize repeating an external effect.
        if op.lease_until and op.lease_until > now():
            return None
        if op.effect_started:
            op.state = "needs_attention"
            op.error = {
                "code": "EXECUTOR_LOST",
                "message": "Reconcilie o efeito externo antes de liberar recursos.",
            }
            append_event(db, op, "operation.needs_attention", op.error)
            db.commit()
            return None
    op.generation += 1
    op.handles = dict(op.handles or {}, executor_exited=False)
    op.state = "running"
    op.holder = holder
    op.started_at = op.started_at or now()
    op.lease_until = now() + timedelta(seconds=30)
    append_event(db, op, "operation.running", {"message": "Executor iniciou"})
    db.commit()
    return op.generation


def fenced(db, op_id, generation):
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if (
        not op
        or op.generation != generation
        or op.state in TERMINAL
        or not op.lease_until
        or op.lease_until <= now()
    ):
        raise ControlError("LEASE_LOST")
    return op


def heartbeat(db, op_id, generation):
    op = fenced(db, op_id, generation)
    op.lease_until = now() + timedelta(seconds=30)
    db.commit()


def event(
    db, op_id, generation, stage, payload=None, kind="stage.changed", effect=False
):
    op = fenced(db, op_id, generation)
    op.stage = stage
    if effect:
        op.effect_started = True
    append_event(db, op, kind, payload or {"message": stage})
    db.commit()


def finish(db, op_id, generation, state, result=None, error=None, safe=False):
    op = fenced(db, op_id, generation)
    if state not in TERMINAL:
        raise ValueError("Invalid terminal state")
    op.state = state
    op.result = clean(result or {})
    op.error = clean(error)
    op.finished_at = now()
    if safe:
        for r in (
            db.query(ControlResource)
            .filter_by(operation_id=op_id)
            .order_by(ControlResource.key)
            .with_for_update()
        ):
            r.operation_id = None
            r.gate_closed = False
            if state == "succeeded":
                r.observed = op.result
                r.observed_at = now()
        if not op.effect_started:
            op.reserved_usd = 0
            op.actual_usd = 0
            op.cost_confirmed = True
        if op.reserved_usd == 0:
            op.actual_usd = 0
            op.cost_confirmed = True
    append_event(db, op, "operation." + state, {"result": op.result, "error": op.error})
    db.commit()
    return operation_view(op)


def request_cancel(db, op_id):
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if not op:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    if op.state not in TERMINAL:
        op.cancel_requested = True
        append_event(db, op, "cancel.requested", {"message": "Cancelamento solicitado"})
        db.commit()
    return operation_view(op)


def events(db, op_id, after=0, limit=100):
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


def publish_applied(db, op_id, generation, observed):
    snapshot = db.get(EngineOperation, op_id)
    if not snapshot:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    e = locked_engine(db, snapshot.engine_id)
    op = fenced(db, op_id, generation)
    plan = db.get(OperationPlan, op.plan_id)
    if plan.body["type"] in ("test", "reconcile"):
        return
    if e.version != plan.engine_version:
        raise ControlError("VERSION_CONFLICT")
    if plan.profile_id:
        p = db.get(RuntimeProfile, plan.profile_id)
        if plan.body["type"] not in ("test", "reconcile"):
            config = dict(e.config or {})
            features = dict(config.get("features") or {})
            if plan.body["feature"] != "live-transcription":
                binding = dict(p.profile["binding"])
                if plan.body["type"] in ("cooldown", "drain_stop"):
                    binding["workers"] = 0
                features[plan.body["feature"]] = binding
            config["features"] = features
            if (op.handles or {}).get("deployment"):
                config["control_fingerprint_version"] = 2
                config["control_memory_mb"] = p.profile.get("memory_mb")
                e.deployments = dict(
                    e.deployments or {},
                    **{plan.body["feature"]: op.handles["deployment"]},
                )
            if observed.get("deployment_stopped"):
                deployments = dict(e.deployments or {})
                deployments.pop(plan.body["feature"], None)
                e.deployments = deployments
            e.config = config
            p.applied_at = now()
            e.version += 1
            for r in db.query(ControlResource).filter_by(operation_id=op_id):
                modes = dict((r.applied or {}).get("feature_modes") or {})
                modes[plan.body["feature"]] = (
                    "stopped"
                    if plan.body["type"] == "drain_stop"
                    else "standby" if plan.body["type"] == "cooldown" else "running"
                )
                r.applied = {
                    "profile_id": p.id,
                    "revision": p.revision,
                    "type": plan.body["type"],
                    "feature": p.feature,
                    "feature_modes": modes,
                }
    db.commit()


def runtime_status(db, engine):
    resources = db.query(ControlResource).filter_by(owner_engine_id=engine.id).all()
    profiles_ = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine.id)
        .order_by(RuntimeProfile.revision.desc())
        .all()
    )
    latest = {}
    for p in profiles_:
        latest.setdefault(p.feature, profile_view(p))
    return dict(
        desired=latest,
        applied=[profile_view(p) for p in profiles_ if p.applied_at],
        resources=[
            dict(
                key=r.key,
                maintenance=r.gate_closed,
                operation_id=r.operation_id,
                applied=r.applied,
                observed=r.observed,
                observed_at=r.observed_at,
            )
            for r in resources
        ],
    )


def request_recovery(db, op_id):
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if not op or op.state != "needs_attention":
        raise ControlError("RECOVERY_NOT_REQUIRED")
    if not (op.handles or {}).get("executor_exited"):
        raise ControlError("EXECUTOR_NOT_NEUTRALIZED")
    op.handles = dict(op.handles or {}, recovery_mode=True)
    op.state = "queued"
    op.cancel_requested = False
    op.deadline = now() + timedelta(minutes=5)
    op.lease_until = None
    row = db.get(OperationOutbox, op.id)
    row.published_at = None
    append_event(
        db,
        op,
        "recovery.requested",
        {"message": "Reconciliar estado sem repetir o efeito externo"},
    )
    db.commit()
    return operation_view(op)
