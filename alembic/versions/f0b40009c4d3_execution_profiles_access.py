"""Execution profiles and scoped access (spec 0009)."""

from alembic import op
from shared.access import migration

revision = "f0b40009c4d3"
down_revision = "c7e10007a1f0"
branch_labels = None
depends_on = None


def upgrade():
    migration.upgrade(op.get_bind())


def downgrade():
    migration.downgrade(op.get_bind())
