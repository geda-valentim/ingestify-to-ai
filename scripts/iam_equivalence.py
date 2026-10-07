#!/usr/bin/env python3
"""
Offline equivalence of the legacy and IAM data decisions (spec 0014 CA3).

Walks every (user, job / project / folder / API key) pair of a database and
compares the pre-0014 owner rule with `shared.iam.decide` for read, update and
delete. Prints each divergence and exits 1 if there is any (0 clean, 2 could not
run). A clean run against the dev snapshot is the gate for IAM_MODE=enforce
(0014 §4.11 step 3).

Usage:
    python scripts/iam_equivalence.py --db-url mysql+pymysql://user:pass@host/ingestify
    python scripts/iam_equivalence.py            # DATABASE_URL of the settings
    python scripts/iam_equivalence.py --user <id> --user <id>

The logic lives in `backend/shared/iam/equivalence.py`, which CI runs against the
SQLite fixture of `backend/tests/test_iam_equivalence.py`.
"""

import sys
from pathlib import Path

# Add project root and backend/ to path (backend modules import as `shared.*`),
# so this works from the repo root and inside the api container (WORKDIR /app).
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from shared.iam.equivalence import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
