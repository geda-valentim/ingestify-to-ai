"""Facial providers and bounded recovery counters for image analysis."""
from alembic import op
from sqlalchemy import text

revision = '02c6000ce6e5'
down_revision = '01b5000bd5d4'
branch_labels = None
depends_on = None


def upgrade():
    from shared.face_analysis_migration import migrate
    migrate(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if bind.execute(text("SELECT COUNT(*) FROM image_analysis_runs WHERE profile <> 'image-full-v1'")).scalar():
        raise RuntimeError('Retain/remove facial and v2 runs before downgrade')
    with op.batch_alter_table('image_analysis_steps') as batch:
        batch.drop_column('provider')
        batch.drop_column('step_kind')
    with op.batch_alter_table('image_analysis_runs') as batch:
        batch.drop_column('faces_resolved')
        batch.drop_column('calls_by_provider')
        batch.drop_column('profile')
