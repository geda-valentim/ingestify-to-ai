#!/usr/bin/env python3
"""
Spec 0003 (projects and folders) - the ONLY migration path in production.

Run it with the OLD code still deployed (DDL first), from a checkout of the NEW
code that is NOT the directory bind-mounted into the containers: the new
models must not reach the running workers before the columns exist.

Steps (stops at the first FAIL):
  0  pre-flight: server version (MariaDB 10.11), users.id collation, transcription
     volume per hour over the last 7 days (to pick the quietest window), long
     InnoDB transactions (> 30 s)
  1  DDL: app_migrations/projects/folders tables, jobs.project_id/folder_id,
     api_keys.project_id (ALGORITHM=INSTANT, WAIT 5, up to 5 retries 30 s apart),
     index ix_jobs_user_type_project_folder (INPLACE, LOCK=NONE)
  2  code pre-flight: every column/table/index present -> OK / FAIL
  3  one-shot backfill (marker 0003_backfill): per-user "Inbox", legacy MAIN jobs
     in batches of 1000 ids, API keys bound; prints the keys bound to Inbox

Usage (see docs/runbooks/0003-projects-migration.md):
    python scripts/migrate_0003_projects.py --database-url mysql+pymysql://USER:PASS@HOST:3306/ingestify
    python scripts/migrate_0003_projects.py --check          # steps 0 and 2 only, no writes
    python scripts/migrate_0003_projects.py --downgrade      # remove index, columns, tables, markers

DATABASE_URL from the environment is used when --database-url is not given.
`alembic upgrade` is forbidden in production (not stamped; see spec 0003 § 4.3).
"""

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if BACKEND_DIR.is_dir():
    sys.path.insert(0, str(BACKEND_DIR))

EXPECTED_SERVER = ("MariaDB", "10.11.")
EXPECTED_USERS_COLLATION = "utf8mb4_general_ci"


def _prepare_environment(database_url):
    """
    shared.config validates secrets this script never uses (JWT, MinIO) at
    import time. Process-local placeholders keep it importable outside the API
    container; they sign nothing and reach nothing.
    """
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("JWT_SECRET_KEY", "migrate-0003-script-placeholder-never-signs-anything")
    os.environ.setdefault("MINIO_ACCESS_KEY", "migrate-0003-unused")
    os.environ.setdefault("MINIO_SECRET_KEY", "migrate-0003-unused-placeholder")


def _ok(msg):
    print(f"OK   {msg}")


def _fail(msg):
    print(f"FAIL {msg}")
    return 1


def preflight(engine, allow_long_transactions=False, skip_version_check=False):
    """Step 0. Returns 0 when everything is OK, 1 otherwise."""
    from sqlalchemy import text

    from shared.migration_0003 import is_mysql, long_transactions

    print("== 0. Pre-flight")
    if not is_mysql(engine):
        _ok(f"dialect {engine.dialect.name}: MariaDB-only checks skipped")
        return 0

    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar() or ""
        # a) server version
        if EXPECTED_SERVER[0].lower() in version.lower() and version.startswith(EXPECTED_SERVER[1]):
            _ok(f"server {version}")
        elif skip_version_check:
            print(f"WARN server {version} (expected MariaDB {EXPECTED_SERVER[1]}x) - check skipped")
        else:
            return _fail(f"server {version}; expected MariaDB {EXPECTED_SERVER[1]}x. "
                         "Stop: this runbook was written for MariaDB 10.11.")

        # FKs of projects/folders -> users need the same charset/collation as users.id
        collation = conn.execute(text(
            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'"
        )).scalar()
        if collation == EXPECTED_USERS_COLLATION:
            _ok(f"users.id collation {collation}")
        else:
            return _fail(f"users.id collation is {collation!r}, the new tables use "
                         f"{EXPECTED_USERS_COLLATION}: the FOREIGN KEYs to users would fail. Stop.")

        # d) quietest hour of the audio client (UTC), from the jobs it created
        rows = conn.execute(text(
            "SELECT HOUR(created_at) AS h, COUNT(*) AS n FROM jobs "
            "WHERE source_type = 'audio' AND job_type = 'MAIN' "
            "AND created_at >= UTC_TIMESTAMP() - INTERVAL 7 DAY GROUP BY HOUR(created_at)"
        )).all()
    per_hour = {int(h): int(n) for h, n in rows}
    print("     transcriptions per hour (UTC, last 7 days):")
    peak = max(per_hour.values(), default=0) or 1
    for hour in range(24):
        n = per_hour.get(hour, 0)
        print(f"       {hour:02d}h {n:6d} {'#' * round(40 * n / peak)}")

    # c) owner action, never verified by the script
    print("WARN 0c (owner action): check the API logs for callers of /upload, /convert, /transcribe,\n"
          "     /images without X-API-Key (e.g. meumentor-api); bind a key for them or set\n"
          "     UPLOAD_FALLBACK_PROJECT before deploying the new code.")

    # e) long transactions would make the ALTERs wait (and everything queue behind them)
    trx = long_transactions(engine, 30)
    if trx:
        for t in trx:
            print(f"     open: {t}")
        if not allow_long_transactions:
            return _fail(f"{len(trx)} InnoDB transactions open for more than 30 s. Wait, or pause the "
                         "queues (docker compose stop worker worker-audio), or pass "
                         "--allow-long-transactions.")
        print(f"WARN {len(trx)} long transactions (allowed by flag)")
    else:
        _ok("no InnoDB transaction open for more than 30 s")
    return 0


def code_preflight(engine):
    """Step 2. Returns 0 when the new code can be deployed."""
    from shared.migration_0003 import missing_schema

    print("== 2. Code pre-flight")
    missing = missing_schema(engine)
    if missing:
        for item in missing:
            print(f"FAIL missing {item}")
        return 1
    _ok("all spec 0003 tables, columns and the index are present")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", help="SQLAlchemy URL (default: $DATABASE_URL)")
    parser.add_argument("--check", action="store_true", help="steps 0 and 2 only; writes nothing")
    parser.add_argument("--downgrade", action="store_true", help="remove index, columns, tables and markers")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--allow-long-transactions", action="store_true")
    parser.add_argument("--skip-version-check", action="store_true", help="dev databases only")
    parser.add_argument("--retry-interval", type=float, default=None,
                        help="seconds between DDL lock-timeout retries (default 30)")
    args = parser.parse_args(argv)

    _prepare_environment(args.database_url)
    from shared.database import engine
    from shared.migration_0003 import (
        DDL_RETRY_INTERVAL_SECONDS,
        MigrationAborted,
        apply_ddl,
        backfill,
        downgrade,
    )

    print(f"Database: {engine.url.render_as_string(hide_password=True)}")

    if args.downgrade:
        if not args.yes and input("Remove the spec 0003 schema (organisation is lost)? [y/N] ").lower() != "y":
            print("Aborted.")
            return 1
        downgrade(engine)
        return 0

    if preflight(engine, args.allow_long_transactions, args.skip_version_check):
        return 1

    if args.check:
        code_preflight(engine)
        return 0

    if not args.yes and input("Apply step 1 (DDL) and step 3 (backfill) now? [y/N] ").lower() != "y":
        print("Aborted.")
        return 1

    print("== 1. DDL")
    try:
        interval = DDL_RETRY_INTERVAL_SECONDS if args.retry_interval is None else args.retry_interval
        apply_ddl(engine, interval=interval)
    except MigrationAborted as e:
        return _fail(str(e))

    if code_preflight(engine):
        return 1

    print("== 3. Backfill")
    backfill(engine)
    print("Done. Next: deploy the new code (api + workers + frontend); the API finishes the tail at boot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
