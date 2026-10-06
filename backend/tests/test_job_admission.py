"""Exercise atomic identity quotas with SQL and a shared Redis server model."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time

import fakeredis
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.job_admission import Admission
from shared.models import Job, JobStatus, User


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/quota.db', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(id='owner', email='quota@example.invalid', username='quota', hashed_password='test'))
        db.commit()
    return factory


@pytest.fixture
def limits():
    return SimpleNamespace(max_file_size_mb=10, vision_max_image_size_mb=1,
        job_max_active=4, job_max_retained=100, job_max_storage_mb=100,
        job_creation_limit=100, job_creation_window_seconds=60, job_admission_timeout_seconds=600)


def test_atomic_concurrent_identity_limit(ledger, limits):
    server = fakeredis.FakeServer()
    def create(_):
        # Distinct connections model replicas and JWT/API-key requests sharing
        # the authoritative authenticated user ID.
        admission = Admission(fakeredis.FakeRedis(server=server, decode_responses=True), 'owner', limits)
        with ledger() as db:
            try:
                admission.reserve(db, 'owner')
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(create, range(16)))
    assert statuses.count(200) == 4
    assert statuses.count(429) == 12


@pytest.mark.parametrize('terminal', [JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED])
def test_terminal_sql_releases_active_budget(ledger, limits, terminal):
    limits.job_max_active = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    first = Admission(client, 'owner', limits)
    with ledger() as db:
        first.reserve(db, 'owner')
        db.merge(Job(id=first.job_id, user_id='owner', status=JobStatus.PENDING, job_type='MAIN', file_size_bytes=1))
        db.commit()
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 429
        job = db.get(Job, first.job_id)
        job.status = terminal
        db.commit()
        Admission(client, 'owner', limits).reserve(db, 'owner')


def test_active_sql_does_not_expire_with_redis_reservation(ledger, limits):
    limits.job_max_active = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    first = Admission(client, 'owner', limits)
    with ledger() as db:
        first.reserve(db, 'owner')
        db.merge(Job(id=first.job_id, user_id='owner', status=JobStatus.PENDING, job_type='MAIN'))
        db.commit()
        client.flushall()
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 429


def test_failed_request_and_expired_crash_reservation_recover(ledger, limits):
    limits.job_max_active = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    with ledger() as db:
        first = Admission(client, 'owner', limits)
        first.reserve(db, 'owner')
        first.release(db)
        second = Admission(client, 'owner', limits)
        second.reserve(db, 'owner')
        slot = db.get(Job, second.job_id)
        from datetime import datetime, timedelta
        slot.created_at = datetime.utcnow() - timedelta(seconds=601)
        db.commit()
        with pytest.raises(HTTPException) as failure:
            second.ensure(db)
        assert failure.value.status_code == 429
        Admission(client, 'owner', limits).reserve(db, 'owner')


def test_storage_retained_and_unknown_remote_sizes(ledger, limits):
    limits.job_max_storage_mb = 19
    client = fakeredis.FakeRedis(decode_responses=True)
    with ledger() as db:
        db.add(Job(id='remote', user_id='owner', status=JobStatus.COMPLETED, job_type='MAIN'))
        db.commit()
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 429


def test_redis_outage_fails_closed(ledger, limits, monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(client, 'pipeline', lambda: (_ for _ in ()).throw(ConnectionError()))
    with ledger() as db, pytest.raises(HTTPException) as failure:
        Admission(client, 'owner', limits).reserve(db, 'owner')
    assert failure.value.status_code == 503


def test_claim_survives_expiry_and_cleanup_after_failure(ledger, limits):
    limits.job_max_active = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    first = Admission(client, 'owner', limits)
    with ledger() as db:
        first.reserve(db, 'owner')
        first.ensure(db)
        slot = db.get(Job, first.job_id)
        from datetime import datetime, timedelta
        slot.created_at = datetime.utcnow() - timedelta(seconds=601)
        db.commit()
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 429
        first.release(db)
        assert db.get(Job, first.job_id).status == JobStatus.FAILED
        Admission(client, 'owner', limits).reserve(db, 'owner')


def test_rate_window_separate_from_active_and_redis_outage_after_admission(ledger, limits, monkeypatch):
    limits.job_creation_limit = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    with ledger() as db:
        first = Admission(client, 'owner', limits)
        first.reserve(db, 'owner')
        first.release(db)
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 429
        client.flushall()
        second = Admission(client, 'owner', limits)
        second.reserve(db, 'owner')
        # Claim relies on the already committed SQL slot, not an expiring Redis
        # permit. A Redis outage cannot release that slot to another request.
        monkeypatch.setattr(client, 'pipeline', lambda: (_ for _ in ()).throw(ConnectionError()))
        second.ensure(db)
        with pytest.raises(HTTPException) as failure:
            Admission(client, 'owner', limits).reserve(db, 'owner')
        assert failure.value.status_code == 503


def test_claim_lock_fences_expiry_until_real_payload_commit(ledger, limits):
    from datetime import datetime, timedelta
    from threading import Event
    limits.job_max_active = 1
    client = fakeredis.FakeRedis(decode_responses=True)
    first = Admission(client, 'owner', limits)
    started = Event()
    with ledger() as db:
        first.reserve(db, 'owner')
        first.ensure(db)
        # Cross the expiry boundary while the uncommitted claim holds the SQL
        # row/write lock. A second admission must wait rather than recycle it.
        db.query(Job).filter(Job.id == first.job_id).update({
            Job.created_at: datetime.utcnow() - timedelta(seconds=601)})
        def another():
            started.set()
            with ledger() as other:
                try:
                    Admission(client, 'owner', limits).reserve(other, 'owner')
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(another)
            assert started.wait(1)
            assert not future.done()
            db.merge(Job(id=first.job_id, user_id='owner', status=JobStatus.PENDING,
                         job_type='MAIN', filename='real.pdf', source_type='file', file_size_bytes=1))
            db.commit()
            assert future.result(timeout=5) == 429
