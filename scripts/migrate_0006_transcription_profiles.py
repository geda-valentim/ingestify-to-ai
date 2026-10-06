#!/usr/bin/env python3
"""Explicit additive migration for durable transcription profiles (spec 0006).

PYTHONPATH=backend python scripts/migrate_0006_transcription_profiles.py
Drain profiled jobs before --downgrade. Existing results are never rewritten.
"""
import argparse
from sqlalchemy import inspect, text

COLUMNS = {'transcription_profile': 'JSON NULL',
           'transcription_profile_hash': 'VARCHAR(64) NULL',
           'transcript_attempt_id': 'VARCHAR(36) NULL'}
INDEX = 'ix_jobs_transcription_profile_hash'


def migrate(bind, downgrade=False):
    if 'jobs' not in inspect(bind).get_table_names():
        raise RuntimeError('The jobs schema must exist before migration 0006')
    with bind.begin() as conn:
        columns = {column['name'] for column in inspect(conn).get_columns('jobs')}
        indexes = {index['name'] for index in inspect(conn).get_indexes('jobs')}
        if downgrade:
            if 'transcription_profile' in columns:
                active = conn.execute(text("SELECT id FROM jobs WHERE transcription_profile IS NOT NULL "
                                           "AND lower(status) NOT IN ('completed','failed','cancelled','skipped') LIMIT 1")).first()
                if active:
                    raise RuntimeError('Drain or cancel profiled jobs before downgrade')
            if INDEX in indexes:
                suffix = ' ON jobs' if bind.dialect.name in ('mysql', 'mariadb') else ''
                conn.execute(text(f'DROP INDEX {INDEX}{suffix}'))
            for name in reversed(COLUMNS):
                if name in columns:
                    conn.execute(text(f'ALTER TABLE jobs DROP COLUMN {name}'))
        else:
            for name, definition in COLUMNS.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE jobs ADD COLUMN {name} {definition}'))
            if INDEX not in indexes:
                conn.execute(text(f'CREATE INDEX {INDEX} ON jobs (transcription_profile_hash)'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downgrade', action='store_true')
    args = parser.parse_args()
    from shared.database import engine
    migrate(engine, args.downgrade)
    print('0006 transcription profiles migration complete')
