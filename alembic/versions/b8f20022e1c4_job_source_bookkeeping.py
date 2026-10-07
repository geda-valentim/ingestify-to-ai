"""jobs source-file / dedup bookkeeping columns; one Page row per (job, page number).

- jobs.purge_source, jobs.source_deleted_at, jobs.operation_key: what
  purge_source and dedup record about a job. They used to be written into
  JobConfiguration.options, the *requested* configuration shown to the user.
- uq_pages_job_page: a split retry reuses the job's Page rows instead of adding a
  second, forever-PENDING row per page. Existing duplicates are removed first,
  keeping per page the COMPLETED row, else the most recently updated
  (shared.database.duplicate_page_rows).

Additive; every step is skipped when already present (fresh databases get them from
Base.metadata.create_all, existing ones may have been upgraded at boot by
shared.database._add_missing_columns, which adds the columns and, when there are no
duplicates, the index).
"""

from alembic import op
import sqlalchemy as sa

revision = "b8f20022e1c4"
down_revision = "a7d30021c5e9"
branch_labels = None
depends_on = None

INDEX = "uq_pages_job_page"
COLUMNS = (
    ("purge_source", sa.Boolean()),
    ("source_deleted_at", sa.DateTime()),
    ("operation_key", sa.String(64)),
)


def _state():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    columns = {c["name"] for c in inspector.get_columns("jobs")} if "jobs" in tables else None
    indexes = constraints = None
    if "pages" in tables:
        indexes = {i["name"] for i in inspector.get_indexes("pages")}
        constraints = {u["name"] for u in inspector.get_unique_constraints("pages")}
    return columns, indexes, constraints


def upgrade():
    from shared.database import duplicate_page_rows

    columns, indexes, constraints = _state()
    if columns is not None:
        for name, type_ in COLUMNS:
            if name not in columns:
                op.add_column("jobs", sa.Column(name, type_, nullable=True))
    if indexes is not None and INDEX not in indexes | constraints:
        bind = op.get_bind()
        extra = duplicate_page_rows(bind)
        for start in range(0, len(extra), 500):
            bind.execute(sa.text("DELETE FROM pages WHERE id IN :ids")
                         .bindparams(sa.bindparam("ids", expanding=True)),
                         {"ids": extra[start:start + 500]})
        op.create_index(INDEX, "pages", ["job_id", "page_number"], unique=True)


def downgrade():
    columns, indexes, constraints = _state()
    sqlite = op.get_bind().dialect.name == "sqlite"
    if indexes is not None and INDEX in indexes | constraints:
        if sqlite:
            # SQLite cannot drop an inline constraint in place: rebuild the table.
            # create_all makes the uniqueness an inline constraint; the upgrade, an index.
            with op.batch_alter_table("pages", recreate="always") as batch:
                if INDEX in constraints:
                    batch.drop_constraint(INDEX, type_="unique")
                else:
                    batch.drop_index(INDEX)
        else:
            op.drop_index(INDEX, table_name="pages")
    present = [name for name, _ in COLUMNS if columns is not None and name in columns]
    if not present:
        return
    if sqlite:
        with op.batch_alter_table("jobs", recreate="always") as batch:
            for name in present:
                batch.drop_column(name)
        return
    for name in present:
        op.drop_column("jobs", name)
