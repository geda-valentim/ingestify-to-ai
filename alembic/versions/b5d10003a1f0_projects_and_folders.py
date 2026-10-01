"""projects and folders (spec 0003)

Revision ID: b5d10003a1f0
Revises: 7c2f4a1d9b30
Create Date: 2026-10-01 12:00:00.000000

FORBIDDEN IN PRODUCTION. Production is not stamped (docs/CODE_REVIEW.md
§ 11.2): `alembic upgrade head` there would try to re-apply e399267560a7 and
7c2f4a1d9b30 and fail. Production runs scripts/migrate_0003_projects.py
directly. This revision only exists so dev databases managed by Alembic
converge; it calls the very same functions (shared/migration_0003.py).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5d10003a1f0'
down_revision: Union[str, Sequence[str], None] = '7c2f4a1d9b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: DDL (idempotent) + one-shot backfill."""
    from shared.migration_0003 import apply_ddl, backfill

    bind = op.get_bind()
    apply_ddl(bind)
    backfill(bind)


def downgrade() -> None:
    """Downgrade schema: index, columns, tables and markers of spec 0003."""
    from shared.migration_0003 import downgrade as downgrade_0003

    downgrade_0003(op.get_bind())
