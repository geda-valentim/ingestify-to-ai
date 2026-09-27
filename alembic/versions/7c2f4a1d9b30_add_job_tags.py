"""add job_tags

Revision ID: 7c2f4a1d9b30
Revises: e399267560a7
Create Date: 2026-09-25 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2f4a1d9b30'
down_revision: Union[str, Sequence[str], None] = 'e399267560a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_tags',
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('tag', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id', 'tag'),
    )
    op.create_index('ix_job_tags_tag', 'job_tags', ['tag'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_job_tags_tag', table_name='job_tags')
    op.drop_table('job_tags')
