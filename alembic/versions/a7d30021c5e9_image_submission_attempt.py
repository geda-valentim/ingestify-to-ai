"""image_analysis_submissions.attempt: one Idempotency-Key, several attempts.

A FAILED job no longer pins its Idempotency-Key: the same key starts attempt+1
(a new job) and the row's job_id moves to it by compare-and-set on
(id, attempt, job_id). Additive: existing rows are attempt 1. Skipped when the
column is already there (fresh databases get it from Base.metadata.create_all,
existing ones may have been upgraded at boot by shared.database._add_missing_columns).
"""

from alembic import op
import sqlalchemy as sa

revision = "a7d30021c5e9"
down_revision = "f1c90019d3e4"
branch_labels = None
depends_on = None

TABLE = "image_analysis_submissions"


def _columns():
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade():
    columns = _columns()
    if columns is not None and "attempt" not in columns:
        op.add_column(TABLE, sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    columns = _columns()
    if columns is None or "attempt" not in columns:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            batch.drop_column("attempt")
        return
    op.drop_column(TABLE, "attempt")
