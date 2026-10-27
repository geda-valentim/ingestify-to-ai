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
import sys
from engine_host_services import SERVICE_PROFILES, SERVICES, profile_args


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _stage(path, data, mode):
    """Create `path` (O_EXCL: never an existing file or symlink) with exactly `mode`, write
    `data` and fsync it. On failure the file it created is removed, so no partial file is left."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)  # exact mode (the umask may have dropped bits), on this inode
        _write_all(fd, data)
        os.fsync(fd)
    except BaseException:
        os.unlink(path)  # O_EXCL: this call created it; never leave a partial file behind
        raise
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
    0600, then gets `group` and `mode` (default: 0640 when a group is given); if
    that fails, the new file is removed again.
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
            except BaseException as exc:
                # From here the live file may be torn, and `<name>.bak` is this run's copy of it.
                exc.live_rewrite_started = True
                raise
            finally:
                os.close(fd)
        else:
            gid = None if group is None else group if isinstance(group, int) else _gid(group)
            _stage(path, data, 0o600)
            try:
                if gid is not None:
                    os.chown(path, -1, gid)
                wanted = mode if mode is not None else (0o640 if group is not None else 0o600)
                os.chmod(path, wanted)
            except BaseException:
                path.unlink()  # created just above: a half-set-up file would block the rerun
                raise
    finally:
        tmp.unlink(missing_ok=True)
        backup_tmp.unlink(missing_ok=True)


def _gid(group):
    if str(group).isdigit():
        return int(group)
    import grp

    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        raise ValueError(f"Unknown --identities-group {group!r}") from None


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


def _identity_state(path, host_id, digest):
    """Whether `path` holds host_id -> digest: "present", "absent", "invalid" (not valid JSON)
    or "unknown" (it could not be read)."""
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return "absent"
    except ValueError:
        return "invalid"
    except OSError:
        return "unknown"
    return "present" if isinstance(data, dict) and data.get(host_id) == digest else "absent"


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
    # Everything that can be checked is checked before anything is written. The group only
    # applies to a NEW identities file (an existing one keeps its own).
    group = None
    if args.identities_group is not None and not Path(args.identities).exists():
        group = _gid(args.identities_group)
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
    digest = hashlib.sha256(token.encode()).hexdigest()
    identities[args.host_id] = digest
    # Born 0600 (never readable under the umask, even briefly); O_EXCL also refuses a file
    # (or symlink) that appeared after the check above.
    _stage(args.output, json.dumps(config, indent=2).encode(), 0o600)
    try:
        write_identities(Path(args.identities), identities, group=group)
    except BaseException as exc:
        # The config was created by this run (O_EXCL above), so it is ours to remove: without
        # its identity the rerun would refuse "Host already registered". Only when the identity
        # is surely absent, though: if the live file already holds it, the token in the config
        # is the only copy of a valid credential. The .bak is only pointed to when this run
        # tore the live file: otherwise it is an older copy, and restoring it would revoke
        # every host registered since.
        state = _identity_state(args.identities, args.host_id, digest)
        if state == "absent":
            Path(args.output).unlink(missing_ok=True)
        elif state == "present":
            print(
                f"The identity was already written to {args.identities}; {args.output} is kept "
                "(it holds the only copy of that token): the registration is in place, start the "
                "agent. After an I/O error, check both files before relying on them.",
                file=sys.stderr,
            )
        elif state == "invalid" and getattr(exc, "live_rewrite_started", False):
            print(
                f"Writing {args.identities} failed and it is no longer valid JSON: restore it from "
                f"{args.identities}.bak with `cp` (keeps the inode the API mounts), remove "
                f"{args.output} and run again.",
                file=sys.stderr,
            )
        else:
            print(
                f"Writing {args.identities} failed and it could not be checked afterwards; "
                f"{args.output} is kept. Check {args.identities} (do not restore an older backup): "
                f"if {args.host_id} is in it, the registration is in place; if not, remove "
                f"{args.output} and run again.",
                file=sys.stderr,
            )
        raise
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
