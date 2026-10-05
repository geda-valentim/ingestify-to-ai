"""engine_feature_state.workers_seen_at: last live local worker seen by the dispatcher (spec 0003, slice 3b)

Revision ID: 5d2e8f1a6c47
Revises: b3e1c0d9a7f2
Create Date: 2026-10-05 12:00:00.000000

Installs that rely on create_all at startup get the column from
shared.database._ADDED_COLUMNS instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '5d2e8f1a6c47'
down_revision: Union[str, Sequence[str], None] = 'b3e1c0d9a7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('engine_feature_state', sa.Column(
        'workers_seen_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('engine_feature_state', 'workers_seen_at')
