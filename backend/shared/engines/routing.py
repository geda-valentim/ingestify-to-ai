"""
Feature routes: the user's ordered rule for where a feature's work runs.

A route is a list of steps; the order is the priority. A step names one engine
or a group of equivalent engines (strategy `priority` or `fill_first`) and may
carry conditions (`when.min_wait_seconds` / `when.min_backlog`, combined with OR)
and a `spend_cap`. With a route, every item of the feature goes through the
durable backlog (job_dispatches) and the dispatcher places it; without one -
the default - nothing here is consulted and the code runs as it always did
(spec 0003, sections 4.4-4.5).

Reading a route never fails a request: any error reads as "no route" (today's
path), cached for 5 s.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, FrozenSet, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from shared.engines.capacity import bindings
from shared.engines.features import FEATURES, get_feature
from shared.models import AdminAudit, Engine, FeatureRoute

logger = logging.getLogger(__name__)

CACHE_SECONDS = 5.0
DEFAULT_SCALE_OUT_AFTER_SECONDS = 300
MAX_STEPS = 10

# Remote adapters with an executor (workers/engines/executors.py). A remote engine
# joins a route only when it is active, healthy, deployed and budgeted, and while a
# worker-remote is alive to run it (spec 0003, slice 4a)
REMOTE_ADAPTERS = frozenset({"modal"})
BAD_HEALTH = ("unhealthy", "exhausted", "degraded")
# Threads of worker-remote kept for control tasks (test, cancel, reconcile)
REMOTE_CONTROL_THREADS = 2
# Every feature has a routed entry point (spec 0003, slice 8): transcription jobs and
# document pages through the backlog (dispatch.submit), vision requests inline in the
# API (dispatch.place_now). Remote engines only run what their adapter supports
# (capacity.ADAPTER_FEATURES: Modal runs transcription), so Docling and vision routes
# are local-only for now.
ROUTABLE_FEATURES = frozenset({"transcription", "document_conversion", "vision"})
REMOTE_ROUTABLE_FEATURES = frozenset({"transcription"})


class When(BaseModel):
    min_wait_seconds: Optional[int] = Field(None, ge=0, le=7 * 86400)
    min_backlog: Optional[int] = Field(None, ge=1, le=100_000)

    @model_validator(mode="after")
    def _something(self):
        if self.min_wait_seconds is None and self.min_backlog is None:
            raise ValueError("when needs min_wait_seconds and/or min_backlog")
        return self


class SpendCap(BaseModel):
    usd: Decimal = Field(gt=0, max_digits=12, decimal_places=6)
    window: Literal["day", "period"]


class RouteStep(BaseModel):
    position: Optional[int] = None  # assigned from the order on save
    engine_ids: List[str] = Field(min_length=1, max_length=20)  # ids or slugs; stored as ids
    group_strategy: Literal["priority", "fill_first"] = "priority"
    scale_out_after_seconds: Optional[int] = Field(None, ge=0, le=86400)
    when: Optional[When] = None
    spend_cap: Optional[SpendCap] = None


class RouteSpec(BaseModel):
    steps: List[RouteStep] = Field(min_length=1, max_length=MAX_STEPS)
    on_no_engine: Literal["hold", "fail"] = "hold"
    fail_after_seconds: Optional[int] = Field(None, ge=0, le=30 * 86400)
    max_attempts: int = Field(3, ge=1, le=10)
    remote_allowed_for: Literal["admins", "all"] = "admins"
    user_period_limit_usd: Optional[Decimal] = Field(None, ge=0, max_digits=12, decimal_places=6)
    remote_data_notice: Optional[str] = Field(None, max_length=2000)
    dispatcher_fallback: Literal["local_direct", "hold"] = "local_direct"
    dispatcher_down_seconds: int = Field(120, ge=30, le=3600)

    @model_validator(mode="after")
    def _fail_needs_a_deadline(self):
        if self.on_no_engine == "fail" and self.fail_after_seconds is None:
            raise ValueError("on_no_engine=fail needs fail_after_seconds")
        return self


class RouteError(ValueError):
    """A route that cannot be saved; `status` is the HTTP status the API answers with"""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class VersionConflict(Exception):
    """The route changed since the caller read it"""


@dataclass(frozen=True)
class RouteSnapshot:
    """A route as the hot paths see it: plain values, safe to cache and share"""
    feature: str
    state: str
    steps: Tuple[Dict[str, Any], ...]
    on_no_engine: str
    fail_after_seconds: Optional[int]
    max_attempts: int
    remote_allowed_for: str
    user_period_limit_usd: Optional[Decimal]
    dispatcher_fallback: str
    dispatcher_down_seconds: int
    version: int
    local_engine_ids: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def active(self) -> bool:
        return self.state == "active"

    def has_local_step(self) -> bool:
        return any(set(s["engine_ids"]) & self.local_engine_ids for s in self.steps)

    def engine_ids(self) -> List[str]:
        return [e for s in self.steps for e in s["engine_ids"]]


def snapshot(route: FeatureRoute, local_engine_ids) -> RouteSnapshot:
    return RouteSnapshot(
        feature=route.feature, state=route.state, steps=tuple(route.steps or ()),
        on_no_engine=route.on_no_engine, fail_after_seconds=route.fail_after_seconds,
        max_attempts=route.max_attempts or 3, remote_allowed_for=route.remote_allowed_for,
        user_period_limit_usd=route.user_period_limit_usd, dispatcher_fallback=route.dispatcher_fallback,
        dispatcher_down_seconds=route.dispatcher_down_seconds or 120, version=route.version or 0,
        local_engine_ids=frozenset(local_engine_ids),
    )


def load_route(db: Session, feature: str) -> Optional[RouteSnapshot]:
    """The route of a feature straight from the database (no cache)"""
    route = db.query(FeatureRoute).filter(FeatureRoute.feature == feature).first()
    if route is None:
        return None
    ids = {e for s in (route.steps or []) for e in s.get("engine_ids", [])}
    local = {e.id for e in db.query(Engine).filter(Engine.id.in_(ids), Engine.adapter_type == "local")} if ids else set()
    return snapshot(route, local)


def load_routes(db: Session) -> List[RouteSnapshot]:
    return [r for r in (load_route(db, f) for f, in db.query(FeatureRoute.feature).all()) if r is not None]


# --- cached read for the request and task hot paths ---------------------------------

_cache: Dict[str, Tuple[float, Optional[RouteSnapshot]]] = {}
_cache_lock = threading.Lock()


def _default_session_factory():
    from shared.database import SessionLocal
    return SessionLocal()


def get_route(feature: str, session_factory=None, clock=time.monotonic) -> Optional[RouteSnapshot]:
    """
    The feature's route, cached for 5 s. Any error reading it counts as "no route",
    so a database hiccup sends work down today's path instead of failing it.
    """
    now = clock()
    with _cache_lock:
        hit = _cache.get(feature)
        if hit and hit[0] > now:
            return hit[1]
    try:
        db = (session_factory or _default_session_factory)()
        try:
            route = load_route(db, feature)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[ENGINES] Could not read the {feature} route, using the default path: {type(e).__name__}")
        route = None
    with _cache_lock:
        _cache[feature] = (now + CACHE_SECONDS, route)
    return route


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()


# --- validation and changes ---------------------------------------------------------


def _resolve(db: Session, ref: str) -> Engine:
    engine = db.query(Engine).filter((Engine.id == ref) | (Engine.slug == ref)).first()
    if engine is None:
        raise RouteError(f"No engine {ref!r}")
    return engine


def _remote_worker_alive() -> bool:
    try:
        from shared.engines.liveness import remote_worker
        from shared.redis_client import get_redis_client
        return bool(remote_worker(get_redis_client().client))
    except Exception:
        return False


def remote_problems(engine: Engine, feature: str, fingerprint_of=None, now: Optional[datetime] = None) -> List[str]:
    """Why a remote engine cannot be routed now (empty when it can)"""
    from shared.engines.capacity import deploy_state

    now = now or datetime.utcnow()
    problems = []
    from workers.engines import executors
    if executors.get(engine.adapter_type) is None:
        problems.append(f"adapter {engine.adapter_type!r} has no executor")
    if engine.status != "active":
        problems.append("it is not active (POST /admin/engines/{id}/activate)")
    if engine.health in BAD_HEALTH and (engine.health_until is None or engine.health_until > now):
        problems.append(f"its health is {engine.health} ({engine.health_reason or 'no reason recorded'})")
    if engine.limit_usd is None:
        problems.append("it has no budget (limit_usd)")
    binding = bindings(engine.config or {}).get(feature)
    if binding is not None:
        expected = fingerprint_of(engine, feature, binding) if fingerprint_of else None
        state = deploy_state(engine.adapter_type, engine.deployments, feature, binding, expected)
        if state != "deployed":
            problems.append(f"{feature} is {state} (engines.py modal-deploy --engine {engine.slug})")
    return problems


def remote_capacity(db: Session, steps: List[Dict[str, Any]], overrides: Optional[Dict[str, dict]] = None) -> int:
    """Sum of the remote capacity a set of steps can keep in flight (each remote item holds a worker-remote thread)"""
    total = 0
    for step in steps:
        for engine_id in step.get("engine_ids", []):
            engine = db.get(Engine, engine_id)
            from shared.engine_control.registry import execution_mode
            if engine is None or execution_mode(engine.adapter_type) != 'remote_runner':
                continue
            config = (overrides or {}).get(engine_id, engine.config or {})
            total += sum(b.capacity for b in bindings(config).values())
    return total


def remote_threads_available() -> int:
    from shared.config import get_settings
    return get_settings().remote_worker_concurrency - REMOTE_CONTROL_THREADS


def validate(db: Session, feature: str, spec: RouteSpec, *, fingerprint_of=None,
             remote_worker_alive=None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Check a route against the engines it names. Returns the steps to store (engine
    ids resolved, positions assigned) and the warnings to show; raises RouteError.
    `fingerprint_of(engine, feature, binding)` (from workers/engines/remote.py) lets
    a remote engine whose deployed code is stale be refused like a stale binding.
    """
    try:
        get_feature(feature)
    except ValueError as e:
        raise RouteError(str(e))
    if feature not in ROUTABLE_FEATURES:
        raise RouteError(f"{feature} cannot be routed yet (spec 0003, slice 8); "
                         f"routable: {', '.join(sorted(ROUTABLE_FEATURES))}")

    steps, seen, has_local, has_remote = [], set(), False, False
    remote_engines = []
    for position, step in enumerate(spec.steps, start=1):
        ids = []
        for ref in step.engine_ids:
            engine = _resolve(db, ref)
            if engine.id in seen:
                raise RouteError(f"Engine {engine.slug} appears more than once in the route")
            seen.add(engine.id)
            if feature not in bindings(engine.config or {}):
                raise RouteError(
                    f"Engine {engine.slug} has no capacity for {feature}: "
                    f"set it first (PUT /admin/engines/{engine.slug}/features/{feature})"
                )
            from shared.engine_control.registry import external_data
            if not external_data(engine.adapter_type):
                has_local = True
            else:
                if feature not in REMOTE_ROUTABLE_FEATURES:
                    raise RouteError(f"Engine {engine.slug} is remote; {feature} runs on local engines only "
                                     f"(no remote adapter for it yet)")
                has_remote = True
                remote_engines.append(engine)
            ids.append(engine.id)
        raw = step.model_dump(mode="json", exclude_none=True)
        raw.update(position=position, engine_ids=ids)
        if step.group_strategy == "fill_first" and step.scale_out_after_seconds is None:
            raw["scale_out_after_seconds"] = DEFAULT_SCALE_OUT_AFTER_SECONDS
        steps.append(raw)

    if has_remote and spec.remote_allowed_for == "admins" and not has_local:
        raise RouteError("A route with a remote step and remote_allowed_for=admins needs a local step "
                         "(otherwise nobody else's work could run)")
    if spec.remote_allowed_for == "all" and (spec.user_period_limit_usd is None or not spec.remote_data_notice):
        raise RouteError("remote_allowed_for=all needs user_period_limit_usd and remote_data_notice")
    if has_remote:
        broken = {e.slug: remote_problems(e, feature, fingerprint_of) for e in remote_engines}
        broken = {slug: p for slug, p in broken.items() if p}
        if broken:
            raise RouteError("Remote engines not ready: " + "; ".join(
                f"{slug}: {', '.join(p)}" for slug, p in broken.items()), status=409)
        from shared.engine_control.registry import execution_mode
        needs_remote_worker=any(execution_mode(e.adapter_type)=='remote_runner' for e in remote_engines)
        if needs_remote_worker and not (remote_worker_alive or _remote_worker_alive)():
            raise RouteError("No worker-remote is running to execute remote steps: "
                             "docker compose --profile engines up -d worker-remote", status=409)
        needed, available = remote_capacity(db, steps), remote_threads_available()
        if needed > available:
            raise RouteError(f"The route's remote capacity ({needed}) exceeds what worker-remote can hold "
                             f"(REMOTE_WORKER_CONCURRENCY - {REMOTE_CONTROL_THREADS} = {available})", status=409)

    warnings = []
    first_ids = set(steps[0]["engine_ids"])
    from shared.engine_control.registry import external_data
    first_is_remote = not any(not external_data(_resolve(db,i).adapter_type) for i in first_ids)
    if first_is_remote and spec.dispatcher_fallback == "local_direct":
        warnings.append("The first step is remote but dispatcher_fallback=local_direct: while the dispatcher "
                        "is down new items go to the local workers, against the order. Use hold to keep it.")
    return steps, warnings


def _audit(db: Session, *, actor_user_id, auth_method, ip, action, feature, before, after) -> None:
    db.add(AdminAudit(actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action=action,
                      target_type="route", target_id=feature, before=before, after=after))


def route_values(route: Optional[FeatureRoute]) -> Optional[Dict[str, Any]]:
    if route is None:
        return None
    return {
        "state": route.state, "steps": route.steps, "on_no_engine": route.on_no_engine,
        "fail_after_seconds": route.fail_after_seconds, "max_attempts": route.max_attempts,
        "remote_allowed_for": route.remote_allowed_for,
        "user_period_limit_usd": float(route.user_period_limit_usd) if route.user_period_limit_usd is not None else None,
        "remote_data_notice": route.remote_data_notice, "dispatcher_fallback": route.dispatcher_fallback,
        "dispatcher_down_seconds": route.dispatcher_down_seconds, "version": route.version,
    }


def put_route(db: Session, feature: str, spec: RouteSpec, *, version: Optional[int], actor_user_id: Optional[str],
              auth_method: str, ip: Optional[str] = None, fingerprint_of=None,
              remote_worker_alive=None) -> Tuple[FeatureRoute, List[str]]:
    """Create or replace a feature's route (active); validated, versioned and audited"""
    steps, warnings = validate(db, feature, spec, fingerprint_of=fingerprint_of,
                               remote_worker_alive=remote_worker_alive)
    route = db.query(FeatureRoute).filter(FeatureRoute.feature == feature).with_for_update().first()
    if route is not None and version is not None and version != route.version:
        raise VersionConflict(f"The {feature} route is at version {route.version}, not {version}; re-read it")
    before = route_values(route)
    if route is None:
        route = FeatureRoute(feature=feature, version=0)
        db.add(route)
    route.state = "active"
    route.steps = steps
    for name in ("on_no_engine", "fail_after_seconds", "max_attempts", "remote_allowed_for",
                 "user_period_limit_usd", "remote_data_notice", "dispatcher_fallback", "dispatcher_down_seconds"):
        setattr(route, name, getattr(spec, name))
    route.version = (route.version or 0) + 1
    route.updated_by = actor_user_id
    route.updated_at = datetime.utcnow()
    db.flush()
    _audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="route.set",
           feature=feature, before=before, after=route_values(route))
    db.commit()
    invalidate_cache()
    return route, warnings


def drain_route(db: Session, feature: str, *, actor_user_id: Optional[str], auth_method: str,
                ip: Optional[str] = None) -> FeatureRoute:
    """
    Remove a route without stranding its backlog: it turns `draining`, new items
    take today's path at once, and the dispatcher hands the queued ones back in
    batches; the row disappears when nothing is left (spec 0003, Appendix E).
    """
    route = db.query(FeatureRoute).filter(FeatureRoute.feature == feature).with_for_update().first()
    if route is None:
        raise LookupError(f"No route for {feature}")
    before = route_values(route)
    route.state = "draining"
    route.version = (route.version or 0) + 1
    route.updated_by = actor_user_id
    route.updated_at = datetime.utcnow()
    _audit(db, actor_user_id=actor_user_id, auth_method=auth_method, ip=ip, action="route.drain",
           feature=feature, before=before, after=route_values(route))
    db.commit()
    invalidate_cache()
    return route


def describe(route: Optional[FeatureRoute], engines_by_id: Dict[str, Engine], feature: str) -> Dict[str, Any]:
    """A route for the admin API; a feature without one shows the implicit "today's path" route"""
    if route is None:
        return {"feature": feature, "implicit": True, "state": "active", "steps": [],
                "description": "no route: today's path (the feature's own queue, no backlog, no dispatcher)",
                "version": 0, "updated_at": None, "updated_by": None}
    steps = []
    for s in route.steps or []:
        step = dict(s)
        step["engines"] = [{"id": i, "slug": engines_by_id[i].slug if i in engines_by_id else None,
                            "adapter_type": engines_by_id[i].adapter_type if i in engines_by_id else None}
                           for i in s.get("engine_ids", [])]
        steps.append(step)
    values = route_values(route)
    values.update(feature=feature, implicit=False, steps=steps,
                  updated_at=route.updated_at.isoformat() if route.updated_at else None,
                  updated_by=route.updated_by)
    return values


def parse_step(text: str) -> RouteStep:
    """
    A step as the CLI writes it: engines (comma-separated slugs) then options, e.g.
    "local" or "modal_1,modal_2 fill_first min_wait=600 min_backlog=20 scale_out=300 cap=1.50/day"
    """
    parts = text.split()
    if not parts:
        raise ValueError("Empty step")
    step: Dict[str, Any] = {"engine_ids": [p for p in parts[0].split(",") if p]}
    when: Dict[str, int] = {}
    for option in parts[1:]:
        key, _, value = option.partition("=")
        if key in ("priority", "fill_first") and not value:
            step["group_strategy"] = key
        elif key == "min_wait":
            when["min_wait_seconds"] = int(value)
        elif key == "min_backlog":
            when["min_backlog"] = int(value)
        elif key == "scale_out":
            step["scale_out_after_seconds"] = int(value)
        elif key == "cap":
            usd, _, window = value.partition("/")
            step["spend_cap"] = {"usd": usd, "window": window or "day"}
        else:
            raise ValueError(f"Unknown step option {option!r}")
    if when:
        step["when"] = when
    return RouteStep(**step)


def all_features() -> List[str]:
    return list(FEATURES)
