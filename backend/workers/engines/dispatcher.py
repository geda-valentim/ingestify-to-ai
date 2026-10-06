"""
The dispatcher: places backlog items on engines by each feature's route
(spec 0003, section 4.4).

One tick, as the leader of the epoch-fenced lease:

    for each feature with an active route:
      candidates = head 20 `waiting` (not_before passed) UNION head 20 that may go
                   remote, in FIFO order (priority, enqueued_at) - so items that
                   can only run locally never hide the ones the cloud could take
      for each candidate:
        for each step, in order, whose conditions hold for it:
          for each engine of the step, in the group's order:
            eligible? (active, healthy, deployed, not excluded, fits max_media_seconds,
                       remote => the item may go remote, not reserved by an earlier
                       blocking candidate)
            under the engine's row lock: in_flight < capacity and the money fits
            -> reserve (engine_usage), CAS waiting->assigned, COMMIT, then publish
        nothing fits -> unplaceable_since; on_no_engine=fail fails it after a while
      skip rule (R7): an earlier candidate passed over while a later one took engine
        M counts a skip only if it could run on M once M's work settled; at 10 it
        reserves M (blocked_engine_id) - later items stop going to M, others go on
    routes being removed (`draining`) hand their backlog back to today's path

Capacity is configured slots minus in-flight ledger rows (reserved/spawning/running,
fallback rows included) - never heartbeats. Heartbeats only decide health.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.engines import budget, dispatch, ledger, routing
from shared.engines.capacity import bindings, deploy_state
from shared.engines.store import in_flight
from shared.models import Engine, EngineFeatureState, EngineUsage, FeatureRoute, JobDispatch
from workers.engines import executors, lease

logger = logging.getLogger(__name__)

HEAD = 20
SKIP_LIMIT = 10
DRAIN_BATCH = 100
BAD_HEALTH = ("unhealthy", "exhausted", "degraded")
LOCAL_UNHEALTHY_AFTER_SECONDS = 180
# The media of a remote item travels in the call (MinIO is not reachable from the
# provider): larger files stay on local steps. Overridable per engine (max_input_bytes)
DEFAULT_MAX_INPUT_BYTES = 512 * 1024 * 1024

# Refusals that only mean "not now": they never make an item unplaceable
TRANSIENT_REFUSALS = {"full", "conditions", "blocked", "conflict"}
MONEY_REFUSALS = {"budget", "spend_cap", "user_cap"}

# This process's leadership, kept between ticks (prefork: one per child)
_leadership: Dict[str, int] = {}


class Fenced(Exception):
    """Our epoch is no longer current: another leader took over; stop writing"""


@dataclass
class TickResult:
    led: bool = False
    epoch: Optional[int] = None
    placed: List[Tuple[int, str, int]] = field(default_factory=list)  # (dispatch id, engine slug, step)
    failed: List[int] = field(default_factory=list)
    drained: List[int] = field(default_factory=list)
    job_changes: list = field(default_factory=list)


@dataclass
class _Tick:
    celery: object
    session_factory: object
    epoch: int
    placed_by: str
    now: datetime
    local_only: bool
    alive: Callable[[str], Optional[int]]
    result: TickResult
    local_unhealthy: Dict[Tuple[str, str], bool] = field(default_factory=dict)


def _session(session_factory) -> Session:
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


def _default_alive(feature: str) -> Optional[int]:
    """Live local workers of a feature (heartbeats); None when Redis cannot tell"""
    try:
        from shared.engines.liveness import alive
        from shared.redis_client import get_redis_client
        return len(alive(feature, get_redis_client().client))
    except Exception:
        return None


def _lead(db: Session, holder: str, kind: str, now: datetime) -> Optional[int]:
    epoch = _leadership.get(holder)
    if epoch is not None and kind == "dispatcher":
        if lease.renew(db, epoch, holder, kind, now):
            return epoch
        logger.warning(f"[ENGINES] {holder} lost the dispatcher lease (epoch {epoch})")
        _leadership.pop(holder, None)
    epoch = lease.acquire(db, holder, kind, now)
    if epoch is not None:
        _leadership[holder] = epoch
    return epoch


def run_tick(*, celery, session_factory=None, holder: Optional[str] = None, kind: str = "dispatcher",
             now: Optional[datetime] = None, local_only: bool = False,
             alive: Optional[Callable[[str], Optional[int]]] = None, redis_client=None,
             only_features: Optional[Set[str]] = None) -> TickResult:
    """
    One dispatcher round. `kind=watchdog` (the API's fallback) takes the lease for
    this round only and places on local steps only (of `only_features`); the rest
    stays in the backlog.
    """
    now = now or datetime.utcnow()
    holder = holder or f"{kind}:{ledger.holder_id()}"
    result = TickResult()
    db = _session(session_factory)
    try:
        epoch = _lead(db, holder, kind, now)
        if epoch is None:
            return result
        result.led, result.epoch = True, epoch
        tick = _Tick(celery, session_factory, epoch, "watchdog" if kind == "watchdog" else "dispatcher", now,
                     local_only, alive or _default_alive, result)
        try:
            routes = routing.load_routes(db)
            db.commit()
            for route in routes:
                if route.active and (only_features is None or route.feature in only_features):
                    _place_feature(tick, route)
            _drain(tick, db, {r.feature: r for r in routes})
        except Fenced:
            logger.warning(f"[ENGINES] {holder}: epoch {epoch} superseded mid-tick; nothing more is placed")
            _leadership.pop(holder, None)
        finally:
            if kind == "watchdog":
                lease.release(db, epoch)
                _leadership.pop(holder, None)
    finally:
        db.close()
    _mirror(result.job_changes, redis_client)
    return result


def _mirror(changes, redis_client) -> None:
    if not changes:
        return
    if redis_client is None:
        try:
            from shared.redis_client import get_redis_client
            redis_client = get_redis_client()
        except Exception:
            return
    for change in changes:
        ledger.apply_job_change(redis_client, change)


# --- one feature ---------------------------------------------------------------------


def _candidates(db: Session, feature: str, now: datetime, with_remote: bool) -> List[JobDispatch]:
    base = (db.query(JobDispatch)
            .filter(JobDispatch.feature == feature, JobDispatch.state == "waiting",
                    or_(JobDispatch.not_before.is_(None), JobDispatch.not_before <= now))
            .order_by(JobDispatch.priority, JobDispatch.enqueued_at, JobDispatch.id))
    rows = {d.id: d for d in base.limit(HEAD).all()}
    if with_remote:
        for d in base.filter(JobDispatch.remote_allowed.is_(True)).limit(HEAD).all():
            rows.setdefault(d.id, d)
    return sorted(rows.values(), key=lambda d: (d.priority, d.enqueued_at, d.id))


def _place_feature(tick: _Tick, route: routing.RouteSnapshot) -> None:
    db = _session(tick.session_factory)
    try:
        engines = {e.id: e for e in db.query(Engine).filter(Engine.id.in_(route.engine_ids()))}
        with_remote = any(e.adapter_type != "local" for e in engines.values())
        for engine in engines.values():
            if engine.adapter_type == "local":
                tick.local_unhealthy[(engine.id, route.feature)] = _local_health(tick, db, engine, route.feature)
        candidates = _candidates(db, route.feature, tick.now, with_remote)
        if not candidates:
            return
        backlog = db.query(func.count(JobDispatch.id)).filter(
            JobDispatch.feature == route.feature, JobDispatch.state == "waiting").scalar() or 0
        db.commit()

        blocked: Dict[str, int] = {}  # engine id -> the earlier candidate that reserved it
        unplaced: List[JobDispatch] = []
        for cand in candidates:
            placed_on, refusals = _try_place(tick, db, route, cand, engines, backlog, blocked)
            if placed_on is not None:
                backlog -= 1
                for earlier in unplaced:
                    _count_skip(tick, db, route, earlier, placed_on, engines, blocked)
            else:
                unplaced.append(cand)
                if cand.blocked_engine_id:
                    blocked.setdefault(cand.blocked_engine_id, cand.id)
                _unplaceable(tick, db, route, cand, refusals)
    finally:
        db.close()


def _conditions_hold(step: dict, cand: JobDispatch, backlog: int, now: datetime) -> Optional[str]:
    """Which condition lets the item use this step ("order" without conditions); None if none holds"""
    when = step.get("when") or {}
    if not when:
        return "order"
    if when.get("min_wait_seconds") is not None and (now - cand.enqueued_at).total_seconds() >= when["min_wait_seconds"]:
        return "min_wait"
    if when.get("min_backlog") is not None and backlog >= when["min_backlog"]:
        return "min_backlog"
    return None


def _excluded(cand: JobDispatch, engine_id: str, now: datetime) -> bool:
    for entry in cand.exclude_engines or []:
        if entry.get("engine_id") != engine_id:
            continue
        until = entry.get("until")
        if until is None or datetime.fromisoformat(until) > now:
            return True
    return False


def _ineligible(tick: _Tick, engine: Engine, cand: JobDispatch, feature: str, blocked: Dict[str, int]) -> Optional[str]:
    if engine.status != "active":
        return "paused"
    if engine.health in BAD_HEALTH and (engine.health_until is None or engine.health_until > tick.now):
        return "unhealthy"
    binding = bindings(engine.config or {}).get(feature)
    if binding is None or binding.capacity <= 0:
        return "no_binding"
    executor = executors.get(engine.adapter_type)
    if executor is None:
        return "no_executor"
    state = (executor.deploy_state(engine, feature, binding) if hasattr(executor, "deploy_state")
             else deploy_state(engine.adapter_type, engine.deployments, feature, binding))
    if state in ("needs_redeploy", "not_deployed"):
        return "not_deployed"
    if tick.local_unhealthy.get((engine.id, feature)):
        return "unhealthy"
    if _excluded(cand, engine.id, tick.now):
        return "excluded"
    options = (((cand.payload or {}).get('kwargs') or {}).get('options') or {})
    if feature == 'transcription' and options.get('transcriber_provider') == 'whisperx':
        if executor.remote:
            capabilities = ((engine.deployments or {}).get(feature) or {}).get('capabilities', [])
            if not {'whisperx', 'diarization', 'transcript_schema_2'} <= set(capabilities):
                return 'diarization_not_ready'
        else:
            from shared.config import get_settings
            if not get_settings().whisperx_diarization_ready:
                return 'diarization_not_ready'
        # The fixed 3 GB legacy footprint cannot qualify this pipeline.
        if not binding.vram_override_gb:
            return 'whisperx_footprint_required'
    if executor.remote:
        max_bytes = (engine.config or {}).get("max_input_bytes") or DEFAULT_MAX_INPUT_BYTES
        if cand.media_bytes and int(cand.media_bytes) > int(max_bytes):
            return "too_large"
        if tick.local_only:
            return "local_only"
        if not cand.remote_allowed:
            return "not_remote_allowed"
        if cand.media_seconds is None:
            return "not_probed"
        if cand.solo and binding.executions_per_worker > 1:
            return "solo"
    max_media = (engine.config or {}).get("max_media_seconds")
    if max_media and cand.media_seconds is not None and float(cand.media_seconds) > float(max_media):
        return "too_long"
    if blocked.get(engine.id) not in (None, cand.id):
        return "blocked"
    return None


def _estimate(executor, engine: Engine, binding, cand: JobDispatch, db: Session) -> Decimal:
    """The executor's reservation for the item; remote ones read the key's learned speed through `db`"""
    if getattr(executor, "wants_db", False):
        return executor.estimate(engine, binding, cand, db=db)
    return executor.estimate(engine, binding, cand)


def _latest_job_rows(db: Session, engines: List[Engine], feature: str, now: datetime) -> Dict[str, datetime]:
    """Each engine's latest kind=job row in its current budget period (probes, benchmarks and tails never count)"""
    latest = {}
    for engine in engines:
        start = budget.period_start(engine, now)
        at = (db.query(func.max(EngineUsage.created_at))
              .filter(EngineUsage.engine_id == engine.id, EngineUsage.feature == feature, EngineUsage.kind == "job",
                      EngineUsage.period_start == start).scalar())
        if at is not None:
            latest[engine.id] = at
    return latest


def _group_order(tick: _Tick, db: Session, step: dict, engines: List[Engine], cand, feature, blocked) -> List[Engine]:
    """
    priority: as listed. fill_first: the current engine first - the eligible one
    with the latest kind=job row of its period, else the first listed - then the
    rest in the group's order after it (spec 0003, 4.5)
    """
    if step.get("group_strategy") != "fill_first" or len(engines) < 2:
        return engines
    latest = _latest_job_rows(db, engines, feature, tick.now)
    eligible = [e for e in engines if latest.get(e.id) and _ineligible(tick, e, cand, feature, blocked) is None]
    if not eligible:
        return engines
    current = max(eligible, key=lambda e: latest[e.id])
    i = engines.index(current)
    return engines[i:] + engines[:i]


def _try_place(tick: _Tick, db: Session, route, cand: JobDispatch, engines: Dict[str, Engine], backlog: int,
               blocked: Dict[str, int]) -> Tuple[Optional[Engine], Set[str]]:
    refusals: Set[str] = set()
    for index, step in enumerate(route.steps):
        step_engines = [engines[i] for i in step["engine_ids"] if i in engines]
        if tick.local_only:
            step_engines = [e for e in step_engines if e.adapter_type == "local"]
        if not step_engines:
            continue
        reason = _conditions_hold(step, cand, backlog, tick.now)
        if reason is None:
            refusals.add("conditions")
            continue
        for engine in _group_order(tick, db, step, step_engines, cand, route.feature, blocked):
            why = _ineligible(tick, engine, cand, route.feature, blocked)
            if why:
                refusals.add(why)
                continue
            outcome = _place(tick, db, route, cand, engine, index, step, reason)
            if outcome == "placed":
                return engine, refusals
            refusals.add(outcome)
            if outcome == "conflict":
                return None, refusals
            if outcome == "full" and step.get("group_strategy") == "fill_first" and not _scaled_out(db, engine, route.feature, step, tick.now):
                break  # the current engine is full but not for long enough: the group waits for it
    return None, refusals


def _place(tick: _Tick, db: Session, route, cand: JobDispatch, engine: Engine, index: int, step: dict,
           reason: str) -> str:
    feature = route.feature
    executor = executors.get(engine.adapter_type)
    binding = bindings(engine.config or {})[feature]
    estimate = _estimate(executor, engine, binding, cand, db)
    now = tick.now
    try:
        if not lease.holds(db, tick.epoch):
            db.rollback()
            raise Fenced()
        locked = db.query(Engine).filter(Engine.id == engine.id).with_for_update().one()
        if in_flight(db, locked.id, feature) >= binding.capacity:
            db.rollback()
            _set_full(db, locked.id, feature, now)
            return "full"
        period = budget.period_start(locked, now)
        refusal = None
        if not budget.admits(db, locked, estimate, period):
            refusal = "budget"
        elif not budget.spend_cap_ok(db, locked, feature, step.get("spend_cap"), estimate, now):
            refusal = "spend_cap"
        elif (executor.remote and route.remote_allowed_for == "all" and route.user_period_limit_usd is not None
                and cand.user_id and budget.user_committed(db, cand.user_id, period) + estimate
                > Decimal(str(route.user_period_limit_usd))):
            refusal = "user_cap"
        if refusal:
            db.rollback()
            _clear_full(db, engine.id, feature)  # it has room: a later "full" starts a new full_since
            return refusal
        values = dict(
            kind="job", engine_id=locked.id, feature=feature, subject_type=cand.subject_type,
            subject_id=cand.subject_id, attempt=cand.placements + 1, job_id=cand.job_id, user_id=cand.user_id,
            period_start=period, status="reserved", placed_by=tick.placed_by, dispatch_epoch=tick.epoch,
            gpu_type=binding.gpu_type or binding.gpu_ref, executions_per_worker=binding.executions_per_worker,
            estimated_usd=estimate, reserved_usd=estimate, rate_usd_per_s=0, heartbeat_at=now, created_at=now,
        )
        if hasattr(executor, "reservation_values"):  # remote: rate, price snapshot, fingerprint
            values.update(executor.reservation_values(locked, binding, feature))
        usage = EngineUsage(**values)
        db.add(usage)
        db.flush()
        usage_id = usage.id
        if not ledger.cas_dispatch(db, cand, ("waiting",), now, state="assigned", usage_id=usage_id,
                                   engine_id=locked.id, placed_step=index + 1, place_reason=reason,
                                   assigned_at=now, placements=cand.placements + 1, skip_count=0,
                                   blocked_engine_id=None, unplaceable_since=None, not_before=None):
            db.rollback()
            return "conflict"
        db.commit()
    except IntegrityError:
        db.rollback()
        return "conflict"

    _clear_full(db, engine.id, feature)
    try:
        executor.publish(tick.celery, engine, cand, usage_id)
        dispatch.mark_published(tick.session_factory, usage_id, tick.now)
    except Exception as e:  # the sweeper republishes a reservation that was never published
        logger.error(f"[ENGINES] Placed {feature} item {cand.id} on {engine.slug} but could not publish: {e}")
    tick.result.placed.append((cand.id, engine.slug, index + 1))
    logger.info(f"[ENGINES] {feature} item {cand.id} (job {cand.job_id}) -> {engine.slug}, step {index + 1} "
                f"({reason}), usage {usage_id}, epoch {tick.epoch}")
    return "placed"


# --- fill_first: how long the current engine has been full -------------------------


def _feature_state(db: Session, engine_id: str, feature: str, now: datetime) -> EngineFeatureState:
    state = db.get(EngineFeatureState, (engine_id, feature))
    if state is None:
        state = EngineFeatureState(engine_id=engine_id, feature=feature, updated_at=now)
        db.add(state)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            state = db.get(EngineFeatureState, (engine_id, feature))
    return state


def _set_full(db: Session, engine_id: str, feature: str, now: datetime) -> None:
    state = _feature_state(db, engine_id, feature, now)
    if state.full_since is None:
        state.full_since = now
        db.commit()


def _clear_full(db: Session, engine_id: str, feature: str) -> None:
    state = db.get(EngineFeatureState, (engine_id, feature))
    if state is not None and state.full_since is not None:
        state.full_since = None
        db.commit()


def _scaled_out(db: Session, engine: Engine, feature: str, step: dict, now: datetime) -> bool:
    state = db.get(EngineFeatureState, (engine.id, feature))
    after = step.get("scale_out_after_seconds", routing.DEFAULT_SCALE_OUT_AFTER_SECONDS)
    return bool(state and state.full_since and (now - state.full_since).total_seconds() >= after)


# --- local health (heartbeats decide health, never capacity) -------------------------


def _local_health(tick: _Tick, db: Session, engine: Engine, feature: str) -> bool:
    """True when no worker of the lane has been seen for local_unhealthy_after_seconds"""
    state = _feature_state(db, engine.id, feature, tick.now)
    if state.workers_seen_at is None:
        state.workers_seen_at = tick.now  # first look: give the lane its grace period
    alive = tick.alive(feature)
    binding = bindings(engine.config or {}).get(feature)
    if alive:
        state.workers_seen_at = tick.now
    if alive is not None and binding is not None:
        if alive < binding.workers:
            if state.alive_below_configured_since is None:
                state.alive_below_configured_since = tick.now
            elif (tick.now - state.alive_below_configured_since).total_seconds() > 300:
                logger.warning(f"[ENGINES] {feature}: {alive} local workers alive of {binding.workers} configured "
                               f"since {state.alive_below_configured_since:%H:%M:%S}")
        else:
            state.alive_below_configured_since = None
    db.commit()
    limit = (engine.config or {}).get("local_unhealthy_after_seconds", LOCAL_UNHEALTHY_AFTER_SECONDS)
    return alive == 0 and (tick.now - state.workers_seen_at).total_seconds() > limit


# --- skips, holds and failures ------------------------------------------------------


def _could_run_on(tick: _Tick, db: Session, route, cand: JobDispatch, engine: Engine) -> bool:
    """Would the candidate fit on `engine` once its in-flight work settled? (R7)"""
    step = next((s for s in route.steps if engine.id in s["engine_ids"]), None)
    executor = executors.get(engine.adapter_type)
    binding = bindings(engine.config or {}).get(route.feature)
    if step is None or executor is None or binding is None:
        return False
    if executor.remote and (not cand.remote_allowed or cand.media_seconds is None):
        return False
    max_media = (engine.config or {}).get("max_media_seconds")
    if max_media and cand.media_seconds is not None and float(cand.media_seconds) > float(max_media):
        return False
    estimate = _estimate(executor, engine, binding, cand, db)
    if not budget.could_ever_admit(db, engine, estimate, budget.period_start(engine, tick.now)):
        return False
    return budget.spend_cap_ok(db, engine, route.feature, step.get("spend_cap"), estimate, tick.now,
                               include_reserved=False)


def _count_skip(tick: _Tick, db: Session, route, earlier: JobDispatch, engine: Engine,
                engines: Dict[str, Engine], blocked: Dict[str, int]) -> None:
    if not _could_run_on(tick, db, route, earlier, engine):
        return
    db.execute(update(JobDispatch).where(JobDispatch.id == earlier.id, JobDispatch.state == "waiting")
               .values(skip_count=JobDispatch.skip_count + 1).execution_options(synchronize_session=False))
    skips = db.query(JobDispatch.skip_count).filter(JobDispatch.id == earlier.id).scalar() or 0
    if skips >= SKIP_LIMIT:
        n = db.execute(update(JobDispatch)
                       .where(JobDispatch.id == earlier.id, JobDispatch.state == "waiting",
                              JobDispatch.blocked_engine_id.is_(None))
                       .values(blocked_engine_id=engine.id).execution_options(synchronize_session=False)).rowcount
        if n:
            blocked.setdefault(engine.id, earlier.id)
            logger.info(f"[ENGINES] {route.feature} item {earlier.id} skipped {skips} times: "
                        f"reserves {engine.slug} until it is placed")
    db.commit()


def _unplaceable(tick: _Tick, db: Session, route, cand: JobDispatch, refusals: Set[str]) -> None:
    if refusals & TRANSIENT_REFUSALS or not refusals:
        return  # waiting for capacity or a condition is not "nothing can take it"
    since = cand.unplaceable_since
    if since is None:
        db.execute(update(JobDispatch).where(JobDispatch.id == cand.id, JobDispatch.state == "waiting",
                                             JobDispatch.unplaceable_since.is_(None))
                   .values(unplaceable_since=tick.now).execution_options(synchronize_session=False))
        db.commit()
        since = tick.now
    if route.on_no_engine != "fail" or route.fail_after_seconds is None:
        return
    if (tick.now - since).total_seconds() < route.fail_after_seconds:
        return
    code = "budget_exhausted" if refusals & MONEY_REFUSALS else "no_engine"
    change = ledger.fail_dispatch(db, cand, code, f"{code}: no engine of the route can run this item",
                                  tick.now, from_states=("waiting",))
    db.commit()
    if change:
        tick.result.failed.append(cand.id)
        tick.result.job_changes.append(change)


# --- routes being removed ------------------------------------------------------------


def _drain(tick: _Tick, db: Session, routes: Dict[str, routing.RouteSnapshot]) -> None:
    """
    Items of a draining route - or left behind by a route that is gone - go back
    to today's path in batches of 100; the route row is deleted once nothing of
    the feature is left in the backlog (spec 0003, Appendix E).
    """
    open_features = {f for f, in db.query(JobDispatch.feature).filter(
        JobDispatch.state.in_(ledger.OPEN_DISPATCH)).distinct()}
    draining = {f for f, r in routes.items() if not r.active} | {f for f in open_features if f not in routes}
    for feature in sorted(draining):
        rows = (db.query(JobDispatch)
                .filter(JobDispatch.feature == feature, JobDispatch.state.in_(("probing", "waiting")))
                .order_by(JobDispatch.priority, JobDispatch.enqueued_at, JobDispatch.id).limit(DRAIN_BATCH).all())
        items = [(d.id, d.version, d.payload) for d in rows]
        for item_id, version, payload in items:
            if not lease.holds(db, tick.epoch):
                db.rollback()
                raise Fenced()
            db.rollback()  # release the share lock before publishing
            try:
                dispatch.publish_today(tick.celery, feature, payload)
            except Exception as e:
                logger.error(f"[ENGINES] Could not hand {feature} item {item_id} back to today's path: {e}")
                break
            n = db.query(JobDispatch).filter(JobDispatch.id == item_id, JobDispatch.version == version,
                                             JobDispatch.state.in_(("probing", "waiting"))).delete(synchronize_session=False)
            db.commit()
            if n:
                tick.result.drained.append(item_id)
            else:
                logger.warning(f"[ENGINES] {feature} item {item_id} changed while being drained")
        route = routes.get(feature)
        if route is not None and not route.active:
            left = db.query(func.count(JobDispatch.id)).filter(
                JobDispatch.feature == feature, JobDispatch.state.in_(ledger.OPEN_DISPATCH)).scalar()
            if not left:
                db.query(FeatureRoute).filter(FeatureRoute.feature == feature, FeatureRoute.state == "draining",
                                              FeatureRoute.version == route.version).delete(synchronize_session=False)
                db.commit()
                routing.invalidate_cache()
                logger.info(f"[ENGINES] The {feature} route finished draining and was removed")
