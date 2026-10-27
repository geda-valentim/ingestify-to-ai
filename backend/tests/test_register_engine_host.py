"""scripts/register_engine_host.py resolves services behind a compose profile (worker-live: `live`).

COMPOSE_PROFILES from .env may leave `live` off; `docker compose config` then does not
render worker-live and the registration died with a KeyError, right after the deploy
had built the image it was told to record. Subprocess is faked: no docker runs here.
"""
import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if not (SCRIPTS / "register_engine_host.py").exists():
    pytest.skip("scripts not mounted", allow_module_level=True)
sys.path.insert(0, str(SCRIPTS))

import register_engine_host  # noqa: E402

ACTIVE = {"worker": {"image": "ingestify-worker", "command": ["celery", "worker"]}}
LIVE = {"worker-live": {"command": "python -m workers.live"}}  # built, no `image:`
ENGINES = {"worker-remote": {"command": ["celery", "remote"]}, "worker-dispatch": {"command": ["celery", "dispatch"]}}


class FakeDocker:
    def __init__(self, live_declared=True):
        self.live_declared = live_declared
        self.calls = []

    def __call__(self, argv, cwd=None, text=False):
        self.calls.append(argv)
        if argv[:2] == ["docker", "compose"] and "config" in argv:
            services = dict(ACTIVE)
            profile = argv[argv.index("config") - 1]
            if self.live_declared and profile == "live":
                services.update(LIVE)
            if profile == "engines":
                services.update(ENGINES)
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
    assert len(configs) == 2 and sum("--profile" in c for c in configs) == 1


def test_engines_profile_services_are_rendered_with_their_profile(args, monkeypatch):
    docker = FakeDocker()
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", docker)
    args.service = ["worker", "worker-remote", "worker-dispatch"]

    register_engine_host.register(args)

    services = json.loads(Path(args.output).read_text())["services"]
    assert services["worker-remote"]["command"] == ["celery", "remote"] and "worker-dispatch" in services
    assert len([c for c in docker.calls if "config" in c]) == 2  # one render per profile set


def test_a_service_missing_from_the_manifests_is_a_clear_error(args, monkeypatch):
    monkeypatch.setattr(register_engine_host.subprocess, "check_output", FakeDocker(live_declared=False))

    with pytest.raises(ValueError, match="worker-live is not declared"):
        register_engine_host.register(args)
    assert not Path(args.output).exists() and not Path(args.identities).exists()


def test_ps_fallback_targets_the_profile_too(args, monkeypatch):
    docker = FakeDocker()

    def check_output(argv, cwd=None, text=False):
        if "ps" in argv:
            docker.calls.append(argv)
            return "c1\n"
        if argv[:2] == ["docker", "inspect"]:
            return json.dumps([{"Image": "sha256:running"}]).encode()
        return docker(argv, cwd=cwd, text=text)

    monkeypatch.setattr(register_engine_host.subprocess, "check_output", check_output)
    args.use_built_image = False
    args.service = ["worker-live"]

    register_engine_host.register(args)

    ps = [c for c in docker.calls if "ps" in c]
    assert ps and ps[0][ps[0].index("ps") - 2:ps[0].index("ps")] == ["--profile", "live"]
