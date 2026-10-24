"""jobs completion-webhook columns.

- jobs.callback_url: where the terminal event of a MAIN job is POSTed (shared/webhooks.py);
- jobs.webhook_state: the latest delivery {delivery_id, event, status, attempts, ...}.

Additive; every column is skipped when already present (fresh databases get them
from Base.metadata.create_all, existing ones may have been upgraded at boot by
shared.database._add_missing_columns).
"""

from alembic import op
import sqlalchemy as sa

revision = "e5c90026a7d3"
down_revision = "d4b80025f6c2"
branch_labels = None
depends_on = None

COLUMNS = (
    ("callback_url", sa.String(2048)),
    ("webhook_state", sa.JSON()),
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
