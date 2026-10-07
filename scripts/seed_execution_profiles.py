#!/usr/bin/env python3
"""
Create the installation's default execution profiles (spec 0020).

As the root user: a published "Padrão — <model>" profile for every approved catalog
model, a published "<engine> — <feature>" profile reproducing each configured
engine/feature, and - best effort - the binding of each engine profile to an
engine/feature that has no runtime profile yet. Never plans, deploys, warms or
reserves anything. Safe to run again: existing seeded profiles are reused.

The API runs the same seeding on every boot once a root exists, and when the root
is created; run this after registering a host agent or configuring a new engine
to pick them up without a restart.

Usage:
    python scripts/seed_execution_profiles.py --dry-run   # show the plan only
    python scripts/seed_execution_profiles.py             # apply
    python scripts/seed_execution_profiles.py --json      # report as JSON

Inside Docker:
    docker compose exec api python scripts/seed_execution_profiles.py --dry-run
    docker compose exec api python -m shared.access.seed --dry-run   # same, no rebuild

Requires the same DATABASE_URL environment the API uses, and IAM_MODE=enforce
(the profile library is closed while engine access is off).
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from shared.access.seed import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
