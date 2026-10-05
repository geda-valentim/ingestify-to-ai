"""
Spec 0004 (projects and folders): schema migration, one-shot backfills and the
API boot guard.

One implementation, three callers:

- `scripts/migrate_0004_projects.py` - the ONLY path in production (runbook in
  docs/runbooks/0004-projects-migration.md and spec 0004 § 4.3). DDL first,
  with the old code still running; then the one-shot backfill.
- `alembic/versions/b5d10003a1f0_projects_and_folders.py` - so dev databases
  managed by Alembic converge. Forbidden in production (not stamped there).
- `api/main.py` at boot - `boot_schema_guard` before `init_db`, then
  `finish_boot_migration` (fresh-database markers, the one-shot tail and the
  read-only invariant check).

Every DDL step looks at the live schema first, so running it twice changes
nothing. Nothing here works on MariaDB-specific behaviour alone: on SQLite
(tests, dev) the same steps run with portable DDL.

MariaDB 10.11 specifics (production):

- `ALTER TABLE jobs WAIT 5 ADD COLUMN ..., ALGORITHM=INSTANT`: never a table
  copy, and the metadata-lock wait is bounded by `WAIT 5` (plus
  `SET SESSION lock_wait_timeout = 5`). A lock timeout is retried up to 5
  times, 30 s apart, then the run aborts cleanly - each ALTER is atomic, so
  nothing is left half-done - and the transactions holding the lock are
  printed.
- the index is `ALGORITHM=INPLACE LOCK=NONE`.
- no FOREIGN KEY is ever added to `jobs` or `api_keys`.
"""

import logging
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

from shared.models import (
    JOBS_PROJECT_INDEX,
    JOBS_PROJECT_INDEX_COLUMNS,
    APIKey,
    AppMigration,
    Folder,
    Job,
    Project,
    User,
    generate_uuid,
)

logger = logging.getLogger(__name__)

MARKER_BACKFILL = "0004_backfill"
MARKER_TAIL = "0004_tail"

INBOX_NAME = "Inbox"
INBOX_KEY = "inbox"

LOCK_WAIT_SECONDS = 5
DDL_ATTEMPTS = 5
DDL_RETRY_INTERVAL_SECONDS = 30
BACKFILL_BATCH_SIZE = 1000

# The three columns the new models read. Their absence makes every SELECT on
# jobs / api_keys fail with "Unknown column".
REQUIRED_COLUMNS = {
    "jobs": ("project_id", "folder_id"),
    "api_keys": ("project_id",),
}

# New tables, in dependency order.
NEW_TABLES = (AppMigration.__table__, Project.__table__, Folder.__table__)

_jobs = Job.__table__
_keys = APIKey.__table__
_projects = Project.__table__
_markers = AppMigration.__table__

RUNBOOK_HINT = (
    "Run the spec 0004 migration first (DDL + backfill), with the OLD code still deployed:\n"
    "    python scripts/migrate_0004_projects.py --database-url <url>\n"
    "See docs/runbooks/0004-projects-migration.md."
)


class MigrationAborted(RuntimeError):
    """A step could not complete; nothing after it ran. The message says why."""


Out = Callable[[str], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_mysql(bind) -> bool:
    return bind.dialect.name in ("mysql", "mariadb")


@contextmanager
def _tx(bind):
    """A transaction on an Engine; the caller's own transaction on a Connection."""
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            yield conn
    else:
        yield bind


@contextmanager
def _connection(bind):
    if isinstance(bind, Engine):
        with bind.connect() as conn:
            yield conn
    else:
        yield bind


def _utcnow() -> datetime:
    return datetime.utcnow()


def _is_lock_timeout(exc: Exception) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    orig = getattr(exc, "orig", None)
    code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
    return code == 1205 or "lock wait timeout" in str(exc).lower()


def schema_snapshot(bind) -> Dict[str, object]:
    """Tables, columns and jobs indexes as they are now."""
    with _connection(bind) as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        columns = {
            table: {c["name"] for c in insp.get_columns(table)}
            for table in REQUIRED_COLUMNS
            if table in tables
        }
        indexes = {i["name"] for i in insp.get_indexes("jobs")} if "jobs" in tables else set()
    return {"tables": tables, "columns": columns, "jobs_indexes": indexes}


def missing_schema(bind) -> List[str]:
    """Everything spec 0004 adds that the database does not have yet (empty = OK)."""
    snap = schema_snapshot(bind)
    missing = [f"table {t.name}" for t in NEW_TABLES if t.name not in snap["tables"]]
    for table, cols in REQUIRED_COLUMNS.items():
        present = snap["columns"].get(table, set())
        missing += [f"column {table}.{c}" for c in cols if c not in present]
    if JOBS_PROJECT_INDEX not in snap["jobs_indexes"]:
        missing.append(f"index jobs.{JOBS_PROJECT_INDEX}")
    return missing


# ---------------------------------------------------------------------------
# DDL (runbook step 1)
# ---------------------------------------------------------------------------

def sql_add_columns(table: str, columns: Iterable[str], mysql: bool) -> List[str]:
    """ADD COLUMN statements. MariaDB: one atomic, INSTANT, lock-bounded ALTER."""
    columns = list(columns)
    if not columns:
        return []
    if mysql:
        # Same charset/collation as projects.id / folders.id, whatever the table's
        # own default: the GET /jobs LEFT JOIN on these ids must never hit
        # "Illegal mix of collations".
        adds = ", ".join(
            f"ADD COLUMN {c} VARCHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL"
            for c in columns
        )
        return [f"ALTER TABLE {table} WAIT {LOCK_WAIT_SECONDS} {adds}, ALGORITHM=INSTANT"]
    return [f"ALTER TABLE {table} ADD COLUMN {c} VARCHAR(36) NULL" for c in columns]


def sql_create_index(mysql: bool) -> str:
    cols = ", ".join(JOBS_PROJECT_INDEX_COLUMNS)
    if mysql:
        return (
            f"CREATE INDEX {JOBS_PROJECT_INDEX} ON jobs ({cols}) "
            f"WAIT {LOCK_WAIT_SECONDS} ALGORITHM=INPLACE LOCK=NONE"
        )
    return f"CREATE INDEX {JOBS_PROJECT_INDEX} ON jobs ({cols})"


def ddl_plan(bind) -> List[Tuple[str, Callable[[Connection], None]]]:
    """The DDL steps still needed, as (label, action) pairs."""
    snap = schema_snapshot(bind)
    mysql = is_mysql(bind)
    plan: List[Tuple[str, Callable[[Connection], None]]] = []

    for table in NEW_TABLES:
        if table.name not in snap["tables"]:
            plan.append((f"CREATE TABLE {table.name}", lambda conn, t=table: t.create(conn, checkfirst=True)))

    for table, cols in REQUIRED_COLUMNS.items():
        missing = [c for c in cols if c not in snap["columns"].get(table, set())]
        for sql in sql_add_columns(table, missing, mysql):
            plan.append((sql, lambda conn, s=sql: conn.exec_driver_sql(s)))

    if JOBS_PROJECT_INDEX not in snap["jobs_indexes"]:
        sql = sql_create_index(mysql)
        plan.append((sql, lambda conn, s=sql: conn.exec_driver_sql(s)))
    return plan


def long_transactions(bind, older_than_seconds: int = 30) -> List[dict]:
    """InnoDB transactions open for longer than the threshold (MariaDB only)."""
    if not is_mysql(bind):
        return []
    with _connection(bind) as conn:
        rows = conn.execute(text(
            "SELECT trx_id, trx_started, trx_mysql_thread_id, trx_query "
            "FROM information_schema.innodb_trx "
            "WHERE trx_started < NOW() - INTERVAL :s SECOND ORDER BY trx_started"
        ), {"s": older_than_seconds}).mappings().all()
    return [dict(r) for r in rows]


def apply_ddl(
    bind,
    *,
    attempts: int = DDL_ATTEMPTS,
    interval: float = DDL_RETRY_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    out: Out = print,
) -> List[str]:
    """
    Runbook step 1: create the new tables, columns and index that are missing.

    Idempotent. A metadata-lock timeout is retried `attempts` times, `interval`
    seconds apart; then `MigrationAborted` (after printing the transactions that
    were holding the lock). Returns the labels of the steps applied.
    """
    applied = []
    plan = ddl_plan(bind)
    if not plan:
        out("DDL: nothing to do (schema already migrated)")
        return applied

    with _connection(bind) as conn:
        if is_mysql(conn):
            conn.exec_driver_sql(f"SET SESSION lock_wait_timeout = {LOCK_WAIT_SECONDS}")
        for label, action in plan:
            for attempt in range(1, attempts + 1):
                try:
                    action(conn)
                    if isinstance(bind, Engine):
                        conn.commit()
                    break
                except OperationalError as e:
                    if isinstance(bind, Engine):
                        conn.rollback()
                    if not _is_lock_timeout(e):
                        raise
                    out(f"LOCK TIMEOUT ({attempt}/{attempts}) on: {label}")
                    if attempt == attempts:
                        for trx in long_transactions(bind, 0):
                            out(f"  holding: {trx}")
                        raise MigrationAborted(
                            f"Gave up after {attempts} lock timeouts on: {label}. "
                            "Nothing was left half-done (each statement is atomic). "
                            "Wait for the long transactions above, or stop the workers, and run again."
                        ) from e
                    sleep(interval)
            applied.append(label)
            out(f"OK   {label}")
    return applied


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def get_marker(bind, name: str) -> Optional[datetime]:
    with _connection(bind) as conn:
        return conn.execute(select(_markers.c.applied_at).where(_markers.c.name == name)).scalar()


def _insert_marker(conn, name: str, when: datetime) -> None:
    conn.execute(_markers.insert().values(name=name, applied_at=when))


def mark_fresh_database(bind, now: Optional[datetime] = None) -> None:
    """A database created by create_all has no legacy rows: both markers, T1 = T2 = now."""
    now = now or _utcnow()
    for name in (MARKER_BACKFILL, MARKER_TAIL):
        try:
            with _tx(bind) as conn:
                if conn.execute(select(_markers.c.name).where(_markers.c.name == name)).first() is None:
                    _insert_marker(conn, name, now)
        except IntegrityError:
            pass  # another process wrote it first


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

def _find_inbox(conn, user_id: str, lock: bool = False) -> Optional[str]:
    query = select(_projects.c.id).where(_projects.c.user_id == user_id, _projects.c.name_key == INBOX_KEY)
    if lock and is_mysql(conn):
        query = query.with_for_update()  # a locking read sees the latest committed row
    return conn.execute(query).scalar()


def _insert_inbox(conn, user_id: str, now: datetime) -> str:
    project_id = generate_uuid()
    conn.execute(_projects.insert().values(
        id=project_id, user_id=user_id, name=INBOX_NAME, name_key=INBOX_KEY,
        created_at=now, updated_at=now,
    ))
    return project_id


def select_or_insert_inbox(bind, user_id: str, now: Optional[datetime] = None) -> str:
    """The user's "inbox" project (any display spelling), created as "Inbox" if absent."""
    now = now or _utcnow()
    for _ in range(2):
        with _tx(bind) as conn:
            existing = _find_inbox(conn, user_id)
            if existing:
                return existing
        try:
            with _tx(bind) as conn:
                return _insert_inbox(conn, user_id, now)
        except IntegrityError:
            if not isinstance(bind, Engine):
                raise
            # created concurrently: read again in a new transaction
    with _tx(bind) as conn:
        existing = _find_inbox(conn, user_id)
    if not existing:
        raise MigrationAborted(f"Could not create or find the Inbox of user {user_id}")
    return existing


# ---------------------------------------------------------------------------
# Backfill (runbook step 3)
# ---------------------------------------------------------------------------

def _main_jobs_without_project(cutoff: datetime):
    return and_(
        _jobs.c.project_id.is_(None),
        _jobs.c.job_type == "MAIN",
        _jobs.c.user_id.isnot(None),
        _jobs.c.created_at <= cutoff,
    )


def _keys_without_project(cutoff: datetime):
    return and_(_keys.c.project_id.is_(None), _keys.c.created_at <= cutoff)


def _users_to_backfill(conn, cutoff: datetime) -> List[str]:
    job_users = select(_jobs.c.user_id).where(_main_jobs_without_project(cutoff)).distinct()
    key_users = select(_keys.c.user_id).where(_keys_without_project(cutoff)).distinct()
    users = {r[0] for r in conn.execute(job_users)} | {r[0] for r in conn.execute(key_users)}
    return sorted(u for u in users if u)


def bound_inbox_keys(bind) -> List[dict]:
    """API keys bound to an "inbox" project, for the owner to re-bind consciously."""
    query = (
        select(User.username, _keys.c.name, _keys.c.last_used_at, _keys.c.id)
        .select_from(_keys.join(_projects, _projects.c.id == _keys.c.project_id)
                     .join(User.__table__, User.__table__.c.id == _keys.c.user_id))
        .where(_projects.c.name_key == INBOX_KEY)
        .order_by(User.username, _keys.c.name)
    )
    with _connection(bind) as conn:
        return [dict(r) for r in conn.execute(query).mappings()]


def backfill(
    bind,
    *,
    now: Optional[datetime] = None,
    batch_size: int = BACKFILL_BATCH_SIZE,
    out: Out = print,
) -> Optional[dict]:
    """
    Runbook step 3, one-shot (marker "0004_backfill" = T1).

    For every user with legacy rows: select-or-insert the "Inbox" project, move
    their MAIN jobs created up to T1 into it in batches of `batch_size` ids
    (one COMMIT per batch, so no long lock), and bind their API keys created up
    to T1 to it. Returns a summary, or None when the marker already exists.
    """
    if get_marker(bind, MARKER_BACKFILL) is not None:
        out(f"Backfill: marker {MARKER_BACKFILL} already present, skipping")
        return None

    t1 = now or _utcnow()
    with _connection(bind) as conn:
        users = _users_to_backfill(conn, t1)
    summary = {"t1": t1, "users": 0, "jobs": 0, "api_keys": 0}

    for user_id in users:
        inbox_id = select_or_insert_inbox(bind, user_id, t1)
        summary["users"] += 1
        while True:
            with _tx(bind) as conn:
                ids = [r[0] for r in conn.execute(
                    select(_jobs.c.id)
                    .where(_main_jobs_without_project(t1), _jobs.c.user_id == user_id)
                    .order_by(_jobs.c.id)
                    .limit(batch_size)
                )]
                if not ids:
                    break
                conn.execute(
                    _jobs.update()
                    .where(_jobs.c.id.in_(ids), _jobs.c.project_id.is_(None))
                    .values(project_id=inbox_id)
                )
            summary["jobs"] += len(ids)
        with _tx(bind) as conn:
            result = conn.execute(
                _keys.update()
                .where(_keys.c.user_id == user_id, _keys_without_project(t1))
                .values(project_id=inbox_id)
            )
            summary["api_keys"] += result.rowcount or 0

    try:
        with _tx(bind) as conn:
            _insert_marker(conn, MARKER_BACKFILL, t1)
    except IntegrityError:
        out(f"Backfill: marker {MARKER_BACKFILL} written concurrently")

    out(
        f"Backfill: T1={t1.isoformat()} users={summary['users']} "
        f"jobs={summary['jobs']} api_keys={summary['api_keys']}"
    )
    keys = bound_inbox_keys(bind)
    if keys:
        out("API keys bound to Inbox (re-bind the ones that deserve their own project):")
        for k in keys:
            out(f"  user={k['username']}  key={k['name']!r}  last_used_at={k['last_used_at']}  id={k['id']}")
    return summary


# ---------------------------------------------------------------------------
# Boot (runbook step 5)
# ---------------------------------------------------------------------------

def boot_schema_guard(engine: Engine) -> str:
    """
    Step 5a. Runs in api/main.py BEFORE init_db and OUTSIDE the try that
    swallows its errors, whatever ENVIRONMENT says.

    Returns:
        "unreachable" - database down: behave as before (log and carry on);
        "empty"       - no `jobs` table (dev, CI, fresh install): create_all
                        creates everything, then `mark_fresh_database`;
        "ok"          - migrated.

    Raises:
        SystemExit(1): `jobs` exists but the 0004 columns, `app_migrations` or
        the "0004_backfill" marker are missing. Starting would make every query
        on jobs fail (or leave legacy jobs without a project).
    """
    try:
        snap = schema_snapshot(engine)
    except (OperationalError, InterfaceError) as e:
        logger.error(f"Schema guard: database unreachable ({e}); continuing as before")
        return "unreachable"

    if "jobs" not in snap["tables"]:
        logger.info("Schema guard: empty database, create_all will build the 0004 schema")
        return "empty"

    missing = []
    for table, cols in REQUIRED_COLUMNS.items():
        present = snap["columns"].get(table, set())
        missing += [f"{table}.{c}" for c in cols if c not in present]
    if "app_migrations" not in snap["tables"]:
        missing.append("table app_migrations")
    else:
        try:
            if get_marker(engine, MARKER_BACKFILL) is None:
                missing.append(f"marker {MARKER_BACKFILL}")
        except (OperationalError, InterfaceError) as e:
            logger.error(f"Schema guard: could not read app_migrations ({e}); continuing as before")
            return "unreachable"

    if missing:
        logger.critical(
            "Schema guard: the database is not migrated for spec 0004 (missing: "
            f"{', '.join(missing)}). Refusing to start.\n{RUNBOOK_HINT}"
        )
        raise SystemExit(1)
    return "ok"


def run_tail(engine: Engine, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Step 5b, one-shot, in ONE transaction: insert marker "0004_tail" (T2) and
    move every MAIN job / API key still without a project and created up to T2
    to its owner's Inbox. No lower bound T1: created_at is set in Python before
    the INSERT commits, so a late job of the old code may predate T1.

    A concurrent boot blocks on the marker's primary key and gets an
    IntegrityError once the first one commits: it skips. Returns a summary, or
    None when skipped.
    """
    if get_marker(engine, MARKER_TAIL) is not None:
        return None
    t2 = now or _utcnow()
    for _attempt in range(2):
        try:
            with engine.begin() as conn:
                _insert_marker(conn, MARKER_TAIL, t2)
                summary = {"t2": t2, "users": 0, "jobs": 0, "api_keys": 0}
                for user_id in _users_to_backfill(conn, t2):
                    inbox_id = _find_inbox(conn, user_id, lock=True) or _insert_inbox(conn, user_id, t2)
                    summary["users"] += 1
                    summary["jobs"] += conn.execute(
                        _jobs.update()
                        .where(_main_jobs_without_project(t2), _jobs.c.user_id == user_id)
                        .values(project_id=inbox_id)
                    ).rowcount or 0
                    summary["api_keys"] += conn.execute(
                        _keys.update()
                        .where(_keys.c.user_id == user_id, _keys_without_project(t2))
                        .values(project_id=inbox_id)
                    ).rowcount or 0
            if summary["jobs"] or summary["api_keys"]:
                logger.warning(
                    f"Spec 0004 tail backfill: {summary['jobs']} jobs and {summary['api_keys']} "
                    f"API keys of {summary['users']} users moved to Inbox (T2={t2.isoformat()})"
                )
            else:
                logger.info(f"Spec 0004 tail backfill: nothing to move (T2={t2.isoformat()})")
            return summary
        except IntegrityError:
            if get_marker(engine, MARKER_TAIL) is not None:
                return None  # another process did it
            # an Inbox created concurrently: the whole transaction rolled back; once more
    raise MigrationAborted("Spec 0004 tail backfill could not complete")


def check_invariant(engine: Engine) -> int:
    """
    Step 5c, every boot, read-only: MAIN jobs without a project created after
    T2 are a bug. Logged as ERROR, never fixed here.
    """
    t2 = get_marker(engine, MARKER_TAIL)
    if t2 is None:
        return 0
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(_jobs).where(
                _jobs.c.project_id.is_(None), _jobs.c.job_type == "MAIN", _jobs.c.created_at > t2,
            )
        ).scalar() or 0
    if count:
        logger.error(f"Invariant violated: {count} MAIN jobs without a project created after {t2.isoformat()}")
    return count


def finish_boot_migration(engine: Engine, fresh: bool) -> None:
    """Steps after create_all: fresh markers (empty database), tail, invariant."""
    if fresh:
        mark_fresh_database(engine)
    run_tail(engine)
    check_invariant(engine)


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade(bind, out: Out = print) -> None:
    """
    Remove the index, columns, tables and markers of spec 0004. Jobs and keys
    are kept; only their organisation is lost. The old code ignores all of it,
    so this is never needed for a code rollback.
    """
    snap = schema_snapshot(bind)
    mysql = is_mysql(bind)
    wait = f" WAIT {LOCK_WAIT_SECONDS}" if mysql else ""
    statements = []
    if JOBS_PROJECT_INDEX in snap["jobs_indexes"]:
        statements.append(
            f"DROP INDEX {JOBS_PROJECT_INDEX} ON jobs{wait}" if mysql else f"DROP INDEX {JOBS_PROJECT_INDEX}"
        )
    for table, cols in REQUIRED_COLUMNS.items():
        present = [c for c in cols if c in snap["columns"].get(table, set())]
        if not present:
            continue
        if mysql:
            statements.append(f"ALTER TABLE {table}{wait} " + ", ".join(f"DROP COLUMN {c}" for c in present))
        else:
            statements += [f"ALTER TABLE {table} DROP COLUMN {c}" for c in present]

    with _connection(bind) as conn:
        if mysql:
            conn.exec_driver_sql(f"SET SESSION lock_wait_timeout = {LOCK_WAIT_SECONDS}")
        for sql in statements:
            conn.exec_driver_sql(sql)
            out(f"OK   {sql}")
        for table in (Folder.__table__, Project.__table__):
            if table.name in snap["tables"]:
                table.drop(conn)
                out(f"OK   DROP TABLE {table.name}")
        if "app_migrations" in snap["tables"]:
            conn.execute(_markers.delete().where(_markers.c.name.in_([MARKER_BACKFILL, MARKER_TAIL])))
            if conn.execute(select(func.count()).select_from(_markers)).scalar() == 0:
                _markers.drop(conn)
                out("OK   DROP TABLE app_migrations")
            else:
                out("OK   markers 0004_* removed (app_migrations kept: other markers)")
        if isinstance(bind, Engine):
            conn.commit()
