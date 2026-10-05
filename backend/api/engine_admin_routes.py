"""
Admin API for execution engines (spec 0003, Appendix B): read engines, GPUs and
adapters; change capacity bindings and declared GPUs; and, from slice 4a, the
lifecycle of a remote engine:

    PUT    /admin/engines/{id}/credentials   seal new credentials (current_password; 409 without a public key)
    DELETE /admin/engines/{id}/credentials   forget them (current_password); an active engine is paused
    POST   /admin/engines/{id}/test          worker-remote checks them against the provider (<= 30 s, no GPU)
    PUT    /admin/engines/{id}/budget        limit_usd, min_remaining_usd, soft_pct, period_tz, period_anchor_day
    POST   /admin/engines/{id}/activate      needs a passing test, a budget, a verified deploy and E=1
    POST   /admin/engines/{id}/pause         nothing new is placed; work in flight finishes
    POST   /admin/engines/{id}/reset-health
    POST   /admin/engines/{id}/reconcile     read the provider's spend report now (worker-remote)
    POST   /admin/engines/test-all           test every remote engine in turn (worker-remote, no GPU)
    GET    /admin/engines/{id}/benchmarks    benchmark rows (gpu x E) and the learned speed per key

Reads need an admin; changes need an admin's login session (a JWT) - an API key
is refused - and are audited. Nothing here ever returns a secret.
"""

import logging
from typing import Any, Dict, List, Optional

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
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
from shared.auth import verify_password
from shared.engines import store
from shared.engines.store import VersionConflict, engine_view, set_binding, set_local_gpus
from shared.models import Engine
from shared.redis_client import get_redis_client
from workers.engines.remote import expected_fingerprint as fingerprint_of

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


def _view(db: Session, engine: Engine) -> Dict[str, Any]:
    return engine_view(db, engine, alive_by_feature=_alive_by_feature(), vision_model_id=settings.vision_model_id,
                       fingerprint_of=fingerprint_of)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


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
    return [engine_view(db, e, alive_by_feature=live, vision_model_id=settings.vision_model_id,
                        fingerprint_of=fingerprint_of) for e in engines]


@router.get("/engines/{engine_id}", summary="One engine")
async def get_engine(engine_id: str, admin_user=Depends(require_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _view(db, _engine_or_404(db, engine_id))


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

    # Live has no Celery lane. Display its separate resident footprint in the
    # same inventory and include it in the physical GPU budget.
    live_worker = None
    try:
        from shared.live.store import LiveStore
        live_worker = LiveStore(get_redis_client().client, settings.live_worker_id).readiness()
    except Exception:
        pass
    if live_worker and live_worker.get('gpu'):
        gpu = live_worker['gpu']
        seen = detected.setdefault(gpu['uuid'], {"uuid": gpu['uuid'], "name": "Live GPU",
            "vram_total_gb": gpu['total_gb'], "vram_used_gb": gpu['used_gb'], "workers": []})
        seen['workers'].append({"feature": "live-transcription", "hostname": settings.live_worker_id})

    gpus = []
    for g in declared:
        users = [(f, b) for f, b in by_feature.items() if b.gpu_ref == g.ref]
        budget = sum(b.workers * b.executions_per_worker * footprint_gb(f, b, settings.vision_model_id) for f, b in users)
        live_reserved = 0.0
        if live_worker and (live_worker.get('gpu') or {}).get('uuid') == g.uuid:
            live_reserved = float(live_worker.get('resident_vram_gb') or 0)
        elif settings.live_transcription_enabled and settings.live_gpu_ref == g.ref:
            live_reserved = settings.live_vram_footprint_gb
        budget += live_reserved
        reserve = max(g.vram_reserve_gb, settings.live_vram_reserve_gb, .2 * g.vram_gb) if live_reserved else g.vram_reserve_gb
        seen = detected.pop(g.uuid, None) if g.uuid else None
        gpus.append({
            "ref": g.ref, "name": g.name, "uuid": g.uuid, "vram_gb": g.vram_gb, "reserve_gb": reserve,
            "budgeted_gb": round(budget + reserve, 2),
            "live_reserved_gb": live_reserved,
            "used_gb": seen["vram_used_gb"] if seen else None,
            "detected": seen is not None,
            "bindings": [{"feature": f, "workers": b.workers, "executions_per_worker": b.executions_per_worker,
                          "vram_each_gb": footprint_gb(f, b, settings.vision_model_id)} for f, b in users],
        })
    return {"declared": gpus, "undeclared_detected": list(detected.values()), "live_worker": live_worker}


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
    except store.RemoteCapacityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except CapacityError as e:
        raise _capacity_error(e)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    logger.warning(f"[ADMIN] {admin_user.id} set {feature} capacity on engine {engine.slug}")
    return _view(db, engine)


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
    return _view(db, engine)


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
    return _view(db, engine)


# --- lifecycle, budget and credentials (slice 4a) ---------------------------------------------


class VersionBody(BaseModel):
    version: Optional[int] = None


class BudgetUpdate(BaseModel):
    limit_usd: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=6)
    min_remaining_usd: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=6)
    soft_pct: Optional[int] = Field(None, ge=1, le=100)
    period_tz: Optional[str] = Field(None, max_length=64)
    period_anchor_day: Optional[int] = Field(None, ge=1, le=28)
    version: Optional[int] = None


class CredentialsUpdate(BaseModel):
    fields: Dict[str, str]
    current_password: str
    version: Optional[int] = None


class CredentialsDelete(BaseModel):
    current_password: str
    version: Optional[int] = None


def _state_error(e: "store.EngineStateError") -> HTTPException:
    detail = {"message": str(e), "problems": e.problems} if e.problems else str(e)
    return HTTPException(status_code=e.status, detail=detail)


def _require_password(admin_user, password: str) -> None:
    if not password or not verify_password(password, admin_user.hashed_password):
        raise HTTPException(status_code=403, detail="Changing engine credentials needs current_password")


def _remote_worker_alive() -> bool:
    try:
        from shared.engines.liveness import remote_worker
        return bool(remote_worker(get_redis_client().client))
    except Exception:
        return False


def _send_test(engine_id: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Ask worker-remote (the only holder of the private keys) to test an engine, and wait for it"""
    from workers.celery_app import celery_app

    result = celery_app.send_task("workers.engines.remote_tasks.test_engine", args=[engine_id],
                                  queue=settings.remote_ctl_queue, expires=timeout)
    try:
        return result.get(timeout=timeout, propagate=True)
    finally:
        result.forget()


@router.post("/engines/{engine_id}/test", summary="Test an engine's credentials and deployment (no GPU)")
async def test_engine(engine_id: str, request: Request, admin_user=Depends(require_admin_session),
                      db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    if engine.adapter_type == "local":
        return {"ok": True, "code": None, "detail": "the local engine needs no connection test"}
    if not engine.credentials_sealed:
        raise HTTPException(status_code=409, detail="The engine has no credentials")
    if not _remote_worker_alive():
        raise HTTPException(status_code=409, detail="worker-remote is not running (docker compose --profile engines "
                                                    "up -d worker-remote); only it can open credentials")
    store.audit(db, actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request), action="engine.test",
                engine=engine, before=None, after=None)
    db.commit()
    try:
        report = await run_in_threadpool(_send_test, engine.id)
    except Exception as e:
        logger.warning(f"[ADMIN] Test of engine {engine.slug} did not answer: {type(e).__name__}")
        raise HTTPException(status_code=504, detail="worker-remote did not answer within 30 s")
    db.expire_all()
    return {**report, "engine": _view(db, _engine_or_404(db, engine.id))}


@router.post("/engines/{engine_id}/activate", summary="Let the dispatcher place work on an engine")
async def activate_engine(engine_id: str, request: Request, body: Optional[VersionBody] = None,
                          admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    try:
        store.set_status(db, engine, "active", version=body.version if body else None,
                         actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request),
                         fingerprint_of=fingerprint_of, vision_model_id=settings.vision_model_id)
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except store.EngineStateError as e:
        raise _state_error(e)
    logger.warning(f"[ADMIN] {admin_user.id} activated engine {engine.slug}")
    return _view(db, engine)


@router.post("/engines/{engine_id}/pause", summary="Stop placing new work on an engine (work in flight finishes)")
async def pause_engine(engine_id: str, request: Request, body: Optional[VersionBody] = None,
                       admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    try:
        store.set_status(db, engine, "paused", version=body.version if body else None,
                         actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request))
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.warning(f"[ADMIN] {admin_user.id} paused engine {engine.slug}")
    return _view(db, engine)


@router.post("/engines/{engine_id}/reset-health", summary="Forget an engine's recorded failures")
async def reset_engine_health(engine_id: str, request: Request, admin_user=Depends(require_admin_session),
                              db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    store.reset_health(db, engine, actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request))
    return _view(db, engine)


@router.put("/engines/{engine_id}/budget", summary="Set an engine's spending ceiling per period")
async def put_engine_budget(engine_id: str, body: BudgetUpdate, request: Request,
                            admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    try:
        store.set_budget(db, engine, limit_usd=body.limit_usd, min_remaining_usd=body.min_remaining_usd,
                         soft_pct=body.soft_pct, period_tz=body.period_tz, period_anchor_day=body.period_anchor_day,
                         version=body.version, actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request))
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except store.EngineStateError as e:
        raise _state_error(e)
    logger.warning(f"[ADMIN] {admin_user.id} set the budget of engine {engine.slug}")
    return _view(db, engine)


@router.put("/engines/{engine_id}/credentials", summary="Replace an engine's credentials (sealed, write-only)")
async def put_engine_credentials(engine_id: str, body: CredentialsUpdate, request: Request,
                                 admin_user=Depends(require_admin_session), db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    if not settings.engine_secrets_public_key:
        raise HTTPException(status_code=409, detail="ENGINE_SECRETS_PUBLIC_KEY is not set: credentials cannot be stored")
    _require_password(admin_user, body.current_password)
    try:
        store.set_credentials(db, engine, body.fields, public_key=settings.engine_secrets_public_key,
                              version=body.version, actor_user_id=str(admin_user.id), auth_method="jwt",
                              ip=_ip(request))
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except store.EngineStateError as e:
        raise _state_error(e)
    logger.warning(f"[ADMIN] {admin_user.id} replaced the credentials of engine {engine.slug}")
    return _view(db, engine)


@router.delete("/engines/{engine_id}/credentials", summary="Forget an engine's credentials")
async def delete_engine_credentials(engine_id: str, body: CredentialsDelete, request: Request,
                                    admin_user=Depends(require_admin_session),
                                    db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    _require_password(admin_user, body.current_password)
    try:
        store.clear_credentials(db, engine, version=body.version, actor_user_id=str(admin_user.id),
                                auth_method="jwt", ip=_ip(request))
    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.warning(f"[ADMIN] {admin_user.id} removed the credentials of engine {engine.slug}")
    return _view(db, engine)


# --- benchmarks, learned speed, spend and every account at once (slices 4b/4c) ----------------


@router.get("/engines/{engine_id}/benchmarks", summary="Benchmark results (gpu x E) and the learned speed per key")
async def engine_benchmarks(engine_id: str, feature: str = "transcription", limit: int = 50,
                            admin_user=Depends(require_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    from shared.engines import speed
    from shared.models import EngineUsage

    engine = _engine_or_404(db, engine_id)
    rows = (db.query(EngineUsage)
            .filter(EngineUsage.engine_id == engine.id, EngineUsage.feature == feature,
                    EngineUsage.kind == "benchmark")
            .order_by(EngineUsage.created_at.desc(), EngineUsage.id.desc()).limit(min(max(limit, 1), 200)).all())
    results = [{"usage_id": r.id, "status": r.status, "outcome": r.outcome, "gpu": r.gpu_type,
                "executions_per_worker": r.executions_per_worker,
                "reserved_usd": str(r.reserved_usd) if r.reserved_usd is not None else None,
                "actual_usd": str(r.actual_usd) if r.actual_usd is not None else None,
                "contended": (r.units or {}).get("contended"), "result": (r.units or {}).get("result"),
                "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    keys = []
    binding = bindings(engine.config or {}).get(feature)
    seen = set()
    for gpu, e in ([(binding.gpu_type or binding.gpu_ref, binding.executions_per_worker)] if binding else []) + \
            [(r["gpu"], r["executions_per_worker"]) for r in results]:
        if (gpu, e) in seen or e is None:
            continue
        seen.add((gpu, e))
        keys.append(speed.compute(db, engine.id, feature, gpu, e).view())
    return {"engine": engine.slug, "feature": feature, "benchmarks": results, "speed": keys}


def _send_control(task: str, args: list, timeout: float) -> Any:
    from workers.celery_app import celery_app

    result = celery_app.send_task(task, args=args, queue=settings.remote_ctl_queue, expires=timeout)
    try:
        return result.get(timeout=timeout, propagate=True)
    finally:
        result.forget()


@router.post("/engines/{engine_id}/reconcile", summary="Read the provider's spend report for one engine now")
async def reconcile_engine(engine_id: str, request: Request, admin_user=Depends(require_admin_session),
                           db: Session = Depends(get_db)) -> Dict[str, Any]:
    engine = _engine_or_404(db, engine_id)
    if engine.adapter_type == "local":
        raise HTTPException(status_code=409, detail="The local engine has no provider spend")
    if not _remote_worker_alive():
        raise HTTPException(status_code=409, detail="worker-remote is not running; only it can read spend reports")
    store.audit(db, actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request), action="engine.reconcile",
                engine=engine, before=None, after=None)
    db.commit()
    try:
        out = await run_in_threadpool(_send_control, "workers.engines.remote_tasks.reconcile_one", [engine.id], 90.0)
    except Exception as e:
        logger.warning(f"[ADMIN] Reconcile of engine {engine.slug} did not answer: {type(e).__name__}")
        raise HTTPException(status_code=504, detail="worker-remote did not answer within 90 s")
    db.expire_all()
    return {"reconcile": out, "engine": _view(db, _engine_or_404(db, engine.id))}


@router.post("/engines/test-all", summary="Test every remote engine's credentials and deployment, in turn (no GPU)")
async def test_all_engines(request: Request, admin_user=Depends(require_admin_session),
                           db: Session = Depends(get_db)) -> Dict[str, Any]:
    remote = [e for e in db.query(Engine).filter(Engine.adapter_type != "local") if e.credentials_sealed]
    if not remote:
        return {"results": {}}
    if not _remote_worker_alive():
        raise HTTPException(status_code=409, detail="worker-remote is not running; only it can open credentials")
    for engine in remote:
        store.audit(db, actor_user_id=str(admin_user.id), auth_method="jwt", ip=_ip(request), action="engine.test",
                    engine=engine, before=None, after=None)
    db.commit()
    timeout = min(30.0 * len(remote), 170.0)
    try:
        out = await run_in_threadpool(_send_control, "workers.engines.remote_tasks.test_all_engines", [], timeout)
    except Exception as e:
        logger.warning(f"[ADMIN] Test of all engines did not answer: {type(e).__name__}")
        raise HTTPException(status_code=504, detail=f"worker-remote did not answer within {timeout:.0f} s")
    return {"results": out}
