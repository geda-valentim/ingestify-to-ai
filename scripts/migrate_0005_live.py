#!/usr/bin/env python3
"""Explicit migration for live sessions. Never called by the API boot path.

Run in the configured backend environment after backup:
  PYTHONPATH=backend python scripts/migrate_0005_live.py [--downgrade]
Existing jobs/results are retained on downgrade; active sessions prohibit it.
"""
import argparse
from sqlalchemy import inspect, select
from shared.database import engine
from shared.models import LiveSession


def migrate(bind, downgrade=False):
    table = LiveSession.__table__
    if downgrade:
        if table.name not in inspect(bind).get_table_names():
            return
        with bind.connect() as conn:
            active = conn.execute(select(table.c.job_id).where(
                table.c.state.notin_(['completed', 'failed', 'cancelled']))).first()
            if active:
                raise RuntimeError('Drain or cancel live sessions before downgrade')
        table.drop(bind)
    else:
        if 'jobs' not in inspect(bind).get_table_names():
            raise RuntimeError('The jobs schema must exist before migration 0005')
        table.create(bind, checkfirst=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downgrade', action='store_true')
    args = parser.parse_args()
    migrate(engine, args.downgrade)
    print('0005 live_sessions migration complete')
