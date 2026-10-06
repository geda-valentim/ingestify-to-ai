"""Optional real InnoDB REPEATABLE READ proof, using a disposable test database.

Set JOB_ADMISSION_MYSQL_TEST_URL to the isolated localhost admission_test schema.
The fixture deliberately refuses other hosts/schemas before creating/deleting
synthetic tables. No application database or services are used.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from api import routes
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import Base, get_db
from shared.job_admission import Admission
from shared.models import Job, JobStatus, Page, User
from shared.redis_client import RedisClient


@pytest.fixture
def mysql():
    value = os.environ.get('JOB_ADMISSION_MYSQL_TEST_URL')
    if not value:
        pytest.skip('requires disposable MariaDB/MySQL admission_test schema')
    parsed = make_url(value)
    assert parsed.host == '127.0.0.1' and parsed.database == 'admission_test'
    engine = create_engine(parsed, isolation_level='REPEATABLE READ', pool_size=20, max_overflow=0)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        # Project/folder tables explicitly use utf8mb4_general_ci; referenced IDs
        # require the matching database default for foreign-key creation.
        conn.execute(text('ALTER DATABASE admission_test CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        assert db.execute(text('SELECT @@tx_isolation')).scalar() == 'REPEATABLE-READ'
        db.add(User(id='owner', username='owner', email='owner@example.invalid', hashed_password='test'))
        db.commit()
    try:
        yield SimpleNamespace(engine=engine, Session=factory)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def limits(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'job_max_active', 4)
    monkeypatch.setattr(settings, 'job_creation_limit', 100)
    monkeypatch.setattr(settings, 'job_max_storage_mb', 1024)
    return settings


def test_innodb_serializes_16_admissions_to_4_slots(mysql, limits):
    server = fakeredis.FakeServer()
    def admit(_):
        client = fakeredis.FakeRedis(server=server, decode_responses=True)
        with mysql.Session() as db:
            try:
                Admission(client, 'owner', limits).reserve(db, 'owner')
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(admit, range(16)))
    assert statuses.count(200) == 4
    assert statuses.count(429) == 12
    with mysql.Session() as db:
        assert db.query(Job).filter(Job.status == JobStatus.PENDING).count() == 4


def test_innodb_claim_lock_fences_expiry_and_crash_cleanup(mysql, limits, monkeypatch):
    monkeypatch.setattr(limits, 'job_max_active', 1)
    client = fakeredis.FakeRedis(decode_responses=True)
    first = Admission(client, 'owner', limits)
    waiting = Event()
    def before_query(conn, cursor, statement, parameters, context, many):
        if statement.startswith('DELETE FROM jobs') or 'FOR UPDATE' in statement:
            waiting.set()
    with mysql.Session() as db:
        first.reserve(db, 'owner')
        first.ensure(db)
        db.query(Job).filter(Job.id == first.job_id).update({Job.created_at: datetime.utcnow() - timedelta(seconds=601)})
        event.listen(mysql.engine, 'before_cursor_execute', before_query)
        def another():
            with mysql.Session() as other:
                try:
                    Admission(client, 'owner', limits).reserve(other, 'owner')
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(another)
            assert waiting.wait(2)
            assert not future.done()
            db.merge(Job(id=first.job_id, user_id='owner', status=JobStatus.PENDING,
                         job_type='MAIN', filename='real.pdf', source_type='file', file_size_bytes=1))
            db.commit()
            assert future.result(timeout=10) == 429
        event.remove(mysql.engine, 'before_cursor_execute', before_query)
    # A process crash before the payload commit rolls back the claim, leaving
    # only ADMISSION, which is safely recycled when it expires.
    with mysql.Session() as db:
        db.query(Job).delete()
        db.commit()
        crashed = Admission(client, 'owner', limits)
        crashed.reserve(db, 'owner')
        crashed.ensure(db)
        db.rollback()
        assert db.get(Job, crashed.job_id).job_type == 'ADMISSION'
        db.query(Job).filter(Job.id == crashed.job_id).update({Job.created_at: datetime.utcnow() - timedelta(seconds=601)})
        db.commit()
        replacement = Admission(client, 'owner', limits)
        replacement.reserve(db, 'owner')
        assert db.get(Job, crashed.job_id) is None


@pytest.fixture
def application(mysql, limits, monkeypatch, tmp_path):
    from workers import tasks
    cache = RedisClient(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(routes, 'get_redis_client', lambda: cache)
    monkeypatch.setattr(routes, 'get_es_client', lambda: MagicMock())
    monkeypatch.setattr(routes, 'get_minio_client', lambda: MagicMock())
    monkeypatch.setattr(limits, 'temp_storage_path', str(tmp_path))
    with mysql.Session() as db:
        db.add(Job(id='parent', user_id='owner', status=JobStatus.COMPLETED,
                   job_type='MAIN', filename='doc.pdf', source_type='file', file_size_bytes=1))
        db.flush()
        db.add(Page(id='page', job_id='parent', page_number=1, status=JobStatus.FAILED, page_job_id='old'))
        db.commit()
    directory = tmp_path / 'uploads' / 'parent'
    directory.mkdir(parents=True)
    (directory / 'doc.pdf').write_bytes(b'%PDF-test')
    app = FastAPI()
    app.include_router(routes.router)
    def session():
        with mysql.Session() as db:
            yield db
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id='owner', username='owner', is_admin=False)
    dispatched = []
    monkeypatch.setattr(tasks.process_page, 'delay', lambda **kwargs: dispatched.append(kwargs))
    # The test deliberately exercises the local publication branch, without a
    # runtime engine route/broker or any other application services.
    from shared.engines import dispatch
    monkeypatch.setattr(dispatch, 'submit', lambda **kwargs: kwargs['today']())
    return SimpleNamespace(app=app, dispatched=dispatched, tasks=tasks)


def test_innodb_delete_reads_fresh_page_state_after_ownership_snapshot(mysql, application):
    with mysql.Session() as stale:
        parent = stale.get(Job, 'parent')
        assert stale.get(Page, 'page').status == JobStatus.FAILED
        with mysql.Session() as updater:
            updater.get(Page, 'page').status = JobStatus.PROCESSING
            updater.commit()
        with pytest.raises(HTTPException) as failure:
            asyncio.run(routes.delete_job('parent', current_user=SimpleNamespace(id='owner', username='owner'),
                                         owned_job=parent, db=stale))
        assert failure.value.status_code == 409
    with mysql.Session() as db:
        assert db.get(Job, 'parent') is not None


def test_innodb_delete_wins_parent_lock_and_retry_cannot_publish(mysql, application, monkeypatch):
    deletion_holds_lock, allow_delete, retry_waiting = Event(), Event(), Event()
    es = MagicMock()
    def cleanup(*args, **kwargs):
        deletion_holds_lock.set()
        assert allow_delete.wait(10)
    es.delete_job_result.side_effect = cleanup
    monkeypatch.setattr(routes, 'get_es_client', lambda: es)
    def before_query(conn, cursor, statement, parameters, context, many):
        if deletion_holds_lock.is_set() and ('FOR UPDATE' in statement or statement.startswith('DELETE FROM jobs')):
            retry_waiting.set()
    event.listen(mysql.engine, 'before_cursor_execute', before_query)
    def delete():
        with TestClient(application.app) as client:
            return client.delete('/jobs/parent')
    def retry():
        with TestClient(application.app) as client:
            return client.post('/jobs/parent/pages/1/retry')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            deletion = pool.submit(delete)
            assert deletion_holds_lock.wait(3)
            retrying = pool.submit(retry)
            assert retry_waiting.wait(3)
            assert not retrying.done()
            allow_delete.set()
            assert deletion.result(timeout=10).status_code == 200
            response = retrying.result(timeout=10)
            # InnoDB may choose the admission transaction as a deadlock victim
            # when FK locks contend; the quota layer deliberately fails closed.
            assert response.status_code in (404, 503)
            if response.status_code == 503:
                assert response.json()['detail']['code'] == 'JOB_ADMISSION_UNAVAILABLE'
    finally:
        allow_delete.set()
        event.remove(mysql.engine, 'before_cursor_execute', before_query)
    assert application.dispatched == []


def test_innodb_retry_wins_and_delete_preserves_running_page(mysql, application, monkeypatch):
    publication_started, allow_publish = Event(), Event()
    def publish(**kwargs):
        application.dispatched.append(kwargs)
        publication_started.set()
        assert allow_publish.wait(10)
    monkeypatch.setattr(application.tasks.process_page, 'delay', publish)
    def retry():
        with TestClient(application.app) as client:
            return client.post('/jobs/parent/pages/1/retry')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            retrying = pool.submit(retry)
            assert publication_started.wait(3)
            with TestClient(application.app) as client:
                assert client.delete('/jobs/parent').status_code == 409
            allow_publish.set()
            assert retrying.result(timeout=10).status_code == 200
    finally:
        allow_publish.set()
    with mysql.Session() as db:
        assert db.get(Job, 'parent') is not None
        assert db.get(Page, 'page').status == JobStatus.PENDING
    assert len(application.dispatched) == 1
