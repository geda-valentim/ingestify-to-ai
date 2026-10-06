"""Identity quotas backed by a durable SQL admission slot and Redis rate window.

A user-row lock serializes count + reservation across API replicas. Only
unclaimed ADMISSION rows expire. Claim changes the row to MAIN atomically;
committed active work is never released by a cache TTL or a worker lease.
"""
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from redis.exceptions import WatchError
from sqlalchemy import text

from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.models import Job, JobStatus, User, Page
from shared.redis_client import get_redis_client


class Admission:
    def __init__(self, client, user_id, settings, allowance_bytes=None):
        self.client, self.settings, self.user_id = client, settings, user_id
        self.job_id = str(uuid4())
        self.rate_key = f'job-admission:{{{user_id}}}:rate'
        self.claimed = False
        self.allowance_bytes = allowance_bytes if allowance_bytes is not None else max(settings.max_file_size_mb, settings.vision_max_image_size_mb) * 1024 * 1024

    def reserve(self, db, user_id):
        maximum = max(self.settings.max_file_size_mb, self.settings.vision_max_image_size_mb) * 1024 * 1024
        try:
            db.rollback()
            if db.get_bind().dialect.name == 'sqlite':
                # SQLite ignores FOR UPDATE; its write transaction provides the
                # same serialization used by integration/unit ledgers.
                db.execute(text('BEGIN IMMEDIATE'))
            db.query(User).filter(User.id == user_id).with_for_update().one()
            deadline = datetime.utcnow() - timedelta(seconds=self.settings.job_admission_timeout_seconds)
            expired = [row.id for row in db.query(Job.id).filter(
                Job.user_id == user_id, Job.job_type == 'ADMISSION', Job.created_at <= deadline).all()]
            if expired:
                # Lock only actual expired slots. An unrestricted UPDATE/DELETE
                # scan can lock unrelated terminal parents in InnoDB, creating
                # an unnecessary User→parent / DELETE parent→User FK deadlock.
                # Recheck predicates after the row lock: a concurrent claim
                # committed as MAIN must never be recycled.
                db.query(Job).filter(Job.id.in_(expired), Job.job_type == 'ADMISSION',
                    Job.created_at <= deadline).delete(synchronize_session=False)
            rows = db.query(Job.status, Job.file_size_bytes).filter(
                Job.user_id == user_id, Job.parent_job_id.is_(None)).all()
            active = sum(row.status in (JobStatus.PENDING, JobStatus.PROCESSING) for row in rows)
            # Retrying a page of a terminal parent consumes its own active slot.
            active += db.query(Page).join(Job, Page.job_id == Job.id).filter(
                Job.user_id == user_id, Job.status.notin_((JobStatus.PENDING, JobStatus.PROCESSING)),
                Page.status.in_((JobStatus.PENDING, JobStatus.PROCESSING))).count()
            total_bytes = sum(row.file_size_bytes if row.file_size_bytes is not None else maximum for row in rows) + self.allowance_bytes
            if (active >= self.settings.job_max_active or len(rows) >= self.settings.job_max_retained or
                total_bytes > self.settings.job_max_storage_mb * 1024 * 1024):
                raise HTTPException(429, detail={'code': 'JOB_QUOTA_EXCEEDED'},
                                    headers={'Retry-After': str(self.settings.job_creation_window_seconds)})
            self._rate()
            db.add(Job(id=self.job_id, user_id=user_id, status=JobStatus.PENDING,
                       job_type='ADMISSION', file_size_bytes=self.allowance_bytes, created_at=datetime.utcnow()))
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise HTTPException(503, detail={'code': 'JOB_ADMISSION_UNAVAILABLE'}, headers={'Retry-After': '5'}) from None

    def _rate(self):
        for _ in range(32):
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(self.rate_key)
                    rate = int(pipe.get(self.rate_key) or 0)
                    if rate >= self.settings.job_creation_limit:
                        raise HTTPException(429, detail={'code': 'JOB_QUOTA_EXCEEDED'},
                                            headers={'Retry-After': str(self.settings.job_creation_window_seconds)})
                    pipe.multi()
                    pipe.incr(self.rate_key)
                    if rate == 0:
                        pipe.expire(self.rate_key, self.settings.job_creation_window_seconds)
                    pipe.execute()
                    return
                except WatchError:
                    continue
        raise RuntimeError('quota contention')

    def ensure(self, db):
        """Claim an unexpired SQL slot; expiry and claim contend on the same row."""
        if self.claimed:
            return
        deadline = datetime.utcnow() - timedelta(seconds=self.settings.job_admission_timeout_seconds)
        try:
            changed = db.query(Job).filter(Job.id == self.job_id, Job.user_id == self.user_id,
                Job.job_type == 'ADMISSION', Job.created_at > deadline).update(
                    {Job.job_type: 'MAIN'}, synchronize_session=False)
            # Keep the row lock until the caller commits the final Job payload.
            # A crash rolls the claim back to expirable ADMISSION, while an
            # expiry sweep waits and rechecks the predicate after real commit.
        except Exception:
            db.rollback()
            raise HTTPException(503, detail={'code': 'JOB_ADMISSION_UNAVAILABLE'}) from None
        if changed != 1:
            raise HTTPException(429, detail={'code': 'JOB_ADMISSION_EXPIRED'})
        self.claimed = True

    def release(self, db):
        try:
            db.rollback()
            db.query(Job).filter(Job.id == self.job_id, Job.user_id == self.user_id,
                                 Job.job_type == 'ADMISSION').delete(synchronize_session=False)
            # A claimed row with no source/filename is still only a slot: no
            # worker payload can refer to it. Fail it on request cleanup.
            db.query(Job).filter(Job.id == self.job_id, Job.user_id == self.user_id,
                Job.job_type == 'MAIN', Job.filename.is_(None), Job.source_type.is_(None)).update(
                    {Job.status: JobStatus.FAILED, Job.file_size_bytes: 0}, synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            # Failure preserves a SQL slot. Expiry reconciles only unclaimed
            # requests; uncertainty never creates extra processing capacity.


async def admit_job(request: Request, user=Depends(get_current_active_user), db=Depends(get_db)):
    settings = get_settings()
    allowance = None
    if request.url.path.rstrip('/') == '/transcribe/live/sessions':
        # Public live audio is 16 kHz mono PCM s16: reserve its full allowed
        # duration, which can exceed a normal multipart file's byte allowance.
        allowance = settings.live_max_duration_seconds * 16000 * 2
    elif request.url.path.startswith('/images/'):
        allowance = settings.vision_max_image_size_mb * 1024 * 1024
    admission = Admission(get_redis_client().client, user.id, settings, allowance_bytes=allowance)
    admission.reserve(db, user.id)
    try:
        yield admission
    finally:
        admission.release(db)
