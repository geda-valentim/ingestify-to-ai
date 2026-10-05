"""
Conditional transitions of the ledger (engine_usage) and the backlog (job_dispatches).

Every change is `UPDATE ... WHERE id=? AND <expected state> [AND version=?]`; zero
rows means someone else moved the row first and nothing is written. A usage row
and its backlog row always change in the same transaction, so a subject is never
left without an owner (spec 0003, section 4.7 and Appendix E):

    claim     reserved -> running            assigned|bypassed -> running
    settle    running  -> settled(succeeded)  running -> done
    failure   running  -> settled(failed)     running -> waiting (backoff) | failed
    lost      running  -> settled(lost|succeeded)   (sweeper, stale heartbeat)
    release   reserved -> released            assigned|bypassed -> waiting (claim timeout)

Workers only claim and settle; they never create, reopen or extend a reservation.
Job state follows Appendix J: PENDING with started_at NULL while in the backlog,
FAILED only on a terminal settle. The Redis mirror is written by the caller with
apply_job_change(), after the commit.
"""

import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional, Tuple

from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from shared.engines.redact import redact
from shared.models import FeatureRoute, Job, JobDispatch, JobStatus, EngineUsage

logger = logging.getLogger(__name__)

IN_FLIGHT = ("reserved", "spawning", "running")
OPEN_DISPATCH = ("probing", "waiting", "assigned", "running", "bypassed")
DEFAULT_MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 60  # the backoff process_conversion's self.retry has always used

# claim() outcomes
CLAIMED = "claimed"
LOST = "lost_claim"  # the row was not `reserved`: someone else has it, or it was released
ALREADY_DONE = "already_done"  # the job completed in an attempt given up as lost
CANCELLED = "cancelled"  # the job is gone, cancelled or failed for good


@dataclass
class JobChange:
    """What the job became, for the Redis mirror (written after the commit)"""
    job_id: str
    status: str  # queued | failed
    error: Optional[str] = None
    name: Optional[str] = None


def holder_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.utcnow()


def _session(session_factory) -> Session:
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


def _retryable(e: OperationalError) -> bool:
    code = getattr(getattr(e, "orig", None), "args", [None])[0]
    return code in (1205, 1213)  # lock wait timeout, deadlock


def run_txn(session_factory, work: Callable[[Session], object], attempts: int = 3):
    """Run `work` in its own transaction, committing on return; retried on deadlock or lock timeout"""
    for attempt in range(1, attempts + 1):
        db = _session(session_factory)
        try:
            result = work(db)
            db.commit()
            return result
        except OperationalError as e:
            db.rollback()
            if attempt == attempts or not _retryable(e):
                raise
            time.sleep(0.05 * attempt)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def cas_dispatch(db: Session, d: JobDispatch, from_states: Iterable[str], now: Optional[datetime] = None,
                 **values) -> bool:
    """Move a backlog row if it is still in one of `from_states` at the version read"""
    values.setdefault("updated_at", _now(now))
    n = db.execute(
        update(JobDispatch)
        .where(JobDispatch.id == d.id, JobDispatch.state.in_(tuple(from_states)), JobDispatch.version == d.version)
        .values(version=JobDispatch.version + 1, **values)
        .execution_options(synchronize_session=False)
    ).rowcount
    return n == 1


def dispatch_of(db: Session, usage: EngineUsage) -> Optional[JobDispatch]:
    return db.query(JobDispatch).filter(JobDispatch.subject_type == usage.subject_type,
                                        JobDispatch.subject_id == usage.subject_id).populate_existing().first()


def max_attempts_for(db: Session, feature: str) -> int:
    route = db.query(FeatureRoute).filter(FeatureRoute.feature == feature).first()
    return (route.max_attempts if route else None) or DEFAULT_MAX_ATTEMPTS


def _job_pending(db: Session, job_id: Optional[str]) -> Optional[JobChange]:
    job = db.get(Job, job_id) if job_id else None
    if job is None:
        return None
    job.status = JobStatus.PENDING
    job.started_at = None
    job.completed_at = None
    return JobChange(job_id, "queued", name=job.name)


def _job_failed(db: Session, job_id: Optional[str], message: str, now: datetime) -> Optional[JobChange]:
    job = db.get(Job, job_id) if job_id else None
    if job is None:
        return None
    job.status = JobStatus.FAILED
    job.error_message = message
    job.completed_at = now
    return JobChange(job_id, "failed", error=message, name=job.name)


def fail_dispatch(db: Session, d: JobDispatch, error_code: str, message: str, now: datetime,
                  from_states: Iterable[str] = OPEN_DISPATCH) -> Optional[JobChange]:
    """Terminal failure of a backlog item (no_engine, budget_exhausted, engine_error...)"""
    if not cas_dispatch(db, d, from_states, now, state="failed", error_code=error_code):
        return None
    return _job_failed(db, d.job_id, message, now) or JobChange(d.job_id or d.subject_id, "failed", error=message)


def excluding(d: JobDispatch, engine_id: str, now: datetime, minutes: int) -> list:
    """The item's exclusions with this engine added for `minutes` (expired ones dropped)"""
    kept = [e for e in (d.exclude_engines or [])
            if e.get("engine_id") != engine_id and (e.get("until") is None or datetime.fromisoformat(e["until"]) > now)]
    return kept + [{"engine_id": engine_id, "until": (now + timedelta(minutes=minutes)).isoformat()}]


def requeue(db: Session, d: JobDispatch, from_states: Iterable[str], now: datetime, *, job_failures: int,
            not_before: Optional[datetime] = None, exclude_engines: Optional[list] = None) -> Optional[JobChange]:
    """Back to the head of the backlog (priority 0); the job reads PENDING again"""
    extra = {"exclude_engines": exclude_engines} if exclude_engines is not None else {}
    if not cas_dispatch(db, d, from_states, now, state="waiting", priority=0, job_failures=job_failures,
                        not_before=not_before, usage_id=None, engine_id=None, assigned_at=None, **extra):
        return None
    return _job_pending(db, d.job_id) or JobChange(d.job_id or d.subject_id, "queued")


def after_failed_attempt(db: Session, d: JobDispatch, *, counts: bool, terminal: bool, error_code: str,
                         message: str, now: datetime, from_states: Iterable[str] = ("running",),
                         exclude_engines: Optional[list] = None) -> Optional[JobChange]:
    """
    The backlog decides what a failed attempt means: back to the queue with the
    backoff process_conversion always had (60 * 2^(n-1) s), or - after
    max_attempts counted failures, or a terminal error - failed for good.
    """
    failures = d.job_failures + (1 if counts else 0)
    if terminal or failures >= max_attempts_for(db, d.feature):
        code = error_code if terminal else "engine_error"
        if not cas_dispatch(db, d, from_states, now, state="failed", error_code=code, job_failures=failures):
            return None
        return _job_failed(db, d.job_id, message, now) or JobChange(d.job_id or d.subject_id, "failed", error=message)
    not_before = now + timedelta(seconds=BACKOFF_BASE_SECONDS * 2 ** (failures - 1)) if counts else None
    return requeue(db, d, from_states, now, job_failures=failures, not_before=not_before,
                   exclude_engines=exclude_engines)


# --- claim, heartbeat, settle (executors and local workers) -------------------------


def claim(usage_id: int, holder: str, *, to_status: str = "running", session_factory=None,
          now: Optional[datetime] = None) -> Tuple[str, Optional[JobChange]]:
    """
    Take a reservation before doing any work. Only `reserved` can be claimed;
    anything else (already running elsewhere, released, settled) means: do not
    run, acknowledge the message and leave.
    """
    now = _now(now)

    def work(db: Session):
        n = db.execute(
            update(EngineUsage)
            .where(EngineUsage.id == usage_id, EngineUsage.status == "reserved")
            .values(status=to_status, holder=holder, heartbeat_at=now, exec_started_at=now)
            .execution_options(synchronize_session=False)
        ).rowcount
        if n == 0:
            return LOST, None
        usage = db.get(EngineUsage, usage_id)
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id or not cas_dispatch(db, d, ("assigned", "bypassed"), now, state="running"):
            db.rollback()
            return LOST, None
        d = dispatch_of(db, usage)
        job = db.get(Job, usage.job_id) if usage.job_id else None
        if job is not None and job.status == JobStatus.COMPLETED:
            # An earlier attempt, given up as lost, finished after all: its output stands
            _settle(db, usage, "succeeded", now, output_persisted_at=job.completed_at or now)
            cas_dispatch(db, d, ("running",), now, state="done")
            return ALREADY_DONE, None
        if job is None or job.status in (JobStatus.CANCELLED, JobStatus.FAILED):
            _settle(db, usage, "cancelled", now, counts=False)
            cas_dispatch(db, d, ("running",), now, state="failed", error_code="cancelled")
            return CANCELLED, None
        return CLAIMED, None

    return run_txn(session_factory, work)


def heartbeat(usage_id: int, holder: str, *, session_factory=None, now: Optional[datetime] = None) -> bool:
    """Renew a claimed row; False once it is no longer ours (the sweeper gave it up)"""
    now = _now(now)

    def work(db: Session):
        return db.execute(
            update(EngineUsage)
            .where(EngineUsage.id == usage_id, EngineUsage.status.in_(("spawning", "running")),
                   EngineUsage.holder == holder)
            .values(heartbeat_at=now)
            .execution_options(synchronize_session=False)
        ).rowcount == 1

    return run_txn(session_factory, work)


def _settle(db: Session, usage: EngineUsage, outcome: str, now: datetime, *, counts: bool = True,
            expected: Iterable[str] = ("reserved", "spawning", "running"), holder: Optional[str] = None,
            **values) -> bool:
    conditions = [EngineUsage.id == usage.id, EngineUsage.status.in_(tuple(expected))]
    if holder is not None:
        conditions.append(EngineUsage.holder == holder)
    values.setdefault("actual_usd", 0)
    values.setdefault("cost_basis", "measured")
    values.setdefault("exec_ended_at", now)
    return db.execute(
        update(EngineUsage).where(*conditions)
        .values(status="settled", outcome=outcome, counts_toward_attempts=counts, finished_at=now, **values)
        .execution_options(synchronize_session=False)
    ).rowcount == 1


def settle_succeeded(usage_id: int, holder: str, *, measured_seconds: Optional[float] = None,
                     session_factory=None, now: Optional[datetime] = None, **values) -> bool:
    """
    Close an attempt whose output is already persisted (finish_* ran). False if the
    sweeper had given the row up meanwhile: the output stands anyway, and the next
    attempt sees the job COMPLETED at its claim and settles without running.
    """
    now = _now(now)

    def work(db: Session):
        usage = db.get(EngineUsage, usage_id)
        if usage is None or not _settle(db, usage, "succeeded", now, expected=("spawning", "running"), holder=holder,
                                        output_persisted_at=now, measured_seconds=measured_seconds, **values):
            return False
        d = dispatch_of(db, usage)
        if d is not None and d.usage_id == usage.id:
            cas_dispatch(db, d, ("running",), now, state="done")
        return True

    return run_txn(session_factory, work)


def settle_failed(usage_id: int, holder: str, *, error_code: str, detail: str = "", counts: bool = True,
                  terminal: bool = False, outcome: str = "failed", exclude_minutes: Optional[int] = None,
                  session_factory=None, now: Optional[datetime] = None, **values) -> Tuple[bool, Optional[JobChange]]:
    """
    Close a failed attempt and let the backlog decide: retry later, or fail the
    job. A remote engine error also keeps the item off that engine for a while
    (`exclude_minutes`), so the next placement walks the route to another one.
    """
    now = _now(now)

    def work(db: Session):
        usage = db.get(EngineUsage, usage_id)
        if usage is None or not _settle(db, usage, outcome, now, counts=counts, expected=("spawning", "running"),
                                        holder=holder, error_code=error_code, error_detail=redact(detail)[:2000],
                                        **values):
            return False, None
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id:
            return True, None
        message = f"{error_code}: {redact(detail)[:500]}" if detail else error_code
        exclude = excluding(d, usage.engine_id, now, exclude_minutes) if exclude_minutes else None
        return True, after_failed_attempt(db, d, counts=counts, terminal=terminal, error_code=error_code,
                                          message=message, now=now, exclude_engines=exclude)

    return run_txn(session_factory, work)


def release(usage_id: int, *, error_code: str = "CLAIM_TIMEOUT", session_factory=None,
            now: Optional[datetime] = None) -> Tuple[bool, Optional[JobChange]]:
    """
    Give back a reservation nobody claimed (claim timeout, drained route): nothing
    was charged and no attempt is counted; the subject goes back to the head of
    the backlog, where any step - this engine included - may take it again.
    """
    now = _now(now)

    def work(db: Session):
        n = db.execute(
            update(EngineUsage).where(EngineUsage.id == usage_id, EngineUsage.status == "reserved")
            .values(status="released", finished_at=now, error_code=error_code, actual_usd=0)
            .execution_options(synchronize_session=False)
        ).rowcount
        if n == 0:
            return False, None
        usage = db.get(EngineUsage, usage_id)
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id:
            return True, None
        return True, requeue(db, d, ("assigned", "bypassed"), now, job_failures=d.job_failures)

    return run_txn(session_factory, work)


def mark_lost(usage_id: int, *, stale_before: datetime, session_factory=None,
              now: Optional[datetime] = None) -> Tuple[Optional[str], Optional[JobChange]]:
    """
    A local attempt whose worker stopped heartbeating (process killed, container
    removed): `succeeded` if the job completed after all, otherwise `lost` - US$ 0,
    counted toward max_attempts so an item that kills its worker cannot loop
    forever - and the subject goes back to the backlog, in the same transaction.
    """
    now = _now(now)

    def work(db: Session):
        usage = db.get(EngineUsage, usage_id)
        if usage is None or usage.status != "running" or (usage.heartbeat_at and usage.heartbeat_at >= stale_before):
            return None, None
        heartbeat_read = usage.heartbeat_at
        conditions = [EngineUsage.id == usage_id, EngineUsage.status == "running"]
        conditions.append(EngineUsage.heartbeat_at == heartbeat_read if heartbeat_read is not None
                          else EngineUsage.heartbeat_at.is_(None))
        job = db.get(Job, usage.job_id) if usage.job_id else None
        completed = job is not None and job.status == JobStatus.COMPLETED
        values = dict(status="settled", outcome="succeeded" if completed else "lost", counts_toward_attempts=not completed,
                      finished_at=now, actual_usd=0, cost_basis="measured",
                      error_code=None if completed else "LOST")
        if completed:
            values["output_persisted_at"] = job.completed_at or now
        n = db.execute(update(EngineUsage).where(*conditions).values(**values)
                       .execution_options(synchronize_session=False)).rowcount
        if n == 0:
            return None, None
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id:
            return values["outcome"], None
        if completed:
            cas_dispatch(db, d, ("running",), now, state="done")
            return "succeeded", None
        return "lost", after_failed_attempt(db, d, counts=True, terminal=False, error_code="LOST",
                                            message="LOST: the worker running this item stopped", now=now)

    return run_txn(session_factory, work)


# --- remote attempts (worker-remote; spec 0003, 4.7 and Appendix E) ---------------------

REFUSED = "refused"  # claim_remote: the engine can no longer take it; released and requeued


def claim_remote(usage_id: int, holder: str, attempt_key: str, check: Callable[[Session, EngineUsage, object], Optional[str]],
                 *, session_factory=None, now: Optional[datetime] = None) -> Tuple[str, Optional[str], Optional[JobChange]]:
    """
    Take a remote reservation: reserved -> spawning with a fresh attempt_key, under
    the engine's row lock, and re-check the engine (CHECK 2: paused, unhealthy,
    redeploy pending, or the budget formula no longer holding with this very
    reservation). A refusal releases the reservation and puts the subject back at
    the head of the backlog in the same transaction. Returns (outcome, refusal
    reason, job change to mirror).
    """
    from shared.models import Engine

    now = _now(now)

    def work(db: Session):
        usage = db.get(EngineUsage, usage_id)
        if usage is None or usage.status != "reserved":
            return LOST, None, None
        engine = db.query(Engine).filter(Engine.id == usage.engine_id).with_for_update().one()
        n = db.execute(
            update(EngineUsage)
            .where(EngineUsage.id == usage_id, EngineUsage.status == "reserved")
            .values(status="spawning", holder=holder, heartbeat_at=now, attempt_key=attempt_key)
            .execution_options(synchronize_session=False)
        ).rowcount
        if n == 0:
            return LOST, None, None
        usage = db.get(EngineUsage, usage_id)
        db.refresh(usage)
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id:
            db.rollback()
            return LOST, None, None
        job = db.get(Job, usage.job_id) if usage.job_id else None
        if job is not None and job.status == JobStatus.COMPLETED:
            cas_dispatch(db, d, ("assigned",), now, state="running")
            d = dispatch_of(db, usage)
            _settle(db, usage, "succeeded", now, output_persisted_at=job.completed_at or now)
            cas_dispatch(db, d, ("running",), now, state="done")
            return ALREADY_DONE, None, None
        if job is None or job.status in (JobStatus.CANCELLED, JobStatus.FAILED):
            cas_dispatch(db, d, ("assigned",), now, state="running")
            d = dispatch_of(db, usage)
            _settle(db, usage, "cancelled", now, counts=False)
            cas_dispatch(db, d, ("running",), now, state="failed", error_code="cancelled")
            return CANCELLED, None, None
        reason = check(db, usage, engine)
        if reason:
            db.execute(update(EngineUsage).where(EngineUsage.id == usage_id)
                       .values(status="released", finished_at=now, error_code=reason[:32], actual_usd=0)
                       .execution_options(synchronize_session=False))
            return REFUSED, reason, requeue(db, d, ("assigned",), now, job_failures=d.job_failures)
        if not cas_dispatch(db, d, ("assigned",), now, state="running"):
            db.rollback()
            return LOST, None, None
        return CLAIMED, None, None

    return run_txn(session_factory, work)


def take_over(usage_id: int, holder: str, heartbeat_read: Optional[datetime], *, session_factory=None,
              now: Optional[datetime] = None) -> bool:
    """Become the holder of a spawning/running row whose holder stopped heartbeating (conditional on the beat read)"""
    now = _now(now)

    def work(db: Session):
        conditions = [EngineUsage.id == usage_id, EngineUsage.status.in_(("spawning", "running"))]
        conditions.append(EngineUsage.heartbeat_at == heartbeat_read if heartbeat_read is not None
                          else EngineUsage.heartbeat_at.is_(None))
        return db.execute(update(EngineUsage).where(*conditions).values(holder=holder, heartbeat_at=now)
                          .execution_options(synchronize_session=False)).rowcount == 1

    return run_txn(session_factory, work)


def record_call(usage_id: int, holder: str, call_id: str, spawned_at: datetime, deadline_at: datetime, *,
                session_factory=None) -> bool:
    """spawning -> running with the provider's call id and the deadline, before anyone waits on the call"""
    def work(db: Session):
        return db.execute(
            update(EngineUsage)
            .where(EngineUsage.id == usage_id, EngineUsage.status.in_(("spawning", "running")),
                   EngineUsage.holder == holder)
            .values(status="running", provider_call_id=call_id[:128], spawned_at=spawned_at, deadline_at=deadline_at,
                    heartbeat_at=datetime.utcnow())
            .execution_options(synchronize_session=False)
        ).rowcount == 1

    return run_txn(session_factory, work)


def settle_remote_lost(usage_id: int, *, session_factory=None, now: Optional[datetime] = None,
                       error_code: str = "LOST") -> Tuple[Optional[str], Optional[JobChange]]:
    """
    A remote attempt nobody could finish (worker-remote kept dying, the call's
    output expired): charged its whole reservation - conservative, the provider's
    report reconciles - and the subject goes back to the backlog without counting
    an attempt; `succeeded` instead if the job completed after all.
    """
    now = _now(now)

    def work(db: Session):
        usage = db.get(EngineUsage, usage_id)
        if usage is None or usage.status not in ("spawning", "running"):
            return None, None
        job = db.get(Job, usage.job_id) if usage.job_id else None
        completed = job is not None and job.status == JobStatus.COMPLETED
        values = dict(status="settled", outcome="succeeded" if completed else "lost", counts_toward_attempts=False,
                      finished_at=now, actual_usd=usage.reserved_usd, cost_basis="reserved",
                      error_code=None if completed else error_code[:32])
        if completed:
            values["output_persisted_at"] = job.completed_at or now
        n = db.execute(update(EngineUsage).where(EngineUsage.id == usage_id,
                                                 EngineUsage.status.in_(("spawning", "running")),
                                                 EngineUsage.heartbeat_at == usage.heartbeat_at)
                       .values(**values).execution_options(synchronize_session=False)).rowcount
        if n == 0:
            return None, None
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id:
            return values["outcome"], None
        if completed:
            cas_dispatch(db, d, ("running",), now, state="done")
            return "succeeded", None
        return "lost", requeue(db, d, ("running", "assigned"), now, job_failures=d.job_failures)

    return run_txn(session_factory, work)


def apply_job_change(redis_client, change: Optional[JobChange]) -> None:
    """Mirror a job's backlog state into its Redis status (best effort, like every Redis write)"""
    if change is None or redis_client is None:
        return
    try:
        if change.status == "failed":
            redis_client.set_job_status(job_id=change.job_id, job_type="main", status="failed", progress=0,
                                        error=change.error, completed_at=datetime.utcnow(), name=change.name)
        else:
            redis_client.set_job_status(job_id=change.job_id, job_type="main", status="queued", progress=0,
                                        name=change.name)
    except Exception as e:
        logger.warning(f"[ENGINES] Could not mirror job {change.job_id} state to Redis: {e}")
