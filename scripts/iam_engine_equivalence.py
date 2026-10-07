#!/usr/bin/env python3
"""
Offline equivalence of the 0009 engine decisions, access_role_grants vs
iam_bindings (spec 0018 CA4).

Runs `policy.authorize` over a request matrix, `navigation`, `visible_catalog`,
`scoped_query` and `_delegator` for every user, once over a frozen copy of the
pre-0018 grant reader (access_role_grants) and once over iam_bindings, and prints
each divergence. Exits 1 if there is any (0 clean, 2 could not run). A clean run
against the dev snapshot, after the 0018 migration, is the gate before deploy.

Usage:
    python scripts/iam_engine_equivalence.py --db-url mysql+pymysql://user:pass@host/ingestify
    python scripts/iam_engine_equivalence.py            # DATABASE_URL of the settings
    python scripts/iam_engine_equivalence.py --user <id> --user <id>

The logic lives in `backend/shared/iam/engine_equivalence.py`, which CI runs
against the SQLite fixtures of `backend/tests/test_iam_engine_equivalence.py`.
"""

import sys
from pathlib import Path

# Add project root and backend/ to path (backend modules import as `shared.*`),
# so this works from the repo root and inside the api container (WORKDIR /app).
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from shared.iam.engine_equivalence import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
