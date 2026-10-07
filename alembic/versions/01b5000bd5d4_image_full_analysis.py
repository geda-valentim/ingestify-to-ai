"""Durable image full-analysis runs, steps and idempotent submissions."""
from alembic import op
from sqlalchemy import text

revision = '01b5000bd5d4'
down_revision = 'f0b40009c4d3'
branch_labels = None
depends_on = None


def upgrade():
    from shared.image_analysis_migration import migrate
    from shared.models import JobConfiguration, DatalakeConnection, JobDatalakeExport, JobDatalakePartition
    bind = op.get_bind()
    for model in (JobConfiguration, DatalakeConnection, JobDatalakeExport, JobDatalakePartition):
        model.__table__.create(bind, checkfirst=True)
    migrate(bind)


def downgrade():
    from shared.models import ImageAnalysisRun, ImageAnalysisStep, ImageAnalysisSubmission
    bind = op.get_bind()
    if bind.execute(text('SELECT COUNT(*) FROM image_analysis_runs')).scalar():
        raise RuntimeError('Drain and retain full analyses before downgrade')
    for model in (ImageAnalysisStep, ImageAnalysisRun, ImageAnalysisSubmission):
        model.__table__.drop(bind, checkfirst=True)
