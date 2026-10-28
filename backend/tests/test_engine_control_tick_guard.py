"""
Spec 0007, section 4.6: the guards of a periodic control tick. One run at a time (a lock
that always expires and, without Redis, lets no run through), an absolute deadline, and
sessions whose MySQL row-lock waits give up early without touching the shared pool.
"""

import pytest

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

    @pytest.fixture
    def mysql(self, monkeypatch):
        """The shared engine pointing at MySQL (never connected here)."""
        from sqlalchemy import create_engine

        from shared import database

        main = create_engine("mysql+pymysql://user:pw@db.invalid/app", **database.engine_options())
        monkeypatch.setattr(database, "engine", main)
        tick_guard._sessions.cache_clear()
        yield main
        tick_guard._sessions.cache_clear()
        main.dispose()

    def test_mysql_gets_its_own_small_pool_with_the_shared_options(self, mysql, monkeypatch):
        from sqlalchemy import event

        def capped(dbapi_connection, record):
            pass

        monkeypatch.setattr(tick_guard, "lock_wait_setter", lambda seconds: capped)
        own = tick_guard.short_lock_wait_sessions(5).kw["bind"]

        assert own is not mysql and own.url == mysql.url, "same database, same config, not the shared pool"
        assert own.pool.size() == 2 and own.pool._max_overflow == 0
        assert own.pool._pre_ping and own.pool._recycle == 3600 and own.pool._timeout == mysql.pool._timeout
        assert event.contains(own, "connect", capped), "every new connection gets the cap"
        own.dispose()

    def test_one_pool_per_process_and_none_before_first_use(self, mysql, monkeypatch):
        """Prefork: a pool built in the parent would hand its connections to the children."""
        import importlib

        importlib.reload(tick_guard)
        assert tick_guard._sessions.cache_info().currsize == 0, "nothing built at import"

        monkeypatch.setattr(tick_guard.os, "getpid", lambda: 101)
        parent = tick_guard.short_lock_wait_sessions(5)
        assert tick_guard.short_lock_wait_sessions(5) is parent
        monkeypatch.setattr(tick_guard.os, "getpid", lambda: 102)
        child = tick_guard.short_lock_wait_sessions(5)

        assert child is not parent and child.kw["bind"] is not parent.kw["bind"]
        for factory in (parent, child):
            factory.kw["bind"].dispose()

    def test_other_databases_get_the_shared_sessions(self, monkeypatch):
        from sqlalchemy import create_engine

        from shared import database

        monkeypatch.setattr(database, "engine", create_engine("sqlite://"))
        tick_guard._sessions.cache_clear()
        try:
            assert tick_guard.short_lock_wait_sessions(5) is SessionLocal
        finally:
            tick_guard._sessions.cache_clear()
