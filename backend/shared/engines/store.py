"""
Engines in the database: the built-in local engine, views for the admin API,
capacity changes and their audit trail. Never returns or logs a secret.
"""

from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from shared.engines.capacity import Binding, CapacityError, LocalGpu, bindings, deploy_state, validate_engine_config
from shared.engines.features import FEATURES, get_feature
from shared.models import AdminAudit, DispatcherLease, Engine, EngineUsage

LOCAL_SLUG = "local"
IN_FLIGHT = ("reserved", "spawning", "running")


def ensure_local_engine(db: Session) -> Engine:
    """The built-in local engine (this server's workers); created once, no bindings until declared"""
    engine = db.query(Engine).filter(Engine.slug == LOCAL_SLUG).first()
    if engine is None:
        engine = Engine(slug=LOCAL_SLUG, display_name="Local workers", adapter_type="local",
                        config={"features": {}, "gpus": []}, deployments={}, status="active",
                        health="unknown", is_system=True, credentials_masked={})
        db.add(engine)
        db.commit()
    return engine


def ensure_lease_row(db: Session) -> None:
    """The single dispatcher_lease row, epoch 0 and no holder (spec 0003, Appendix E)"""
    if db.get(DispatcherLease, 1) is None:
        db.add(DispatcherLease(id=1, epoch=0))
        try:
            db.commit()
        except Exception:  # another process seeded it first
            db.rollback()


def audit(db: Session, *, actor_user_id: Optional[str], auth_method: str, ip: Optional[str], action: str,
          engine: Engine, before, after) -> None:
    db.add(AdminAudit(actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action=action,
                      target_type="engine", target_id=engine.id, before=before, after=after))


class VersionConflict(Exception):
    """The engine changed since the caller read it"""


def _check_version(engine: Engine, version: Optional[int]) -> None:
    if version is not None and version != engine.version:
        raise VersionConflict(f"Engine {engine.slug} is at version {engine.version}, not {version}; re-read it")


def set_binding(db: Session, engine: Engine, feature: str, binding: Optional[Binding], *, version: Optional[int],
                actor_user_id: Optional[str], auth_method: str, ip: Optional[str] = None,
                vision_model_id: Optional[str] = None) -> Engine:
    """Set (or with None remove) how a feature runs on an engine; validated, versioned and audited"""
    get_feature(feature)
    from shared.engine_control.guards import before_write
    before_write(db, engine, version, runtime=True)
    _check_version(engine, version)
    config = dict(engine.config or {})
    features = dict(config.get("features") or {})
    before = features.get(feature)
    if binding is None:
        features.pop(feature, None)
    else:
        features[feature] = binding.model_dump(exclude_none=True)
    config["features"] = features
    validate_engine_config(engine.adapter_type, config, vision_model_id)  # raises CapacityError
    if engine.adapter_type != "local":
        _check_remote_threads(db, engine, config)
    engine.config = config
    engine.version = (engine.version or 0) + 1
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.set_capacity",
          engine=engine, before={"feature": feature, "binding": before},
          after={"feature": feature, "binding": features.get(feature)})
    db.commit()
    return engine


class RemoteCapacityError(CapacityError):
    """More remote work in routes than worker-remote has threads for (409)"""


def _check_remote_threads(db: Session, engine: Engine, config: dict) -> None:
    """A binding change revalidates every route that uses the engine (spec 0003, R25)"""
    from shared.engines import routing
    from shared.models import FeatureRoute

    available = routing.remote_threads_available()
    for route in db.query(FeatureRoute).filter(FeatureRoute.state == "active"):
        steps = route.steps or []
        if not any(engine.id in s.get("engine_ids", []) for s in steps):
            continue
        needed = routing.remote_capacity(db, steps, overrides={engine.id: config})
        if needed > available:
            raise RemoteCapacityError(
                f"The {route.feature} route would need {needed} remote slots; worker-remote holds {available} "
                f"(REMOTE_WORKER_CONCURRENCY - {routing.REMOTE_CONTROL_THREADS})")


def set_local_gpus(db: Session, engine: Engine, gpus: list, *, version: Optional[int], actor_user_id: Optional[str],
                   auth_method: str, ip: Optional[str] = None, vision_model_id: Optional[str] = None) -> Engine:
    """Declare the local engine's physical GPUs; every binding is revalidated against them"""
    if engine.adapter_type != "local":
        raise CapacityError("Only the local engine declares physical GPUs")
    from shared.engine_control.guards import before_write
    before_write(db, engine, version)
    _check_version(engine, version)
    declared = [LocalGpu(**g).model_dump(exclude_none=True) for g in gpus]
    config = dict(engine.config or {})
    before = config.get("gpus")
    config["gpus"] = declared
    validate_engine_config(engine.adapter_type, config, vision_model_id)
    engine.config = config
    engine.version = (engine.version or 0) + 1
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.set_gpus",
          engine=engine, before={"gpus": before}, after={"gpus": declared})
    db.commit()
    return engine


def in_flight(db: Session, engine_id: str, feature: str) -> int:
    return db.query(EngineUsage).filter(
        EngineUsage.engine_id == engine_id, EngineUsage.feature == feature,
        EngineUsage.kind == "job", EngineUsage.status.in_(IN_FLIGHT),
    ).count()


def engine_view(db: Session, engine: Engine, *, alive_by_feature: dict, vision_model_id: Optional[str] = None,
                fingerprint_of: Optional[Callable] = None) -> dict:
    """
    What the admin API shows for one engine: budget, masked credentials, per-feature
    capacity. `fingerprint_of(engine, feature, binding)` (remote engines) is what a
    deploy would record now; a different recorded one reads `needs_redeploy`.
    """
    try:
        gpu_budget = [
            {"gpu": u.gpu, "vram_gb": u.vram_gb, "budgeted_gb": u.budgeted_gb, "fits": u.fits, "terms": u.terms}
            for u in validate_engine_config(engine.adapter_type, engine.config or {}, vision_model_id)
        ]
        config_error = None
    except CapacityError as e:
        gpu_budget, config_error = [], {"message": str(e), "lines": e.lines}

    features = {}
    for feature, binding in bindings(engine.config or {}).items():
        alive = alive_by_feature.get(feature, []) if engine.adapter_type == "local" else None
        expected = None
        if fingerprint_of is not None and engine.adapter_type != "local":
            try:
                expected = fingerprint_of(engine, feature, binding)
            except Exception:  # e.g. an invalid binding: shown by config_error
                expected = None
        deployed = (engine.deployments or {}).get(feature) or {}
        view = {
            "binding": binding.model_dump(exclude_none=True),
            "capacity": binding.capacity,
            "in_flight": in_flight(db, engine.id, feature),
            "deploy_state": deploy_state(engine.adapter_type, engine.deployments, feature, binding, expected),
        }
        if engine.adapter_type != "local":
            view["deployed_fingerprint"] = deployed.get("fingerprint")
            view["expected_fingerprint"] = expected
            view["deployed_at"] = deployed.get("verified_at")
        if alive is not None:
            view["workers_alive"] = len(alive)
            view["workers_configured"] = binding.workers
            view["scale_hint"] = FEATURES[feature].scale_hint.format(workers=binding.workers)
        features[feature] = view

    return {
        "id": engine.id,
        "slug": engine.slug,
        "display_name": engine.display_name,
        "adapter_type": engine.adapter_type,
        "status": engine.status,
        "health": engine.health,
        "health_reason": engine.health_reason,
        "is_system": engine.is_system,
        "version": engine.version,
        "budget": {
            "limit_usd": float(engine.limit_usd) if engine.limit_usd is not None else None,
            "min_remaining_usd": float(engine.min_remaining_usd) if engine.min_remaining_usd is not None else None,
            "soft_pct": engine.soft_pct,
            "period_tz": engine.period_tz,
            "period_anchor_day": engine.period_anchor_day,
        },
        "credentials": {k: v for k, v in (engine.credentials_masked or {}).items() if k != "fingerprint"},
        "credentials_updated_at": engine.credentials_updated_at.isoformat() if engine.credentials_updated_at else None,
        "config": {k: v for k, v in (engine.config or {}).items() if k != "features"},
        "features": features,
        "gpu_budget": gpu_budget,
        "config_error": config_error,
        "updated_at": engine.updated_at.isoformat() if engine.updated_at else None,
    }


# --- lifecycle, budget and credentials (spec 0003, Appendix B; slice 4a) ---------------------

class EngineStateError(Exception):
    """A change the engine's current state does not allow; `status` is the HTTP answer"""

    def __init__(self, message: str, status: int = 409, problems: Optional[list] = None):
        super().__init__(message)
        self.status = status
        self.problems = problems or []


def _bump(engine: Engine) -> None:
    engine.version = (engine.version or 0) + 1


def activation_problems(engine: Engine, fingerprint_of: Optional[Callable] = None,
                        vision_model_id: Optional[str] = None) -> list:
    """Why a remote engine cannot be activated (empty when it can); the local engine always can"""
    if engine.adapter_type == "local":
        return []
    problems = []
    if not engine.credentials_sealed:
        problems.append("no credentials: PUT /admin/engines/{id}/credentials or `engines.py import-env`")
    test = (engine.config or {}).get("last_test") or {}
    if not test.get("ok"):
        problems.append("no passing connection test: POST /admin/engines/{id}/test or `engines.py test`")
    elif engine.credentials_updated_at and test.get("at") and \
            datetime.fromisoformat(test["at"]) < engine.credentials_updated_at:
        problems.append("the last passing test is older than the credentials: test again")
    if engine.limit_usd is None:
        problems.append("no budget: PUT /admin/engines/{id}/budget with limit_usd")
    elif engine.min_remaining_usd is None or engine.min_remaining_usd < 0:
        problems.append("min_remaining_usd must be >= 0")
    try:
        validate_engine_config(engine.adapter_type, engine.config or {}, vision_model_id)
    except CapacityError as e:
        problems.append(str(e))
    features = bindings(engine.config or {})
    if not features:
        problems.append("no feature binding: set capacity first")
    for feature, binding in features.items():
        expected = fingerprint_of(engine, feature, binding) if fingerprint_of else None
        state = deploy_state(engine.adapter_type, engine.deployments, feature, binding, expected)
        if state != "deployed":
            problems.append(f"{feature}: {state} - run `engines.py modal-deploy --engine {engine.slug}`")
    return problems


def set_status(db: Session, engine: Engine, status: str, *, version: Optional[int], actor_user_id: Optional[str],
               auth_method: str, ip: Optional[str] = None, fingerprint_of: Optional[Callable] = None,
               vision_model_id: Optional[str] = None) -> Engine:
    """activate (remote: tested, budgeted, deployed, E=1) or pause (in-flight work finishes; nothing new)"""
    if status not in ("active", "paused"):
        raise ValueError("status must be active or paused")
    from shared.engine_control.guards import before_write
    before_write(db, engine, version)
    _check_version(engine, version)
    if status == "active":
        problems = activation_problems(engine, fingerprint_of, vision_model_id)
        if problems:
            raise EngineStateError(f"{engine.slug} cannot be activated", 409, problems)
    before = {"status": engine.status}
    engine.status = status
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip,
          action="engine.activate" if status == "active" else "engine.pause", engine=engine,
          before=before, after={"status": status})
    db.commit()
    return engine


def reset_health(db: Session, engine: Engine, *, actor_user_id: Optional[str], auth_method: str,
                 ip: Optional[str] = None) -> Engine:
    from shared.engine_control.guards import before_write
    before_write(db, engine)
    before = {"health": engine.health, "health_reason": engine.health_reason}
    engine.health, engine.health_reason, engine.health_until, engine.consecutive_failures = "unknown", None, None, 0
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.reset_health",
          engine=engine, before=before, after={"health": "unknown"})
    db.commit()
    return engine


def set_budget(db: Session, engine: Engine, *, limit_usd, min_remaining_usd=None, soft_pct=None, period_tz=None,
               period_anchor_day=None, version: Optional[int], actor_user_id: Optional[str], auth_method: str,
               ip: Optional[str] = None) -> Engine:
    """
    The account's ceiling per period. A remote engine that is active must keep a
    limit (spec 0003, 4.8); raising it clears `exhausted`.
    """
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from shared.engine_control.guards import before_write
    before_write(db, engine, version)
    _check_version(engine, version)
    limit = Decimal(str(limit_usd)) if limit_usd is not None else None
    if limit is not None and limit <= 0:
        raise EngineStateError("limit_usd must be positive", 422)
    if limit is None and engine.adapter_type != "local" and engine.status == "active":
        raise EngineStateError("An active remote engine needs limit_usd: pause it first", 422)
    remaining = Decimal(str(min_remaining_usd)) if min_remaining_usd is not None else engine.min_remaining_usd
    if remaining is None or remaining < 0:
        raise EngineStateError("min_remaining_usd must be >= 0", 422)
    if soft_pct is not None and not 1 <= int(soft_pct) <= 100:
        raise EngineStateError("soft_pct must be 1..100", 422)
    if period_tz is not None:
        try:
            ZoneInfo(period_tz)
        except Exception:
            raise EngineStateError(f"Unknown time zone {period_tz!r}", 422) from None
    if period_anchor_day is not None and not 1 <= int(period_anchor_day) <= 28:
        raise EngineStateError("period_anchor_day must be 1..28", 422)

    before = {"limit_usd": str(engine.limit_usd) if engine.limit_usd is not None else None,
              "min_remaining_usd": str(engine.min_remaining_usd), "soft_pct": engine.soft_pct,
              "period_tz": engine.period_tz, "period_anchor_day": engine.period_anchor_day}
    raised = limit is not None and (engine.limit_usd is None or limit > engine.limit_usd)
    engine.limit_usd = limit
    engine.min_remaining_usd = remaining
    if soft_pct is not None:
        engine.soft_pct = int(soft_pct)
    if period_tz is not None:
        engine.period_tz = period_tz
    if period_anchor_day is not None:
        engine.period_anchor_day = int(period_anchor_day)
    if raised and engine.health == "exhausted":
        engine.health, engine.health_reason, engine.health_until = "unknown", None, None
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.set_budget", engine=engine,
          before=before, after={"limit_usd": str(limit) if limit is not None else None,
                                "min_remaining_usd": str(remaining), "soft_pct": engine.soft_pct,
                                "period_tz": engine.period_tz, "period_anchor_day": engine.period_anchor_day})
    db.commit()
    return engine


CREDENTIAL_FIELDS = {"modal": {"token_id": "last4", "token_secret": "none"}}


def set_credentials(db: Session, engine: Engine, fields: dict, *, public_key: str, version: Optional[int],
                    actor_user_id: Optional[str], auth_method: str, ip: Optional[str] = None) -> Engine:
    """
    Seal new credentials to the public key (the API can never open them again).
    A new test is required before the engine can be (re)activated; the audit
    trail records that they changed, never what they are.
    """
    import hashlib

    from shared.engines.redact import register_secret
    from shared.engines.sealing import mask, seal

    from shared.engine_control.registry import descriptor
    try:
        schema = {f['name']:f.get('mask','none') for f in descriptor(engine.adapter_type).get('credential_fields',[])}
    except ValueError:
        schema = CREDENTIAL_FIELDS.get(engine.adapter_type)
    if schema is None:
        raise EngineStateError(f"The {engine.adapter_type} engine takes no credentials", 422)
    if not public_key:
        raise EngineStateError("ENGINE_SECRETS_PUBLIC_KEY is not set: credentials cannot be stored", 409)
    from shared.engine_control.guards import before_write
    before_write(db, engine, version, credentials=True)
    _check_version(engine, version)
    clean = {}
    for name in schema:
        value = (fields or {}).get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise EngineStateError(f"credentials need {', '.join(schema)}", 422)
        clean[name] = value.strip()
        register_secret(clean[name])
    unknown = set(fields or {}) - set(schema)
    if unknown:
        raise EngineStateError(f"unknown credential fields: {', '.join(sorted(unknown))}", 422)

    blob, kid = seal(clean, public_key, engine.id)
    masked = {name: mask(clean[name], hint) for name, hint in schema.items()}
    masked["fingerprint"] = hashlib.sha256(":".join(clean[n] for n in schema).encode()).hexdigest()[:16]
    engine.credentials_sealed, engine.credentials_key_id, engine.credentials_masked = blob, kid, masked
    engine.credentials_updated_at = datetime.utcnow()
    engine.credentials_updated_by = actor_user_id or auth_method
    config = dict(engine.config or {})
    config.pop("last_test", None)
    engine.config = config
    if engine.health == "unhealthy":
        engine.health, engine.health_reason, engine.health_until = "unknown", None, None
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.set_credentials",
          engine=engine, before=None, after={"credentials": "replaced", "key_id": kid})
    db.commit()
    return engine


def clear_credentials(db: Session, engine: Engine, *, version: Optional[int], actor_user_id: Optional[str],
                      auth_method: str, ip: Optional[str] = None) -> Engine:
    """Forget the credentials; an active remote engine is paused (it could not run anyway)"""
    from shared.engine_control.guards import before_write
    before_write(db, engine, version, credentials=True)
    _check_version(engine, version)
    before = {"status": engine.status, "credentials": "set" if engine.credentials_sealed else "unset"}
    engine.credentials_sealed = engine.credentials_key_id = None
    engine.credentials_masked = {}
    engine.credentials_updated_at = datetime.utcnow()
    engine.credentials_updated_by = actor_user_id or auth_method
    config = dict(engine.config or {})
    config.pop("last_test", None)
    engine.config = config
    if engine.adapter_type != "local" and engine.status == "active":
        engine.status = "paused"
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.clear_credentials",
          engine=engine, before=before, after={"status": engine.status, "credentials": "unset"})
    db.commit()
    return engine


def record_deployment(db: Session, engine: Engine, feature: str, entry: dict, *, actor_user_id: Optional[str],
                      auth_method: str, ip: Optional[str] = None) -> Engine:
    """What a verified deploy put in the account: {fingerprint, protocol, binding, verified_at, ...}"""
    from shared.engine_control.guards import before_write
    before_write(db, engine, runtime=True)
    deployments = dict(engine.deployments or {})
    before = deployments.get(feature)
    deployments[feature] = entry
    engine.deployments = deployments
    _bump(engine)
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.deploy", engine=engine,
          before={"feature": feature, "deployment": before}, after={"feature": feature, "deployment": entry})
    db.commit()
    return engine
