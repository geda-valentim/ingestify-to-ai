"""Guards for a periodic control tick (spec 0007, section 4.6): one run at a time, within a
time budget, and never stuck behind a row lock for the database's default wait (50 s on
InnoDB). The control worker runs threads, which no Celery time limit stops, and they are
the same threads humans' operations use.

Each guard stands alone and calls nothing of the caller's: the idle policy's tick uses them.
"""

import os
import time
from functools import lru_cache
from uuid import uuid4

LOCK_WAIT_SECONDS = 5


def _redis():
    from shared.redis_client import get_redis_client

    return get_redis_client().client


def acquire(name, ttl_seconds):
    """A token when this run may go ahead, else None: another run holds `name`, or there is
    no Redis (fail closed: no lock, no run). The lock always expires (SET NX EX), and it
    never authorizes anything."""
    token = uuid4().hex
    try:
        return token if _redis().set(name, token, nx=True, ex=ttl_seconds) else None
    except Exception:  # noqa: BLE001
        return None


def release(name, token):
    """Drop the lock if it is still this run's; it expires on its own otherwise."""
    try:
        client = _redis()
        if client.get(name) in (token, token.encode()):
            client.delete(name)  # a lock taken over after expiry is left alone (bar a tiny race)
    except Exception:  # noqa: BLE001
        pass


class Deadline:
    """An absolute deadline on a monotonic clock, to check between steps of a run."""

    def __init__(self, seconds, clock=time.monotonic):
        self.clock = clock
        self.at = clock() + seconds

    def expired(self):
        return self.clock() > self.at


def lock_wait_setter(seconds):
    """The `connect` listener that caps a MySQL connection's wait for a row lock."""

    def set_lock_wait(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET SESSION innodb_lock_wait_timeout = {int(seconds)}")
        finally:
            cursor.close()

    return set_lock_wait


def short_lock_wait_sessions(seconds=LOCK_WAIT_SECONDS):
    """Sessions whose MySQL row-lock waits give up after `seconds`.

    They use their own small pool: a SET on a session of the shared pool would stay on that
    connection after it goes back (a session returns its connection at every commit), and
    would cut every later user's wait too. The pool is built on first use in each process,
    never at import or in a parent that forks (a connection opened before a fork would be
    shared by the children). Other databases (SQLite in tests) get the shared sessions.
    """
    return _sessions(seconds, os.getpid())


@lru_cache(maxsize=None)
def _sessions(seconds, _pid):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from shared.database import SessionLocal, engine, engine_options

    if engine.dialect.name != "mysql":
        return SessionLocal
    own = create_engine(engine.url, **engine_options(pool_size=2, max_overflow=0))
    event.listen(own, "connect", lock_wait_setter(seconds))
    return sessionmaker(autocommit=False, autoflush=False, bind=own)
