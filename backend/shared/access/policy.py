"""No permission comes from JWT claims, Redis or missing actors."""

from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError
from shared.config import get_settings
from shared.admin import is_effective_admin
from shared.models import User, Engine, AdminAudit
from shared.engine_control.contracts import ACTIONS
from shared.engine_control.service import ControlError, digest
from shared.access.models import (
    PolicyRevision,
    AuthorizationEpoch,
    EngineAttributes,
    ResourceScope,
)

READ = {"engines.read", "execution_profiles.read", "engine_operations.read"}
ROLES = {
    "observer": READ,
    "profile_editor": {
        "execution_profiles.read",
        "execution_profiles.create",
        "execution_profiles.update",
        "execution_profiles.publish",
        "execution_profiles.archive",
    },
    "runtime_configurator": READ | {"engine_runtime.bind"},
    "engine_operator": READ
    | {
        "engine_operations.plan",
        "engine_operations.cancel",
        "engine_operations.recover",
    }
    | {f"engine_operations.execute.{a}" for a in ACTIONS},
    "access_admin": {"access.grants.manage"},
    "connection_manager": READ | {"engine_connections.credentials.manage"},
}
PERMISSIONS = set().union(*ROLES.values()) | {
    "engine_connections.credentials.manage",
    "access.resources.manage",
}


def enabled():
    return get_settings().engine_access_enabled


def epoch(db, lock=False):
    q = db.query(AuthorizationEpoch).filter_by(id=1).populate_existing()
    row = q.with_for_update().one_or_none() if lock else q.one_or_none()
    if row is None:
        raise ControlError("ACCESS_SCHEMA_NOT_READY", 503)
    return row


def audit(db, actor, action, target, after=None):
    db.add(
        AdminAudit(
            actor_user_id=actor,
            auth_method="jwt",
            action=action,
            target_type="access",
            target_id=str(target),
            after=after,
        )
    )


def active_grant(db, grant, seen=None, lock=False):
    """The grant and its whole parent chain are active (read from `iam_bindings`, 0018)."""
    from shared.iam import engine_bindings

    return engine_bindings.active_grant(db, grant, seen, lock)


def grants(db, actor, lock=False):
    """
    Every active engines grant of `actor`.

    Since spec 0018 the grants live in `iam_bindings` (engines family); the thin
    adapter of `shared.iam.engine_bindings` keeps the 0009 interface and rules.
    """
    from shared.iam import engine_bindings

    return engine_bindings.grants(db, actor, lock)


def subset(child, parent):
    for k in (
        "engine_ids",
        "profile_ids",
        "adapters",
        "features",
        "environments",
        "host_ids",
        "gpu_uuids",
        "model_ids",
    ):
        upper = parent.get(k)
        lower = child.get(k)
        if upper is not None and (lower is None or not set(lower).issubset(upper)):
            return False
    for k in (
        "max_replicas",
        "max_concurrency",
        "max_cpu",
        "max_memory_mb",
        "max_warm_seconds",
        "max_usd",
    ):
        if Decimal(str(child.get(k, 0))) > Decimal(str(parent.get(k, 0))):
            return False
    return True


def _in(value, values):
    return values is None or value in values


def _engine_matches(db, engine, c, feature=None, lock=False):
    q = db.query(EngineAttributes).filter_by(engine_id=engine.id).populate_existing()
    attr = (q.with_for_update() if lock else q).first()
    return (
        engine.id in c["engine_ids"]
        and engine.adapter_type in c["adapters"]
        and (feature is None or feature in c["features"])
        and attr is not None
        and attr.environment in c["environments"]
    )


def _profile_matches(profile, c, creating=False):
    return (
        profile.adapter_type in c["adapters"]
        and profile.feature in c["features"]
        and profile.environment in c["environments"]
        and (
            c["profile_ids"] is None if creating else _in(profile.id, c["profile_ids"])
        )
    )


def _limits(db, engine, runtime, c, max_usd, warm_seconds):
    if not runtime:
        return max_usd is None or Decimal(str(max_usd)) <= Decimal(str(c["max_usd"]))
    b = runtime.get("binding") or {}
    limits = (
        ("max_replicas", runtime.get("max_replicas", 0)),
        ("max_concurrency", b.get("executions_per_worker", 1)),
        ("max_cpu", b.get("cpu") or 0),
        ("max_memory_mb", runtime.get("memory_mb") or 0),
    )
    if any(Decimal(str(v)) > Decimal(str(c[k])) for k, v in limits):
        return False
    host = (runtime.get("provider_settings") or {}).get("host_id")
    if host and not _in(host, c["host_ids"]):
        return False
    if not _in(runtime.get("model_profile_id"), c["model_ids"]):
        return False
    uuid = runtime.get("gpu_uuid")
    if b.get("gpu_ref") and not uuid and engine:
        uuid = next(
            (
                g.get("uuid")
                for g in (engine.config or {}).get("gpus", [])
                if g["ref"] == b["gpu_ref"]
            ),
            None,
        )
    if (
        engine
        and engine.adapter_type == "local"
        and b.get("gpu_ref")
        and (not uuid or not _in(uuid, c["gpu_uuids"]))
    ):
        return False
    # Provider defaults may exceed the envelope. Delegated templates must state both.
    if c["max_cpu"] is not None and b.get("cpu") is None:
        return False
    if c["max_memory_mb"] is not None and runtime.get("memory_mb") is None:
        return False
    if runtime.get("warm_until"):
        from shared.engine_control.contracts import utc_deadline

        warm_seconds = max(
            warm_seconds or 0,
            (utc_deadline(runtime["warm_until"]) - datetime.utcnow()).total_seconds(),
        )
    if (warm_seconds or 0) > c["max_warm_seconds"]:
        return False
    return max_usd is None or Decimal(str(max_usd)) <= Decimal(str(c["max_usd"]))


def _resources(db, keys, c, lock=False):
    for key in keys or []:
        q = db.query(ResourceScope).filter_by(key=key).populate_existing()
        scope = (q.with_for_update() if lock else q).first()
        if not scope or not scope.qualified or not scope.consumers:
            return False
        # Local canonical keys come from the reviewed adapter, never request labels.
        if key.startswith("local:"):
            parts = key.split(":", 3)
            if len(parts) != 4 or not _in(parts[1], c["host_ids"]):
                return False
            if parts[2] == "gpu" and not _in(parts[3], c["gpu_uuids"]):
                return False
        for consumer in scope.consumers:
            engine = db.get(Engine, consumer["engine_id"])
            if not engine or not _engine_matches(
                db, engine, c, consumer["feature"], lock
            ):
                return False
            from shared.engine_control import service, registry
            from shared.engine_control.models import RuntimeProfile

            desired = service.latest_profile(db, engine.id, consumer["feature"])
            applied = (
                db.query(RuntimeProfile)
                .filter_by(engine_id=engine.id, feature=consumer["feature"])
                .filter(RuntimeProfile.applied_at.isnot(None))
                .order_by(RuntimeProfile.applied_at.desc())
                .first()
            )
            for p in {r.id: r for r in (desired, applied) if r}.values():
                driver = registry.create(
                    engine.adapter_type, p.profile.get("adapter_version", 1)
                )
                if key in driver.resource_keys(
                    engine, consumer["feature"], p.profile
                ) and not identities(engine, p.profile, c):
                    return False
    return True


def identities(engine, runtime, c):
    """Read scope covers identities; numeric execution ceilings never hide history."""
    if not runtime:
        return True
    if not _in(runtime.get("model_profile_id"), c["model_ids"]):
        return False
    host = (runtime.get("provider_settings") or {}).get("host_id")
    if host and not _in(host, c["host_ids"]):
        return False
    if engine and engine.adapter_type == "local":
        uuid = runtime.get("gpu_uuid")
        ref = (runtime.get("binding") or {}).get("gpu_ref")
        if ref and not uuid:
            uuid = next(
                (
                    g.get("uuid")
                    for g in (engine.config or {}).get("gpus", [])
                    if g.get("ref") == ref
                ),
                None,
            )
        if ref and (not uuid or not _in(uuid, c["gpu_uuids"])):
            return False
    return True


def authorize(
    db,
    actor,
    permission,
    *,
    engine=None,
    profile=None,
    feature=None,
    runtime=None,
    max_usd=None,
    warm_seconds=None,
    resources=None,
    creating=False,
    force=False,
    lock=False,
):
    if not enabled() and not force:
        # Domain compatibility while rollout is off; API dependencies still require bootstrap.
        return {"bootstrap": True, "epoch": 0}
    authority = epoch(db, lock)
    q = db.query(User).filter_by(id=str(actor)).populate_existing()
    user = (q.with_for_update() if lock else q).first() if actor else None
    if not user or not user.is_active:
        raise ControlError("ACCESS_REVOKED", 403)
    if is_effective_admin(user):
        return {"bootstrap": True, "epoch": authority.version}
    if not enabled():
        raise ControlError("ACCESS_REVOKED", 403)
    for grant in grants(db, actor, lock):
        needed = {permission} if isinstance(permission, str) else set(permission)
        if not needed.issubset(grant.permissions):
            continue
        c = db.get(PolicyRevision, grant.policy_revision_id).constraints
        if engine and not _engine_matches(db, engine, c, feature, lock):
            continue
        if profile and not _profile_matches(profile, c, creating):
            continue
        if engine and runtime and c["profile_ids"] is not None and profile is None:
            continue
        read = needed.issubset(READ)
        if read:
            if not identities(engine, runtime, c):
                continue
        elif not _limits(db, engine, runtime, c, max_usd, warm_seconds):
            continue
        if not _resources(db, resources, c, lock):
            continue
        return {
            "grant_id": grant.id,
            "policy_revision_id": grant.policy_revision_id,
            "epoch": authority.version,
        }
    raise ControlError("ACCESS_DENIED", 403)


def allowed(db, actor, permission, **kwargs):
    try:
        authorize(db, actor, permission, **kwargs)
        return True
    except ControlError:
        return False


def navigation(db, user):
    if is_effective_admin(user):
        return {
            "enabled": enabled(),
            "bootstrap": True,
            "permissions": sorted(PERMISSIONS),
        }
    if not enabled():
        return {"enabled": False, "bootstrap": False, "permissions": []}
    ps = set().union(*(set(g.permissions) for g in grants(db, user.id)))
    return {"enabled": True, "bootstrap": False, "permissions": sorted(ps)}


def operation_authority(db, op, *, effect=False):
    from shared.engine_control.models import OperationPlan

    plan = db.get(OperationPlan, op.plan_id)
    if not enabled() and not plan.body.get("authorization"):
        return None
    recovering = (op.handles or {}).get("recovery_mode", False)
    actor = op.recovery_requested_by if recovering else op.actor_id
    permission = (
        "engine_operations.recover"
        if recovering
        else "engine_operations.execute." + plan.body["type"]
    )
    from shared.engine_control.service import source_profile, validate_source_model

    if not recovering:
        validate_source_model(db, plan.body.get("source_profile_revision_id"))
    return authorize(
        db,
        actor,
        permission,
        engine=db.get(Engine, op.engine_id),
        feature=plan.body["feature"],
        profile=(
            None
            if recovering
            else source_profile(db, plan.body.get("source_profile_revision_id"))
        ),
        runtime=None if recovering else plan.body.get("profile"),
        resources=plan.body.get("resources"),
        max_usd=None if recovering else plan.body.get("max_usd"),
        force=True,
        lock=effect,
    )


def visible_catalog(db, actor, rows, kind):
    user = db.get(User, actor)
    if user and is_effective_admin(user):
        return rows
    if not enabled():
        return []
    constraints = [
        db.get(PolicyRevision, g.policy_revision_id).constraints
        for g in grants(db, actor)
        if set(g.permissions)
        & (READ | {"execution_profiles.create", "execution_profiles.update"})
    ]

    def visible(row, c):
        if kind == "adapter":
            return row["type"] in c["adapters"]
        if kind == "host":
            return _in(row["id"], c["host_ids"])
        if kind == "model":
            return (
                row["feature"] in c["features"]
                and bool(set(row["adapters"]) & set(c["adapters"]))
                and _in(row["id"], c["model_ids"])
            )
        return False

    selected = [r for r in rows if any(visible(r, c) for c in constraints)]
    if kind == "adapter":
        result = []
        for r in selected:
            features = {
                f
                for c in constraints
                if r["type"] in c["adapters"]
                for f in c["features"]
            }
            r = dict(r, features=[f for f in r.get("features", []) if f in features])
            if "feature_info" in r:
                r["feature_info"] = {
                    f: v for f, v in r["feature_info"].items() if f in features
                }
            if "model_profiles" in r:
                r["model_profiles"] = visible_catalog(
                    db, actor, r["model_profiles"], "model"
                )
            result.append(r)
        return result
    return selected


def scoped_query(db, actor, q, kind):
    """Filter SQL by stable resource attributes before paging or serializing rows."""
    from sqlalchemy import or_, and_, false
    from shared.access.models import ExecutionProfile
    from shared.engine_control.models import EngineOperation, OperationPlan

    user = db.get(User, actor)
    if user and is_effective_admin(user):
        return q
    if not enabled():
        return q.filter(false())
    permission = {
        "engine": "engines.read",
        "profile": "execution_profiles.read",
        "operation": "engine_operations.read",
    }[kind]
    conditions = []
    for g in grants(db, actor):
        if permission not in g.permissions:
            continue
        c = db.get(PolicyRevision, g.policy_revision_id).constraints
        engine_ids = (
            db.query(Engine.id)
            .join(EngineAttributes, EngineAttributes.engine_id == Engine.id)
            .filter(
                Engine.id.in_(c["engine_ids"]),
                Engine.adapter_type.in_(c["adapters"]),
                EngineAttributes.environment.in_(c["environments"]),
            )
        )
        if kind == "engine":
            conditions.append(Engine.id.in_(engine_ids))
        elif kind == "profile":
            t = and_(
                ExecutionProfile.adapter_type.in_(c["adapters"]),
                ExecutionProfile.feature.in_(c["features"]),
                ExecutionProfile.environment.in_(c["environments"]),
            )
            if c["profile_ids"] is not None:
                t = and_(t, ExecutionProfile.id.in_(c["profile_ids"]))
            conditions.append(t)
        else:
            plan_ids = db.query(OperationPlan.id).filter(
                OperationPlan.body["feature"].as_string().in_(c["features"])
            )
            conditions.append(
                and_(
                    EngineOperation.engine_id.in_(engine_ids),
                    EngineOperation.plan_id.in_(plan_ids),
                )
            )
    return q.filter(or_(*conditions) if conditions else false())
