"""jobs describe-stage columns of describe_images / ocr_images.

- jobs.figures_stage: "describing" while a conversion's figures go through the
  vision worker, "finishing" between the COMPLETED commit and the steps after it,
  NULL otherwise;
- jobs.figures_stage_at: the stage's heartbeat (a figure dispatched, started or
  settled). The stuck-job monitor reads it instead of started_at, and the beat
  sweep finds stalled stages by it.

Additive; every column is skipped when already present (fresh databases get them
from Base.metadata.create_all, existing ones may have been upgraded at boot by
shared.database._add_missing_columns).
"""

from alembic import op
import sqlalchemy as sa

revision = "d4b80025f6c2"
down_revision = "c3a70024e5b1"
branch_labels = None
depends_on = None

COLUMNS = (
    ("figures_stage", sa.String(16)),
    ("figures_stage_at", sa.DateTime()),
)


def _columns():
    inspector = sa.inspect(op.get_bind())
    if "jobs" not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns("jobs")}


def upgrade():
    columns = _columns()
    if columns is None:
        return
    for name, type_ in COLUMNS:
        if name not in columns:
            op.add_column("jobs", sa.Column(name, type_, nullable=True))


def downgrade():
    columns = _columns()
    present = [name for name, _ in COLUMNS if columns is not None and name in columns]
    if not present:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("jobs", recreate="always") as batch:
            for name in present:
                batch.drop_column(name)
        return
    for name in present:
        op.drop_column("jobs", name)
