#!/usr/bin/env python3
"""One-time registration from trusted host manifests; never prints machine tokens/env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import stat
import subprocess
from engine_host_agent import SERVICES


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _stage(path, data, mode):
    """Write `data` to a fresh sibling file (O_EXCL, `mode`) and fsync it."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def write_identities(path, identities, *, group=None, mode=None):
    """Rewrite the identities file without changing its inode, mode or group.

    The file holds only token hashes. The API container (uid/gid 10001) reads it
    through a single-file bind mount, so it must stay the same inode (a rename
    would leave the container on the old file) and keep an existing
    0640 root:10001 mode.

    The new content is validated and staged in a temp file next to the target
    (same mode, fsynced) before the target is touched; the previous content is
    kept in `<name>.bak`. The target is then overwritten with one write from
    offset 0, truncated to the new length and fsynced, so a reader sees either
    the old or the new JSON except for the instant of that write (the API retries
    once on a decode error). A brand-new target is created with O_EXCL and mode
    0600, then gets `group` and `mode` (default: 0640 when a group is given).
    """
    path = Path(path)
    if not isinstance(identities, dict):
        raise ValueError("identities must be a JSON object")
    data = json.dumps(identities).encode()
    if json.loads(data) != identities:
        raise ValueError("identities do not round-trip as JSON")
    existed = path.exists()
    st = path.stat() if existed else None
    staged_mode = stat.S_IMODE(st.st_mode) if st else 0o600
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    backup_tmp = tmp.with_suffix(".bak.tmp")
    _stage(tmp, data, staged_mode)
    try:
        if json.loads(tmp.read_bytes()) != identities:
            raise ValueError("staged identities file does not match")
        if existed:
            backup = path.with_name(path.name + ".bak")
            _stage(backup_tmp, path.read_bytes(), staged_mode)
            os.replace(backup_tmp, backup)  # the backup is never bind-mounted
            fd = os.open(path, os.O_WRONLY)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                _write_all(fd, data)
                os.ftruncate(fd, len(data))
                os.fsync(fd)
            finally:
                os.close(fd)
        else:
            _stage(path, data, 0o600)
            if group is not None:
                gid = group if isinstance(group, int) else _gid(group)
                os.chown(path, -1, gid)
            wanted = mode if mode is not None else (0o640 if group is not None else 0o600)
            os.chmod(path, wanted)
    finally:
        tmp.unlink(missing_ok=True)
        backup_tmp.unlink(missing_ok=True)


def _gid(group):
    if str(group).isdigit():
        return int(group)
    import grp

    return grp.getgrnam(group).gr_gid


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
    write_identities(
        Path(args.identities), identities, group=args.identities_group
    )
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
    p.add_argument(
        "--identities-group",
        default=None,
        help="group (name or GID, e.g. 10001) for a NEW identities file; it then gets 0640",
    )
    p.add_argument("--state", default="/var/lib/ingestify-engine-agent/state.json")
    register(p.parse_args())
