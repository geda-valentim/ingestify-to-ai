import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=settings.sql_echo,  # SQL_ECHO=true to debug (logs parameters, e.g. password hashes)
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session.

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables.
    Called during app startup.
    """
    from shared.models import User, APIKey, Job, Page  # Import models to register them
    from sqlalchemy import inspect
    existing = "jobs" in inspect(engine).get_table_names()
    # Existing deployments use the explicit 0005 migration. Disabled live must
    # not introduce DDL or require its table on a routine API restart.
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if not (
            existing
            and (
                table.name == "live_sessions"
                or table.name.startswith("engine_control_")
                or table.name.startswith("engine_operation")
                or table.name == "engine_runtime_profiles"
                or table.name.startswith("access_")
                or table.name.startswith("execution_profile")
                or table.name.startswith("iam_")
            )
        )
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    if settings.engine_control_enabled:
        from shared.engine_control.migration import TABLES
        missing={table.name for table in TABLES}-set(inspect(engine).get_table_names())
        if missing:
            raise RuntimeError('Engine control requires the explicit 0007 migration before enabling it')
    _add_missing_columns()
    if settings.engine_control_enabled:
        # The additive runtime columns are used even when delegated access is off.
        from shared.access.migration import RUNTIME_COLUMNS as COLUMNS

        inspector = inspect(engine)
        if any(
            not set(columns).issubset({c["name"] for c in inspector.get_columns(table)})
            for table, columns in COLUMNS.items()
        ):
            raise RuntimeError(
                "Engine control requires the additive 0009 migration for this release"
            )
    if settings.engine_access_enabled:
        from shared.access.migration import validate_schema

        validate_schema(engine)
    # Engine grants live in iam_bindings since spec 0018: engine access needs the
    # IAM schema too. Reconciliation runs on every boot, only ever restricts, and
    # brings back revocations the pre-0018 code made during a rollback (§4.2.3).
    from shared.iam.migration import reconcile_on_boot, validate_schema as validate_iam_schema

    reconcile_on_boot(engine)
    if settings.iam_mode != "off" or settings.engine_access_enabled:
        validate_iam_schema(engine)

    # The built-in local engine (spec 0003): this server's workers, no bindings until declared
    from shared.engines.store import ensure_local_engine, ensure_lease_row
    with SessionLocal() as db:
        ensure_local_engine(db)
        ensure_lease_row(db)


# Columns added to existing tables after they were first created. create_all() only
# creates missing tables, so existing databases need these ALTERs (otherwise every
# query on the model fails with "Unknown column"). Plain ADD COLUMN works on both
# MySQL and MariaDB. Keep in sync with backend/migrations/*.sql.
_ADDED_COLUMNS = {
    "jobs": {
        "crawler_config": "JSON NULL",  # migrations/002_add_crawler_fields.sql
        "crawler_schedule": "JSON NULL",
        # alembic b8f20022e1c4: source-file / dedup bookkeeping, out of JobConfiguration.options
        "purge_source": "BOOLEAN NULL",
        "source_deleted_at": "DATETIME NULL",
        "operation_key": "VARCHAR(64) NULL",
    },
    "engine_feature_state": {
        "workers_seen_at": "DATETIME(6) NULL",  # alembic 5d2e8f1a6c47 (spec 0003, slice 3b)
    },
    "users": {
        "root_slot": "SMALLINT NULL",  # alembic f1c90019d3e4 (spec 0019); unique index below
    },
    "image_analysis_submissions": {
        "attempt": "INTEGER NOT NULL DEFAULT 1",  # alembic a7d30021c5e9 (attempt per Idempotency-Key)
    },
}

# Unique indexes on _ADDED_COLUMNS, created separately: SQLite cannot ADD COLUMN ... UNIQUE.
_ADDED_UNIQUE_INDEXES = {
    "uq_users_root_slot": ("users", "root_slot"),  # at most one root user (spec 0019)
    # one row per page of a split PDF (alembic b8f20022e1c4)
    "uq_pages_job_page": ("pages", "job_id, page_number"),
}


def duplicate_page_rows(conn) -> list:
    """
    Page rows that repeat a (job_id, page_number) already present: an old split
    retry added a second row per page. The row kept per page is the COMPLETED one,
    else the most recently updated. Returns the ids of the others.
    """
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT p.id, p.job_id, p.page_number, p.status, p.updated_at FROM pages p "
        "JOIN (SELECT job_id, page_number FROM pages GROUP BY job_id, page_number HAVING COUNT(*) > 1) d "
        "ON d.job_id = p.job_id AND d.page_number = p.page_number"
    )).fetchall()
    groups: dict = {}
    for row in rows:
        groups.setdefault((row.job_id, row.page_number), []).append(row)
    extra = []
    for group in groups.values():
        group.sort(key=lambda r: (str(r.status).upper().endswith("COMPLETED"), str(r.updated_at or "")),
                   reverse=True)
        extra.extend(r.id for r in group[1:])
    return extra


def _add_missing_columns(bind=None) -> None:
    """Add columns from _ADDED_COLUMNS that an existing table does not have yet"""
    from sqlalchemy import inspect, text

    bind = bind or engine
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    with bind.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for column, ddl in columns.items():
                if column not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        for name, (table, column) in _ADDED_UNIQUE_INDEXES.items():
            if table not in existing_tables:
                continue
            indexes = {i["name"] for i in inspector.get_indexes(table)}
            indexes |= {u["name"] for u in inspector.get_unique_constraints(table)}
            if name not in indexes:
                if name == "uq_pages_job_page" and duplicate_page_rows(conn):
                    # Never delete rows at boot: the alembic migration cleans them up
                    logger.warning("pages has duplicate (job_id, page_number) rows: run "
                                   "`alembic upgrade head` to add uq_pages_job_page")
                    continue
                conn.execute(text(f"CREATE UNIQUE INDEX {name} ON {table} ({column})"))
