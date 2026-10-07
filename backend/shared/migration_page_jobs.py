"""Align legacy pages with PAGE jobs that live in Redis, not the jobs table."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade(bind):
    """Drop only the obsolete page_job_id FK; keep the MAIN ownership FK.

    Standalone migrations must also work on installations whose Alembic stamp
    predates tables provisioned by create_all. Inspect names instead of assuming
    MySQL's generated constraint name. Fresh schemas already need no change.
    """
    if isinstance(bind, Engine):
        with bind.begin() as connection:
            return upgrade(connection)

    inspector = inspect(bind)
    if not inspector.has_table("pages"):
        return []
    obsolete = [fk for fk in inspector.get_foreign_keys("pages")
                if fk["constrained_columns"] == ["page_job_id"]
                and fk["referred_table"] == "jobs"]
    if not obsolete:
        return []

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    if bind.dialect.name in ("mysql", "mariadb"):
        bind.execute(text("SET SESSION lock_wait_timeout = 5"))
    operations = Operations(MigrationContext.configure(bind))
    with operations.batch_alter_table("pages") as batch:
        for fk in obsolete:
            batch.drop_constraint(fk["name"], type_="foreignkey")
    return [fk["name"] for fk in obsolete]
