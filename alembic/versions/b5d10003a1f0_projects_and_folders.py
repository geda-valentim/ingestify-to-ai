"""projects and folders (spec 0004)

Revision ID: b5d10003a1f0
Revises: 5d2e8f1a6c47
Create Date: 2026-10-01 12:00:00.000000

FORBIDDEN IN PRODUCTION. Production is not stamped (docs/CODE_REVIEW.md
§ 11.2): `alembic upgrade head` there would try to re-apply e399267560a7,
7c2f4a1d9b30 and the engines revisions b3e1c0d9a7f2/5d2e8f1a6c47 (whose tables
and column production got from create_all/_ADDED_COLUMNS) and fail.
Production runs scripts/migrate_0004_projects.py directly. This revision only exists so dev databases managed by Alembic
converge; it calls the very same functions (shared/migration_0004.py).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5d10003a1f0'
down_revision: Union[str, Sequence[str], None] = '5d2e8f1a6c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: DDL (idempotent) + one-shot backfill."""
    from shared.migration_0004 import apply_ddl, backfill

    bind = op.get_bind()
    apply_ddl(bind)
    backfill(bind)


def downgrade() -> None:
    """Downgrade schema: index, columns, tables and markers of spec 0004."""
    from shared.migration_0004 import downgrade as downgrade_0004

    downgrade_0004(op.get_bind())
