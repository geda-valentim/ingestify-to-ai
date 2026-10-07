#!/usr/bin/env python3
"""
Promote an existing user to administrator (is_admin = True)

Admin endpoints (/admin/*) are restricted to administrators. Since there is no
HTTP endpoint to grant that flag (on purpose), the first administrator must be
bootstrapped from the server / container shell with this script.

Usage:
    python scripts/make_admin.py --email alice@example.com
    python scripts/make_admin.py --id 3f1c9a2e-...
    python scripts/make_admin.py --email alice@example.com --root

--root (spec 0019) also makes the user the installation's root user, for
installations that had users before root existed. It refuses when a root already
exists: root is never replaced by this script. New installations do not need it:
the first registered account becomes root. Designating root also seeds the default
execution profiles (spec 0020; scripts/seed_execution_profiles.py runs it again).

The user is identified by email or id only - never by username, which anyone can
choose at registration (a username like "alice@example.com" would otherwise be
mistaken for that email). The script shows who it found and asks to confirm;
pass --yes to skip the question in automation.

Inside Docker:
    docker compose exec api python scripts/make_admin.py --email alice@example.com

Requires the same DATABASE_URL environment the API uses
(see backend/shared/config.py).
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root and backend/ to path (backend modules import as `shared.*`)
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

# Import as `shared.*` so this works both from the repo root (backend/ is on
# sys.path above) and inside the api container, where WORKDIR is /app and
# shared/ sits at the top level.
from shared.admin import AdminPromotionError, find_user_to_promote
from shared.database import SessionLocal
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("make_admin")


def make_admin(email=None, user_id=None, assume_yes=False, as_root=False) -> int:
    """Set is_admin = True (and, with as_root, root) for the user named by email or id"""
    db = SessionLocal()

    try:
        try:
            user = find_user_to_promote(db, email=email, user_id=user_id)
        except AdminPromotionError as e:
            print(f"\n❌ {e}")
            return 1

        print(f"\n   id:       {user.id}")
        print(f"   username: {user.username}")
        print(f"   email:    {user.email}")

        if as_root:
            from shared.root import root_exists

            if root_exists(db):
                print("\n❌ This installation already has a root user; it is never replaced.")
                return 1
            if not user.is_active:
                print("\n❌ This user is inactive; root must be an active account.")
                return 1
        elif user.is_admin:
            print("\n✅ Already an admin.")
            return 0

        if not assume_yes:
            if not sys.stdin.isatty():
                print("\n❌ Not a terminal: pass --yes to confirm.")
                return 1
            question = "Make this user the installation's root?" if as_root else "Promote this user to admin?"
            if input(f"\n{question} [y/N] ").strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 1

        from shared.access import policy

        if policy.enabled():
            authority = policy.epoch(db, True)
            from shared.models import User, AdminAudit

            user = (
                db.query(User)
                .filter_by(id=user.id)
                .populate_existing()
                .with_for_update()
                .one()
            )
            authority.version += 1
            db.add(
                AdminAudit(
                    actor_user_id="installation:make_admin",
                    auth_method="cli",
                    action="access.bootstrap_promoted",
                    target_type="user",
                    target_id=user.id,
                )
            )
        user.is_admin = True
        if as_root:
            from shared.models import ROOT_SLOT, AdminAudit

            user.root_slot = ROOT_SLOT  # the unique index refuses a concurrent second root
            db.add(
                AdminAudit(
                    actor_user_id="installation:make_admin",
                    auth_method="cli",
                    action="platform.root.designated",
                    target_type="user",
                    target_id=user.id,
                )
            )
        db.commit()
        logger.warning(
            f"[ADMIN] User {user.id} ({user.email}) promoted to {'root' if as_root else 'admin'} by make_admin.py"
        )

        print("\n✅ Promoted. They can now access the /admin/* endpoints.")
        if as_root:
            # Spec 0020: the new root creates the default execution profiles (best effort)
            from shared.access.seed import seed_quietly

            report = seed_quietly(db, user.id, "make_admin --root")
            if report is not None:
                print("\n" + report.summary())
        return 0

    except IntegrityError:
        db.rollback()
        print("\n❌ Another user became root at the same time; root is never replaced.")
        return 1

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

    parser = argparse.ArgumentParser(description="Promote an existing user to administrator.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--email", help="the user's email address")
    target.add_argument("--id", dest="user_id", help="the user's id")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--root", dest="as_root", action="store_true",
                        help="also make the user root, only when the installation has none (spec 0019)")
    args = parser.parse_args()

    sys.exit(make_admin(email=args.email, user_id=args.user_id, assume_yes=args.yes, as_root=args.as_root))


if __name__ == "__main__":
    main()
