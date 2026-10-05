"""
Admin API for execution engines (spec 0003): read engines, GPUs and adapters;
change capacity bindings and declared GPUs.

Reads need an admin; changes need an admin's login session (a JWT) - an API key
is refused - and are audited. Nothing here ever returns a secret.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.admin_routes import require_admin
from shared.config import get_settings
from shared.database import get_db
from shared.engines.capacity import (
    ADAPTER_FEATURES, MODAL_MAX_E, Binding, CapacityError, LOCAL_GPU_MAX_E, LocalGpu, bindings,
    footprint_gb,
)
from shared.engines.features import FEATURES, default_vram_gb
from shared.engines.gpus import DEFAULT_ACCOUNT_MAX_GPUS, DEFAULT_VRAM_RESERVE_GB, MODAL_GPUS, PRICES_AS_OF, PRICES_VERIFIED
from shared.engines.liveness import alive
from shared.engines.store import VersionConflict, engine_view, set_binding, set_local_gpus
from shared.models import Engine
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/admin", tags=["Admin - Engines"])


def require_admin_session(request: Request, admin_user=Depends(require_admin)):
    """An admin authenticated by a login session; API keys cannot change engines"""
    if request.headers.get("x-api-key") or not request.headers.get("authorization", "").lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="Engine changes require a login session (JWT); API keys are not accepted")
    return admin_user


def _alive_by_feature() -> Dict[str, list]:
    try:
        client = get_redis_client().client
        return {feature: alive(feature, client) for feature in FEATURES}
    except Exception as e:  # liveness is informative; never fail the admin view over it
        logger.warning(f"[ENGINES] Could not read worker heartbeats: {e}")
        return {}


def _engine_or_404(db: Session, engine_id: str) -> Engine:
    engine = db.query(Engine).filter((Engine.id == engine_id) | (Engine.slug == engine_id)).first()
    if engine is None:
        raise HTTPException(status_code=404, detail="Engine not found")
    return engine


def _capacity_error(e: CapacityError) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": str(e), "vram": e.lines})


@router.get("/engine-adapters", summary="Engine adapters, their GPUs and limits")
async def list_engine_adapters(admin_user=Depends(require_admin)) -> List[Dict[str, Any]]:
    features = {
        name: {"title": f.title, "vram_per_execution_gb": default_vram_gb(name, settings.vision_model_id)}
        for name, f in FEATURES.items()
    }
    return [
        {
            "type": "local",
            "features": sorted(ADAPTER_FEATURES["local"]),
            "feature_info": features,
            "gpu_options": "detected by worker heartbeats and declared on the engine (PUT /admin/engines/local/gpus)",
            "max_executions_per_worker": {"gpu": LOCAL_GPU_MAX_E, "cpu": None},
            "vram_reserve_gb": DEFAULT_VRAM_RESERVE_GB,
        },
        {
            "type": "modal",
            "features": sorted(ADAPTER_FEATURES["modal"]),
            "feature_info": {k: v for k, v in features.items() if k in ADAPTER_FEATURES["modal"]},
            "gpu_options": [
                {"gpu_type": g.gpu_type, "vram_gb": g.vram_gb, "usd_per_second": g.usd_per_second,
                 "usd_per_hour": round(g.usd_per_second * 3600, 2)}
                for g in MODAL_GPUS.values()
            ],
            "prices_as_of": PRICES_AS_OF,
            "prices_verified": PRICES_VERIFIED,
            "account_max_gpus_default": DEFAULT_ACCOUNT_MAX_GPUS,
            "max_executions_per_worker": MODAL_MAX_E,
            "vram_reserve_gb": DEFAULT_VRAM_RESERVE_GB,
        },
    ]


@router.get("/engines", summary="List engines")
async def list_engines(admin_user=Depends(require_admin), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    live = _alive_by_feature()
    engines = db.query(Engine).order_by(Engine.is_system.desc(), Engine.slug).all()
    return [engine_view(db, e, alive_by_feature=live, vision_model_id=settings.vision_model_id) for e in engines]


@router.get("/engines/{engine_id}", summary="One engine")
async def get_engine(engine_id: str, admin_user=Depends(require_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    return engine_view(db, _engine_or_404(db, engine_id), alive_by_feature=_alive_by_feature(),
                       vision_model_id=settings.vision_model_id)


@router.get("/gpus", summary="Physical GPUs: declared vs detected, VRAM budgeted and used")
async def list_gpus(admin_user=Depends(require_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    local = db.query(Engine).filter(Engine.slug == "local").first()
    declared = [LocalGpu(**g) for g in ((local.config or {}).get("gpus") or [])] if local else []
    by_feature = bindings(local.config or {}) if local else {}
    live = _alive_by_feature()

    detected: Dict[str, dict] = {}
    for feature, workers in live.items():
        for w in workers:
            if not w.get("gpu_uuid"):
                continue
            gpu = detected.setdefault(w["gpu_uuid"], {
                "uuid": w["gpu_uuid"], "name": w.get("gpu_name"),
                "vram_total_gb": float(w.get("vram_total_gb") or 0), "vram_used_gb": float(w.get("vram_used_gb") or 0),
                "workers": [],
            })
            gpu["workers"].append({"feature": feature, "hostname": w["hostname"]})

    gpus = []
    for g in declared:
        users = [(f, b) for f, b in by_feature.items() if b.gpu_ref == g.ref]
        budget = sum(b.workers * b.executions_per_worker * footprint_gb(f, b, settings.vision_model_id) for f, b in users)
        seen = detected.pop(g.uuid, None) if g.uuid else None
        gpus.append({
            "ref": g.ref, "name": g.name, "uuid": g.uuid, "vram_gb": g.vram_gb, "reserve_gb": g.vram_reserve_gb,
            "budgeted_gb": round(budget + g.vram_reserve_gb, 2),
            "used_gb": seen["vram_used_gb"] if seen else None,
            "detected": seen is not None,
            "bindings": [{"feature": f, "workers": b.workers, "executions_per_worker": b.executions_per_worker,
                          "vram_each_gb": footprint_gb(f, b, settings.vision_model_id)} for f, b in users],
        })
    return {"declared": gpus, "undeclared_detected": list(detected.values())}


class BindingUpdate(Binding):
    version: Optional[int] = None


class GpusUpdate(BaseModel):
    gpus: List[LocalGpu]
    version: Optional[int] = None


@router.put("/engines/{engine_id}/features/{feature}", summary="Set how a feature runs on an engine")
async def put_engine_feature(engine_id: str, feature: str, body: BindingUpdate, request: Request,
                             admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    binding = Binding(**body.model_dump(exclude={"version"}))
    try:
        set_binding(db, engine, feature, binding, version=body.version, actor_user_id=str(admin_user.id),
                    auth_method="jwt", ip=request.client.host if request.client else None,
                    vision_model_id=settings.vision_model_id)
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CapacityError as e:
        raise _capacity_error(e)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    logger.warning(f"[ADMIN] {admin_user.id} set {feature} capacity on engine {engine.slug}")
    return engine_view(db, engine, alive_by_feature=_alive_by_feature(), vision_model_id=settings.vision_model_id)


@router.delete("/engines/{engine_id}/features/{feature}", summary="Stop running a feature on an engine")
async def delete_engine_feature(engine_id: str, feature: str, request: Request, version: Optional[int] = None,
                                admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    try:
        set_binding(db, engine, feature, None, version=version, actor_user_id=str(admin_user.id),
                    auth_method="jwt", ip=request.client.host if request.client else None,
                    vision_model_id=settings.vision_model_id)
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (CapacityError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return engine_view(db, engine, alive_by_feature=_alive_by_feature(), vision_model_id=settings.vision_model_id)


@router.put("/engines/{engine_id}/gpus", summary="Declare the local engine's physical GPUs")
async def put_engine_gpus(engine_id: str, body: GpusUpdate, request: Request,
                          admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    try:
        set_local_gpus(db, engine, [g.model_dump(exclude_none=True) for g in body.gpus], version=body.version,
                       actor_user_id=str(admin_user.id), auth_method="jwt",
                       ip=request.client.host if request.client else None, vision_model_id=settings.vision_model_id)
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except CapacityError as e:
        raise _capacity_error(e)
    return engine_view(db, engine, alive_by_feature=_alive_by_feature(), vision_model_id=settings.vision_model_id)
