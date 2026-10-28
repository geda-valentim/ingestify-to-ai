"""
Spec 0007, section 4.6: the guards of a periodic control tick. One run at a time (a lock
that always expires and, without Redis, lets no run through), an absolute deadline, and
sessions whose MySQL row-lock waits give up early without touching the shared pool.
"""

import pytest

from shared.config import get_settings
from shared.database import SessionLocal
from workers.engine_control import tick_guard

LOCK = "engine_idle:tick"


@pytest.fixture
def redis(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(tick_guard, "_redis", lambda: client)
    return client


def _down():
    raise ConnectionError("redis down")


class TestLock:
    def test_one_run_at_a_time(self, redis):
        first = tick_guard.acquire(LOCK, 60)

        assert first and tick_guard.acquire(LOCK, 60) is None
        tick_guard.release(LOCK, first)
        assert tick_guard.acquire(LOCK, 60)

    def test_it_always_expires(self, redis):
        tick_guard.acquire(LOCK, 60)

        assert 0 < redis.ttl(LOCK) <= 60

    def test_a_lock_taken_over_after_expiry_is_not_released_by_the_old_run(self, redis):
        old = tick_guard.acquire(LOCK, 60)
        redis.set(LOCK, "newer", ex=60)  # the old run's lock expired; another took it

        tick_guard.release(LOCK, old)

        assert redis.get(LOCK) == "newer"

    def test_without_redis_no_run_goes_ahead(self, monkeypatch):
        monkeypatch.setattr(tick_guard, "_redis", _down)

        assert tick_guard.acquire(LOCK, 60) is None
        tick_guard.release(LOCK, "token")  # never raises


def test_the_deadline_is_absolute():
    now = [100.0]
    deadline = tick_guard.Deadline(10, clock=lambda: now[0])

    now[0] = 110.0
    assert not deadline.expired()
    now[0] = 110.5
    assert deadline.expired()


class TestShortLockWaits:
    def test_the_listener_caps_the_connection_s_row_lock_wait(self):
        executed = []

        class Cursor:
            def execute(self, sql):
                executed.append(sql)

            def close(self):
                executed.append("closed")

        class Connection:
            def cursor(self):
                return Cursor()

        tick_guard.lock_wait_setter(5)(Connection(), None)

        assert executed == ["SET SESSION innodb_lock_wait_timeout = 5", "closed"]

    def test_mysql_gets_its_own_pool_and_never_the_shared_one(self, monkeypatch):
        from sqlalchemy import event

        def capped(dbapi_connection, record):
            pass

        monkeypatch.setattr(get_settings(), "database_url", "mysql+pymysql://user:pw@db.invalid/app")
        monkeypatch.setattr(tick_guard, "lock_wait_setter", lambda seconds: capped)
        tick_guard.short_lock_wait_sessions.cache_clear()
        try:
            factory = tick_guard.short_lock_wait_sessions(5)
            bind = factory.kw["bind"]

            assert factory is not SessionLocal and bind is not SessionLocal.kw["bind"]
            assert event.contains(bind, "connect", capped), "every new connection gets the cap"
            bind.dispose()
        finally:
            tick_guard.short_lock_wait_sessions.cache_clear()

    def test_other_databases_get_the_shared_sessions(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "database_url", "sqlite://")
        tick_guard.short_lock_wait_sessions.cache_clear()
        try:
            assert tick_guard.short_lock_wait_sessions(5) is SessionLocal
        finally:
            tick_guard.short_lock_wait_sessions.cache_clear()
