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

    python scripts/engines.py list
    python scripts/engines.py set-gpus gpu0:16:RTX5060Ti[:GPU-uuid]
    python scripts/engines.py set-capacity local transcription --workers 2 --gpu-ref gpu0
    python scripts/engines.py set-capacity modal_1 transcription --workers 2 --gpu-type L4
        Inspect engines, declare the local GPUs, and set how each feature runs on
        an engine. Changes are validated against VRAM (summed over every feature on a
        shared local GPU) and audited.

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


def _manage(args) -> int:
    import json

    from shared.config import get_settings
    from shared.database import SessionLocal
    from shared.engines.capacity import Binding, CapacityError
    from shared.engines.store import VersionConflict, engine_view, ensure_local_engine, set_binding, set_local_gpus
    from shared.models import Engine

    vision_model_id = get_settings().vision_model_id
    db = SessionLocal()
    try:
        ensure_local_engine(db)
        if args.command == "list":
            views = [engine_view(db, e, alive_by_feature=_alive(), vision_model_id=vision_model_id)
                     for e in db.query(Engine).order_by(Engine.is_system.desc(), Engine.slug)]
            if args.json:
                print(json.dumps(views, indent=1, default=str))
                return 0
            for v in views:
                limit = v["budget"]["limit_usd"]
                print(f"\n{v['slug']:<10} {v['adapter_type']:<6} {v['status']:<7} limit={limit if limit is not None else '-'}")
                for feature, f in v["features"].items():
                    alive = f" alive={f['workers_alive']}/{f['workers_configured']}" if "workers_alive" in f else ""
                    print(f"  {feature:<20} {f['binding']} capacity={f['capacity']} in_flight={f['in_flight']}"
                          f" {f['deploy_state']}{alive}")
                for g in v["gpu_budget"]:
                    print(f"  VRAM {g['gpu']}: {g['budgeted_gb']} of {g['vram_gb']} GB ({' + '.join(g['terms']) or 'unused'})")
                if v["config_error"]:
                    print(f"  ⚠ {v['config_error']['message']}")
            return 0

        engine = db.query(Engine).filter(Engine.slug == getattr(args, "engine", "local")).first()
        if engine is None:
            print(f"❌ No engine {getattr(args, 'engine', 'local')!r}")
            return 1
        if args.command == "set-capacity":
            binding = None
            if not args.remove:
                if args.workers is None:
                    print("❌ --workers is required (or --remove)")
                    return 1
                binding = Binding(workers=args.workers, executions_per_worker=args.executions_per_worker,
                                  gpu_type=args.gpu_type, gpu_ref=args.gpu_ref, cpu=args.cpu,
                                  vram_override_gb=args.vram_override_gb)
            set_binding(db, engine, args.feature, binding, version=None, actor_user_id=None, auth_method="cli",
                        vision_model_id=vision_model_id)
        else:
            declared = []
            for spec in args.gpu:
                parts = spec.split(":")
                declared.append({"ref": parts[0], "vram_gb": float(parts[1]),
                                 "name": parts[2] if len(parts) > 2 else "",
                                 "uuid": parts[3] if len(parts) > 3 else None,
                                 "vram_reserve_gb": args.reserve_gb})
            set_local_gpus(db, engine, declared, version=None, actor_user_id=None, auth_method="cli",
                           vision_model_id=vision_model_id)
        print(f"✅ {engine.slug} updated (version {engine.version}). Run `list` to see capacity and VRAM.")
        return 0
    except CapacityError as e:
        print(f"❌ {e}")
        for line in e.lines:
            print(f"   {line}")
        return 1
    except (VersionConflict, ValueError) as e:
        print(f"❌ {e}")
        return 1
    finally:
        db.close()


def _alive() -> dict:
    try:
        from shared.engines.features import FEATURES
        from shared.engines.liveness import alive
        from shared.redis_client import get_redis_client

        client = get_redis_client().client
        return {f: alive(f, client) for f in FEATURES}
    except Exception:
        return {}


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

    show = sub.add_parser("list", help="engines, their capacity and VRAM budget")
    show.add_argument("--json", action="store_true")

    cap = sub.add_parser("set-capacity", help="set how a feature runs on an engine")
    cap.add_argument("engine", help="slug, e.g. local or modal_1")
    cap.add_argument("feature", help="transcription | document_conversion | vision")
    cap.add_argument("--workers", type=int, help="Modal containers, or local replicas (declared)")
    cap.add_argument("--executions-per-worker", type=int, default=1)
    cap.add_argument("--gpu-type", help="remote: e.g. L4, T4, A10G")
    cap.add_argument("--gpu-ref", help="local: a declared GPU (see set-gpus); omit for CPU work")
    cap.add_argument("--cpu", type=float)
    cap.add_argument("--vram-override-gb", type=float)
    cap.add_argument("--remove", action="store_true", help="stop running this feature on the engine")

    gpus = sub.add_parser("set-gpus", help="declare the local engine's physical GPUs")
    gpus.add_argument("gpu", nargs="+", help="ref:vram_gb[:name[:uuid]], e.g. gpu0:16:RTX5060Ti:GPU-1234")
    gpus.add_argument("--reserve-gb", type=float, default=1.0)

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

    if args.command in ("list", "set-capacity", "set-gpus"):
        return _manage(args)

    if args.command == "import-modal-toml":
        return _import(accounts_from_modal_toml(Path(args.path).read_text()), args.limit_usd, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())
