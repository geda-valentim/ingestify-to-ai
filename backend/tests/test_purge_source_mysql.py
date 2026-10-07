"""
purge_source / page retry / ledger locking on InnoDB (SQLite ignores FOR UPDATE).

Opt-in like the other InnoDB gates: set ENGINE_CONTROL_TEST_DATABASE_URL to a
disposable database named engine_control_test_*. Every lock is taken in one
global order: the MAIN job's row (`lock_job`, SELECT ... FOR UPDATE) -> its Page
rows. A page status write by a worker locks only its page and commits before it
recounts (which then takes job -> pages). The interleavings below run two real
sessions against each other and assert there is no deadlock (1213) or lock-wait
timeout, that the second session really waited, and the final state:

a. DELETE /jobs/{id}/source x page retry (both orders);
b. the worker purge hook x page retry (both orders);
c. concurrent recounts from page completions / failures;
d. the monitoring stuck-page settle x a late page completion (both orders);
e. the split's page upsert under uq_pages_job_page (same page, different jobs);
plus the b8f20022e1c4 / a7d30021c5e9 migrations and the boot-time schema upgrade.
"""
import importlib.util
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

import workers.celery_app  # noqa: F401  (import order used by the worker)
from api import routes
from shared.config import get_settings
from shared.database import Base, _add_missing_columns, get_db
from shared.models import Job, JobStatus, Page, User
from tests.test_execution_profiles_migration import mysql_url
from tests.test_purge_source import ALICE, BOB, JOB_ID, FakeMinio, add_job, jwt
from workers import tasks

ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = f"uploads/{JOB_ID}/livro.pdf"
WAIT = 1.0  # how long "the other session is blocked" is checked for


def _drop_every_table(engine):
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in inspect(conn).get_table_names():
            conn.execute(text(f"DROP TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@pytest.fixture
def engine():
    sql = create_engine(mysql_url(), pool_pre_ping=True, pool_size=10)

    @event.listens_for(sql, "connect")
    def _short_lock_wait(dbapi_connection, _record):
        # A lock-wait timeout fails the test in seconds instead of InnoDB's 50
        cursor = dbapi_connection.cursor()
        cursor.execute("SET SESSION innodb_lock_wait_timeout = 8")
        cursor.close()

    _drop_every_table(sql)
    yield sql
    _drop_every_table(sql)
    sql.dispose()


@pytest.fixture
def Session(engine):
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)  # as shared.database
    with factory() as db:
        db.add_all([
            User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"),
            User(id=BOB, email="bob@example.com", username="bob", hashed_password="x"),
        ])
        db.commit()
    return factory


class GatedMinio(FakeMinio):
    """FakeMinio whose delete / download stops (holding whatever locks the caller holds)
    until released: the other session runs into the lock meanwhile."""

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def _gate(self):
        self.entered.set()
        assert self.release.wait(20), "never released"

    def delete_file(self, bucket_name, object_name):
        self._gate()
        return super().delete_file(bucket_name, object_name)

    def download_file(self, bucket_name, object_name, file_path=None):
        self._gate()
        return super().download_file(bucket_name, object_name, file_path=file_path)


def page_row(Session, number, job_id=JOB_ID):
    with Session() as db:
        return db.query(Page).filter(Page.job_id == job_id, Page.page_number == number).one()


def job_row(Session, job_id=JOB_ID):
    with Session() as db:
        return db.get(Job, job_id)


def first_then_second(first, second, gate):
    """Run `first` until it holds its locks (gate.entered), then `second`, check that
    `second` waits for them, release `first`. Returns both results (re-raising)."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first)
        assert gate.entered.wait(10), "the first session never reached its critical section"
        b = pool.submit(second)
        time.sleep(WAIT)
        waited = not b.done()
        gate.release.set()
        results = a.result(timeout=30), b.result(timeout=30)
    assert waited, "the second session did not wait for the first one's row lock"
    return results


# ---------------------------------------------------------------------------
# a / b: purges x page retry
# ---------------------------------------------------------------------------

@pytest.fixture
def api(Session, fake_redis, tmp_path, monkeypatch):
    minio = GatedMinio()
    queued = []
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))  # shared.job_source
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: minio)
    monkeypatch.setattr(routes, "_engine_celery", lambda: None)
    monkeypatch.setattr(routes.engine_dispatch, "submit", lambda **kw: queued.append(kw))

    def db():
        session = Session()  # one session per request, as get_db
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = db
    client = TestClient(app)

    def delete_source():
        return client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    def retry(number=2):
        return client.post(f"/jobs/{JOB_ID}/pages/{number}/retry", headers=jwt())

    return SimpleNamespace(minio=minio, queued=queued, delete_source=delete_source, retry=retry,
                           Session=Session)


def _partial_pdf_job(Session, purge=False):
    add_job(Session, purge=purge, status=JobStatus.PARTIAL, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.FAILED})


def test_a_delete_source_first_then_page_retry_is_409(api):
    _partial_pdf_job(api.Session)

    deleted, retried = first_then_second(api.delete_source, api.retry, api.minio)

    assert deleted.status_code == 200, deleted.text
    assert retried.status_code == 409, retried.text
    assert retried.json()["detail"]["code"] == "SOURCE_NOT_AVAILABLE"
    page = page_row(api.Session, 2)
    assert (page.status, page.retry_count, page.minio_page_path) == (JobStatus.FAILED, 0, None)
    job = job_row(api.Session)
    assert job.status == JobStatus.PARTIAL and job.source_deleted_at is not None
    assert job.minio_upload_path is None and api.queued == []


def test_a_page_retry_first_then_delete_source_is_409(api):
    _partial_pdf_job(api.Session)  # no local copy: the retry restores it from MinIO

    retried, deleted = first_then_second(api.retry, api.delete_source, api.minio)

    assert retried.status_code == 200, retried.text
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["detail"]["code"] == "JOB_STILL_PROCESSING"
    page = page_row(api.Session, 2)
    assert (page.status, page.retry_count) == (JobStatus.PENDING, 1)
    job = job_row(api.Session)
    assert job.status == JobStatus.PROCESSING and job.source_deleted_at is None
    assert job.minio_upload_path == PDF_PATH and api.minio.deleted == [] and len(api.queued) == 1


def _purge_hook(Session, minio):
    from shared.job_source import purge_source_if_requested

    return lambda: purge_source_if_requested(JOB_ID, session_factory=Session, minio_factory=lambda: minio)


def test_b_worker_purge_first_then_page_retry_is_409(api):
    _partial_pdf_job(api.Session, purge=True)

    purged, retried = first_then_second(_purge_hook(api.Session, api.minio), api.retry, api.minio)

    assert purged is True
    assert retried.status_code == 409 and retried.json()["detail"]["code"] == "SOURCE_NOT_AVAILABLE"
    assert page_row(api.Session, 2).status == JobStatus.FAILED
    assert job_row(api.Session).source_deleted_at is not None


def test_b_page_retry_first_then_worker_purge_refuses(api):
    _partial_pdf_job(api.Session, purge=True)

    retried, purged = first_then_second(api.retry, _purge_hook(api.Session, api.minio), api.minio)

    assert retried.status_code == 200, retried.text
    assert purged is False
    assert page_row(api.Session, 2).status == JobStatus.PENDING
    job = job_row(api.Session)
    assert job.status == JobStatus.PROCESSING and job.source_deleted_at is None
    assert api.minio.deleted == []


# ---------------------------------------------------------------------------
# c / d: the ledger recount, page completions, monitoring
# ---------------------------------------------------------------------------

@pytest.fixture
def worker(Session, fake_redis, tmp_path, monkeypatch):
    minio = FakeMinio()
    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    return SimpleNamespace(Session=Session, minio=minio)


def complete_page(Session, number, before_commit=None, job_id=JOB_ID):
    """What _run_page_conversion writes when a page converted: its page row(s),
    committed alone, then the recount (job lock -> pages) in a new transaction."""
    db = Session()
    try:
        pages = db.query(Page).filter(Page.job_id == job_id, Page.page_number == number).all()
        for page in pages:
            page.status = JobStatus.COMPLETED
            page.markdown_content = f"# page {number}"
            page.error_message = None
            page.completed_at = datetime.utcnow()
        db.flush()
        if before_commit:
            before_commit()
        db.commit()
        tasks._recount_parent_pages(db, job_id)
    finally:
        db.close()


@pytest.mark.parametrize("round_", range(5))
def test_c_concurrent_page_settles_recount_without_deadlock(worker, monkeypatch, round_):
    n = 8
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={i: JobStatus.PROCESSING for i in range(1, n + 1)})
    barrier = threading.Barrier(n)
    original = tasks._recount_parent_pages

    def recount_together(db, parent_job_id):
        barrier.wait(10)  # every page row committed, all recounts at once
        original(db, parent_job_id)

    monkeypatch.setattr(tasks, "_recount_parent_pages", recount_together)
    failing = {2, 5}

    def settle(number):
        if number in failing:
            tasks._mark_page_failed("[test]", f"page-{number}", JOB_ID, number, "boom", retrying=False)
        else:
            complete_page(worker.Session, number)

    with ThreadPoolExecutor(max_workers=n) as pool:
        for future in [pool.submit(settle, i) for i in range(1, n + 1)]:
            future.result(timeout=30)

    job = job_row(worker.Session)
    assert (job.pages_completed, job.pages_failed) == (n - len(failing), len(failing))
    assert job.status == JobStatus.PARTIAL
    # the last settle purged (purge_source) once nothing was pending
    assert job.source_deleted_at is not None and job.minio_upload_path is None


def test_c_ledger_terminal_page_failure_and_completion_recount(worker):
    """ledger._job_failed (job lock first, then the page) against a page completion."""
    from shared.engines import ledger

    add_job(worker.Session, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.PROCESSING, 2: JobStatus.PROCESSING})
    d = SimpleNamespace(subject_type="page", job_id=JOB_ID, subject_id="page-2",
                        payload={"kwargs": {"page_number": 2}})
    barrier = threading.Barrier(2)

    def fail_two():
        with worker.Session() as db:
            barrier.wait(10)
            ledger._job_failed(db, d, "engine_error", datetime.utcnow())
            db.commit()

    def complete_one():
        complete_page(worker.Session, 1, before_commit=lambda: barrier.wait(10))

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(fail_two), pool.submit(complete_one)]:
            future.result(timeout=30)

    job = job_row(worker.Session)
    assert (job.pages_completed, job.pages_failed, job.status) == (1, 1, JobStatus.PARTIAL)


@pytest.fixture
def monitor(worker, fake_redis, monkeypatch):
    from shared import minio_client
    from workers import monitoring

    monkeypatch.setattr(monitoring, "SessionLocal", worker.Session)
    monkeypatch.setattr(minio_client, "get_minio_client", lambda: worker.minio)
    return SimpleNamespace(fail_stuck_page=lambda page_id: monitoring._fail_stuck_page(page_id, fake_redis))


def test_d_late_completion_holds_the_page_then_monitoring_sees_it_completed(worker, monitor):
    add_job(worker.Session, purge=True, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})
    stuck_id = page_row(worker.Session, 2).id
    gate = SimpleNamespace(entered=threading.Event(), release=threading.Event())

    def completion():
        complete_page(worker.Session, 2,
                      before_commit=lambda: (gate.entered.set(), gate.release.wait(20)))

    _, failed = first_then_second(completion, lambda: monitor.fail_stuck_page(stuck_id), gate)

    assert failed is False  # re-read under the lock: no longer PROCESSING
    assert page_row(worker.Session, 2).status == JobStatus.COMPLETED
    job = job_row(worker.Session)
    assert (job.pages_completed, job.pages_failed, job.status) == (2, 0, JobStatus.PROCESSING)
    assert worker.minio.deleted == []  # the merge settles it, then purges


def test_d_monitoring_first_then_the_late_completion_waits(worker, monitor, monkeypatch):
    from shared.engines import ledger

    add_job(worker.Session, status=JobStatus.PROCESSING, path=PDF_PATH, filename="livro.pdf",
            pages={1: JobStatus.COMPLETED, 2: JobStatus.PROCESSING})
    stuck_id = page_row(worker.Session, 2).id
    gate = SimpleNamespace(entered=threading.Event(), release=threading.Event())
    original = ledger.recount_parent_pages

    def recount_held(db, parent_job_id):  # monitoring holds job + page 2 here
        original(db, parent_job_id)
        gate.entered.set()
        gate.release.wait(20)

    from workers import monitoring  # noqa: F401
    monkeypatch.setattr(ledger, "recount_parent_pages", recount_held)

    def completion():
        monkeypatch.setattr(ledger, "recount_parent_pages", original)  # only the monitor is held
        complete_page(worker.Session, 2)

    failed, _ = first_then_second(lambda: monitor.fail_stuck_page(stuck_id), completion, gate)

    assert failed is True
    # The late completion wins the page (as before this branch); the recount after it
    # sees 2 completed but the job stays settled PARTIAL until the merge completes it
    job = job_row(worker.Session)
    assert page_row(worker.Session, 2).status == JobStatus.COMPLETED
    assert (job.pages_completed, job.pages_failed) == (2, 0)
    assert job.status == JobStatus.PARTIAL


# ---------------------------------------------------------------------------
# e: the split's page upsert under uq_pages_job_page
# ---------------------------------------------------------------------------

def _add_bare_job(Session, job_id):
    with Session() as db:
        db.add(Job(id=job_id, user_id=ALICE, filename="livro.pdf", name="livro.pdf", job_type="MAIN",
                   source_type="file", status=JobStatus.PROCESSING, total_pages=3))
        db.commit()


def _upserts_meeting_at_insert(Session, monkeypatch, calls):
    """Run `_upsert_split_page(*call)` concurrently; every session has done its
    lookup before any inserts (the window a redelivered split, or another job's
    split, can hit)."""
    barrier = threading.Barrier(len(calls))

    class MeetingSession(sa.orm.Session):
        def add(self, instance, *a, **kw):
            try:
                barrier.wait(5)
            except threading.BrokenBarrierError:
                pass
            return super().add(instance, *a, **kw)

    factory = sessionmaker(bind=Session.kw["bind"], class_=MeetingSession, autoflush=False)
    monkeypatch.setattr(tasks, "SessionLocal", factory)
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(tasks._upsert_split_page, "split-x", job_id, number, path)
                   for job_id, number, path in calls]
        return [f.result(timeout=30) for f in futures]


@pytest.mark.parametrize("round_", range(3))
def test_e_same_page_upserted_concurrently_gives_one_row(Session, monkeypatch, round_):
    _add_bare_job(Session, JOB_ID)

    results = _upserts_meeting_at_insert(Session, monkeypatch, [(JOB_ID, 1, "p/1.pdf")] * 2)

    with Session() as db:
        rows = db.query(Page).filter(Page.job_id == JOB_ID).all()
    assert len(rows) == 1
    assert {r[0] for r in results} == {rows[0].page_job_id}
    assert sorted(r[1] for r in results) == [True, True]  # PENDING: both may queue it (same id)


@pytest.mark.parametrize("round_", range(3))
def test_e_different_jobs_upserted_concurrently(Session, monkeypatch, round_):
    other = "22222222-2222-4333-8444-555555555555"
    _add_bare_job(Session, JOB_ID)
    _add_bare_job(Session, other)

    _upserts_meeting_at_insert(Session, monkeypatch, [(JOB_ID, 1, None), (other, 1, None)])

    with Session() as db:
        assert db.query(Page).count() == 2


def test_e_split_retry_reuses_rows_and_keeps_started_pages(Session, monkeypatch):
    _add_bare_job(Session, JOB_ID)
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    first = [tasks._upsert_split_page("split-1", JOB_ID, n, f"p/{n}.pdf") for n in (1, 2)]
    with Session() as db:
        db.query(Page).filter(Page.page_number == 1).update({"status": JobStatus.COMPLETED})
        db.commit()

    again = [tasks._upsert_split_page("split-2", JOB_ID, n, f"p/{n}.pdf") for n in (1, 2, 3)]

    assert again[0] == (first[0][0], False) and again[1] == (first[1][0], True) and again[2][1] is True
    with Session() as db:
        assert db.query(Page).filter(Page.job_id == JOB_ID).count() == 3


# ---------------------------------------------------------------------------
# Migrations b8f20022e1c4 / a7d30021c5e9 and the boot path on MySQL
# ---------------------------------------------------------------------------

def _load(name):
    path = next((ROOT / "alembic" / "versions").glob(f"{name}_*.py"))
    spec = importlib.util.spec_from_file_location(f"rev_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, name, fn):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(_load(name), fn)()


def _shape(engine):
    inspector = inspect(engine)
    jobs = {c["name"] for c in inspector.get_columns("jobs")}
    names = {i["name"] for i in inspector.get_indexes("pages")}
    names |= {u["name"] for u in inspector.get_unique_constraints("pages")}
    attempt = "attempt" in {c["name"] for c in inspector.get_columns("image_analysis_submissions")}
    return {"purge_source", "source_deleted_at", "operation_key"} <= jobs, "uq_pages_job_page" in names, attempt


def _previous_head(engine):
    """A database at f1c90019d3e4: create_all, then both revisions downgraded."""
    Base.metadata.create_all(engine)
    _run(engine, "b8f20022e1c4", "downgrade")
    _run(engine, "a7d30021c5e9", "downgrade")
    assert _shape(engine) == (False, False, False)


def _insert_pages(engine, rows):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, hashed_password, is_active, created_at, "
                          "updated_at) VALUES ('u', 'u@x.io', 'u', 'x', 1, NOW(), NOW())"))
        for job_id in sorted({r[1] for r in rows}):
            conn.execute(text("INSERT INTO jobs (id, user_id, job_type, status, created_at, updated_at) "
                              "VALUES (:id, 'u', 'MAIN', 'PROCESSING', NOW(), NOW())"), {"id": job_id})
        for id_, job_id, number, status, updated in rows:
            conn.execute(text("INSERT INTO pages (id, job_id, page_number, status, retry_count, updated_at, "
                              "created_at) VALUES (:id, :job, :n, :s, 0, :u, :u)"),
                         {"id": id_, "job": job_id, "n": number, "s": status, "u": updated})


DUPLICATES = [
    ("a", "j1", 1, "COMPLETED", "2026-01-01 00:00:00"),
    ("b", "j1", 1, "PENDING", "2026-02-01 00:00:00"),   # newer, but not COMPLETED
    ("c", "j1", 2, "PENDING", "2026-01-01 00:00:00"),
    ("d", "j1", 3, "FAILED", "2026-01-01 00:00:00"),
    ("e", "j1", 3, "PENDING", "2026-03-01 00:00:00"),   # latest wins without a COMPLETED
    ("f", "j2", 1, "PENDING", "2026-01-01 00:00:00"),
]


def test_migrations_round_trip_with_duplicate_pages(engine):
    _previous_head(engine)
    _insert_pages(engine, DUPLICATES)

    _run(engine, "a7d30021c5e9", "upgrade")
    _run(engine, "b8f20022e1c4", "upgrade")
    assert _shape(engine) == (True, True, True)
    with engine.connect() as conn:
        assert sorted(r[0] for r in conn.execute(text("SELECT id FROM pages"))) == ["a", "c", "e", "f"]
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(text("INSERT INTO pages (id, job_id, page_number, status, retry_count, created_at, "
                              "updated_at) VALUES ('z', 'j1', 1, 'PENDING', 0, NOW(), NOW())"))
    _run(engine, "b8f20022e1c4", "upgrade")  # idempotent
    _run(engine, "a7d30021c5e9", "upgrade")

    _run(engine, "b8f20022e1c4", "downgrade")
    _run(engine, "a7d30021c5e9", "downgrade")
    assert _shape(engine) == (False, False, False)
    # the FK on pages.job_id still has its own index after the unique one is gone
    assert any(fk["referred_table"] == "jobs" for fk in inspect(engine).get_foreign_keys("pages"))

    _run(engine, "a7d30021c5e9", "upgrade")
    _run(engine, "b8f20022e1c4", "upgrade")
    assert _shape(engine) == (True, True, True)


def test_downgrade_of_a_schema_built_by_create_all(engine):
    Base.metadata.create_all(engine)
    _run(engine, "b8f20022e1c4", "upgrade")  # nothing to do
    _run(engine, "b8f20022e1c4", "downgrade")
    _run(engine, "a7d30021c5e9", "downgrade")
    assert _shape(engine) == (False, False, False)


def test_boot_upgrade_skips_the_index_while_duplicates_exist(engine, caplog):
    _previous_head(engine)
    _insert_pages(engine, DUPLICATES)

    with caplog.at_level("WARNING"):
        _add_missing_columns(engine)
    assert _shape(engine) == (True, False, True)
    assert "alembic upgrade head" in caplog.text
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM pages")).scalar() == len(DUPLICATES)  # nothing deleted

    _run(engine, "b8f20022e1c4", "upgrade")  # the migration cleans up and adds it
    assert _shape(engine) == (True, True, True)
    _add_missing_columns(engine)  # idempotent


def test_boot_upgrade_adds_the_index_without_duplicates(engine):
    _previous_head(engine)
    _insert_pages(engine, [r for r in DUPLICATES if r[0] in ("a", "c", "e", "f")])

    _add_missing_columns(engine)
    assert _shape(engine) == (True, True, True)
    _add_missing_columns(engine)  # idempotent
    _run(engine, "b8f20022e1c4", "upgrade")  # nothing left to do
    assert _shape(engine) == (True, True, True)
