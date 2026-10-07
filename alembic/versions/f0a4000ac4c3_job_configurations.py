"""Persist job requests independently of cache and queue retention."""
from alembic import op

revision = 'f0a4000ac4c3'
down_revision = 'e9a30009c3b2'
branch_labels = None
depends_on = None


def upgrade():
    from shared.models import JobConfiguration
    JobConfiguration.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    from shared.models import JobConfiguration
    JobConfiguration.__table__.drop(op.get_bind(), checkfirst=True)
