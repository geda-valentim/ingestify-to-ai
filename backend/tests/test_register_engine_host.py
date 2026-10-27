"""scripts/register_engine_host.py resolves services behind a compose profile (`live`, `engines`).

COMPOSE_PROFILES from .env may leave `live` off; `docker compose config` then does not
render worker-live and the registration died with a KeyError, right after the deploy
had built the image it was told to record. Subprocess is faked: no docker runs here.
"""
import argparse
import errno
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if not (SCRIPTS / "register_engine_host.py").exists():
    pytest.skip("scripts not mounted", allow_module_level=True)
sys.path.insert(0, str(SCRIPTS))

import register_engine_host  # noqa: E402

BUILD = {"context": "/repo"}
ACTIVE = {"worker": {"build": BUILD, "image": "ingestify-worker", "command": ["celery", "worker"]},
          "worker-vision": {"build": BUILD, "command": ["celery", "vision"]}}  # built, no `image:`
LIVE = {"worker-live": {"build": BUILD, "command": "python -m workers.live"}}  # built, no `image:`
ENGINES = {"worker-remote": {"build": BUILD, "command": ["celery", "remote"]},
           "worker-dispatch": {"build": BUILD, "command": ["celery", "dispatch"]}}
PINNED = {"worker-audio": {"image": "ingestify-audio:old", "command": ["celery", "audio"]}}  # merged config has no build
PROFILED = {"live": LIVE, "engines": ENGINES}


class FakeDocker:
    """`--profile` REPLACES the active profiles, as in Compose v2. Active: COMPOSE_PROFILES from the
    process env (a shell export wins over .env), else `active` (the .env value)."""

    def __init__(self, active=(), live_declared=True):
        self.active, self.live_declared = tuple(active), live_declared
        self.calls = []

    def __call__(self, argv, cwd=None, text=False, env=None):
        self.calls.append(argv)
        if argv[:2] == ["docker", "compose"] and "config" in argv:
            flags = tuple(argv[i + 1] for i, a in enumerate(argv) if a == "--profile")
            exported = (os.environ if env is None else env).get("COMPOSE_PROFILES")
            active = tuple(p for p in exported.split(",") if p) if exported is not None else self.active
            services = {**ACTIVE, **PINNED}
            for profile in flags or active:
                if profile != "live" or self.live_declared:
                    services.update(PROFILED[profile])
            return json.dumps({"services": services}).encode()
        if argv[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": f"sha256:{argv[3]}", "Config": {"Cmd": ["x"]}}]).encode()
        raise AssertionError(f"unexpected call: {argv}")


@pytest.fixture
def args(tmp_path):
    manifest = tmp_path / "docker-compose.yml"
    manifest.write_text("services: {}\n")
    return argparse.Namespace(
        manifest=[str(manifest)], service=["worker", "worker-live"], project="ingestify-to-ai",
        cwd=str(tmp_path), use_built_image=True, host_id="h1", api_url="http://127.0.0.1:8080",
        gpu_uuid=[], output=str(tmp_path / "engine-host.json"), identities=str(tmp_path / "ids.json"),
        identities_group=None, state=str(tmp_path / "state.json"),
    )


def test_worker_live_is_rendered_with_its_profile_and_the_rest_without(args, monkeypatch):
    docker = FakeDocker()
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", docker)

    register_engine_host.register(args)

    services = json.loads(Path(args.output).read_text())["services"]
    assert services["worker-live"] == {
        "image": "sha256:ingestify-to-ai-worker-live", "command": ["python", "-m", "workers.live"],
    }
    assert services["worker"]["image"] == "sha256:ingestify-worker"
    configs = [c for c in docker.calls if "config" in c]
    assert len(configs) == 2 and [c[c.index("config") - 2:c.index("config")] for c in configs if "--profile" in c] == [
        ["--profile", "live"]]


def test_engines_profile_services_are_rendered_with_their_profile(args, monkeypatch):
    docker = FakeDocker(active=("engines",))  # the deploy built them: engines is in COMPOSE_PROFILES
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", docker)
    args.service = ["worker", "worker-remote", "worker-dispatch"]

    register_engine_host.register(args)

    services = json.loads(Path(args.output).read_text())["services"]
    assert services["worker-remote"]["command"] == ["celery", "remote"] and "worker-dispatch" in services
    configs = [c for c in docker.calls if "config" in c]
    assert len(configs) == 2  # one render per profile set
    assert [c[c.index("config") - 2:c.index("config")] for c in configs if "--profile" in c] == [["--profile", "engines"]]


def test_a_service_missing_from_the_manifests_is_a_clear_error(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker(live_declared=False))

    with pytest.raises(ValueError, match="worker-live is not declared.*or its compose profile is not active"):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()


def test_ps_fallback_targets_the_profile_too(args, monkeypatch):
    docker = FakeDocker()

    envs = []

    def check_output(argv, cwd=None, text=False, env=None):
        if "ps" in argv:
            docker.calls.append(argv)
            envs.append(env)
            return "c1\n"
        if argv[:2] == ["docker", "inspect"]:
            return json.dumps([{"Image": "sha256:running"}]).encode()
        return docker(argv, cwd=cwd, text=text, env=env)

    monkeypatch.setattr(register_engine_host.subprocess, "check_output", check_output)
    monkeypatch.setenv("COMPOSE_PROFILES", "engines")
    args.use_built_image = False
    args.service = ["worker-live", "worker-vision"]

    register_engine_host.register(args)

    ps = {c[-1]: c for c in docker.calls if "ps" in c}
    assert all(not any(k.startswith("COMPOSE_") for k in e) for e in envs)  # ps: the deploy's env too
    assert ps["worker-live"][ps["worker-live"].index("ps") - 2:ps["worker-live"].index("ps")] == ["--profile", "live"]
    assert "--profile" not in ps["worker-vision"]  # an unprofiled service keeps the active profiles


def test_use_built_image_refuses_a_service_without_build(args, monkeypatch):
    # e.g. declared only in a local override: the deploy built nothing, the declared image is not new
    docker = FakeDocker()
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", docker)
    args.service = ["worker", "worker-audio"]

    with pytest.raises(ValueError, match="worker-audio has no build section"):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()
    assert not any("ingestify-audio:old" in c for c in docker.calls)


def test_without_use_built_image_the_declared_image_is_recorded(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    args.service, args.use_built_image = ["worker-audio"], False

    register_engine_host.register(args)

    assert json.loads(Path(args.output).read_text())["services"]["worker-audio"]["image"] == "sha256:ingestify-audio:old"


def test_use_built_image_refuses_a_profiled_service_the_deploy_did_not_build(args, monkeypatch):
    # engines is not in COMPOSE_PROFILES: the deploy built neither worker-remote nor worker-dispatch,
    # so `ingestify-to-ai-worker-remote` is an old image (it holds the engine-secrets key)
    docker = FakeDocker(active=())
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", docker)
    args.service = ["worker", "worker-remote"]

    with pytest.raises(ValueError, match="deploy does not build worker-remote.*engines"):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()
    assert not any("ingestify-to-ai-worker-remote" in c for c in docker.calls)


def test_without_use_built_image_an_inactive_profile_still_registers(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker(active=()))
    args.service, args.use_built_image = ["worker-remote"], False
    ENGINES_IMAGE = {"worker-remote": {**ENGINES["worker-remote"], "image": "ingestify-remote:1"}}
    monkeypatch.setitem(PROFILED, "engines", ENGINES_IMAGE)

    register_engine_host.register(args)

    assert json.loads(Path(args.output).read_text())["services"]["worker-remote"]["image"] == "sha256:ingestify-remote:1"


def test_a_shell_export_of_compose_profiles_does_not_widen_what_counts_as_built(args, monkeypatch):
    # .env leaves engines off (the deploy, under `env -i`, did not build worker-remote); the
    # operator exported COMPOSE_PROFILES=engines in this shell to run it by hand
    monkeypatch.setenv("COMPOSE_PROFILES", "engines")
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker(active=()))
    args.service = ["worker-remote"]

    with pytest.raises(ValueError, match="deploy does not build worker-remote"):
        register_engine_host.register(args)
    assert not Path(args.output).exists()


def test_every_shell_compose_variable_is_dropped(args, monkeypatch):
    # another env file could switch engines on in the default render; the deploy passes no COMPOSE_*
    seen = []
    docker = FakeDocker(active=())

    def check_output(argv, cwd=None, text=False, env=None):
        seen.append(env)
        return docker(argv, cwd=cwd, text=text, env=env)

    monkeypatch.setenv("COMPOSE_ENV_FILES", "/tmp/other.env")
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", check_output)
    args.service = ["worker"]

    register_engine_host.register(args)

    compose_envs = [e for e in seen if e is not None]
    assert compose_envs and all(not any(k.startswith("COMPOSE_") for k in e) for e in compose_envs)


def test_the_refusal_says_how_to_really_build(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker(active=()))
    args.service = ["worker-remote"]

    with pytest.raises(ValueError, match=r"FORCE_REBUILD=1"):
        register_engine_host.register(args)


def test_the_token_file_is_born_0600_under_a_permissive_umask(args, monkeypatch):
    # write_text + chmod left the machine token world-readable (0644 under umask 022) until chmod
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    modes_when_token_written = []
    real_write_all = register_engine_host._write_all

    def write_all(fd, data):
        if b"machine_token" in data:
            modes_when_token_written.append(os.fstat(fd).st_mode & 0o777)
        real_write_all(fd, data)

    monkeypatch.setattr(register_engine_host, "_write_all", write_all)
    old = os.umask(0o022)
    try:
        register_engine_host.register(args)
    finally:
        os.umask(old)

    assert modes_when_token_written == [0o600]
    assert os.stat(args.output).st_mode & 0o777 == 0o600
    assert "machine_token" in json.loads(Path(args.output).read_text())


def test_a_strict_umask_still_leaves_the_owner_able_to_read_the_token(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    old = os.umask(0o277)  # would drop the owner's write bit
    try:
        register_engine_host.register(args)
    finally:
        os.umask(old)

    assert os.stat(args.output).st_mode & 0o777 == 0o600


def _enospc_when(marker):
    real_write_all = register_engine_host._write_all

    def write_all(fd, data):
        if marker in data:
            raise OSError(errno.ENOSPC, "No space left on device")
        real_write_all(fd, data)

    return write_all


_write_all_real = register_engine_host._write_all


def _rerun_is_possible(args, monkeypatch):
    """After the failure, the same registration goes through (nothing blocks it)."""
    monkeypatch.setattr(register_engine_host, "_write_all", _write_all_real)
    register_engine_host.register(args)
    assert args.host_id in json.loads(Path(args.identities).read_text())


def test_identities_group_is_ignored_for_an_existing_file(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    _existing_identities(args)
    args.identities_group = "no-such-group-for-this-test"  # only applies to a new file

    register_engine_host.register(args)

    assert args.host_id in json.loads(Path(args.identities).read_text())


def test_unknown_identities_group_fails_before_anything_is_written(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    args.identities_group = "no-such-group-for-this-test"

    with pytest.raises(ValueError, match="Unknown --identities-group"):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()


def test_enospc_writing_the_config_leaves_no_partial_file(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    monkeypatch.setattr(register_engine_host, "_write_all", _enospc_when(b"machine_token"))

    with pytest.raises(OSError):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()
    _rerun_is_possible(args, monkeypatch)


def test_enospc_writing_the_identities_removes_this_runs_config(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    # the identities JSON, not the config (which also says "h1", but indented)
    fail = _enospc_when(f'{{"{args.host_id}": "'.encode())
    config_existed = []

    def write_all(fd, data):
        config_existed.append(Path(args.output).exists())
        fail(fd, data)

    monkeypatch.setattr(register_engine_host, "_write_all", write_all)

    with pytest.raises(OSError):
        register_engine_host.register(args)
    assert config_existed[-1]  # it failed in write_identities, after the config was written
    assert not Path(args.output).exists() and not Path(args.identities).exists()
    assert not list(Path(args.identities).parent.glob(".*.tmp"))  # no staged leftovers either
    _rerun_is_possible(args, monkeypatch)


def test_a_refused_chown_on_a_new_identities_file_undoes_both_files(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    args.identities_group = "10001"

    def chown(path, uid, gid):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(register_engine_host.os, "chown", chown)

    with pytest.raises(PermissionError):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()


def test_an_existing_registration_is_never_touched(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    Path(args.output).write_text('{"machine_token": "old"}')

    with pytest.raises(ValueError, match="Host already registered"):
        register_engine_host.register(args)
    assert Path(args.output).read_text() == '{"machine_token": "old"}'


def _assert_no_secret(err, args):
    token = json.loads(Path(args.output).read_text())["machine_token"]
    assert token not in err and register_engine_host.hashlib.sha256(token.encode()).hexdigest() not in err


def _existing_identities(args):
    Path(args.identities).write_text(json.dumps({"other-host": "f" * 64}))
    return os.stat(args.identities).st_ino


def test_failure_after_the_live_identities_got_our_entry_keeps_the_config(args, monkeypatch, capsys):
    # re-registration: the live file (the inode the API mounts) is rewritten in place, then fsync
    # fails; the API already sees the new hash, so the config holds the only copy of a valid token
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    live = _existing_identities(args)
    real_fsync = os.fsync

    def fsync(fd):
        if os.fstat(fd).st_ino == live:
            raise OSError(errno.EIO, "I/O error")
        real_fsync(fd)

    monkeypatch.setattr(register_engine_host.os, "fsync", fsync)

    with pytest.raises(OSError):
        register_engine_host.register(args)
    assert args.host_id in json.loads(Path(args.identities).read_text())
    assert "machine_token" in json.loads(Path(args.output).read_text())
    err = capsys.readouterr().err
    assert "is kept" in err and "start the agent" in err
    _assert_no_secret(err, args)


def test_a_torn_rewrite_of_the_live_identities_points_to_the_backup(args, monkeypatch, capsys):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    live = _existing_identities(args)
    before = Path(args.identities).read_text()

    def write_all(fd, data):
        if os.fstat(fd).st_ino == live:
            os.write(fd, data[:-10])  # past the old content's end, short of the new one: invalid JSON
            raise OSError(errno.ENOSPC, "No space left on device")
        _write_all_real(fd, data)

    monkeypatch.setattr(register_engine_host, "_write_all", write_all)

    with pytest.raises(OSError):
        register_engine_host.register(args)
    err = capsys.readouterr().err
    assert ".bak" in err
    _assert_no_secret(err, args)
    assert Path(args.identities + ".bak").read_text() == before
    assert Path(args.output).exists()  # kept: the operator decides after restoring the backup


def test_an_early_identities_failure_with_an_intact_live_file_never_points_to_the_backup(
    args, monkeypatch, capsys
):
    # ENOSPC staging the temp copy: the live file was never touched, and any .bak is from an
    # OLDER registration; restoring it would revoke the hosts registered since
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    _existing_identities(args)
    before = Path(args.identities).read_text()
    monkeypatch.setattr(register_engine_host, "_write_all", _enospc_when(b'{"other-host": '))

    with pytest.raises(OSError):
        register_engine_host.register(args)
    assert ".bak" not in capsys.readouterr().err
    assert Path(args.identities).read_text() == before
    assert not Path(args.output).exists()  # surely absent: this run's config is removed


def test_an_unreadable_identities_file_keeps_the_config_and_never_points_to_the_backup(
    args, monkeypatch, capsys
):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker())
    _existing_identities(args)
    failed = []
    fail = _enospc_when(b'{"other-host": ')

    def write_all(fd, data):
        try:
            fail(fd, data)
        except OSError:
            failed.append(True)
            raise

    real_read_text = Path.read_text

    def read_text(self, *a, **kw):
        if failed and str(self) == args.identities:
            raise OSError(errno.EIO, "I/O error")
        return real_read_text(self, *a, **kw)

    monkeypatch.setattr(register_engine_host, "_write_all", write_all)
    monkeypatch.setattr(Path, "read_text", read_text)

    with pytest.raises(OSError):
        register_engine_host.register(args)
    err = capsys.readouterr().err
    assert "could not be checked" in err and ".bak" not in err
    assert Path(args.output).exists()  # unknown: kept, the operator decides
    _assert_no_secret(err, args)
