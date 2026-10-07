"""
Explicit, additive 0014 migration: only `CREATE TABLE iam_bindings` (spec 0014 §4.8).

Applied like 0009 (alembic revision calling `upgrade`), and recorded as the marker
`0014_iam_bindings` in `app_migrations`. No pre-existing row is touched. Reversible
with `downgrade` (DROP TABLE) once `IAM_MODE=off`.
"""

from datetime import datetime

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from shared.config import get_settings
from shared.database import Base
from shared import models  # register the complete FK graph (users)

MARKER = "0014_iam_bindings"
TABLES = [t for t in Base.metadata.sorted_tables if t.name.startswith("iam_")]
_markers = models.AppMigration.__table__


def _upgrade(conn):
    if "users" not in set(inspect(conn).get_table_names()):
        raise RuntimeError("Apply the base schema before the 0014 IAM migration")
    _markers.create(conn, checkfirst=True)
    Base.metadata.create_all(conn, tables=TABLES)
    for table in TABLES:
        for index in table.indexes:
            index.create(conn, checkfirst=True)
    if conn.execute(_markers.select().where(_markers.c.name == MARKER)).first() is None:
        conn.execute(_markers.insert().values(name=MARKER, applied_at=datetime.utcnow()))


def upgrade(bind):
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            _upgrade(conn)
    else:
        _upgrade(bind)


def validate_schema(bind):
    if not {t.name for t in TABLES}.issubset(inspect(bind).get_table_names()):
        raise RuntimeError("IAM_MODE requires the explicit 0014 migration")


def _downgrade(conn):
    if get_settings().iam_mode != "off":
        raise RuntimeError("Set IAM_MODE=off before dropping iam_bindings")
    for table in reversed(TABLES):
        table.drop(conn, checkfirst=True)
    if "app_migrations" in set(inspect(conn).get_table_names()):
        conn.execute(_markers.delete().where(_markers.c.name == MARKER))


def downgrade(bind):
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            _downgrade(conn)
    else:
        _downgrade(bind)
