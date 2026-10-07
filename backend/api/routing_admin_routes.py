"""
Admin API for feature routes and the dispatcher (spec 0003, Appendix B).

    GET    /admin/routing             every feature's route (implicit "today's path" when none), backlog
    PUT    /admin/routing/{feature}   create or replace a route (validated; audited)
    DELETE /admin/routing/{feature}   remove it: the route drains back to today's path (202)
    GET    /admin/engines/status      in flight / capacity, backlog per feature, the dispatcher lease

Reads need `platform.routing.read`; changes need `platform.routing.update` and a
login session (JWT), and are audited (spec 0014 §4.7).
A remote step needs its engines active, healthy, deployed and budgeted, and a
live worker-remote (409 otherwise).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.engine_admin_routes import _alive_by_feature, _remote_worker_alive, fingerprint_of
from api.iam_deps import require
from shared.auth import verify_password
from shared.database import get_db
from shared.engines import dispatch, routing
from shared.engines.capacity import bindings
from shared.engines.features import FEATURES
from shared.engines.store import in_flight
from shared.models import DispatcherLease, Engine, EngineUsage, FeatureRoute, JobDispatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin - Engines"])

ROUTING_READ = require("platform.routing.read")
# Same rule and detail as the 0009 `require_admin_session` it replaces (CA12).
ROUTING_UPDATE = require(
    "platform.routing.update",
    session=True,
    session_detail="Engine changes require a login session (JWT); API keys are not accepted",
)


class RouteUpdate(routing.RouteSpec):
    version: Optional[int] = None
    # Required to open remote work to every user (remote_allowed_for=all)
    current_password: Optional[str] = None


def _backlog(db: Session, feature: str, now: datetime) -> Dict[str, Any]:
    counts = dict(db.query(JobDispatch.state, func.count(JobDispatch.id))
                  .filter(JobDispatch.feature == feature).group_by(JobDispatch.state).all())
    oldest = db.query(func.min(JobDispatch.enqueued_at)).filter(
        JobDispatch.feature == feature, JobDispatch.state.in_(("probing", "waiting"))).scalar()
    fallback_in_flight = db.query(func.count(EngineUsage.id)).filter(
        EngineUsage.feature == feature, EngineUsage.placed_by == "fallback",
        EngineUsage.status.in_(("reserved", "spawning", "running"))).scalar()
    bypassed_24h = db.query(func.count(EngineUsage.id)).filter(
        EngineUsage.feature == feature, EngineUsage.placed_by == "fallback",
        EngineUsage.created_at >= now - timedelta(hours=24)).scalar()
    return {
        "waiting": counts.get("waiting", 0) + counts.get("probing", 0),
        "by_state": {state: counts.get(state, 0) for state in
                     ("probing", "waiting", "assigned", "running", "bypassed", "done", "failed")},
        "oldest_wait_seconds": round((now - oldest).total_seconds()) if oldest else None,
        "bypassed_24h": bypassed_24h or 0,
        "fallback_in_flight": fallback_in_flight or 0,
    }


def _lease_view(db: Session, now: datetime) -> Dict[str, Any]:
    lease = db.get(DispatcherLease, 1)
    seen = lease.dispatcher_seen_at if lease else None
    return {
        "epoch": lease.epoch if lease else 0,
        "holder": lease.holder if lease else None,
        "holder_kind": lease.holder_kind if lease else None,
        "renewed_at": lease.renewed_at.isoformat() if lease and lease.renewed_at else None,
        "dispatcher_seen_at": seen.isoformat() if seen else None,
        "dispatcher_seen_seconds_ago": round((now - seen).total_seconds()) if seen else None,
    }


@router.get("/routing", summary="Feature routes and their backlog")
async def list_routes(admin_user=Depends(ROUTING_READ), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    engines = {e.id: e for e in db.query(Engine)}
    routes = {r.feature: r for r in db.query(FeatureRoute)}
    views = []
    for feature in FEATURES:
        view = routing.describe(routes.get(feature), engines, feature)
        view["backlog"] = _backlog(db, feature, now)
        views.append(view)
    return views


@router.put("/routing/{feature}", summary="Create or replace a feature's route")
async def put_route(feature: str, body: RouteUpdate, request: Request,
                    admin_user=Depends(ROUTING_UPDATE), db: Session = Depends(get_db)) -> Dict[str, Any]:
    if body.remote_allowed_for == "all":
        current = db.query(FeatureRoute).filter(FeatureRoute.feature == feature).first()
        if current is None or current.remote_allowed_for != "all":
            if not body.current_password or not verify_password(body.current_password, admin_user.hashed_password):
                raise HTTPException(status_code=403, detail="Opening remote engines to every user needs current_password")
    spec = routing.RouteSpec(**body.model_dump(exclude={"version", "current_password"}))
    try:
        route, warnings = routing.put_route(db, feature, spec, version=body.version, actor_user_id=str(admin_user.id),
                                            auth_method="jwt", ip=request.client.host if request.client else None,
                                            fingerprint_of=fingerprint_of, remote_worker_alive=_remote_worker_alive)
    except routing.VersionConflict as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except routing.RouteError as e:
        db.rollback()
        raise HTTPException(status_code=e.status, detail=str(e))

    lease = db.get(DispatcherLease, 1)
    if dispatch.dispatcher_down(routing.load_route(db, feature), lease.dispatcher_seen_at if lease else None,
                                datetime.utcnow()):
        warnings.append("The dispatcher (worker-dispatch, compose profile `engines`) is not running: items "
                        + ("go straight to the local workers (dispatcher_fallback=local_direct) and the API "
                           "watchdog places the backlog" if route.dispatcher_fallback == "local_direct"
                           else "wait in the backlog (dispatcher_fallback=hold)"))
    logger.warning(f"[ADMIN] {admin_user.id} set the {feature} route (version {route.version})")
    engines = {e.id: e for e in db.query(Engine)}
    view = routing.describe(route, engines, feature)
    view["warnings"] = warnings
    return view


@router.delete("/routing/{feature}", status_code=202, summary="Remove a route (it drains back to today's path)")
async def delete_route(feature: str, request: Request, admin_user=Depends(ROUTING_UPDATE),
                       db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        route = routing.drain_route(db, feature, actor_user_id=str(admin_user.id), auth_method="jwt",
                                    ip=request.client.host if request.client else None)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.warning(f"[ADMIN] {admin_user.id} removed the {feature} route; it drains")
    engines = {e.id: e for e in db.query(Engine)}
    view = routing.describe(route, engines, feature)
    view["backlog"] = _backlog(db, feature, datetime.utcnow())
    return view


@router.get("/engines/status", summary="Dispatcher, in-flight work and backlog")
async def engines_status(admin_user=Depends(ROUTING_READ), db: Session = Depends(get_db)) -> Dict[str, Any]:
    now = datetime.utcnow()
    live = _alive_by_feature()
    capacity = []
    for engine in db.query(Engine).order_by(Engine.is_system.desc(), Engine.slug):
        for feature, binding in bindings(engine.config or {}).items():
            row = {
                "engine": engine.slug, "adapter_type": engine.adapter_type, "feature": feature,
                "status": engine.status, "health": engine.health,
                "capacity": binding.capacity, "in_flight": in_flight(db, engine.id, feature),
                "fallback_in_flight": db.query(func.count(EngineUsage.id)).filter(
                    EngineUsage.engine_id == engine.id, EngineUsage.feature == feature,
                    EngineUsage.placed_by == "fallback",
                    EngineUsage.status.in_(("reserved", "spawning", "running"))).scalar() or 0,
            }
            if engine.adapter_type == "local":
                row["workers_configured"] = binding.workers
                row["workers_alive"] = len(live.get(feature, [])) if live else None
            capacity.append(row)
    return {
        "dispatcher": _lease_view(db, now),
        "engines": capacity,
        "backlog": {feature: _backlog(db, feature, now) for feature in FEATURES},
        "remote_worker": _remote_worker_view(),
    }


def _remote_worker_view() -> Optional[Dict[str, Any]]:
    """worker-remote's heartbeat (None when none is alive)"""
    try:
        from shared.engines.liveness import remote_worker
        from shared.redis_client import get_redis_client
        return remote_worker(get_redis_client().client) or None
    except Exception:
        return None
