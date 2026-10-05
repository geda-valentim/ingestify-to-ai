"""
Engines in the database: the built-in local engine, views for the admin API,
capacity changes and their audit trail. Never returns or logs a secret.
"""

from datetime import datetime
from typing import Optional

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
    engine.config = config
    engine.version = (engine.version or 0) + 1
    audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="engine.set_capacity",
          engine=engine, before={"feature": feature, "binding": before},
          after={"feature": feature, "binding": features.get(feature)})
    db.commit()
    return engine


def set_local_gpus(db: Session, engine: Engine, gpus: list, *, version: Optional[int], actor_user_id: Optional[str],
                   auth_method: str, ip: Optional[str] = None, vision_model_id: Optional[str] = None) -> Engine:
    """Declare the local engine's physical GPUs; every binding is revalidated against them"""
    if engine.adapter_type != "local":
        raise CapacityError("Only the local engine declares physical GPUs")
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


def engine_view(db: Session, engine: Engine, *, alive_by_feature: dict, vision_model_id: Optional[str] = None) -> dict:
    """What the admin API shows for one engine: budget, masked credentials, per-feature capacity"""
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
        view = {
            "binding": binding.model_dump(exclude_none=True),
            "capacity": binding.capacity,
            "in_flight": in_flight(db, engine.id, feature),
            "deploy_state": deploy_state(engine.adapter_type, engine.deployments, feature, binding),
        }
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
