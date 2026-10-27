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
from engine_host_services import SERVICE_PROFILES, SERVICES, profile_args


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _stage(path, data, mode):
    """Write `data` to a fresh sibling file (O_EXCL, `mode`) and fsync it."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)  # exact mode (the umask may have dropped bits), on this inode
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


# COMPOSE_PROFILES (often from .env) may leave a service's profile (SERVICE_PROFILES) off, and
# then `config` does not render it; `--profile` replaces COMPOSE_PROFILES, so profile_args()
# is only passed for those services, never for the rest.
# What the deploy builds, so what --use-built-image may record: the services of the default
# render (the active COMPOSE_PROFILES) plus these, which it builds with their own profile
# (worker-live: BUILD_LIVE=1). Keep it in step with scripts/deploy.sh.
DEPLOY_BUILDS_WITH_PROFILE = {"worker-live"}


def _compose_env():
    """`make deploy` runs under `env -i` and passes no COMPOSE_* variable: its compose reads
    COMPOSE_PROFILES from .env only. Drop every shell COMPOSE_* (a profile list or another env
    file would win over .env), so this sees the services the deploy built."""
    return {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}


def _service_configs(cmd, cwd, services):
    """(rendered config of each of `services`, names in the default render); ValueError if one is missing."""
    rendered = {}
    for extra in dict.fromkeys([()] + [tuple(profile_args(s)) for s in services]):
        cfg = json.loads(
            subprocess.check_output(
                cmd + list(extra) + ["config", "--format", "json"], cwd=cwd, env=_compose_env()
            )
        )
        rendered[extra] = cfg.get("services") or {}
    configs = {}
    for service in services:
        found = rendered[tuple(profile_args(service))].get(service)
        if found is None:
            raise ValueError(
                f"Service {service} is not declared by the given manifests, or its compose "
                "profile is not active; pass the compose file that defines it with --manifest"
            )
        configs[service] = found
    return configs, set(rendered[()])


def register(args):
    manifests = {
        str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in args.manifest
    }
    cmd = ["docker", "compose", "--project-name", args.project]
    for p in manifests:
        cmd += ["-f", p]
    for service in args.service:
        if service not in SERVICES:
            raise ValueError("Unknown worker service")
    configs, default_render = _service_configs(cmd, args.cwd, args.service)
    allowed = {}
    for service in args.service:
        image = configs[service].get("image")
        if args.use_built_image:
            if service not in default_render and service not in DEPLOY_BUILDS_WITH_PROFILE:
                raise ValueError(
                    f"--use-built-image: the deploy does not build {service}, its compose profile "
                    f"({SERVICE_PROFILES.get(service, '?')}) is not in COMPOSE_PROFILES; add it to "
                    "COMPOSE_PROFILES in .env and run `make deploy FORCE_REBUILD=1` (.env is not "
                    "tracked: a plain deploy may detect no change and build nothing), or register "
                    "without the flag"
                )
            # Without `build:` in the merged config (e.g. declared only in a local override, or
            # `build: !reset`) `compose build` built nothing: the declared image is not new.
            if not configs[service].get("build"):
                raise ValueError(
                    f"--use-built-image: service {service} has no build section, so no image "
                    "was built for it; drop the flag to record its declared image"
                )
            image = image or f"{args.project}-{service}"  # `image:` is the built tag; else compose's default
        if not image:
            ids = subprocess.check_output(
                cmd + profile_args(service) + ["ps", "--all", "--quiet", service],
                cwd=args.cwd,
                env=_compose_env(),
                text=True,
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
        command = configs[service].get("command")
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
    # Born 0600 (never readable under the umask, even briefly); O_EXCL also refuses a file
    # (or symlink) that appeared after the check above.
    _stage(args.output, json.dumps(config, indent=2).encode(), 0o600)
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
    p.add_argument(
        "--use-built-image",
        action="store_true",
        help="record the freshly built <project>-<service> image, not the one "
        "of the existing container (use after a deploy that rebuilt the images)",
    )
    p.add_argument("--output", default="/etc/ingestify/engine-host.json")
    p.add_argument("--identities", default="secrets/engine_host_identities.json")
    p.add_argument(
        "--identities-group",
        default=None,
        help="group (name or GID, e.g. 10001) for a NEW identities file; it then gets 0640",
    )
    p.add_argument("--state", default="/var/lib/ingestify-engine-agent/state.json")
    register(p.parse_args())
