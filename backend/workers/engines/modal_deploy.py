"""
Deploy the Whisper app to one Modal account, and verify it (spec 0003, 4.11).

    python scripts/engines.py modal-deploy --engine modal_1 [--dry-run] [--allow-unhashed]

Run it where the private keys are - the worker-remote container:

    docker compose --profile engines run --rm worker-remote \\
        python scripts/engines.py modal-deploy --engine modal_1

Steps: the deploy spec of the engine's binding (decorator + fingerprint); the
engine's credentials opened in this process only; `python -m modal deploy` in a
subprocess whose environment is built from scratch (token as variables, never
argv; HOME a temp dir, so no ~/.modal.toml is read or written); then the
CPU-only `meta()` function is called to check that the account now serves this
very fingerprint and protocol, and only then is the deploy recorded on the
engine (`deployments[feature]`, audited) and in the account's state Dict.

Costs: the image build (CPU, billed by Modal as build time; the first one
downloads ~1.6 GB of weights) and a few seconds of a 0.25-CPU container for
meta(). No GPU is started.
"""

import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Callable, Dict, Optional

from shared.engines import store
from shared.engines.capacity import bindings, validate_engine_config
from shared.engines.redact import redact
from shared.models import Engine
from workers.engines import remote
from workers.engines.modal_apps import protocol
from workers.engines.modal_apps.files import ALLOW_UNHASHED_ENV, BACKEND_DIR, DEPLOY_ENV, LOCK_FILE, lock_is_hashed
from workers.engines.modal_apps.fingerprint import deploy_spec

logger = logging.getLogger(__name__)

DEPLOY_TIMEOUT_SECONDS = 3600
APP_MODULE = "workers.engines.modal_apps.whisper_app"


class DeployError(Exception):
    pass


def _session(session_factory=None):
    if session_factory is not None:
        return session_factory()
    from shared.database import SessionLocal
    return SessionLocal()


def deploy_command() -> list:
    return [sys.executable, "-m", "modal", "deploy", "--name", protocol.APP_NAME, "-m", APP_MODULE]


def plan(engine: Engine, feature: str) -> Dict[str, object]:
    if engine.adapter_type != "modal":
        raise DeployError(f"{engine.slug} is a {engine.adapter_type} engine; only Modal engines are deployed")
    binding = bindings(engine.config or {}).get(feature)
    if binding is None:
        raise DeployError(f"{engine.slug} has no {feature} binding: "
                          f"engines.py set-capacity {engine.slug} {feature} --workers 1 --gpu-type L4")
    validate_engine_config(engine.adapter_type, engine.config or {})
    spec = deploy_spec(feature, engine.config or {}, binding)
    return {"engine": engine.slug, "feature": feature, "binding": binding.model_dump(exclude_none=True),
            "spec": spec, "hashed": lock_is_hashed(), "command": " ".join(deploy_command()[1:])}


def deploy(slug: str, feature: str = "transcription", *, dry_run: bool = False, allow_unhashed: bool = False,
           session_factory=None, run: Callable = subprocess.run, out: Callable[[str], None] = print) -> Optional[dict]:
    db = _session(session_factory)
    try:
        engine = db.query(Engine).filter(Engine.slug == slug).first()
        if engine is None:
            raise DeployError(f"No engine {slug!r}")
        p = plan(engine, feature)
        spec = p["spec"]
        out(f"Engine {slug}, {feature}: {json.dumps(spec['decorator'])}")
        out(f"Fingerprint {spec['fingerprint']}, protocol {spec['protocol']}, "
            f"model {protocol.MODEL_REPO}@{protocol.MODEL_REVISION[:12]}")
        if not p["hashed"]:
            message = f"{LOCK_FILE.name} is missing or not fully hashed (run `engines.py modal-lock`)"
            if not allow_unhashed:
                raise DeployError(message + "; or pass --allow-unhashed (recorded on the engine)")
            out(f"WARNING: {message}; installing the unhashed pins (--allow-unhashed)")
        if dry_run:
            out(f"Dry run: would run `{p['command']}` with the engine's token in a from-scratch environment, "
                f"then verify meta() and record the deploy. Nothing was sent.")
            return None

        adapter = remote.adapter_factory(engine, remote.open_credentials(engine))
        extra = {DEPLOY_ENV: json.dumps(spec, sort_keys=True), "PYTHONPATH": str(BACKEND_DIR)}
        if allow_unhashed:
            extra[ALLOW_UNHASHED_ENV] = "1"
        with tempfile.TemporaryDirectory(prefix="modal-deploy-home-") as home:
            out(f"Deploying {protocol.APP_NAME} to {slug} (this builds the image; the first build takes minutes)...")
            done = run(deploy_command(), env=adapter.subprocess_env(home, extra), cwd=str(BACKEND_DIR),
                       capture_output=True, text=True, timeout=DEPLOY_TIMEOUT_SECONDS)
        output = redact((done.stdout or "") + (done.stderr or ""))
        if done.returncode != 0:
            raise DeployError(f"modal deploy failed (exit {done.returncode}):\n{output[-3000:]}")
        out(output[-1500:])

        meta = adapter.deployed_meta()
        if not isinstance(meta, dict) or meta.get("fingerprint") != spec["fingerprint"] \
                or meta.get("protocol") != protocol.PROTOCOL_VERSION:
            raise DeployError(f"The account does not serve what was deployed: meta() answered "
                              f"{redact(json.dumps(meta, default=str))[:300]}")
        verified_at = datetime.utcnow().isoformat()
        entry = {"fingerprint": spec["fingerprint"], "protocol": protocol.PROTOCOL_VERSION,
                 "binding": p["binding"], "verified_at": verified_at, "app": protocol.APP_NAME,
                 "decorator": spec["decorator"], "hashed": p["hashed"]}
        adapter.record_deployment({"fingerprint": spec["fingerprint"], "protocol": protocol.PROTOCOL_VERSION,
                                   "verified_at": verified_at})
        store.record_deployment(db, engine, feature, entry, actor_user_id=None, auth_method="cli")
        out(f"Deployed and verified: {slug} {feature} serves fingerprint {spec['fingerprint'][:16]}...")
        return entry
    finally:
        db.close()


if __name__ == "__main__":  # python -m workers.engines.modal_deploy --engine modal_1
    import argparse

    from shared.engines.redact import install_log_redaction

    install_log_redaction()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--engine", required=True)
    parser.add_argument("--feature", default="transcription")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-unhashed", action="store_true")
    args = parser.parse_args()
    try:
        deploy(args.engine, args.feature, dry_run=args.dry_run, allow_unhashed=args.allow_unhashed)
    except DeployError as e:
        print(f"❌ {e}")
        sys.exit(1)
