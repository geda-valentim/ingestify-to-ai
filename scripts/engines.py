#!/usr/bin/env python3
"""
Manage execution engines (spec 0003) from the server shell.

    python scripts/engines.py keygen
        Print a new key pair for sealing engine credentials. The public key goes
        to ENGINE_SECRETS_PUBLIC_KEY (api, CLI); the private key ONLY to the
        worker-remote service (ENGINE_SECRETS_PRIVATE_KEYS[_FILE]).

    python scripts/engines.py import-env [--prefix MODAL_ACCOUNT_] [--limit-usd 30] [--apply] < accounts.env
        Import Modal accounts given as {prefix}{N}_NAME / _ID / _SECRET (N = 1..19)
        on standard input - e.g. another project's .env. Engines are created or
        updated by slug (modal_{N}), always PAUSED, with credentials sealed to the
        public key. Without --apply nothing is written: it only shows the plan.

    python scripts/engines.py import-modal-toml [--path ~/.modal.toml] [--limit-usd 30] [--apply]
        Same, from the profiles of a Modal CLI config file.

Inside Docker (the API container has the database and the public key):
    docker compose exec -T api python scripts/engines.py import-env < /path/to/.env
    docker compose exec -T api python scripts/engines.py import-env --apply < /path/to/.env

Secrets are never printed, logged or put in the environment; only the last four
characters of a token id are shown.
"""

import argparse
import io
import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from shared.engines.importer import accounts_from_env, accounts_from_modal_toml, plan_and_apply  # noqa: E402
from shared.engines.redact import install_log_redaction  # noqa: E402
from shared.engines.sealing import SealingError, generate_keypair  # noqa: E402

install_log_redaction()


def _print_plan(rows: list, applied: bool) -> None:
    print(f"\n{'slug':<10} {'token id':<10} {'limit':>8}  action / name")
    for r in rows:
        limit = f"{float(r['limit_usd']):.2f}" if r["limit_usd"] is not None else "-"
        print(f"{r['slug']:<10} {r['token_id']:<10} {limit:>8}  {r['action']:<22} {r['name']}")
    if applied:
        print("\n✅ Applied. Engines are PAUSED: nothing runs on them until an admin activates them.")
    else:
        print("\nDry run: nothing was written. Re-run with --apply to import.")


def _import(accounts: list, limit_usd: Optional[float], apply: bool) -> int:
    from shared.config import get_settings
    from shared.database import SessionLocal

    if not accounts:
        print("No accounts found.")
        return 1
    public_key = get_settings().engine_secrets_public_key
    if apply and not public_key:
        print("❌ ENGINE_SECRETS_PUBLIC_KEY is not set: run `keygen` and configure it first.")
        return 1

    db = SessionLocal()
    try:
        rows = plan_and_apply(db, accounts, public_key, limit_usd, apply)
    except SealingError as e:
        db.rollback()
        print(f"❌ {e}")
        return 1
    finally:
        db.close()
    _print_plan(rows, apply)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage Ingestify execution engines (spec 0003).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="print a new key pair for sealing engine credentials")

    env = sub.add_parser("import-env", help="import Modal accounts from env lines on stdin")
    env.add_argument("--prefix", default="MODAL_ACCOUNT_")
    env.add_argument("--limit-usd", type=float, help="monthly ceiling to set on each imported account")
    env.add_argument("--apply", action="store_true", help="write; without it only the plan is shown")

    toml = sub.add_parser("import-modal-toml", help="import Modal accounts from a Modal CLI config")
    toml.add_argument("--path", default=str(Path.home() / ".modal.toml"))
    toml.add_argument("--limit-usd", type=float)
    toml.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "keygen":
        public, private = generate_keypair()
        print("# Public key: set on the api service (and wherever the CLI runs)")
        print(f"ENGINE_SECRETS_PUBLIC_KEY={public}")
        print("# Private key: ONLY for worker-remote, preferably as a file (ENGINE_SECRETS_PRIVATE_KEYS_FILE)")
        print(f"ENGINE_SECRETS_PRIVATE_KEYS={private}")
        return 0

    if args.command == "import-env":
        if sys.stdin.isatty():
            print("Pipe the env lines on stdin, e.g. `... import-env < accounts.env`.")
            return 1
        from dotenv import dotenv_values

        values = dotenv_values(stream=io.StringIO(sys.stdin.read()))  # parsed, never exported to os.environ
        return _import(accounts_from_env(values, args.prefix), args.limit_usd, args.apply)

    if args.command == "import-modal-toml":
        return _import(accounts_from_modal_toml(Path(args.path).read_text()), args.limit_usd, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())
