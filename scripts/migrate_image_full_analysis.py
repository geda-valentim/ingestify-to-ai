#!/usr/bin/env python3
"""Apply the additive full-image schema before restarting API and workers."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from shared.database import engine
from shared.image_analysis_migration import migrate

if __name__ == '__main__':
    with engine.begin() as connection:
        migrate(connection)
    print('Full image analysis schema ready; existing single-task jobs preserved.')
