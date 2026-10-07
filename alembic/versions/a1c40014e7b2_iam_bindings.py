"""IAM bindings for platform roles (spec 0014)."""

from alembic import op
from shared.iam import migration

revision = "a1c40014e7b2"
# Linearized after main's image full analysis + face migrations (merge of #48).
down_revision = "02c6000ce6e5"
branch_labels = None
depends_on = None


def upgrade():
    migration.upgrade(op.get_bind())


def downgrade():
    migration.downgrade(op.get_bind())
