"""Explicit, repeatable migration for full image analysis."""
from sqlalchemy import Enum, inspect, text
from shared.models import ImageAnalysisRun, ImageAnalysisStep, ImageAnalysisSubmission


def migrate(bind):
    inspector = inspect(bind)
    if bind.dialect.name in ('mysql', 'mariadb') and 'jobs' in inspector.get_table_names():
        status = next(c for c in inspector.get_columns('jobs') if c['name'] == 'status')
        values = list(status['type'].enums)
        if 'PARTIAL' not in values:
            ddl = Enum(*values, 'PARTIAL').compile(dialect=bind.dialect)
            bind.execute(text(f'ALTER TABLE jobs MODIFY COLUMN status {ddl} NOT NULL'))
    for model in (ImageAnalysisRun, ImageAnalysisStep, ImageAnalysisSubmission):
        model.__table__.create(bind, checkfirst=True)
