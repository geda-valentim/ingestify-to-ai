"""
API boot for spec 0003 (§ 4.3 step 5): schema guard before create_all, fresh
database markers, the one-shot tail and the read-only invariant check.
"""
import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

import api.main as main
import shared.database as database
from shared import migration_0003 as m
from tests.legacy_schema import T0, add_job, add_key, add_user, column, make_legacy_database, sqlite_engine


def quiet(_msg):
    pass


@pytest.fixture
def boot(monkeypatch):
    """Run init_database_on_boot against `engine`; returns the list of init_db calls."""
    monkeypatch.setattr(main.settings, "environment", "development")

    def run(engine, real_init_db=True):
        calls = []
        real = database.init_db

        def init_db():
            calls.append("init_db")
            if real_init_db:
                real()
            else:
                raise RuntimeError("database unreachable")

        monkeypatch.setattr(database, "engine", engine)
        monkeypatch.setattr(database, "init_db", init_db)
        main.init_database_on_boot()
        return calls

    return run


@pytest.fixture
def migrated(tmp_path):
    """Old schema + data, then the runbook's DDL and backfill at T1 = T0 + 1h."""
    engine = make_legacy_database(tmp_path / "db.sqlite")
    with engine.begin() as conn:
        add_user(conn, "alice")
        add_user(conn, "bob")
        add_job(conn, "a-main-1", "alice")
        add_key(conn, "a-key", "alice")
    m.apply_ddl(engine, out=quiet)
    m.backfill(engine, now=T0 + timedelta(hours=1), out=quiet)
    return engine


# --- 5a: the guard ------------------------------------------------------------

def test_jobs_without_the_column_stops_the_api_before_create_all(tmp_path, boot):
    engine = make_legacy_database(tmp_path / "old.db")
    with pytest.raises(SystemExit) as exc:
        boot(engine)
    assert exc.value.code == 1


def test_guard_runs_before_init_db(tmp_path, monkeypatch):
    """Whatever ENVIRONMENT says: development swallows init_db errors, not this."""
    engine = make_legacy_database(tmp_path / "old.db")
    calls = []
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "init_db", lambda: calls.append("init_db"))
    with pytest.raises(SystemExit):
        main.init_database_on_boot()
    assert calls == []


def test_missing_backfill_marker_stops_the_api(tmp_path, boot):
    engine = make_legacy_database(tmp_path / "old.db")
    m.apply_ddl(engine, out=quiet)  # DDL done, step 3 forgotten
    with pytest.raises(SystemExit):
        boot(engine)


def test_empty_database_boots_and_gets_both_markers(tmp_path, boot):
    engine = sqlite_engine(tmp_path / "empty.db")
    before = datetime.utcnow()
    assert boot(engine) == ["init_db"]

    assert m.missing_schema(engine) == []  # create_all built tables, columns and index
    t1 = m.get_marker(engine, m.MARKER_BACKFILL)
    t2 = m.get_marker(engine, m.MARKER_TAIL)
    assert t1 is not None and t1 == t2 and t1 >= before
    # and the next boot passes the guard
    assert boot(engine) == ["init_db"]


def test_unreachable_database_behaves_as_before(tmp_path, boot):
    engine = create_engine(f"sqlite:///{tmp_path / 'no-such-dir' / 'x.db'}")
    assert boot(engine, real_init_db=False) == ["init_db"]  # logged, not raised


def test_migrated_database_boots(migrated, boot):
    assert boot(migrated) == ["init_db"]
    assert m.get_marker(migrated, m.MARKER_TAIL) is not None


# --- 5b: the tail -------------------------------------------------------------

def test_tail_catches_rows_the_backfill_missed(migrated, boot):
    with migrated.begin() as conn:
        # a late job of the old code: created_at before T1 but committed after step 3
        add_job(conn, "a-late", "alice", created_at=T0 + timedelta(minutes=30))
        add_job(conn, "b-late", "bob", created_at=T0 + timedelta(hours=2))
        add_job(conn, "b-page", "bob", job_type="PAGE", created_at=T0 + timedelta(hours=2))
        add_key(conn, "b-key", "bob", created_at=T0 + timedelta(hours=2))

    boot(migrated)

    alice_inbox = column(migrated, "jobs", "project_id", "a-main-1")
    assert column(migrated, "jobs", "project_id", "a-late") == alice_inbox
    bob_inbox = column(migrated, "jobs", "project_id", "b-late")
    assert bob_inbox and bob_inbox != alice_inbox
    assert column(migrated, "api_keys", "project_id", "b-key") == bob_inbox
    assert column(migrated, "jobs", "project_id", "b-page") is None
    assert m.get_marker(migrated, m.MARKER_TAIL) is not None


def test_tail_marker_is_written_in_the_same_transaction(migrated, monkeypatch):
    with migrated.begin() as conn:
        add_job(conn, "b-late", "bob", created_at=T0 + timedelta(hours=2))

    def broken_insert(conn, user_id, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "_insert_inbox", broken_insert)
    with pytest.raises(RuntimeError):
        m.run_tail(migrated)
    assert m.get_marker(migrated, m.MARKER_TAIL) is None  # rolled back with the rows


def test_existing_marker_skips_without_touching_rows(migrated, monkeypatch):
    with migrated.begin() as conn:
        conn.execute(text("INSERT INTO app_migrations (name, applied_at) VALUES ('0003_tail', :t)"),
                     {"t": T0 + timedelta(hours=3)})
        add_job(conn, "b-late", "bob", created_at=T0 + timedelta(hours=2))

    # Lose the race: the first read does not see the marker yet.
    real = m.get_marker
    seen = {"n": 0}

    def get_marker(bind, name):
        seen["n"] += 1
        return None if seen["n"] == 1 else real(bind, name)

    monkeypatch.setattr(m, "get_marker", get_marker)
    assert m.run_tail(migrated) is None
    assert column(migrated, "jobs", "project_id", "b-late") is None


def test_second_boot_touches_nothing(migrated, boot, caplog):
    boot(migrated)
    t2 = m.get_marker(migrated, m.MARKER_TAIL)
    later = t2 + timedelta(minutes=5)
    alice_inbox = column(migrated, "jobs", "project_id", "a-main-1")
    with migrated.begin() as conn:
        add_key(conn, "unbound-on-purpose", "alice", created_at=later)
        add_job(conn, "bug-job", "alice", created_at=later)
        # the owner deleted alice's Inbox (phase 2): the boot must not recreate it
        conn.execute(text("UPDATE jobs SET project_id = NULL WHERE project_id = :p"), {"p": alice_inbox})
        conn.execute(text("UPDATE api_keys SET project_id = NULL WHERE project_id = :p"), {"p": alice_inbox})
        conn.execute(text("DELETE FROM projects WHERE id = :p"), {"p": alice_inbox})

    with caplog.at_level(logging.ERROR, logger="shared.migration_0003"):
        boot(migrated)

    assert m.get_marker(migrated, m.MARKER_TAIL) == t2
    assert column(migrated, "api_keys", "project_id", "unbound-on-purpose") is None
    assert column(migrated, "jobs", "project_id", "bug-job") is None
    with migrated.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM projects WHERE user_id = 'alice'")).scalar() == 0
    assert any("Invariant violated: 1 MAIN jobs" in r.message for r in caplog.records)
