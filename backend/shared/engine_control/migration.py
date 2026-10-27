"""Explicit idempotent 0007 DDL, independent of legacy Alembic stamping."""

from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn
from shared.engine_control import models
from shared.database import Base

TABLES = [
    t
    for t in Base.metadata.sorted_tables
    if t.name.startswith("engine_control_")
    or t.name.startswith("engine_operation")
    or t.name == "engine_runtime_profiles"
]


@contextmanager
def _bounded_metadata_lock(connection, seconds=30):
    """MySQL/MariaDB DDL on an existing table waits for an exclusive metadata lock behind any
    open transaction that touched it, and every later read/write of that table (admission
    tickets: every task) queues behind the DDL. Give up after `seconds` instead of the server
    default (a year in MySQL 8): the rerun is idempotent. Set on THIS connection, restored
    before it goes back to the pool."""
    if connection.dialect.name not in ("mysql", "mariadb"):
        yield
        return
    connection.execute(text(f"SET SESSION lock_wait_timeout = {int(seconds)}"))
    try:
        yield
    finally:
        connection.execute(text("SET SESSION lock_wait_timeout = @@GLOBAL.lock_wait_timeout"))


def _upgrade(connection):
    Base.metadata.create_all(connection, tables=TABLES)
    with _bounded_metadata_lock(connection):
        _alter_existing_tables(connection)


def _alter_existing_tables(connection):
    # Early opt-in installations already created this table. create_all does
    # not add columns or indexes to it; retain its operations and resource gates.
    resource = models.ControlResource.__table__
    column = resource.c.maintenance_operation_id
    present = {c["name"] for c in inspect(connection).get_columns(resource.name)}
    if column.name not in present:
        definition = str(CreateColumn(column).compile(dialect=connection.dialect))
        connection.execute(
            text(f"ALTER TABLE {resource.name} ADD COLUMN {definition}")
        )
    for index in resource.indexes:
        if column.name in index.columns:
            index.create(connection, checkfirst=True)
    # Indexes added to tables that already exist (create_all skips them): additive. InnoDB
    # builds a secondary index online, after a brief exclusive metadata lock (bounded above).
    for index in models.ControlAdmission.__table__.indexes:
        index.create(connection, checkfirst=True)


def upgrade(bind):
    if isinstance(bind, Engine):
        with bind.begin() as connection:
            _upgrade(connection)
    else:
        # Alembic supplies a connection with its transaction already open.
        _upgrade(bind)


def downgrade(bind):
    from sqlalchemy import text

    present = set(inspect(bind).get_table_names())
    with bind.connect() as conn:
        if (
            "engine_operations" in present
            and conn.execute(
                text(
                    "SELECT count(*) FROM engine_operations WHERE state NOT IN ('succeeded','failed','cancelled') OR reserved_usd > 0"
                )
            ).scalar()
        ):
            raise RuntimeError(
                "Active/uncertain operations or financial exposure prevent downgrade"
            )
        if (
            "engine_control_resources" in present
            and conn.execute(
                text(
                    "SELECT count(*) FROM engine_control_resources WHERE operation_id IS NOT NULL OR gate_closed = 1"
                )
            ).scalar()
        ):
            raise RuntimeError(
                "Resources still controlled; reconcile and disable writers first"
            )
    raise RuntimeError(
        "Audit retained: export/archive control tables before explicit removal"
    )
