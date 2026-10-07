"""Admin control APIs: JWT-only; machine endpoints have distinct host authority."""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from api.error_guidance import GuidedRoute
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from sqlalchemy.orm import Session
from shared.config import get_settings
from shared.database import get_db, SessionLocal
from shared.engine_control import service, registry, catalog
from shared.engine_control.contracts import Closed, RuntimeSettings, PlanRequest
from shared.engine_control.models import EngineOperation, OperationPlan, ControlHost
from shared.models import Engine
from api.engine_admin_routes import require_admin_session, _engine_or_404
from api.admin_routes import require_admin
from api.access_deps import access_session, scoped_engine, scoped_features
from api.iam_deps import engine_access
from shared.access import policy

# 0009 routes: engine_access only declares them in the IAM inventory (0014 CA1).
router = APIRouter(prefix="/admin", tags=["Admin - Engine control"], dependencies=[Depends(engine_access())], route_class=GuidedRoute)
host_router = APIRouter(prefix="/internal/engine-hosts", tags=["Engine hosts"])


def enabled():
    if not get_settings().engine_control_enabled:
        raise HTTPException(503, detail={"code": "CONTROL_NOT_ENABLED"})


def invoke(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except service.ControlError as exc:
        raise HTTPException(exc.status, detail=exc.detail()) from None
    except ValueError as exc:
        # Adapter gates (e.g. HOST_AGENT_NOT_READY) keep INVALID_CONFIGURATION as the
        # code and surface the gate as `cause` with its own message (0009 CA1).
        from shared import error_catalog

        raise HTTPException(
            422,
            detail=error_catalog.detail(
                "INVALID_CONFIGURATION",
                text=str(exc),
                context=getattr(exc, "context", None),
            ),
        ) from None


class ProfileUpdate(Closed):
    feature: str
    version: int = Field(ge=0)
    profile: RuntimeSettings


class Execute(Closed):
    plan_id: str
    plan_hash: str
    confirm_paid_operation: bool = False


class Connection(Closed):
    adapter_type: str
    display_name: str = Field(min_length=1, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")


@router.get("/engine-control-adapters")
def adapters(user=Depends(access_session), db: Session = Depends(get_db)):
    return policy.visible_catalog(db, user.id, registry.descriptors(), "adapter")


@router.post("/engines", status_code=201)
def connection(
    body: Connection, user=Depends(require_admin_session), db: Session = Depends(get_db)
):
    enabled()
    d = invoke(registry.descriptor, body.adapter_type)
    if not d.get("create_connection", False):
        raise HTTPException(422, detail={"code": "SYSTEM_ENGINE_ALREADY_EXISTS"})
    if db.query(Engine).filter_by(slug=body.slug).first():
        raise HTTPException(409, detail={"code": "SLUG_IN_USE"})
    e = Engine(
        slug=body.slug,
        display_name=body.display_name,
        adapter_type=body.adapter_type,
        config={"features": {}},
        deployments={},
        status="paused",
        health="unknown",
        credentials_masked={},
        created_by=user.id,
    )
    db.add(e)
    db.flush()
    from shared.engines.store import audit

    audit(
        db,
        actor_user_id=user.id,
        auth_method="jwt",
        ip=None,
        action="engine.created",
        engine=e,
        before=None,
        after={"slug": e.slug},
    )
    db.commit()
    return {"id": e.id, "slug": e.slug}


@router.get("/engines/{engine_id}/capabilities")
def caps(
    engine_id: str,
    feature: str | None = None,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    e = scoped_engine(db, engine_id, user.id, feature)
    descriptor = invoke(registry.descriptor, e.adapter_type)
    features = scoped_features(db, e, user.id, descriptor["features"])
    if not features:
        raise HTTPException(404, detail={"code": "ENGINE_NOT_FOUND"})
    selected = feature if feature is not None else features[0]
    out = invoke(service.capabilities, db, e, selected)
    filtered = policy.visible_catalog(db, user.id, [descriptor], "adapter")
    if filtered:
        out.update(
            {k: v for k, v in filtered[0].items() if k not in ("actions", "features")}
        )
    out["features"] = features
    latest = service.latest_profile(db, e.id, selected)
    profile_visible = not latest or policy.allowed(
        db,
        user.id,
        "engines.read",
        engine=e,
        feature=selected,
        profile=service.source_profile(db, latest.source_profile_revision_id),
        runtime=latest.profile,
    )
    if not profile_visible:
        out["managed"] = False
    out["hosts"] = policy.visible_catalog(db, user.id, out["hosts"], "host")
    for action in out["actions"]:
        if not profile_visible or not policy.allowed(
            db,
            user.id,
            "engine_operations.execute." + action["type"],
            engine=e,
            feature=selected,
        ):
            from shared import error_catalog

            message, steps = error_catalog.describe("ACCESS_DENIED")
            action.update(
                enabled=False, reason="ACCESS_DENIED", message=message, next_steps=steps
            )
    return out


@router.get("/model-profiles")
def model_profiles(user=Depends(access_session), db: Session = Depends(get_db)):
    return policy.visible_catalog(db, user.id, catalog.profiles(), "model")


@router.get("/engines/{engine_id}/runtime-profile")
def get_profile(
    engine_id: str,
    feature: str = "transcription",
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    e = scoped_engine(db, engine_id, user.id, feature)
    p = service.latest_profile(db, e.id, feature)
    if p and not policy.allowed(
        db,
        user.id,
        "engines.read",
        engine=e,
        feature=feature,
        runtime=p.profile,
        profile=service.source_profile(db, p.source_profile_revision_id),
    ):
        raise HTTPException(404, detail={"code": "RUNTIME_PROFILE_NOT_FOUND"})
    return service.profile_view(p)


@router.put("/engines/{engine_id}/runtime-profile")
def put_profile(
    engine_id: str,
    body: ProfileUpdate,
    user=Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    enabled()
    return invoke(
        service.save_profile,
        db,
        _engine_or_404(db, engine_id),
        body.feature,
        body.profile.model_dump(mode="json"),
        body.version,
        str(user.id),
    )


@router.get("/engines/{engine_id}/runtime-status")
def status(engine_id: str, user=Depends(access_session), db: Session = Depends(get_db)):
    enabled()
    e = scoped_engine(db, engine_id, user.id)
    out = service.runtime_status(db, e)
    fs = scoped_features(db, e, user.id, out["desired"].keys())
    out["desired"] = {
        k: v
        for k, v in out["desired"].items()
        if k in fs
        and policy.allowed(
            db,
            user.id,
            "engines.read",
            engine=e,
            feature=k,
            runtime=v["profile"],
            profile=service.source_profile(db, v.get("source_profile_revision_id")),
        )
    }
    out["applied"] = [
        r
        for r in out["applied"]
        if r["feature"] in fs
        and policy.allowed(
            db,
            user.id,
            "engines.read",
            engine=e,
            feature=r["feature"],
            runtime=r["profile"],
            profile=service.source_profile(db, r.get("source_profile_revision_id")),
        )
    ]
    out["resources"] = [
        r
        for r in out["resources"]
        if policy.allowed(db, user.id, "engines.read", engine=e, resources=[r["key"]])
    ]
    return out


@router.post("/engines/{engine_id}/operation-plans")
def plan(
    engine_id: str,
    body: PlanRequest,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    return invoke(
        service.create_plan,
        db,
        scoped_engine(db, engine_id, user.id, body.feature),
        body,
        str(user.id),
    )


@router.post("/engines/{engine_id}/operations", status_code=202)
def execute(
    engine_id: str,
    body: Execute,
    idempotency_key: str = Header(...),
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    e = scoped_engine(db, engine_id, user.id)
    p = db.get(OperationPlan, body.plan_id)
    if not p or p.engine_id != e.id:
        raise HTTPException(404, detail={"code": "PLAN_NOT_FOUND"})
    return invoke(
        service.enqueue,
        db,
        body.plan_id,
        body.plan_hash,
        idempotency_key,
        str(user.id),
        body.confirm_paid_operation,
    )


@router.get("/engine-operations")
def history(
    engine_id: str | None = None,
    limit: int = 50,
    before: str | None = None,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    q = policy.scoped_query(db, user.id, db.query(EngineOperation), "operation")
    if engine_id:
        q = q.filter_by(engine_id=scoped_engine(db, engine_id, user.id).id)
    if before:
        old = invoke(service.authorize_operation, db, before, user.id)
        if old:
            q = q.filter(EngineOperation.created_at < old.created_at)
    page_size = min(max(limit, 1), 100)
    # Scan already scoped SQL in bounded chunks until enough identity-qualified rows are found.
    rows = []
    offset = 0
    while len(rows) < page_size:
        candidates = (
            q.order_by(EngineOperation.created_at.desc(), EngineOperation.id.desc())
            .offset(offset)
            .limit(100)
            .all()
        )
        if not candidates:
            break
        rows.extend(r for r in candidates if can_read_operation(db, r, user.id))
        offset += len(candidates)
        if len(candidates) < 100:
            break
    rows = rows[:page_size]
    return {
        "operations": [operation_view(db, x, user.id) for x in rows],
        "next": rows[-1].id if rows else None,
    }


@router.get("/engine-operations/{operation_id}")
def snapshot(
    operation_id: str,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    op = invoke(service.authorize_operation, db, operation_id, user.id)
    if not op:
        raise HTTPException(404, detail={"code": "OPERATION_NOT_FOUND"})
    return operation_view(db, op, user.id)


@router.get("/engine-operations/{operation_id}/events")
def events(
    operation_id: str,
    after: int = 0,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    invoke(service.authorize_operation, db, operation_id, user.id)
    return invoke(service.events, db, operation_id, max(after, 0))


@router.post("/engine-operations/{operation_id}/cancel")
def cancel(
    operation_id: str,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    return invoke(service.request_cancel, db, operation_id, user.id)


@router.get("/engine-operations/{operation_id}/stream")
async def stream(
    operation_id: str,
    request: Request,
    after: int = 0,
    user=Depends(access_session),
):
    enabled()

    # Validate existence before sending headers, never place credentials in URLs.
    def read(cursor, reauthorize=True):
        with SessionLocal() as db:
            if reauthorize:
                from shared.models import User
                from shared.auth import verify_token

                fresh = db.get(User, user.id)
                token = request.headers.get("authorization", "").split(" ", 1)[-1]
                try:
                    subject = verify_token(token)
                    if (
                        str(subject) != str(user.id)
                        or not fresh
                        or not fresh.is_active
                    ):
                        return None
                except Exception:
                    return None
            try:
                service.authorize_operation(db, operation_id, user.id)
            except service.ControlError:
                if reauthorize:
                    return None
                raise HTTPException(404, detail={"code": "OPERATION_NOT_FOUND"})
            return invoke(service.events, db, operation_id, cursor)

    await run_in_threadpool(read, max(after, 0), False)

    async def gen():
        import time

        start = time.monotonic()
        cursor = max(after, 0)
        while time.monotonic() - start < 60:
            if await request.is_disconnected():
                return
            # Reauthorize on each poll without blocking the ASGI loop or holding
            # a SQL session for the lifetime of the streaming connection.
            page = await run_in_threadpool(read, cursor)
            if page is None:
                return
            for ev in page["events"]:
                cursor = ev["seq"]
                yield f"id: {cursor}\nevent: operation\ndata: {json.dumps(jsonable_encoder(ev))}\n\n"
            if not page["has_more"]:
                if page["state"] in service.TERMINAL:
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def host_identity(host_id: str, request: Request):
    enabled()
    path = get_settings().engine_host_identities_file
    try:
        identities = json.loads(Path(path).read_text())
        presented = request.headers.get("x-engine-host-token", "")
        expected = identities.get(host_id, "")
        if (
            len(presented) < 32
            or not expected
            or not hmac.compare_digest(
                hashlib.sha256(presented.encode()).hexdigest(), expected
            )
        ):
            raise ValueError()
    except Exception:
        raise HTTPException(403, detail={"code": "HOST_IDENTITY_REQUIRED"}) from None
    return host_id


class HostHeartbeat(Closed):
    inventory: dict


@host_router.post("/{host_id}/heartbeat")
def host_heartbeat(
    host_id: str, body: HostHeartbeat, request: Request, db: Session = Depends(get_db)
):
    host_identity(host_id, request)
    if set(body.inventory) - {
        "services",
        "manifest_hash",
        "gpu_uuids",
        "project",
        "images",
        "readiness",
    }:
        raise HTTPException(422, detail={"code": "INVALID_INVENTORY"})
    h = db.get(ControlHost, host_id) or ControlHost(id=host_id)
    h.inventory = body.inventory
    h.seen_at = datetime.utcnow()
    db.add(h)
    db.commit()
    return {"ok": True}


@host_router.get("/{host_id}/next")
def host_next(host_id: str, request: Request, db: Session = Depends(get_db)):
    host_identity(host_id, request)
    for op in (
        db.query(EngineOperation)
        .filter_by(state="running")
        .order_by(EngineOperation.created_at)
        .limit(100)
    ):
        if (op.handles or {}).get("host_id") != host_id or (op.handles or {}).get(
            "host_result"
        ):
            continue
        p = db.get(OperationPlan, op.plan_id)
        if (
            op.lease_until is None
            or op.lease_until <= datetime.utcnow()
            or op.cancel_requested
        ):
            continue
        try:
            policy.operation_authority(db, op)
        except service.ControlError:
            continue
        return {
            "operation_id": op.id,
            "generation": op.generation,
            "plan": p.body,
            "observe_only": bool(op.handles.get("recovery_observe")),
        }
    return None


@host_router.get("/{host_id}/operations/{op_id}/check")
def host_check(
    host_id: str,
    op_id: str,
    generation: int,
    request: Request,
    db: Session = Depends(get_db),
):
    host_identity(host_id, request)
    if policy.enabled():
        invoke(policy.epoch, db, True)
    op = invoke(service.fenced, db, op_id, generation)
    invoke(policy.operation_authority, db, op, effect=policy.enabled())
    if op.handles.get("host_id") != host_id:
        raise HTTPException(403)
    return {"cancel_requested": op.cancel_requested, "deadline": op.deadline}


class HostEvent(Closed):
    generation: int
    stage: str
    message: str = Field(max_length=8192)
    effect: bool = False


@host_router.post("/{host_id}/operations/{op_id}/events")
def host_event(
    host_id: str,
    op_id: str,
    body: HostEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    host_identity(host_id, request)
    if body.effect and policy.enabled():
        invoke(policy.epoch, db, True)
    op = invoke(service.fenced, db, op_id, body.generation)
    if op.handles.get("host_id") != host_id:
        raise HTTPException(403)
    invoke(
        service.event,
        db,
        op_id,
        body.generation,
        body.stage,
        {"message": body.message},
        effect=body.effect,
    )
    return {"ok": True}


class HostResult(Closed):
    generation: int
    ok: bool
    observed: dict = Field(default_factory=dict)
    code: str | None = None


@host_router.post("/{host_id}/operations/{op_id}/result")
def host_result(
    host_id: str,
    op_id: str,
    body: HostResult,
    request: Request,
    db: Session = Depends(get_db),
):
    host_identity(host_id, request)
    op = invoke(service.fenced, db, op_id, body.generation)
    if op.handles.get("host_id") != host_id:
        raise HTTPException(403)
    op.handles = dict(
        op.handles or {},
        host_result=service.clean(body.model_dump(exclude={"generation"})),
    )
    db.commit()
    return {"ok": True}


@router.post("/engine-operations/{operation_id}/recover", status_code=202)
def recover(
    operation_id: str,
    user=Depends(access_session),
    db: Session = Depends(get_db),
):
    enabled()
    return invoke(service.request_recovery, db, operation_id, user.id)


def can_read_operation(db, op, actor):
    try:
        service.authorize_operation(db, op.id, actor)
        return True
    except service.ControlError:
        return False


def operation_view(db, op, actor):
    out = service.operation_view(op)
    for flag, permission in [
        ("can_cancel", "engine_operations.cancel"),
        ("can_recover", "engine_operations.recover"),
    ]:
        try:
            service.authorize_operation(db, op.id, actor, permission)
        except service.ControlError:
            out[flag] = False
    return out
