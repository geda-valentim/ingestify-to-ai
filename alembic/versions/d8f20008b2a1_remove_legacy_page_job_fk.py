"""Remove the obsolete FK to Redis-only PAGE jobs.

Legacy installations use scripts/migrate_page_jobs.py without changing their
Alembic stamp or applying unrelated revisions.
"""
from alembic import op

revision = "d8f20008b2a1"
down_revision = "c7e10007a1f0"
branch_labels = None
depends_on = None


def upgrade():
    from shared.migration_page_jobs import upgrade as migrate
    migrate(op.get_bind())


def downgrade():
    # Restoring the FK would invalidate every PAGE job created by the worker.
    raise RuntimeError("PAGE jobs have no jobs row; the legacy FK cannot be restored safely")
