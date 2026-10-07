"""Explicit, additive migration. Never infer execution or consumer qualification."""

from sqlalchemy import inspect, text, Column
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn
from shared.database import Base
from shared import models  # register the complete FK graph

TABLES = [
    t
    for t in Base.metadata.sorted_tables
    if t.name.startswith(("access_", "execution_profile"))
]
RUNTIME_COLUMNS = {
    "engine_runtime_profiles": ("source_profile_revision_id", "source_hash"),
    "engine_operations": ("cancel_requested_by", "recovery_requested_by"),
}
COLUMNS = dict(
    RUNTIME_COLUMNS,
    access_effect_admissions=("action", "targets", "decision", "valid_until"),
)


def _upgrade(conn):
    existing = set(inspect(conn).get_table_names())
    if not set(RUNTIME_COLUMNS).issubset(existing):
        raise RuntimeError("Apply the explicit 0007 engine-control migration first")
    Base.metadata.create_all(conn, tables=TABLES)
    for name, columns in COLUMNS.items():
        table = Base.metadata.tables[name]
        present = {c["name"] for c in inspect(conn).get_columns(name)}
        for name_ in columns:
            if name_ not in present:
                column = table.c[name_]
                # Earlier opt-in schemas retain their admissions. Missing metadata
                # is unknown; add nullable, then backfill only neutral defaults.
                added = Column(column.name, column.type, nullable=True)
                ddl = str(CreateColumn(added).compile(dialect=conn.dialect))
                conn.execute(text(f"ALTER TABLE {name} ADD COLUMN {ddl}"))
        for index in table.indexes:
            if any(c.name in columns for c in index.columns):
                index.create(conn, checkfirst=True)
    admission = Base.metadata.tables["access_effect_admissions"]
    for field, value in [("action", "effect"), ("targets", []), ("decision", {})]:
        conn.execute(
            admission.update()
            .where(admission.c[field].is_(None))
            .values({field: value})
        )
    if (
        conn.execute(
            text("SELECT count(*) FROM access_authorization_epoch WHERE id=1")
        ).scalar()
        == 0
    ):
        conn.execute(
            text("INSERT INTO access_authorization_epoch (id,version) VALUES (1,0)")
        )


def upgrade(bind):
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            _upgrade(conn)
    else:
        _upgrade(bind)


def validate_schema(bind):
    inspector = inspect(bind)
    if not {t.name for t in TABLES}.issubset(inspector.get_table_names()):
        raise RuntimeError("Execution profiles require the explicit 0009 migration")
    for table, columns in COLUMNS.items():
        if not set(columns).issubset({c["name"] for c in inspector.get_columns(table)}):
            raise RuntimeError("Execution profiles require the explicit 0009 migration")
    with bind.connect() as conn:
        if not conn.execute(
            text("SELECT count(*) FROM access_authorization_epoch WHERE id=1")
        ).scalar():
            raise RuntimeError("0009 authorization epoch is missing")


def downgrade(bind):
    raise RuntimeError(
        "Audit, grants and profile history are retained. Disable ENGINE_ACCESS_ENABLED to roll back access."
    )
