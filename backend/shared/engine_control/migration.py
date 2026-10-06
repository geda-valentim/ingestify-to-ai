"""Explicit idempotent 0007 DDL, independent of legacy Alembic stamping."""

from sqlalchemy import inspect
from shared.engine_control import models
from shared.database import Base

TABLES = [
    t
    for t in Base.metadata.sorted_tables
    if t.name.startswith("engine_control_")
    or t.name.startswith("engine_operation")
    or t.name == "engine_runtime_profiles"
]


def upgrade(bind):
    Base.metadata.create_all(bind, tables=TABLES)


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
