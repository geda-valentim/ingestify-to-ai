"""
Authorization tests for api.deps.

These cover the IDOR fixed in DELETE /jobs/{job_id}: authorization used to be
derived from Redis (a cache with a TTL) and both checks were conditional, so a
job whose Redis status had expired AND whose user_id was NULL - which happens
to every job of a deleted user, because the FK is ondelete="SET NULL" - was
reachable by any authenticated account.

The invariant under test: access requires a positive, explicit owner match.
Absent data must never authorize.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.models import Job, Page, User
from api.deps import resolve_owned_job


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def users(db):
    alice = User(id="user-alice", email="alice@example.com", username="alice",
                 hashed_password="x")
    mallory = User(id="user-mallory", email="mallory@example.com", username="mallory",
                   hashed_password="x")
    db.add_all([alice, mallory])
    db.commit()
    return alice, mallory


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Redis must not be consulted for authorization decisions in these tests.
    Every test that needs it opts in explicitly via `redis_owner`."""
    monkeypatch.setattr("api.deps._redis_job_status", lambda job_id: None)
    monkeypatch.setattr("api.deps._redis_owner_matches", lambda job_id, user_id: False)


@pytest.fixture
def redis_owner(monkeypatch):
    def _set(job_id, owner_id):
        monkeypatch.setattr(
            "api.deps._redis_owner_matches",
            lambda j, u: j == job_id and u == owner_id,
        )
    return _set


def _job(db, job_id, user_id, **kw):
    job = Job(id=job_id, user_id=user_id, job_type="MAIN", **kw)
    db.add(job)
    db.commit()
    return job


class TestOwnJob:
    def test_owner_gets_the_job(self, db, users):
        alice, _ = users
        _job(db, "j1", alice.id)
        assert resolve_owned_job(db, "j1", alice).id == "j1"

    def test_other_user_is_denied(self, db, users):
        alice, mallory = users
        _job(db, "j1", alice.id)
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "j1", mallory)
        assert exc.value.status_code == 404

    def test_denial_is_indistinguishable_from_absence(self, db, users):
        """403 would confirm the job exists. Both cases must look identical."""
        alice, mallory = users
        _job(db, "j1", alice.id)
        with pytest.raises(HTTPException) as denied:
            resolve_owned_job(db, "j1", mallory)
        with pytest.raises(HTTPException) as missing:
            resolve_owned_job(db, "does-not-exist", mallory)
        assert denied.value.status_code == missing.value.status_code == 404
        assert denied.value.detail == missing.value.detail


class TestOrphanedJob:
    """The exact IDOR that was exploitable."""

    def test_orphaned_job_authorizes_nobody(self, db, users):
        alice, mallory = users
        _job(db, "orphan", None)  # user deleted -> ondelete="SET NULL"
        for user in (alice, mallory):
            with pytest.raises(HTTPException) as exc:
                resolve_owned_job(db, "orphan", user)
            assert exc.value.status_code == 404

    def test_orphaned_job_is_denied_even_with_a_matching_redis_owner(
        self, db, users, redis_owner
    ):
        """A MySQL row that exists must decide. The Redis fallback exists only
        for jobs MySQL has never heard of - it must not rescue an orphan."""
        alice, _ = users
        _job(db, "orphan", None)
        redis_owner("orphan", alice.id)
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "orphan", alice)
        assert exc.value.status_code == 404

    def test_orphaned_parent_does_not_authorize_its_child(self, db, users):
        alice, _ = users
        _job(db, "parent", None)
        db.add(Page(job_id="parent", page_job_id="page-1", page_number=1))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "page-1", alice)
        assert exc.value.status_code == 404


class TestChildJobs:
    """Child jobs (SPLIT/PAGE/MERGE) are not persisted as `jobs` rows; ownership
    must resolve through the MAIN job."""

    def test_page_job_inherits_owner_via_pages_table(self, db, users):
        alice, _ = users
        _job(db, "main", alice.id)
        db.add(Page(job_id="main", page_job_id="page-1", page_number=1))
        db.commit()
        assert resolve_owned_job(db, "page-1", alice).id == "main"

    def test_page_job_of_another_user_is_denied(self, db, users):
        alice, mallory = users
        _job(db, "main", alice.id)
        db.add(Page(job_id="main", page_job_id="page-1", page_number=1))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "page-1", mallory)
        assert exc.value.status_code == 404

    def test_child_row_with_null_owner_walks_up_parent_chain(self, db, users):
        alice, _ = users
        _job(db, "main", alice.id)
        _job(db, "split", None, parent_job_id="main")
        assert resolve_owned_job(db, "split", alice).id == "split"

    def test_parent_chain_cycle_does_not_hang_or_authorize(self, db, users):
        alice, _ = users
        _job(db, "a", None, parent_job_id="b")
        _job(db, "b", None, parent_job_id="a")
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "a", alice)
        assert exc.value.status_code == 404

    def test_redis_discovered_parent_still_takes_owner_from_mysql(
        self, db, users, monkeypatch
    ):
        alice, mallory = users
        _job(db, "main", alice.id)
        monkeypatch.setattr(
            "api.deps._redis_job_status",
            lambda job_id: {"parent_job_id": "main"} if job_id == "merge-1" else None,
        )
        assert resolve_owned_job(db, "merge-1", alice).id == "main"
        with pytest.raises(HTTPException):
            resolve_owned_job(db, "merge-1", mallory)


class TestRedisFallback:
    """Only reachable when MySQL has no record of the job at all - the upload
    handlers log-and-continue on a MySQL write failure, so such jobs exist."""

    def test_redis_owner_authorizes_when_mysql_knows_nothing(
        self, db, users, redis_owner
    ):
        alice, _ = users
        redis_owner("redis-only", alice.id)
        assert resolve_owned_job(db, "redis-only", alice) is None

    def test_redis_fallback_denies_a_different_user(self, db, users, redis_owner):
        alice, mallory = users
        redis_owner("redis-only", alice.id)
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "redis-only", mallory)
        assert exc.value.status_code == 404

    def test_no_owner_anywhere_denies(self, db, users):
        alice, _ = users
        with pytest.raises(HTTPException) as exc:
            resolve_owned_job(db, "ghost", alice)
        assert exc.value.status_code == 404
