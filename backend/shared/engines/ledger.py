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
from shared.models import FeatureRoute, Job, JobDispatch, JobStatus, EngineUsage, Page

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
    """What the job (or the page job) became, for the Redis mirror (written after the commit)"""
    job_id: str
    status: str  # queued | failed
    error: Optional[str] = None
    name: Optional[str] = None
    job_type: str = "main"  # "page" for a routed PDF page (subject_type=page)
    parent_job_id: Optional[str] = None
    page_number: Optional[int] = None


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


# --- subjects: a whole job, one page of a split PDF, or a synchronous vision request ---------


def page_number_of(d: Optional[JobDispatch]) -> Optional[int]:
    try:
        return int(((d.payload or {}).get("kwargs") or {}).get("page_number")) if d is not None else None
    except (TypeError, ValueError):
        return None


def _page(db: Session, parent_job_id: Optional[str], subject_id: str, page_number: Optional[int]) -> Optional[Page]:
    """The Page row of a routed page: by number (a retry runs under a new page job id), else by page job id"""
    if parent_job_id and page_number is not None:
        page = db.query(Page).filter(Page.job_id == parent_job_id, Page.page_number == page_number).first()
        if page is not None:
            return page
    return db.query(Page).filter(Page.page_job_id == subject_id).first()


def subject_state(db: Session, subject_type: Optional[str], subject_id: Optional[str], job_id: Optional[str],
                  page_number: Optional[int] = None) -> Tuple[str, Optional[datetime]]:
    """
    ("completed", when) | ("closed", None) | ("open", None) for the thing an attempt
    works on. A job is closed when deleted, cancelled or failed; a page when its
    parent job is. A vision request is always open (it has no backlog to return to).
    """
    if subject_type == "vision_request":
        from shared.models import ImageAnalysisRun
        run = db.get(ImageAnalysisRun, job_id) if job_id else None
        job = db.get(Job, job_id) if run else None
        if job and job.minio_result_path and run.status == 'completed':
            return 'completed', job.completed_at
        if job and job.minio_result_path and run.status in ('partial', 'failed', 'cancelled'):
            return 'closed', job.completed_at
        return "open", None
    job = db.get(Job, job_id) if job_id else None
    if job is None or job.status in (JobStatus.CANCELLED, JobStatus.FAILED):
        return "closed", None
    if subject_type == "page":
        page = _page(db, job_id, subject_id, page_number)
        if page is None:
            return "closed", None
        if page.status == JobStatus.COMPLETED:
            return "completed", page.completed_at
        return "open", None
    if job.status == JobStatus.COMPLETED:
        return "completed", job.completed_at
    return "open", None


def recount_parent_pages(db: Session, parent_job_id: str) -> None:
    """
    pages_completed / pages_failed of a split job, recounted from its Page rows (no commit).

    When every page has settled and some failed for good, the MAIN job is settled
    too: PARTIAL (the converted pages are kept, the failed ones can be retried),
    instead of PROCESSING forever. A page retry opens it again (PROCESSING); the
    merge completes it once every page is COMPLETED.

    Concurrent recounts (two pages settling at once) serialize on the parent's row
    lock (SELECT ... FOR UPDATE), and the pages are read with a locking read after
    it, so each recount sees every page change committed before it: the last
    writer's counts are correct (a plain read could return an older snapshot).
    """
    parent = db.query(Job).filter(Job.id == parent_job_id).with_for_update().populate_existing().first()
    if parent is None:
        return
    statuses = [status for (status,) in db.query(Page.status).filter(Page.job_id == parent_job_id)
                .with_for_update().all()]
    parent.pages_completed = sum(1 for status in statuses if status == JobStatus.COMPLETED)
    parent.pages_failed = sum(1 for status in statuses if status == JobStatus.FAILED)
    settle_parent_with_failed_pages(db, parent, page_count=len(statuses))


def settle_parent_with_failed_pages(db: Session, parent: Job, page_count: Optional[int] = None) -> bool:
    """MAIN job -> PARTIAL once all its pages are terminal and some failed (no commit)."""
    total = parent.total_pages or 0
    if not total or not parent.pages_failed or parent.status not in (JobStatus.PENDING, JobStatus.PROCESSING):
        return False
    pages = page_count if page_count is not None else db.query(Page).filter(Page.job_id == parent.id).count()
    if pages < total or parent.pages_completed + parent.pages_failed < pages:
        return False  # still splitting, or some page is queued / running / waiting for a retry
    from shared import error_catalog

    parent.status = JobStatus.PARTIAL
    parent.completed_at = datetime.utcnow()
    parent.error_message = error_catalog.describe("PAGES_FAILED", failed=parent.pages_failed, total=total)[0]
    return True


def _page_change(d: JobDispatch, status: str, error: Optional[str] = None) -> JobChange:
    return JobChange(d.subject_id, status, error=error, job_type="page", parent_job_id=d.job_id,
                     page_number=page_number_of(d))


def _job_pending(db: Session, d: JobDispatch) -> Optional[JobChange]:
    if d.subject_type == "page":
        page = _page(db, d.job_id, d.subject_id, page_number_of(d))
        if page is not None:
            page.status = JobStatus.PENDING
        return _page_change(d, "queued")
    job = db.get(Job, d.job_id) if d.job_id else None
    if job is None:
        return None
    job.status = JobStatus.PENDING
    job.started_at = None
    job.completed_at = None
    return JobChange(d.job_id, "queued", name=job.name)


def _job_failed(db: Session, d: JobDispatch, message: str, now: datetime) -> Optional[JobChange]:
    if d.subject_type == "page":
        # One page failing for good fails that page, never the whole document (as today).
        # The parent's row lock first, the page after: the order every purge, page
        # retry and recount takes them in
        if d.job_id:
            db.query(Job).filter(Job.id == d.job_id).with_for_update().first()
        page = _page(db, d.job_id, d.subject_id, page_number_of(d))
        if page is not None:
            page.status = JobStatus.FAILED
            page.error_message = message
            db.flush()
            recount_parent_pages(db, d.job_id)
        return _page_change(d, "failed", error=message)
    job = db.get(Job, d.job_id) if d.job_id else None
    if job is None:
        return None
    job.status = JobStatus.FAILED
    job.error_message = message
    job.completed_at = now
    return JobChange(d.job_id, "failed", error=message, name=job.name)


def fail_dispatch(db: Session, d: JobDispatch, error_code: str, message: str, now: datetime,
                  from_states: Iterable[str] = OPEN_DISPATCH) -> Optional[JobChange]:
    """Terminal failure of a backlog item (no_engine, budget_exhausted, engine_error...)"""
    if not cas_dispatch(db, d, from_states, now, state="failed", error_code=error_code):
        return None
    return _job_failed(db, d, message, now) or JobChange(d.job_id or d.subject_id, "failed", error=message)


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
    return _job_pending(db, d) or JobChange(d.job_id or d.subject_id, "queued")


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
        return _job_failed(db, d, message, now) or JobChange(d.job_id or d.subject_id, "failed", error=message)
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
        if usage.subject_type == "vision_request":
            return CLAIMED, None  # synchronous: placed inline by the API, no backlog row (spec 0003, 4.14)
        d = dispatch_of(db, usage)
        if d is None or d.usage_id != usage.id or not cas_dispatch(db, d, ("assigned", "bypassed"), now, state="running"):
            db.rollback()
            return LOST, None
        d = dispatch_of(db, usage)
        state, completed_at = subject_state(db, usage.subject_type, usage.subject_id, usage.job_id, page_number_of(d))
        if state == "completed":
            # An earlier attempt, given up as lost, finished after all: its output stands
            _settle(db, usage, "succeeded", now, output_persisted_at=completed_at or now)
            cas_dispatch(db, d, ("running",), now, state="done")
            return ALREADY_DONE, None
        if state == "closed":
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
        state, completed_at = subject_state(db, usage.subject_type, usage.subject_id, usage.job_id,
                                            page_number_of(dispatch_of(db, usage)))
        completed = state == "completed"
        from shared.models import ImageAnalysisRun
        full = db.get(ImageAnalysisRun, usage.job_id) if usage.subject_type == 'vision_request' and usage.job_id else None
        durable_full = full and full.status in ('completed', 'partial', 'failed', 'cancelled') and completed_at
        outcome = ('succeeded' if full.status == 'completed' else 'cancelled' if full.status == 'cancelled' else 'failed') if durable_full else ('succeeded' if completed else 'lost')
        values = dict(status="settled", outcome=outcome, counts_toward_attempts=outcome not in ('succeeded', 'cancelled'),
                      finished_at=now, actual_usd=0, cost_basis="measured",
                      error_code=None if completed else "LOST")
        if completed or durable_full:
            values["output_persisted_at"] = completed_at or now
        if full:
            # Hardkill has no observed stop time. Keep duration unknown; for a
            # priced lane retain its reservation instead of claiming a free run.
            values.update(error_code='MEASUREMENT_MISSING', units={'measurement': 'unavailable'},
                          actual_usd=usage.reserved_usd if usage.rate_usd_per_s else 0,
                          cost_basis='reserved' if usage.rate_usd_per_s else 'measured')
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
        state, completed_at = subject_state(db, usage.subject_type, usage.subject_id, usage.job_id, page_number_of(d))
        if state == "completed":
            cas_dispatch(db, d, ("assigned",), now, state="running")
            d = dispatch_of(db, usage)
            _settle(db, usage, "succeeded", now, output_persisted_at=completed_at or now)
            cas_dispatch(db, d, ("running",), now, state="done")
            return ALREADY_DONE, None, None
        if state == "closed":
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
        state, completed_at = subject_state(db, usage.subject_type, usage.subject_id, usage.job_id,
                                            page_number_of(dispatch_of(db, usage)))
        completed = state == "completed"
        values = dict(status="settled", outcome="succeeded" if completed else "lost", counts_toward_attempts=False,
                      finished_at=now, actual_usd=usage.reserved_usd, cost_basis="reserved",
                      error_code=None if completed else error_code[:32])
        if completed:
            values["output_persisted_at"] = completed_at or now
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
    extra = {}
    if change.job_type == "page":
        extra = {"parent_job_id": change.parent_job_id, "page_number": change.page_number}
    else:
        extra = {"name": change.name}
    try:
        if change.status == "failed":
            redis_client.set_job_status(job_id=change.job_id, job_type=change.job_type, status="failed", progress=0,
                                        error=change.error, completed_at=datetime.utcnow(), **extra)
        else:
            redis_client.set_job_status(job_id=change.job_id, job_type=change.job_type, status="queued", progress=0,
                                        **extra)
    except Exception as e:
        logger.warning(f"[ENGINES] Could not mirror job {change.job_id} state to Redis: {e}")
    if change.status == "failed":
        _purge_after_terminal_failure(change.parent_job_id if change.job_type == "page" else change.job_id)


def _purge_after_terminal_failure(job_id: Optional[str]) -> None:
    """A backlog item failed for good (after the commit): purge_source applies once the
    MAIN job is settled (FAILED, or PARTIAL when this was its last page). Never raises."""
    if not job_id:
        return
    try:
        from shared.database import SessionLocal
        from shared.job_source import purge_source_if_requested
        from shared.minio_client import get_minio_client

        purge_source_if_requested(job_id, session_factory=SessionLocal, minio_factory=get_minio_client)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ENGINES] purge_source check for job {job_id} failed: {e}")
