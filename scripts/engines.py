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

    python scripts/engines.py routes show [--json]
    python scripts/engines.py routes set transcription --step local [--step "modal_1,modal_2 fill_first min_wait=600"]
        [--max-attempts 3] [--fallback local_direct|hold] [--on-no-engine hold|fail --fail-after 3600]
    python scripts/engines.py routes set document_conversion --step local
    python scripts/engines.py routes set vision --step local
    python scripts/engines.py routes delete transcription
        Feature routes (spec 0003): with a route, the feature's items queue in the
        backlog and the dispatcher (worker-dispatch, compose profile `engines`)
        places them step by step - transcription per job, document_conversion per
        PDF page; vision is placed inline by the API (no backlog). Deleting a route
        drains its backlog back to the default path. A remote step needs its engines
        active and deployed, and a running worker-remote; document_conversion and
        vision take local steps only.

    python scripts/engines.py budget modal_1 --limit-usd 30 [--min-remaining-usd 0.5] [--tz UTC] [--anchor-day 1]
    python scripts/engines.py activate modal_1 | pause modal_1
        A remote engine's ceiling per period, and its lifecycle. Activation needs a
        passing `test`, a budget, a verified deploy and executions_per_worker=1.

  Remote engines (spec 0003, slice 4a) - run these in worker-remote, the only
  service holding the private keys:
    docker compose --profile engines run --rm worker-remote python scripts/engines.py ...

    python scripts/engines.py modal-lock
        Regenerate backend/workers/engines/modal_apps/requirements-whisper-modal.lock
        (every pin with sha256 hashes) with `uv pip compile`. Talks to PyPI only.

    python scripts/engines.py test --engine modal_1 [--spend]
        Open the engine's credentials and check them against Modal: auth,
        workspace, is the app deployed. Starts no container. --spend also reads the
        account's billing report for the current period (free).

    python scripts/engines.py modal-deploy --engine modal_1 [--feature transcription] [--dry-run] [--allow-unhashed]
        Build and deploy the Whisper app with the engine's binding, verify it with
        the CPU-only meta() function, and record the fingerprint on the engine.

  Several accounts (slice 4c), each in turn - one failing never stops the next:
    python scripts/engines.py modal-deploy --all [--dry-run]
    python scripts/engines.py test --all
    python scripts/engines.py reconcile [--engine modal_2]
        The last one reads the billing reports now (worker-remote also does it every
        10 min): keeps the larger figure, alerts at soft_pct and at exhaustion.

  Benchmark (slice 4b; Appendix H of the spec). Remote costs money: it prints the
  pessimistic estimate, asks for confirmation (or --yes), reserves --max-usd in the
  ledger and cuts each (gpu, E) at its share. Samples are paths inside the container
  (./tmp is /tmp/ingestify in worker-remote), optionally path:seconds:
    python scripts/engines.py benchmark --engine modal_1 --sample /tmp/ingestify/bench/a.mp3:240 \
        --gpus T4,L4,A10G --concurrency 1 --max-usd 0.30 [--plan] [--yes] [--apply]
    python scripts/engines.py benchmark --engine local --sample ./tmp/bench/a.mp3:240 --concurrency 1,2
        (local: prints the one-off container command that runs it next to the live workers)
    python scripts/engines.py speed [--engine modal_1]
        What the estimate uses per (engine, feature, gpu, E): learned from 50 rows on.

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


def _routes(args) -> int:
    import json

    from shared.database import SessionLocal
    from shared.engines import routing
    from shared.models import Engine, FeatureRoute

    db = SessionLocal()
    try:
        if args.action == "show":
            engines = {e.id: e for e in db.query(Engine)}
            routes = {r.feature: r for r in db.query(FeatureRoute)}
            views = [routing.describe(routes.get(f), engines, f) for f in routing.all_features()]
            if args.json:
                print(json.dumps(views, indent=1, default=str))
                return 0
            for v in views:
                if v["implicit"]:
                    print(f"{v['feature']:<20} no route: today's path")
                    continue
                print(f"{v['feature']:<20} {v['state']} v{v['version']} fallback={v['dispatcher_fallback']} "
                      f"max_attempts={v['max_attempts']} on_no_engine={v['on_no_engine']}")
                for s in v["steps"]:
                    slugs = ",".join(e["slug"] or e["id"] for e in s["engines"])
                    extra = " ".join(f"{k}={s[k]}" for k in ("when", "spend_cap", "scale_out_after_seconds") if s.get(k))
                    print(f"  {s['position']}. [{slugs}] {s['group_strategy']} {extra}")
            return 0
        if args.action == "set":
            spec = routing.RouteSpec(
                steps=[routing.parse_step(text) for text in args.step], max_attempts=args.max_attempts,
                dispatcher_fallback=args.fallback, on_no_engine=args.on_no_engine,
                fail_after_seconds=args.fail_after, remote_allowed_for=args.remote_allowed_for,
                user_period_limit_usd=args.user_limit_usd, remote_data_notice=args.remote_data_notice,
            )
            route, warnings = routing.put_route(db, args.feature, spec, version=None, actor_user_id=None,
                                                auth_method="cli")
            for w in warnings:
                print(f"⚠ {w}")
            print(f"✅ {args.feature} route saved (version {route.version}). Items now queue in the backlog; "
                  f"the dispatcher runs in worker-dispatch (docker compose --profile engines up -d worker-dispatch).")
            return 0
        routing.drain_route(db, args.feature, actor_user_id=None, auth_method="cli")
        print(f"✅ {args.feature} route is draining: its backlog returns to the default path, then it is removed.")
        return 0
    except (routing.RouteError, routing.VersionConflict, LookupError, ValueError) as e:
        db.rollback()
        print(f"❌ {e}")
        return 1
    finally:
        db.close()


def _lifecycle(args) -> int:
    from shared.database import SessionLocal
    from shared.engines import store
    from shared.models import Engine

    db = SessionLocal()
    try:
        engine = db.query(Engine).filter(Engine.slug == args.engine).first()
        if engine is None:
            print(f"❌ No engine {args.engine!r}")
            return 1
        if args.command == "budget":
            store.set_budget(db, engine, limit_usd=args.limit_usd, min_remaining_usd=args.min_remaining_usd,
                             soft_pct=args.soft_pct, period_tz=args.tz, period_anchor_day=args.anchor_day,
                             version=None, actor_user_id=None, auth_method="cli")
            print(f"✅ {engine.slug}: limit US$ {engine.limit_usd} per period "
                  f"(min remaining {engine.min_remaining_usd}, {engine.period_tz}, day {engine.period_anchor_day})")
            return 0
        fingerprint_of = None
        if engine.adapter_type != "local":
            from workers.engines.remote import expected_fingerprint as fingerprint_of
        store.set_status(db, engine, "active" if args.command == "activate" else "paused", version=None,
                         actor_user_id=None, auth_method="cli", fingerprint_of=fingerprint_of)
        print(f"✅ {engine.slug} is {engine.status}.")
        return 0
    except store.EngineStateError as e:
        db.rollback()
        print(f"❌ {e}")
        for problem in e.problems:
            print(f"   - {problem}")
        return 1
    finally:
        db.close()


def _remote(args) -> int:
    if args.command == "modal-lock":
        import subprocess

        from workers.engines.modal_apps.files import LOCK_FILE, REQUIREMENTS_IN
        command = ["uv", "pip", "compile", str(REQUIREMENTS_IN), "--generate-hashes", "--python-version", "3.13",
                   "--python-platform", "x86_64-manylinux_2_28", "--no-header", "-o", str(LOCK_FILE)]
        print("Running: " + " ".join(command))
        try:
            return subprocess.run(command, env={"PATH": __import__("os").environ.get("PATH", "/usr/bin:/bin"),
                                                "HOME": "/tmp", "LANG": "C.UTF-8"}).returncode
        except FileNotFoundError:
            print("❌ uv is not installed here (pip install uv), or run the same command on any machine with uv.")
            return 1

    if args.command == "modal-deploy":
        from workers.engines.modal_deploy import DeployError, deploy, deploy_all
        if args.all == bool(args.engine):
            print("❌ Pass --engine <slug> or --all")
            return 1
        if args.all:
            summary = deploy_all(args.feature, dry_run=args.dry_run, allow_unhashed=args.allow_unhashed)
            return 0 if summary and not any(v.startswith("FAILED") for v in summary.values()) else 1
        try:
            deploy(args.engine, args.feature, dry_run=args.dry_run, allow_unhashed=args.allow_unhashed)
            return 0
        except DeployError as e:
            print(f"❌ {e}")
            return 1

    if args.command == "reconcile":
        import json

        from workers.engines.remote_tasks import reconcile_now
        print(json.dumps(reconcile_now(only=args.engine), indent=1, default=str))
        return 0

    # test
    import json

    from workers.engines.remote_tasks import test_all_now, test_engine_now
    if args.all == bool(args.engine):
        print("❌ Pass --engine <slug> or --all")
        return 1
    if args.all:
        reports = test_all_now()
        for slug, report in reports.items():
            print(f"{slug:<12} {'ok' if report.get('ok') else report.get('code')}: {report.get('detail')}")
        return 0 if reports and all(r.get("ok") for r in reports.values()) else 1
    report = test_engine_now(args.engine)
    print(json.dumps(report, indent=1))
    if args.spend and report.get("ok"):
        from datetime import datetime

        from shared.database import SessionLocal
        from shared.engines import budget
        from shared.models import Engine
        from workers.engines import remote
        from workers.engines.remote_tasks import _next_period

        db = SessionLocal()
        try:
            engine = db.query(Engine).filter(Engine.slug == args.engine).first()
            db.expunge(engine)
        finally:
            db.close()
        start = budget.period_start(engine, datetime.utcnow())
        spent = remote.adapter_factory(engine, remote.open_credentials(engine)).provider_spend(
            start, _next_period(engine, start))
        print(f"Reported spend since {start}: US$ {spent} (Modal's report lags a few minutes)")
    return 0 if report.get("ok") else 1


def _speed(args) -> int:
    import json

    from shared.database import SessionLocal
    from shared.engines import speed
    from shared.engines.capacity import bindings
    from shared.models import Engine

    db = SessionLocal()
    try:
        query = db.query(Engine).order_by(Engine.slug)
        if args.engine:
            query = query.filter(Engine.slug == args.engine)
        rows = []
        for engine in query:
            for feature, binding in bindings(engine.config or {}).items():
                stats = speed.compute(db, engine.id, feature, binding.gpu_type or binding.gpu_ref,
                                      binding.executions_per_worker)
                rows.append({"engine": engine.slug, "feature": feature, **stats.view()})
    finally:
        db.close()
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    for r in rows:
        print(f"{r['engine']:<10} {r['feature']:<20} {r['gpu']:<6} E={r['executions_per_worker']} "
              f"rows={r['rows']} s_p20={r['s_p20']} cold_p80={r['cold_s_p80']} "
              f"q95 US$/h={r['usd_per_audio_hour_q95']} source={r['source']}"
              + ("" if r["learned"] else f" (worst case until {r['needs_rows']} more rows)"))
    return 0


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

    routes = sub.add_parser("routes", help="show, set or remove feature routes")
    routes_sub = routes.add_subparsers(dest="action", required=True)
    routes_show = routes_sub.add_parser("show")
    routes_show.add_argument("--json", action="store_true")
    routes_set = routes_sub.add_parser("set")
    routes_set.add_argument("feature")
    routes_set.add_argument("--step", action="append", required=True,
                            help='engines and options, in order, e.g. "local" or "modal_1,modal_2 fill_first min_wait=600"')
    routes_set.add_argument("--max-attempts", type=int, default=3)
    routes_set.add_argument("--fallback", choices=["local_direct", "hold"], default="local_direct",
                            help="while the dispatcher is down: send new items straight to the local workers, or hold them")
    routes_set.add_argument("--on-no-engine", choices=["hold", "fail"], default="hold")
    routes_set.add_argument("--remote-allowed-for", choices=["admins", "all"], default="admins",
                            help="who may have items sent to remote engines (all requires --user-limit-usd)")
    routes_set.add_argument("--user-limit-usd", type=float,
                            help="per-user spend ceiling per period on remote engines (required with all)")
    routes_set.add_argument("--remote-data-notice", help="shown to users whose media may leave this server")
    routes_set.add_argument("--fail-after", type=int, help="seconds before on-no-engine=fail fails an item")
    routes_delete = routes_sub.add_parser("delete")
    routes_delete.add_argument("feature")

    budget_p = sub.add_parser("budget", help="set a remote engine's spending ceiling per period")
    budget_p.add_argument("engine")
    budget_p.add_argument("--limit-usd", type=float, required=True)
    budget_p.add_argument("--min-remaining-usd", type=float)
    budget_p.add_argument("--soft-pct", type=int)
    budget_p.add_argument("--tz", help="IANA time zone of the period (default UTC)")
    budget_p.add_argument("--anchor-day", type=int, help="first day of the period, 1-28 (default 1)")
    for name in ("activate", "pause"):
        life = sub.add_parser(name, help=f"{name} an engine")
        life.add_argument("engine")

    sub.add_parser("modal-lock", help="regenerate the hashed requirements lock of the Modal image")
    test = sub.add_parser("test", help="check a remote engine's credentials and deployment (no GPU)")
    test.add_argument("--engine", help="slug, e.g. modal_1")
    test.add_argument("--all", action="store_true", help="every remote engine with credentials, in turn")
    test.add_argument("--spend", action="store_true", help="also read the account's billing report")
    deploy_p = sub.add_parser("modal-deploy", help="deploy the Whisper app to an engine's Modal account")
    deploy_p.add_argument("--engine", help="slug, e.g. modal_1")
    deploy_p.add_argument("--all", action="store_true",
                          help="every Modal engine with credentials and a binding, one after the other")
    deploy_p.add_argument("--feature", default="transcription")
    deploy_p.add_argument("--dry-run", action="store_true")
    deploy_p.add_argument("--allow-unhashed", action="store_true",
                          help="deploy even if the requirements lock has no hashes (recorded on the engine)")

    recon = sub.add_parser("reconcile", help="read the providers' spend reports now (as the 10-min beat does)")
    recon.add_argument("--engine", help="one engine (paused ones too); default every active remote engine")

    from workers.engines.benchmark import add_arguments as benchmark_arguments
    bench = sub.add_parser("benchmark", help="measure speed, US$/h of audio and VRAM per (gpu, E); remote costs money")
    benchmark_arguments(bench)

    speed_p = sub.add_parser("speed", help="learned speed and cost per (engine, feature, gpu, E), from the ledger")
    speed_p.add_argument("--engine", help="one engine (default all)")
    speed_p.add_argument("--json", action="store_true")

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

    if args.command == "routes":
        return _routes(args)

    if args.command in ("budget", "activate", "pause"):
        return _lifecycle(args)

    if args.command in ("modal-lock", "modal-deploy", "test", "reconcile"):
        return _remote(args)

    if args.command == "benchmark":
        from workers.engines.benchmark import run_command
        return run_command(args)

    if args.command == "speed":
        return _speed(args)

    if args.command == "import-modal-toml":
        return _import(accounts_from_modal_toml(Path(args.path).read_text()), args.limit_usd, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())
