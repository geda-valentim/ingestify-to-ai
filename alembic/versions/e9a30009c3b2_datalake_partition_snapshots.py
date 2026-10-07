"""Immutable partition layout snapshots without altering existing export rows."""
from alembic import op

revision = 'e9a30009c3b2'
down_revision = 'd8f20008b2a1'
branch_labels = None
depends_on = None


def upgrade():
    from shared.models import JobDatalakePartition
    JobDatalakePartition.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    # Removing snapshots changes retry destinations. Preserve data until an
    # operator explicitly archives exports and disables their delivery.
    raise RuntimeError('Archive partition snapshots and disable delivery before removing this table')
