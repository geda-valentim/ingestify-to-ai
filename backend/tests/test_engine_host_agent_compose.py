"""
scripts/engine_host_agent.py passes `--profile` for services behind a Compose profile.

Current Compose activates the profile of a service named on the command line, but
that was never checked for `ps`, and an older Compose returns an empty `ps` without
an error - the agent would read it as "no replicas". So the profile is explicit.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


@pytest.fixture
def agent_module():
    if not (SCRIPTS / "engine_host_agent.py").exists():
        pytest.skip("scripts not mounted")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import engine_host_agent

    return engine_host_agent


def _agent(module, tmp_path, monkeypatch, service):
    agent = module.HostAgent.__new__(module.HostAgent)
    agent.config = {
        "project": "ingestify",
        "manifests": {"docker-compose.yml": "x", "docker-compose.live.yml": "y"},
        "services": {service: {"image": "sha256:" + "0" * 64}},
        "cwd": str(tmp_path),
    }
    agent.done_path = tmp_path / "state.json"
    agent.active = None
    calls = []

    def run(argv, timeout=180):
        calls.append(argv)
        return ""  # `ps` finds no containers

    monkeypatch.setattr(agent, "run", run)
    monkeypatch.setattr(agent, "check", lambda: None)
    monkeypatch.setattr(agent, "event", lambda *a, **k: None)
    monkeypatch.setattr(agent, "inventory", lambda: {"manifest_hash": "h"})
    return agent, calls


def _global_args(argv, subcommand):
    """Everything between `docker compose` and the subcommand."""
    return argv[2 : argv.index(subcommand)]


@pytest.mark.parametrize(
    "service,profile",
    [
        ("worker-live", "live"),
        ("worker-dispatch", "engines"),
        ("worker-remote", "engines"),
        ("worker", None),
        ("worker-audio", None),
        ("worker-vision", None),
    ],
)
def test_ps_carries_the_service_profile(agent_module, tmp_path, monkeypatch, service, profile):
    agent, calls = _agent(agent_module, tmp_path, monkeypatch, service)

    assert agent.inspect(service, "overlay.json") == []

    args = _global_args(calls[0], "ps")
    if profile:
        assert args[-2:] == ["--profile", profile]
    else:
        assert "--profile" not in args


def test_up_carries_the_service_profile(agent_module, tmp_path, monkeypatch):
    agent, calls = _agent(agent_module, tmp_path, monkeypatch, "worker-live")
    plan = {
        "service": "worker-live",
        "type": "cooldown",
        "feature": "live-transcription",
        "manifest_hash": "h",
        "profile_revision": 3,
        "profile": {
            "model_profile_id": "mp",
            "model": {"model": "small"},
            "binding": {},
            "desired_replicas": 1,
            "min_ready_replicas": 0,
        },
    }

    result = agent.apply({"operation_id": "op", "generation": 1, "plan": plan})

    assert result["replicas_alive"] == 0
    up = next(argv for argv in calls if "up" in argv)
    assert _global_args(up, "up")[-2:] == ["--profile", "live"]
    assert all(_global_args(argv, "ps")[-2:] == ["--profile", "live"] for argv in calls if "ps" in argv)


def test_the_map_matches_the_compose_files(agent_module):
    """A service that gains or loses a profile in Compose must update the agent too."""
    yaml = pytest.importorskip("yaml")
    declared = {}
    for path in sorted(REPO.glob("docker-compose*.yml")):
        services = (yaml.safe_load(path.read_text()) or {}).get("services") or {}
        for name, spec in services.items():
            if name in agent_module.SERVICES and (spec or {}).get("profiles"):
                declared.setdefault(name, set()).update(spec["profiles"])

    assert {name: profiles for name, profiles in declared.items()} == {
        name: {profile} for name, profile in agent_module.SERVICE_PROFILES.items()
    }
