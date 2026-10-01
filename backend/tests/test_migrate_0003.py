"""
The spec 0003 migration (shared/migration_0003.py, driven by
scripts/migrate_0003_projects.py): DDL, one-shot backfill, downgrade.

SQLite stands in for MariaDB; the MariaDB-only SQL is checked as text (no
ALGORITHM=COPY, WAIT, INSTANT/INPLACE) and as compiled DDL (charset, binary key).
"""
import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateTable

from shared import migration_0003 as m
from shared.database import Base
from shared.models import JOBS_PROJECT_INDEX, JOBS_PROJECT_INDEX_COLUMNS, AppMigration, Folder, Project
from tests.legacy_schema import T0, add_job, add_key, add_user, column, make_legacy_database, sqlite_engine


@pytest.fixture
def legacy(tmp_path):
    engine = make_legacy_database(tmp_path / "legacy.db")
    with engine.begin() as conn:
        for u in ("alice", "bob", "carol", "dave"):
            add_user(conn, u)
        add_job(conn, "a-main-1", "alice")
        add_job(conn, "a-main-2", "alice")
        add_job(conn, "a-page-1", "alice", job_type="PAGE")
        add_job(conn, "b-main-1", "bob")
        add_job(conn, "d-page-1", "dave", job_type="PAGE")   # no MAIN job, no key: no Inbox
        add_key(conn, "a-key", "alice", name="cliente-audio")
        add_key(conn, "c-key", "carol", name="carol-script")  # only a key: gets an Inbox
    return engine


def inbox_of(engine, user_id):
    with engine.connect() as conn:
        return conn.execute(
            select(Project.__table__.c.id).where(
                Project.__table__.c.user_id == user_id, Project.__table__.c.name_key == "inbox")
        ).scalar()


def quiet(_msg):
    pass


# --- DDL ---------------------------------------------------------------------

def test_ddl_creates_tables_columns_and_index(legacy):
    assert set(m.missing_schema(legacy)) == {
        "table app_migrations", "table projects", "table folders",
        "column jobs.project_id", "column jobs.folder_id", "column api_keys.project_id",
        f"index jobs.{JOBS_PROJECT_INDEX}",
    }
    m.apply_ddl(legacy, out=quiet)
    assert m.missing_schema(legacy) == []


def test_ddl_is_idempotent(legacy):
    m.apply_ddl(legacy, out=quiet)
    assert m.apply_ddl(legacy, out=quiet) == []
    assert m.missing_schema(legacy) == []


def test_ddl_only_adds_what_is_missing(legacy):
    with legacy.begin() as conn:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN project_id VARCHAR(36) NULL"))
    applied = m.apply_ddl(legacy, out=quiet)
    assert "ALTER TABLE jobs ADD COLUMN folder_id VARCHAR(36) NULL" in applied
    assert not any(a.startswith("ALTER TABLE jobs ADD COLUMN project_id") for a in applied)


def test_mariadb_statements_never_copy_the_jobs_table():
    alter = m.sql_add_columns("jobs", ["project_id", "folder_id"], mysql=True)
    assert alter == [
        "ALTER TABLE jobs WAIT 5 ADD COLUMN project_id VARCHAR(36) NULL, "
        "ADD COLUMN folder_id VARCHAR(36) NULL, ALGORITHM=INSTANT"
    ]
    index = m.sql_create_index(mysql=True)
    assert "WAIT 5 ALGORITHM=INPLACE LOCK=NONE" in index
    for sql in alter + [index]:
        assert "COPY" not in sql.upper()
        assert "FOREIGN KEY" not in sql.upper()


def test_new_tables_declare_charset_and_a_binary_key_on_mariadb():
    for model in (Project, Folder):
        ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert "CHARSET=utf8mb4" in ddl and "COLLATE utf8mb4_general_ci" in ddl
        assert "ENGINE=InnoDB" in ddl
        assert "name_key VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin" in ddl
    jobs_ddl = str(CreateTable(Base.metadata.tables["jobs"]).compile(dialect=mysql.dialect()))
    assert "project_id VARCHAR(36)" in jobs_ddl
    assert "REFERENCES projects" not in jobs_ddl and "REFERENCES folders" not in jobs_ddl


def test_create_all_and_the_script_produce_the_same_index(legacy, tmp_path):
    m.apply_ddl(legacy, out=quiet)
    fresh = sqlite_engine(tmp_path / "fresh.db")
    Base.metadata.create_all(bind=fresh)

    def index(engine):
        return next(i for i in inspect(engine).get_indexes("jobs") if i["name"] == JOBS_PROJECT_INDEX)

    assert index(legacy)["column_names"] == index(fresh)["column_names"] == list(JOBS_PROJECT_INDEX_COLUMNS)


def _lock_timeout():
    return OperationalError("ALTER TABLE jobs", {}, Exception(1205, "Lock wait timeout exceeded"))


def _plan_with_failing_jobs_alter(engine, fail_times):
    calls = {"n": 0}
    plan = []
    for label, action in m.ddl_plan(engine):
        if label.startswith("ALTER TABLE jobs"):
            def failing(conn, action=action):
                calls["n"] += 1
                if calls["n"] <= fail_times:
                    raise _lock_timeout()
                action(conn)
            plan.append((label, failing))
        else:
            plan.append((label, action))
    return plan, calls


def test_lock_timeout_is_retried(legacy, monkeypatch):
    plan, calls = _plan_with_failing_jobs_alter(legacy, fail_times=2)
    monkeypatch.setattr(m, "ddl_plan", lambda bind: plan)
    sleeps = []
    m.apply_ddl(legacy, sleep=sleeps.append, out=quiet)
    assert sleeps == [m.DDL_RETRY_INTERVAL_SECONDS] * 2
    assert m.missing_schema(legacy) == []


def test_lock_timeouts_exhausted_abort_without_partial_ddl(legacy, monkeypatch):
    plan, calls = _plan_with_failing_jobs_alter(legacy, fail_times=99)
    monkeypatch.setattr(m, "ddl_plan", lambda bind: plan)
    sleeps, printed = [], []
    with pytest.raises(m.MigrationAborted):
        m.apply_ddl(legacy, sleep=sleeps.append, out=printed.append)

    assert calls["n"] == m.DDL_ATTEMPTS
    assert len(sleeps) == m.DDL_ATTEMPTS - 1
    missing = m.missing_schema(legacy)
    # the failing ALTER changed nothing, and nothing after it ran
    assert {"column jobs.project_id", "column jobs.folder_id", "column api_keys.project_id",
            f"index jobs.{JOBS_PROJECT_INDEX}"} <= set(missing)
    assert any("LOCK TIMEOUT (5/5)" in p for p in printed)


def test_other_errors_are_not_retried(legacy, monkeypatch):
    def broken(conn):
        raise OperationalError("ALTER", {}, Exception(1064, "syntax error"))

    monkeypatch.setattr(m, "ddl_plan", lambda bind: [("ALTER broken", broken)])
    sleeps = []
    with pytest.raises(OperationalError):
        m.apply_ddl(legacy, sleep=sleeps.append, out=quiet)
    assert sleeps == []


# --- backfill ----------------------------------------------------------------

def test_backfill_creates_one_inbox_per_user_and_fills_only_main_jobs(legacy):
    m.apply_ddl(legacy, out=quiet)
    printed = []
    summary = m.backfill(legacy, now=T0 + timedelta(hours=1), out=printed.append)

    alice, bob, carol = (inbox_of(legacy, u) for u in ("alice", "bob", "carol"))
    assert alice and bob and carol and len({alice, bob, carol}) == 3
    assert inbox_of(legacy, "dave") is None
    assert column(legacy, "projects", "name", alice) == "Inbox"

    assert column(legacy, "jobs", "project_id", "a-main-1") == alice
    assert column(legacy, "jobs", "project_id", "a-main-2") == alice
    assert column(legacy, "jobs", "project_id", "b-main-1") == bob
    assert column(legacy, "jobs", "project_id", "a-page-1") is None  # children inherit via parent
    assert column(legacy, "api_keys", "project_id", "a-key") == alice
    assert column(legacy, "api_keys", "project_id", "c-key") == carol

    assert summary == {"t1": T0 + timedelta(hours=1), "users": 3, "jobs": 3, "api_keys": 2}
    assert m.get_marker(legacy, m.MARKER_BACKFILL) == T0 + timedelta(hours=1)
    listing = "\n".join(printed)
    assert "cliente-audio" in listing and "carol-script" in listing


def test_backfill_works_in_small_batches(legacy):
    m.apply_ddl(legacy, out=quiet)
    with legacy.begin() as conn:
        for i in range(7):
            add_job(conn, f"a-extra-{i}", "alice")
    m.backfill(legacy, now=T0 + timedelta(hours=1), batch_size=2, out=quiet)
    with legacy.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM jobs WHERE job_type='MAIN' AND project_id IS NULL")).scalar() == 0


def test_backfill_leaves_rows_after_t1_to_the_tail(legacy):
    m.apply_ddl(legacy, out=quiet)
    with legacy.begin() as conn:
        add_job(conn, "a-late", "alice", created_at=T0 + timedelta(hours=2))
    m.backfill(legacy, now=T0 + timedelta(hours=1), out=quiet)
    assert column(legacy, "jobs", "project_id", "a-late") is None


def test_second_run_changes_nothing(legacy):
    m.apply_ddl(legacy, out=quiet)
    m.backfill(legacy, now=T0 + timedelta(hours=1), out=quiet)
    with legacy.begin() as conn:
        add_job(conn, "a-new", "alice", created_at=T0)  # would be filled if it ran again
    printed = []
    assert m.backfill(legacy, now=T0 + timedelta(hours=5), out=printed.append) is None
    assert column(legacy, "jobs", "project_id", "a-new") is None
    assert m.get_marker(legacy, m.MARKER_BACKFILL) == T0 + timedelta(hours=1)
    with legacy.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM projects")).scalar() == 3


def test_an_existing_inbox_project_is_reused(legacy):
    m.apply_ddl(legacy, out=quiet)
    with legacy.begin() as conn:
        conn.execute(Project.__table__.insert().values(
            id="alice-own-inbox", user_id="alice", name="INBOX", name_key="inbox",
            created_at=T0, updated_at=T0))
    m.backfill(legacy, now=T0 + timedelta(hours=1), out=quiet)
    assert inbox_of(legacy, "alice") == "alice-own-inbox"
    assert column(legacy, "projects", "name", "alice-own-inbox") == "INBOX"
    assert column(legacy, "jobs", "project_id", "a-main-1") == "alice-own-inbox"


# --- downgrade ---------------------------------------------------------------

def test_downgrade_removes_everything_and_keeps_the_jobs(legacy):
    m.apply_ddl(legacy, out=quiet)
    m.backfill(legacy, now=T0 + timedelta(hours=1), out=quiet)
    m.downgrade(legacy, out=quiet)

    insp = inspect(legacy)
    assert not {"projects", "folders", "app_migrations"} & set(insp.get_table_names())
    assert "project_id" not in {c["name"] for c in insp.get_columns("jobs")}
    assert "project_id" not in {c["name"] for c in insp.get_columns("api_keys")}
    with legacy.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar() == 5
    # and it can be migrated again
    m.apply_ddl(legacy, out=quiet)
    assert m.missing_schema(legacy) == []


# --- the CLI -----------------------------------------------------------------

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_0003_projects.py"


@pytest.mark.skipif(not SCRIPT.exists(), reason="scripts/ not present in this checkout")
def test_script_runs_end_to_end_and_twice(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "cli.db"
    engine = make_legacy_database(db_path)
    with engine.begin() as conn:
        add_user(conn, "alice")
        add_job(conn, "a-main-1", "alice")
        add_key(conn, "a-key", "alice", name="cliente-audio")

    spec = importlib.util.spec_from_file_location("migrate_0003_projects", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    # The script imports shared.database.engine; point it at the test database.
    import shared.database as database
    monkeypatch.setattr(database, "engine", engine)

    assert script.main(["--yes"]) == 0
    assert script.main(["--yes"]) == 0
    out = capsys.readouterr().out
    assert "nothing to do" in out and "already present" in out
    assert "cliente-audio" in out
    assert column(engine, "jobs", "project_id", "a-main-1") == inbox_of(engine, "alice")
    assert script.main(["--check"]) == 0
