"""Repeatable additive upgrade of durable image runs for facial providers."""
from sqlalchemy import inspect, text


def migrate(bind):
    additions = {
        'image_analysis_runs': {
            'profile': "VARCHAR(30) NOT NULL DEFAULT 'image-full-v1'",
            'calls_by_provider': 'JSON',
            'faces_resolved': 'BOOLEAN NOT NULL DEFAULT 0',
        },
        'image_analysis_steps': {
            'step_kind': "VARCHAR(20) NOT NULL DEFAULT 'florence'",
            'provider': "VARCHAR(30) NOT NULL DEFAULT 'florence'",
        },
    }
    for table, columns in additions.items():
        existing = {c['name'] for c in inspect(bind).get_columns(table)}
        for name, ddl in columns.items():
            if name not in existing:
                bind.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
    bind.execute(text("UPDATE image_analysis_runs SET calls_by_provider = '{}' WHERE calls_by_provider IS NULL"))
    if bind.dialect.name in ('mysql', 'mariadb'):
        bind.execute(text('ALTER TABLE image_analysis_runs MODIFY COLUMN calls_by_provider JSON NOT NULL'))

