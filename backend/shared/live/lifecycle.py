"""Short MySQL transactions with consistent Job -> LiveSession lock ordering."""
from datetime import datetime
from sqlalchemy import inspect
from shared.database import SessionLocal
from shared.models import Job, JobStatus, LiveSession
from shared.live.protocol import LiveError, TERMINAL


def available(db):
    return inspect(db.get_bind()).has_table('live_sessions')


def lock_rows(db, job_id):
    job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
    session = db.query(LiveSession).filter(LiveSession.job_id == job_id).with_for_update().first()
    return job, session


def transition(job_id, generation, expected, state, samples=None, error=None):
    with SessionLocal() as db:
        job, live = lock_rows(db, job_id)
        if not job or not live or live.generation != generation or live.state not in expected:
            raise LiveError('LIVE_SESSION_GONE', 4404)
        live.state = state
        if samples is not None:
            live.audio_samples = samples
            live.last_audio_at = datetime.utcnow()
        if state == 'streaming' and not live.connected_at:
            live.connected_at = datetime.utcnow()
            job.started_at = live.connected_at
        if state in TERMINAL:
            live.ended_at = datetime.utcnow()
            live.error_code = error
            job.completed_at = live.ended_at
            job.error_message = error
        job.status = {'created': JobStatus.PENDING, 'streaming': JobStatus.PROCESSING,
                      'finalizing': JobStatus.PROCESSING, 'completed': JobStatus.COMPLETED,
                      'failed': JobStatus.FAILED, 'cancelled': JobStatus.CANCELLED}[state]
        db.commit()


def terminate(job_id, state, code, store, redis_client, generation=None):
    """Revoke before cleanup. Completed sessions are immutable/idempotent."""
    with SessionLocal() as db:
        if not available(db):
            return False
        job, live = lock_rows(db, job_id)
        if not job or not live or live.state in TERMINAL or (generation is not None and live.generation != generation):
            return False
        gen = live.generation
        try:
            store.release(job_id, gen)
        except Exception:
            # SQL is the publication fence even when Redis is unreachable.
            # Expiring slots still reclaim capacity; no decoder can complete a
            # terminal MySQL session after connectivity returns.
            pass
        live.state, live.error_code, live.ended_at = state, code, datetime.utcnow()
        job.status = JobStatus.CANCELLED if state == 'cancelled' else JobStatus.FAILED
        job.completed_at, job.error_message = live.ended_at, code
        # Serialize cache cleanup/publication with DELETE as well as SQL state.
        # There are no writes after the row lock is released.
        redis_client.set_job_status(job_id, 'main', state, error=code)
        if state == 'cancelled':
            redis_client.delete_partial_transcript(job_id)
        db.commit()
    return True


def sweep(store, redis_client):
    with SessionLocal() as db:
        if not available(db):
            return
        sessions = db.query(LiveSession).filter(LiveSession.state.in_(
            ['created', 'streaming', 'finalizing'])).all()
        candidates = [(s.job_id, s.generation, s.state) for s in sessions]
    for job_id, generation, state in candidates:
        try:
            valid = store.valid(job_id, generation)
        except Exception:
            valid = False  # Live never continues through a lost control store.
        if not valid:
            terminate(job_id, 'cancelled' if state == 'created' else 'failed', 'LIVE_RESERVATION_EXPIRED' if state == 'created' else 'LIVE_LEASE_LOST',
                      store, redis_client, generation)
