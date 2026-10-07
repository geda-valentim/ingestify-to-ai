#!/usr/bin/env python3
"""One-time registration from trusted host manifests; never prints machine tokens/env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
from engine_host_agent import SERVICES


def register(args):
    manifests = {
        str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in args.manifest
    }
    cmd = ["docker", "compose", "--project-name", args.project]
    for p in manifests:
        cmd += ["-f", p]
    cfg = json.loads(
        subprocess.check_output(cmd + ["config", "--format", "json"], cwd=args.cwd)
    )
    allowed = {}
    for service in args.service:
        if service not in SERVICES:
            raise ValueError("Unknown worker service")
        image = cfg["services"][service].get("image")
        if not image:
            ids = subprocess.check_output(
                cmd + ["ps", "--all", "--quiet", service], cwd=args.cwd, text=True
            ).split()
            if not ids:
                raise ValueError(
                    "Build or start the approved worker image before registration"
                )
            image = json.loads(subprocess.check_output(["docker", "inspect", ids[0]]))[
                0
            ]["Image"]
        else:
            image = json.loads(
                subprocess.check_output(["docker", "image", "inspect", image])
            )[0]["Id"]
        command = cfg["services"][service].get("command")
        if not command:
            command = json.loads(
                subprocess.check_output(["docker", "image", "inspect", image])
            )[0]["Config"]["Cmd"]
        if isinstance(command, str):
            command = shlex.split(command)
        allowed[service] = {"image": image, "command": command}
    token = secrets.token_urlsafe(48)
    config = {
        "host_id": args.host_id,
        "api_url": args.api_url,
        "machine_token": token,
        "project": args.project,
        "cwd": str(Path(args.cwd).resolve()),
        "manifests": manifests,
        "services": allowed,
        "gpu_uuids": args.gpu_uuid,
        "state_path": str(Path(args.state).resolve()),
    }
    for filename in (args.output, args.identities, args.state):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
    identities = (
        json.loads(Path(args.identities).read_text())
        if Path(args.identities).exists()
        else {}
    )
    if args.host_id in identities or Path(args.output).exists():
        raise ValueError(
            "Host already registered; rotate deliberately, do not overwrite"
        )
    identities[args.host_id] = hashlib.sha256(token.encode()).hexdigest()
    Path(args.output).write_text(json.dumps(config, indent=2))
    os.chmod(args.output, 0o600)
    Path(args.identities).write_text(json.dumps(identities))
    os.chmod(args.identities, 0o600)
    print(
        "Registration written. Install the systemd unit and mount the identities file in API."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host-id", required=True)
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--project", default="ingestify-to-ai")
    p.add_argument("--cwd", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--manifest", action="append", required=True)
    p.add_argument("--service", action="append", required=True)
    p.add_argument("--gpu-uuid", action="append", default=[])
    p.add_argument("--output", default="/etc/ingestify/engine-host.json")
    p.add_argument("--identities", default="secrets/engine_host_identities.json")
    p.add_argument("--state", default="/var/lib/ingestify-engine-agent/state.json")
    register(p.parse_args())
