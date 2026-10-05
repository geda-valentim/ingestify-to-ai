"""
Celery tasks of worker-remote (spec 0003, slice 4a; compose profile `engines`).

    ingestify-remote      execute_remote(usage_id)   one remote attempt (workers/engines/remote.py)
    ingestify-remote-ctl  test_engine(engine_id)     credentials + deployment, no GPU
                          test_all_engines()         the same for every account, in turn
                          cancel_remote(usage_id)    stop a call past its deadline (sweeper)
                          reconcile_spend()          the provider's own spend report (every 10 min)
                          probe_engines()            cheap health of accounts used in 24 h (10 min)

Only worker-remote consumes these queues, and only it holds the private keys
that open engine credentials. Nothing is published here on an install without
a remote engine in a route, and importing this module loads no provider SDK.

worker-remote also announces itself every 10 s (engines:remote:heartbeat, 30 s
TTL): a route with a remote step is refused while nobody is listening.
"""

import logging
import socket
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from celery.signals import worker_ready, worker_shutting_down

from shared.config import get_settings
from shared.engines import alerts, budget, budget_watch, ledger
from shared.engines.liveness import REMOTE_KEY, REMOTE_TTL_SECONDS
from shared.engines.redact import redact
from shared.models import Engine, EngineUsage
from workers.celery_app import celery_app
from workers.engines import remote
from workers.engines.base import EngineError, ErrorCode, HealthReport

logger = logging.getLogger(__name__)
settings = get_settings()

HEARTBEAT_SECONDS = 10
_stop = threading.Event()


def _session(session_factory=None):
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


# --- execution ------------------------------------------------------------------------------


@celery_app.task(name="workers.engines.remote_tasks.execute_remote", acks_late=True)
def execute_remote(usage_id: int):
    from shared.elasticsearch_client import get_es_client

    return {"usage_id": usage_id, "outcome": remote.run(usage_id, celery=celery_app, es_client=get_es_client())}


@celery_app.task(name="workers.engines.remote_tasks.cancel_remote", soft_time_limit=60, time_limit=90)
def cancel_remote(usage_id: int):
    return cancel_usage(usage_id)


def cancel_usage(usage_id: int, session_factory=None) -> str:
    """Cancel the provider call of a remote attempt (the sweeper asks once its deadline is long past)"""
    db = _session(session_factory)
    try:
        usage = db.get(EngineUsage, usage_id)
        if usage is None or usage.status not in ("spawning", "running"):
            return "nothing to cancel"
        engine = db.get(Engine, usage.engine_id)
        call_id, key = usage.provider_call_id, usage.attempt_key
        db.expunge(engine)
    finally:
        db.close()
    adapter = remote.adapter_factory(engine, remote.open_credentials(engine))
    adapter.cancel(call_id, key)
    logger.warning(f"[ENGINES] Usage {usage_id}: cancel sent to {engine.slug} (call {call_id})")
    return "cancelled"


# --- control ---------------------------------------------------------------------------------


def test_engine_now(engine_id: str, *, session_factory=None) -> Dict[str, Any]:
    """
    Open the engine's credentials and check them against the provider (auth,
    workspace, deployment) without starting a container. The outcome is
    recorded on the engine (`config.last_test`, health) - activation requires a
    passing test newer than the credentials.
    """
    db = _session(session_factory)
    try:
        engine = db.query(Engine).filter((Engine.id == engine_id) | (Engine.slug == engine_id)).first()
        if engine is None:
            return HealthReport(False, "NOT_FOUND", f"no engine {engine_id!r}").as_dict()
        db.expunge(engine)
    finally:
        db.close()
    if engine.adapter_type == "local":
        return HealthReport(True, None, "the local engine needs no connection test").as_dict()
    try:
        report = remote.adapter_factory(engine, remote.open_credentials(engine)).test_connection()
    except EngineError as e:
        report = HealthReport(False, e.code, redact(e.detail)[:500], checked_at=datetime.utcnow().isoformat())
    except Exception as e:
        report = HealthReport(False, ErrorCode.INTERNAL, redact(f"{type(e).__name__}: {e}")[:500],
                              checked_at=datetime.utcnow().isoformat())
    result = report.as_dict()

    def record(db):
        row = db.query(Engine).filter(Engine.id == engine.id).with_for_update().one()
        config = dict(row.config or {})
        config["last_test"] = {"ok": report.ok, "code": report.code, "at": report.checked_at,
                               "deployed": report.deployed, "detail": report.detail[:300]}
        row.config = config
        credential_problem = row.health == "unhealthy" and (row.health_reason or "").startswith(("AUTH", "TEST"))
        if report.ok and (row.health == "unknown" or credential_problem):
            row.health, row.health_reason, row.health_until = "healthy", None, None
        elif not report.ok:
            row.health, row.health_reason, row.health_until = "unhealthy", f"TEST {report.code}: {report.detail}"[:1000], None
    ledger.run_txn(session_factory, record)
    logger.info(f"[ENGINES] Test of {engine.slug}: {'ok' if report.ok else report.code} - {report.detail}")
    return result


@celery_app.task(name="workers.engines.remote_tasks.test_engine", soft_time_limit=25, time_limit=40)
def test_engine(engine_id: str):
    return test_engine_now(engine_id)


def _next_period(engine: Engine, start: date) -> date:
    return budget.next_period_start(engine, start)


# The billing report's resolution (cents); "zero while our ledger says otherwise" only counts above
# max(0.50, 5 x resolution), for longer than 3 h (spec 0003, 4.8)
BILLING_RESOLUTION_USD = Decimal("0.01")
ZERO_REPORT_LEDGER_USD = max(Decimal("0.50"), 5 * BILLING_RESOLUTION_USD)
ZERO_REPORT_HOURS = 3


def _remote_engines(session_factory, only: Optional[str] = None) -> List[Engine]:
    db = _session(session_factory)
    try:
        query = db.query(Engine).filter(Engine.adapter_type != "local")
        if only:
            query = query.filter((Engine.id == only) | (Engine.slug == only))
        engines = [e for e in query.order_by(Engine.slug).all()
                   if e.credentials_sealed and (only or e.status == "active")]
        for e in engines:
            db.expunge(e)
        return engines
    finally:
        db.close()


def reconcile_now(*, session_factory=None, now: Optional[datetime] = None, only: Optional[str] = None) -> Dict[str, Any]:
    """
    Pull each remote engine's spend for its current period from the provider and
    keep the larger of what was known and what is reported (never decreases). A
    report that cannot be read marks the engine `degraded` - it takes no new work
    until a later report succeeds (fail closed; spec 0003, 4.8). So does a report
    of zero for more than 3 h while our own ledger has settled more than US$ 0.50.
    Then the period's alerts and exhaustion are re-evaluated (budget_watch).
    `only` (id or slug) reconciles one engine, paused or not.
    """
    now = now or datetime.utcnow()
    out: Dict[str, Any] = {}
    for engine in _remote_engines(session_factory, only):
        start = budget.period_start(engine, now)
        try:
            adapter = remote.adapter_factory(engine, remote.open_credentials(engine))
            spent = adapter.provider_spend(start, _next_period(engine, start))
        except Exception as e:
            reason = redact(f"BILLING: {e}")[:1000]
            out[engine.slug] = {"error": reason}
            _degrade(session_factory, engine, reason, now)
            continue

        def store(db, engine_id=engine.id, spent=spent, start=start):
            row = db.query(Engine).filter(Engine.id == engine_id).with_for_update().one()
            previous = row.provider_reported_usd if row.provider_reported_period == start else None
            row.provider_reported_usd = max(spent, previous) if previous is not None else spent
            row.provider_reported_period = start
            row.provider_reported_at = now
            ledger_usd = budget.settled(db, engine_id, start)
            config = dict(row.config or {})
            zero_since = None
            if row.provider_reported_usd == 0 and ledger_usd > ZERO_REPORT_LEDGER_USD:
                zero_since = config.get("billing_zero_since") or now.isoformat()
            if zero_since != config.get("billing_zero_since"):
                if zero_since is None:
                    config.pop("billing_zero_since", None)
                else:
                    config["billing_zero_since"] = zero_since
                row.config = config
            stuck_at_zero = zero_since is not None and \
                (now - datetime.fromisoformat(zero_since)).total_seconds() > ZERO_REPORT_HOURS * 3600
            if stuck_at_zero:
                return row.provider_reported_usd, ledger_usd, "zero"
            if row.health == "degraded" and (row.health_reason or "").startswith("BILLING"):
                row.health, row.health_reason, row.health_until = "healthy", None, None
            return row.provider_reported_usd, ledger_usd, None
        reported, ledger_usd, problem = ledger.run_txn(session_factory, store)
        out[engine.slug] = {"reported_usd": str(reported), "ledger_usd": str(ledger_usd),
                            "unattributed_usd": str(reported - ledger_usd), "period": start.isoformat()}
        if problem == "zero":
            reason = (f"BILLING: the report says US$ 0 for over {ZERO_REPORT_HOURS} h while the ledger settled "
                      f"US$ {ledger_usd} this period")
            out[engine.slug]["error"] = reason
            _degrade(session_factory, engine, reason, now)
            continue
        budget_watch.check(engine.id, session_factory=session_factory, now=now)
    return out


def _degrade(session_factory, engine: Engine, reason: str, now: datetime) -> None:
    def degrade(db, engine_id=engine.id):
        row = db.query(Engine).filter(Engine.id == engine_id).with_for_update().one()
        if row.health in ("unknown", "healthy"):
            row.health, row.health_reason, row.health_until = "degraded", reason, None
            return True
        return False
    if ledger.run_txn(session_factory, degrade):
        alerts.alert(alerts.BILLING_DEGRADED, engine.slug, f"spend report unusable, no new work: {reason}",
                     now=now)
    else:
        logger.warning(f"[ENGINES] Spend of {engine.slug} could not be read: {reason}")


@celery_app.task(name="workers.engines.remote_tasks.reconcile_spend", soft_time_limit=240, time_limit=300)
def reconcile_spend():
    return reconcile_now()


@celery_app.task(name="workers.engines.remote_tasks.reconcile_one", soft_time_limit=75, time_limit=90)
def reconcile_one(engine_id: str):
    return reconcile_now(only=engine_id)


# --- cheap health probes and testing every account (slice 4c) ----------------------------------

PROBE_USED_WITHIN_HOURS = 24
PROBE_UNHEALTHY_MINUTES = 10


def probe_engines_now(*, session_factory=None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Health of the active remote engines that ran a job in the last 24 h, without a
    container: test_connection() only checks the token, the workspace and that the
    deployed app answers with the fingerprint this engine recorded (spec 0003,
    A12). Free, so no ledger row. A failure keeps the engine off routes for 10 min
    (AUTH: until a new test) and alerts; transient errors change nothing.
    """
    now = now or datetime.utcnow()
    engines = _remote_engines(session_factory)
    db = _session(session_factory)
    try:
        since = now - timedelta(hours=PROBE_USED_WITHIN_HOURS)
        used = {e for e, in db.query(EngineUsage.engine_id).filter(
            EngineUsage.kind == "job", EngineUsage.created_at >= since).distinct()}
    finally:
        db.close()
    out: Dict[str, Any] = {}
    for engine in engines:
        if engine.id not in used:
            out[engine.slug] = "skipped: no job in 24 h"
            continue
        try:
            report = remote.adapter_factory(engine, remote.open_credentials(engine)).test_connection()
        except EngineError as e:
            report = HealthReport(False, e.code, redact(e.detail)[:300], checked_at=now.isoformat())
        except Exception as e:
            report = HealthReport(False, ErrorCode.TRANSIENT, redact(f"{type(e).__name__}: {e}")[:300],
                                  checked_at=now.isoformat())
        problem, code = None, report.code
        recorded = {f: (d or {}).get("fingerprint") for f, d in (engine.deployments or {}).items()}
        if not report.ok:
            problem = f"PROBE {report.code}: {report.detail}"
        elif report.deployed is False and any(recorded.values()):
            problem, code = "PROBE NOT_DEPLOYED: the app is gone from the account", ErrorCode.NOT_DEPLOYED
        elif report.deployed_fingerprint and any(recorded.values()) \
                and report.deployed_fingerprint not in recorded.values():
            problem, code = (f"PROBE DEPLOY_CHANGED: the account serves {report.deployed_fingerprint[:12]}, "
                             f"not what this engine recorded"), ErrorCode.NOT_DEPLOYED
        if code == ErrorCode.TRANSIENT:
            out[engine.slug] = {"ok": None, "detail": "transient, unchanged: " + report.detail[:200]}
            continue

        def record(db, engine_id=engine.id, problem=problem, code=code):
            row = db.query(Engine).filter(Engine.id == engine_id).with_for_update().one()
            config = dict(row.config or {})
            config["last_probe"] = {"ok": problem is None, "code": code if problem else None, "at": now.isoformat()}
            row.config = config
            if problem:
                probe_owned = row.health == "unhealthy" and (row.health_reason or "").startswith("PROBE")
                if row.health in ("unknown", "healthy", "degraded") or probe_owned \
                        or (row.health_until is not None and row.health_until <= now):
                    row.health, row.health_reason = "unhealthy", problem[:1000]
                    row.health_until = None if code == ErrorCode.AUTH else now + timedelta(minutes=PROBE_UNHEALTHY_MINUTES)
            elif row.health == "unhealthy" and (row.health_reason or "").startswith("PROBE"):
                row.health, row.health_reason, row.health_until = "healthy", None, None
        ledger.run_txn(session_factory, record)
        out[engine.slug] = {"ok": problem is None, "detail": problem or report.detail[:200]}
        if problem:
            alerts.alert(alerts.ENGINE_PROBE_FAILED, engine.slug, problem, {"code": code}, now=now)
    return out


@celery_app.task(name="workers.engines.remote_tasks.probe_engines", soft_time_limit=240, time_limit=300)
def probe_engines():
    return probe_engines_now()


def test_all_now(*, session_factory=None) -> Dict[str, Any]:
    """test_engine_now() on every remote engine with credentials, one after the other (paused ones too)"""
    db = _session(session_factory)
    try:
        slugs = [e.slug for e in db.query(Engine).filter(Engine.adapter_type != "local").order_by(Engine.slug)
                 if e.credentials_sealed]
    finally:
        db.close()
    return {slug: test_engine_now(slug, session_factory=session_factory) for slug in slugs}


@celery_app.task(name="workers.engines.remote_tasks.test_all_engines", soft_time_limit=170, time_limit=200)
def test_all_engines():
    return test_all_now()


# --- worker-remote heartbeat -----------------------------------------------------------------


def heartbeat_fields(hostname: str) -> Dict[str, str]:
    try:
        keys = bool(settings.engine_private_keys())
    except OSError:
        keys = False
    return {"hostname": hostname, "concurrency": str(settings.remote_worker_concurrency),
            "private_keys": "yes" if keys else "no", "updated_at": f"{time.time():.0f}"}


def publish_heartbeat(hostname: str, client=None) -> None:
    if client is None:
        from shared.redis_client import get_redis_client
        client = get_redis_client().client
    pipe = client.pipeline()
    pipe.hset(REMOTE_KEY, mapping=heartbeat_fields(hostname))
    pipe.expire(REMOTE_KEY, REMOTE_TTL_SECONDS)
    pipe.execute()


def _loop(hostname: str) -> None:
    while not _stop.is_set():
        try:
            publish_heartbeat(hostname)
        except Exception as e:  # a heartbeat must never take the worker down
            logger.warning(f"[ENGINES] worker-remote heartbeat failed: {e}")
        _stop.wait(HEARTBEAT_SECONDS)


@worker_ready.connect
def _start(sender=None, **kwargs):
    try:
        queues = {q.name for q in sender.task_consumer.queues}
    except Exception:
        return
    if settings.remote_queue not in queues:
        return
    hostname = getattr(sender, "hostname", None) or socket.gethostname()
    threading.Thread(target=_loop, args=(hostname,), name="engine-remote-heartbeat", daemon=True).start()
    logger.info(f"[ENGINES] worker-remote heartbeat started as {hostname}")


@worker_shutting_down.connect
def _stop_heartbeat(**kwargs):
    _stop.set()
