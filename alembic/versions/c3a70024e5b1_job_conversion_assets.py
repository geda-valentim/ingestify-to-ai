"""jobs image-asset columns of a document conversion.

- jobs.assets_manifest: the durable list of extracted pictures / page renders
  (image_mode=referenced, page_images=true) and the skipped counts;
- jobs.assets_expire_at: when the periodic beat deletes them (purge_source=true,
  ASSET_RETENTION_SECONDS after the job settled);
- jobs.assets_deleted_at: when they were deleted (GET /jobs/{id}/assets/{name}
  then answers 410 SOURCE_PURGED).

Additive; every column is skipped when already present (fresh databases get them
from Base.metadata.create_all, existing ones may have been upgraded at boot by
shared.database._add_missing_columns).
"""

from alembic import op
import sqlalchemy as sa

revision = "c3a70024e5b1"
down_revision = "b8f20022e1c4"
branch_labels = None
depends_on = None

COLUMNS = (
    ("assets_manifest", sa.JSON()),
    ("assets_expire_at", sa.DateTime()),
    ("assets_deleted_at", sa.DateTime()),
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
