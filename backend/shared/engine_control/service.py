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
from shared import error_catalog


class ControlError(Exception):
    """A refusal with a stable machine `code` (0009). `str()` keeps the code (or the
    explicit technical message) for logs and callers that match on it; `detail()`
    adds the Portuguese message and next steps from `shared.error_catalog`.
    """

    def __init__(
        self,
        code,
        status=409,
        message=None,
        *,
        cause=None,
        context=None,
        feature=None,
        needs_connection=False,
    ):
        self.code, self.status, self.cause = code, status, cause
        self.context, self.feature = dict(context or {}), feature
        self.needs_connection = needs_connection
        super().__init__(message or code)

    def detail(self):
        text = str(self)
        return error_catalog.detail(
            self.code,
            text=None if text == self.code else text,
            cause=self.cause,
            context=self.context,
            feature=self.feature,
            needs_connection=self.needs_connection,
        )


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
            source_profile_revision_id=p.source_profile_revision_id,
            source_hash=p.source_hash,
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
    host_context = {}
    if d["execution_mode"] == "queue":
        if latest is None:
            dependency = "RUNTIME_PROFILE_REQUIRED"
        else:
            host_id = (latest.profile.get("provider_settings") or {}).get("host_id")
            h = db.get(ControlHost, host_id) if host_id else None
            if not h or h.seen_at < now() - timedelta(seconds=30):
                dependency = "HOST_AGENT_NOT_READY"
                host_context = error_catalog.host_context(host_id, h)
    if (
        not __import__("shared.config", fromlist=["get_settings"])
        .get_settings()
        .engine_control_enabled
    ):
        dependency = "CONTROL_NOT_ENABLED"
    connect_first = error_catalog.needs_connection(engine, d)
    # Remote runners (Modal) also cannot plan anything but test/reconcile without a
    # desired profile for this feature: say so up front instead of failing on submit.
    remote_unbound = (
        dependency is None and d["execution_mode"] != "queue" and latest is None
    )
    for a in d["actions"]:
        reason = dependency
        if remote_unbound and a not in error_catalog.PROFILE_ACTIONS_EXEMPT:
            reason = (
                "NOTHING_TO_COOL_DOWN" if a == "cooldown" else "RUNTIME_PROFILE_REQUIRED"
            )
        if (
            d.get("credential_fields")
            and a not in ("test", "reconcile")
            and not engine.credentials_sealed
        ):
            reason = "CREDENTIALS_REQUIRED"
        if reason is None and d.get("requires_cleanup_watchdog") and a in (
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

        message, steps = error_catalog.describe(
            reason,
            feature=feature,
            needs_connection=connect_first,
            **(host_context if reason == "HOST_AGENT_NOT_READY" else {}),
        )
        actions.append(
            dict(
                type=a,
                supported=True,
                enabled=reason is None,
                reason=reason,
                message=message,
                next_steps=steps,
            )
        )
    # The first thing to fix, in the order the admin has to do it.
    if d.get("credential_fields") and not engine.credentials_sealed:
        setup_code, setup_context = "CREDENTIALS_REQUIRED", {}
    elif dependency == "CONTROL_NOT_ENABLED":
        setup_code, setup_context = dependency, {}
    elif latest is None:
        setup_code, setup_context = "RUNTIME_PROFILE_REQUIRED", {}
    elif connect_first:
        setup_code, setup_context = "TEST_CONNECTION_FIRST", {}
    elif dependency == "HOST_AGENT_NOT_READY":
        setup_code, setup_context = dependency, host_context
    else:
        setup_code, setup_context = None, {}
    setup_message, setup_steps = error_catalog.describe(
        setup_code, feature=feature, needs_connection=connect_first, **setup_context
    )
    return dict(
        d,
        actions=actions,
        # 0009 CA1: what is missing before operating this feature, and what to do next.
        setup=dict(
            feature=feature,
            profile_bound=latest is not None,
            connection_verified=None
            if not d.get("requires_control_identity")
            else not connect_first,
            code=setup_code,
            message=setup_message,
            next_steps=setup_steps,
        ),
        managed=bool(latest),
        hosts=[
            dict(id=h.id, seen_at=h.seen_at, services=h.inventory.get("services", []))
            for h in db.query(ControlHost)
        ],
    )


def save_profile(
    db,
    engine,
    feature,
    raw,
    version,
    actor,
    *,
    source_profile_revision_id=None,
    source_hash=None,
    audit_extra=None,
):
    from shared.access import policy

    if policy.enabled():
        policy.epoch(db, True)
        if not source_profile_revision_id:
            from shared.access.service import bootstrap

            bootstrap(db, actor)
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
    origin = (
        source_profile(db, source_profile_revision_id)
        if source_profile_revision_id
        else None
    )
    if source_profile_revision_id:
        from shared.access.models import ExecutionRevision, EngineAttributes

        revision = db.get(ExecutionRevision, source_profile_revision_id)
        attributes = db.get(EngineAttributes, engine.id)
        if (
            not origin
            or not revision.published_at
            or origin.status == "archived"
            or revision.content_hash != source_hash
        ):
            raise ControlError("PUBLISHED_REVISION_REQUIRED", 422)
        if (
            origin.adapter_type != engine.adapter_type
            or origin.feature != feature
            or not attributes
            or attributes.environment != origin.environment
        ):
            raise ControlError("PROFILE_INCOMPATIBLE", 422)
        template = dict(p, warm_until=None)
        if template != revision.settings:
            raise ControlError("PROFILE_CONTENT_MISMATCH", 422)
        if (
            digest(catalog.get(p["model_profile_id"], engine.adapter_type, feature))
            != revision.model_fingerprint
        ):
            raise ControlError("MODEL_METADATA_CHANGED")
        if revision.warm_for_seconds:
            from shared.engine_control.contracts import utc_deadline

            remaining = (
                (utc_deadline(p["warm_until"]) - now()).total_seconds()
                if p["warm_until"]
                else 0
            )
            if not 0 < remaining <= revision.warm_for_seconds:
                raise ControlError("INVALID_WARM_DEADLINE", 422)
        elif p["warm_until"]:
            raise ControlError("INVALID_WARM_DEADLINE", 422)
    driver = registry.create(engine.adapter_type, p["adapter_version"])
    p = driver.validate(engine, feature, p, db)
    affected = set(driver.resource_keys(engine, feature, p))
    previous = latest_profile(db, engine.id, feature)
    applied = (
        db.query(RuntimeProfile)
        .filter_by(engine_id=engine.id, feature=feature)
        .filter(RuntimeProfile.applied_at.isnot(None))
        .order_by(RuntimeProfile.applied_at.desc())
        .first()
    )
    for before in (previous, applied):
        if before:
            affected.update(driver.resource_keys(engine, feature, before.profile))
    if policy.enabled():
        # The same grant covers binding, the resolved runtime and every consumer.
        policy.authorize(
            db,
            actor,
            "engine_runtime.bind",
            engine=engine,
            feature=feature,
            profile=origin,
            runtime=p,
            resources=sorted(affected),
            lock=True,
        )
    old = latest_profile(db, engine.id, feature)
    row = RuntimeProfile(
        engine_id=engine.id,
        feature=feature,
        revision=(old.revision if old else 0) + 1,
        profile=p,
        source_profile_revision_id=source_profile_revision_id,
        source_hash=source_hash,
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
            after={"feature": feature, "revision": row.revision, **(audit_extra or {})},
        )
    )
    db.commit()
    return profile_view(row)


def _host_context(db, engine_id, feature):
    latest = latest_profile(db, engine_id, feature)
    host_id = ((latest.profile if latest else {}).get("provider_settings") or {}).get(
        "host_id"
    )
    return error_catalog.host_context(host_id, db.get(ControlHost, host_id) if host_id else None)


def create_plan(db, engine, req, actor):
    from shared.access import policy

    if policy.enabled():
        policy.epoch(db, True)
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
    connect_first = error_catalog.needs_connection(
        engine, registry.descriptor(engine.adapter_type)
    )
    if cap is None or not cap["enabled"]:
        reason = cap["reason"] if cap else "ACTION_UNSUPPORTED"
        status = {
            "ACTION_UNSUPPORTED": 422,
            "RUNTIME_PROFILE_REQUIRED": 422,
            "NOTHING_TO_COOL_DOWN": 409,
            "ACCESS_DENIED": 403,
        }.get(reason, 503)
        raise ControlError(
            reason,
            status,
            feature=req.feature,
            needs_connection=connect_first,
            context=_host_context(db, engine.id, req.feature)
            if reason == "HOST_AGENT_NOT_READY"
            else None,
        )
    p = latest_profile(db, engine.id, req.feature, req.profile_revision)
    if not p and req.type not in error_catalog.PROFILE_ACTIONS_EXEMPT:
        if req.type == "cooldown" and req.profile_revision is None:
            # Without a desired profile no control operation ever warmed this
            # feature (every effectful plan needs one), so there is nothing to release.
            raise ControlError(
                "NOTHING_TO_COOL_DOWN", 409, feature=req.feature,
                needs_connection=connect_first,
            )
        raise ControlError(
            "RUNTIME_PROFILE_REQUIRED", 422, feature=req.feature,
            needs_connection=connect_first,
        )
    driver = registry.create(engine.adapter_type)
    if p:
        validate_source_model(db, p.source_profile_revision_id)
    profile = p.profile if p else {}
    try:
        body = driver.plan(engine, req, profile, db)
    except ValueError as exc:
        raise ControlError(
            "INVALID_OPERATION", 422, str(exc),
            cause=error_catalog.split(str(exc))[0],
            context=getattr(exc, "context", None),
            feature=req.feature, needs_connection=connect_first,
        ) from None
    body.update(
        adapter_type=engine.adapter_type,
        adapter_version=1,
        engine_id=engine.id,
        feature=req.feature,
        type=req.type,
        profile=profile,
        profile_revision=p.revision if p else None,
        source_profile_revision_id=p.source_profile_revision_id if p else None,
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
    if policy.enabled():
        body["authorization"] = policy.authorize(
            db,
            actor,
            {"engine_operations.plan", "engine_operations.execute." + req.type},
            engine=engine,
            feature=req.feature,
            runtime=profile,
            profile=source_profile(db, p.source_profile_revision_id) if p else None,
            max_usd=req.max_usd,
            resources=body["resources"],
            lock=True,
        )
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
    from shared.access import policy

    if policy.enabled():
        policy.epoch(db, True)
        authority_plan = db.get(OperationPlan, plan_id)
        if not authority_plan or authority_plan.actor_id != actor:
            raise ControlError("PLAN_NOT_FOUND", 404)
        b = authority_plan.body
        validate_source_model(db, b.get("source_profile_revision_id"))
        policy.authorize(
            db,
            actor,
            "engine_operations.execute." + b["type"],
            engine=db.get(Engine, authority_plan.engine_id),
            feature=b["feature"],
            profile=source_profile(db, b.get("source_profile_revision_id")),
            runtime=b.get("profile"),
            resources=b.get("resources"),
            max_usd=b.get("max_usd"),
            lock=True,
        )
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
        error=error_catalog.operation_error(op.error),
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
    if effect:
        admit_effect(db, op_id, generation, "stage:" + stage)
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
        from shared.access import policy

        if policy.enabled() and state == "succeeded":
            from shared.access.models import EffectAdmission

            db.query(EffectAdmission).filter_by(
                operation_id=op_id, generation=generation
            ).update({"state": "confirmed"})
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


def request_cancel(db, op_id, actor=None):
    authorize_operation(db, op_id, actor, "engine_operations.cancel", lock=True)
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if not op:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    if op.state not in TERMINAL:
        op.cancel_requested = True
        op.cancel_requested_by = actor
        if actor:
            from shared.access.policy import audit

            audit(db, actor, "engine.cancel_requested", op.id)
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


def request_recovery(db, op_id, actor=None):
    authorize_operation(db, op_id, actor, "engine_operations.recover", lock=True)
    op = db.query(EngineOperation).filter_by(id=op_id).with_for_update().first()
    if not op or op.state != "needs_attention":
        raise ControlError("RECOVERY_NOT_REQUIRED")
    if not (op.handles or {}).get("executor_exited"):
        raise ControlError("EXECUTOR_NOT_NEUTRALIZED")
    op.handles = dict(op.handles or {}, recovery_mode=True)
    op.recovery_requested_by = actor
    if actor:
        from shared.access.policy import audit

        audit(db, actor, "engine.recovery_requested", op.id)
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


def authorize_operation(
    db, op_id, actor, permission="engine_operations.read", lock=False
):
    from shared.access import policy

    if not policy.enabled():
        return db.get(EngineOperation, op_id)
    if lock:
        policy.epoch(db, True)
    op = db.query(EngineOperation).filter_by(id=op_id).populate_existing().first()
    if not op:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    plan = db.get(OperationPlan, op.plan_id)
    try:
        reading = permission == "engine_operations.read"
        policy.authorize(
            db,
            actor,
            permission,
            engine=db.get(Engine, op.engine_id),
            profile=(
                source_profile(db, plan.body.get("source_profile_revision_id"))
                if reading
                else None
            ),
            runtime=plan.body.get("profile") if reading else None,
            feature=plan.body["feature"],
            resources=plan.body.get("resources"),
            lock=lock,
        )
    except ControlError as exc:
        if permission == "engine_operations.read":
            raise ControlError("OPERATION_NOT_FOUND", 404) from None
        raise exc
    return op


def admit_effect(db, op_id, generation, step, executor="control"):
    """Serialize a durable admission with revocation; release SQL before the SDK call.

    An admitted call may already be in flight when permission is revoked. A crash
    leaves this record uncertain and the existing operation fencing prevents replay.
    """
    from shared.access import policy
    from shared.access.models import EffectAdmission

    if not policy.enabled():
        return
    policy.epoch(db, True)
    op = db.query(EngineOperation).filter_by(id=op_id).populate_existing().first()
    if not op:
        raise ControlError("OPERATION_NOT_FOUND", 404)
    decision = policy.operation_authority(db, op, effect=True)
    op = fenced(db, op_id, generation)
    if op.cancel_requested or op.deadline <= now():
        raise ControlError("OPERATION_ABORTED")
    if (
        db.query(EffectAdmission)
        .filter_by(operation_id=op_id, generation=generation, step=step)
        .first()
    ):
        raise ControlError("EFFECT_ALREADY_ADMITTED")
    actor = (
        op.recovery_requested_by
        if (op.handles or {}).get("recovery_mode")
        else op.actor_id
    )
    db.add(
        EffectAdmission(
            operation_id=op_id,
            generation=generation,
            step=step,
            actor_id=actor,
            executor=(op.handles or {}).get("host_id") or op.holder or executor,
            epoch=decision["epoch"],
            state="uncertain",
            action=db.get(OperationPlan, op.plan_id).body["type"],
            targets=db.get(OperationPlan, op.plan_id).body.get("resources", []),
            decision=decision,
            valid_until=op.deadline,
        )
    )
    op.effect_started = True
    db.flush()


def source_profile(db, revision_id):
    if not revision_id:
        return None
    from shared.access.models import ExecutionRevision, ExecutionProfile

    r = db.get(ExecutionRevision, revision_id)
    return db.get(ExecutionProfile, r.profile_id) if r else None


def validate_source_model(db, revision_id):
    if not revision_id:
        return
    from shared.access.models import ExecutionRevision

    r = db.get(ExecutionRevision, revision_id)
    p = source_profile(db, revision_id)
    if not r or not p:
        raise ControlError("SOURCE_PROFILE_NOT_FOUND")
    try:
        current = catalog.get(r.settings["model_profile_id"], p.adapter_type, p.feature)
    except ValueError as exc:
        raise ControlError("MODEL_METADATA_CHANGED") from exc
    if digest(current) != r.model_fingerprint:
        raise ControlError("MODEL_METADATA_CHANGED")
