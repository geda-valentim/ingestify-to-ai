#!/usr/bin/env python3
"""
Promote an existing user to administrator (is_admin = True)

Admin endpoints (/admin/*) are restricted to users with is_admin = True.
Since there is no HTTP endpoint to grant that flag (on purpose), the first
administrator must be bootstrapped from the server / container shell with
this script.

Usage:
    python scripts/make_admin.py <username-or-email>

Examples:
    python scripts/make_admin.py alice
    python scripts/make_admin.py alice@example.com

Inside Docker:
    docker compose exec api python scripts/make_admin.py alice@example.com

Requires the same DATABASE_URL environment the API uses
(see backend/shared/config.py).
"""

import sys
from pathlib import Path

# Add project root and backend/ to path (backend modules import as `shared.*`)
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

# Import as `shared.*` so this works both from the repo root (backend/ is on
# sys.path above) and inside the api container, where WORKDIR is /app and
# shared/ sits at the top level.
from shared.database import SessionLocal
from shared.models import User


def make_admin(identifier: str) -> int:
    """Set is_admin = True for the user matching username or email"""
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.username == identifier).first()

        if not user:
            user = db.query(User).filter(User.email == identifier).first()

        if not user:
            print(f"\n❌ User not found: {identifier}")
            print("   Pass an existing username or email address.")
            return 1

        if user.is_admin:
            print(f"\n✅ User '{user.username}' ({user.email}) is already an admin.")
            return 0

        user.is_admin = True
        db.commit()

        print(f"\n✅ User '{user.username}' ({user.email}) is now an admin.")
        print("   They can now access the /admin/* endpoints.")
        return 0

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error promoting user: {e}")
        print("\nPlease check:")
        print("  1. MySQL is running and reachable")
        print("  2. Migrations are applied (alembic upgrade head)")
        return 1

    finally:
        db.close()


def main():
    print("=" * 60)
    print("Ingestify - Grant Admin Privileges")
    print("=" * 60)

    if len(sys.argv) != 2:
        print("\nUsage: python scripts/make_admin.py <username-or-email>")
        sys.exit(1)

    sys.exit(make_admin(sys.argv[1]))


if __name__ == "__main__":
    main()
