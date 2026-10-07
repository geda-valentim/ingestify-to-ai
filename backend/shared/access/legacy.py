"""Frozen human authority for legacy tasks; explicit OS bootstrap for direct CLI.

System billing/probing have separate entrypoints and never call human test-all.
"""

from contextvars import ContextVar
from datetime import datetime, timedelta
from shared.access import policy
from shared.access.models import LegacyRequest, ServicePrincipal
from shared.engine_control import service, registry
from shared.engine_control.models import EngineOperation, OperationPlan
from shared.models import Engine, AdminAudit
from shared.config import get_settings

installation_context = ContextVar("installation_principal", default=None)


def installation(db, principal=None):
    principal = principal or installation_context.get()
    expected = get_settings().engine_installation_principal_id
    p = (
        db.query(ServicePrincipal)
        .filter_by(id=principal)
        .populate_existing()
        .with_for_update()
        .first()
        if principal
        else None
    )
    if (
        not expected
        or principal != expected
        or not p
        or not p.active
        or p.purpose != "installation_cli"
    ):
        raise service.ControlError("INSTALLATION_PRINCIPAL_REQUIRED", 403)
    return p.id


def accept(db, actor, action, engines):
    if not policy.enabled():
        return None
    authority = policy.epoch(db, True)
    for e in engines:
        policy.authorize(
            db,
            actor,
            "engine_operations.execute." + action,
            engine=e,
            feature="transcription",
            lock=True,
        )
    req = LegacyRequest(
        actor_id=actor,
        action=action,
        engine_ids=[e.id for e in engines],
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        epoch=authority.version,
    )
    db.add(req)
    db.flush()
    policy.audit(
        db,
        actor,
        "engine.legacy_accepted",
        req.id,
        {"action": action, "engine_ids": req.engine_ids},
    )
    db.commit()
    return req.id


def authorize(db, engine, action, context=None):
    if not policy.enabled():
        return
    policy.epoch(db, True)
    if isinstance(context, dict) and context.get("operation_id"):
        op = service.fenced(db, context["operation_id"], context["generation"])
        plan = db.get(OperationPlan, op.plan_id)
        if op.engine_id != engine.id or plan.body["type"] != action:
            raise service.ControlError("LEGACY_CONTEXT_INVALID", 403)
        return policy.operation_authority(db, op, effect=True)
    if isinstance(context, str):
        req = db.get(LegacyRequest, context)
        if (
            not req
            or req.expires_at <= datetime.utcnow()
            or req.action != action
            or engine.id not in req.engine_ids
        ):
            raise service.ControlError("LEGACY_CONTEXT_INVALID", 403)
        p = service.latest_profile(db, engine.id, "transcription")
        return policy.authorize(
            db,
            req.actor_id,
            "engine_operations.execute." + action,
            engine=engine,
            feature="transcription",
            profile=(
                service.source_profile(db, p.source_profile_revision_id) if p else None
            ),
            runtime=p.profile if p else None,
            resources=registry.create(engine.adapter_type).resource_keys(
                engine, "transcription", p.profile if p else {}
            ),
            lock=True,
        )
    actor = installation(
        db,
        (
            (context or {}).get("installation_principal")
            if isinstance(context, dict)
            else None
        ),
    )
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="cli",
            action="engine.cli_" + action,
            target_type="engine",
            target_id=engine.id,
        )
    )


def admit_cli_deploy(db, engine, feature):
    """Use the existing canonical resource fence for an unmanaged bootstrap deploy.

    A crash retains locks and an uncertain admission; never retry it blindly.
    Managed engines continue to require the durable engine-control operation API.
    """
    from uuid import uuid4
    from shared.access.models import EffectAdmission
    from shared.engine_control.models import ControlResource
    from shared.engines.capacity import bindings

    authority = policy.epoch(db, True)
    actor = installation(db)
    operation_id = str(uuid4())
    profile = {
        "binding": bindings(engine.config or {})[feature].model_dump(mode="json")
    }
    keys = registry.create(engine.adapter_type).resource_keys(engine, feature, profile)
    for key in sorted(keys):
        r = (
            db.query(ControlResource)
            .filter_by(key=key)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if not r:
            r = ControlResource(key=key, owner_engine_id=engine.id)
            db.add(r)
        if r.owner_engine_id != engine.id or r.operation_id:
            raise service.ControlError("RESOURCE_LOCKED")
        r.operation_id = operation_id
        r.gate_closed = True
    db.add(
        EffectAdmission(
            operation_id=operation_id,
            generation=0,
            step="cli:deploy",
            actor_id=actor,
            executor="installation_cli",
            epoch=authority.version,
            state="uncertain",
            action="deploy",
            targets=keys,
            valid_until=datetime.utcnow() + timedelta(hours=1),
            decision={"installation_principal": actor},
        )
    )
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="cli",
            action="engine.cli_deploy_admitted",
            target_type="engine",
            target_id=engine.id,
            after={"admission_operation_id": operation_id, "resources": keys},
        )
    )
    db.flush()
    return operation_id


def confirm_cli_deploy(db, engine, operation_id, expected_version):
    from shared.engine_control.models import ControlResource
    from shared.access.models import EffectAdmission

    policy.epoch(db, True)
    installation(db)
    engine = service.locked_engine(db, engine.id)
    if engine.version != expected_version:
        raise service.ControlError("VERSION_CONFLICT")
    rows = (
        db.query(ControlResource)
        .filter_by(operation_id=operation_id)
        .order_by(ControlResource.key)
        .with_for_update()
        .all()
    )
    if not rows:
        raise service.ControlError("CLI_ADMISSION_LOST")
    for r in rows:
        r.operation_id = None
        r.gate_closed = False
    db.query(EffectAdmission).filter_by(operation_id=operation_id, generation=0).update(
        {"state": "confirmed"}
    )
    db.flush()
    # Caller records the verified deployment in this same transaction.


def admit_cli_step(db, engine, operation_id, step):
    from shared.access.models import EffectAdmission
    from shared.engine_control.models import ControlResource

    authority = policy.epoch(db, True)
    actor = installation(db)
    resources = (
        db.query(ControlResource)
        .filter_by(operation_id=operation_id)
        .order_by(ControlResource.key)
        .with_for_update()
        .all()
    )
    if not resources or any(r.owner_engine_id != engine.id for r in resources):
        raise service.ControlError("CLI_ADMISSION_LOST")
    if (
        db.query(EffectAdmission)
        .filter_by(operation_id=operation_id, generation=0, step=step)
        .first()
    ):
        raise service.ControlError("EFFECT_ALREADY_ADMITTED")
    db.add(
        EffectAdmission(
            operation_id=operation_id,
            generation=0,
            step=step,
            actor_id=actor,
            executor="installation_cli",
            epoch=authority.version,
            state="uncertain",
            action="deploy",
            targets=[r.key for r in resources],
            valid_until=datetime.utcnow() + timedelta(hours=1),
            decision={"installation_principal": actor},
        )
    )
    db.commit()
