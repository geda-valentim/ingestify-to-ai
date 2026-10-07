#!/usr/bin/env python3
"""Create the snapshot table without ALTERs or changing legacy Alembic stamps."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from shared.database import engine
from shared.models import JobDatalakePartition

if __name__ == '__main__':
    JobDatalakePartition.__table__.create(engine, checkfirst=True)
    print('Datalake partition snapshot table ready; existing jobs keep their original paths.')
