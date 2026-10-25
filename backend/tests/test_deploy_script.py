"""Static guarantees of scripts/deploy.sh and the Makefile `deploy` target."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "scripts" / "deploy.sh").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()
CODE = "\n".join(
    line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#")
)


def _regex(name):
    m = re.search(rf"^{name}='(.*)'$", SCRIPT, re.M)
    assert m, name
    return re.compile(m.group(1))


def test_makefile_runs_script_with_clean_env():
    block = MAKEFILE.split("\ndeploy:", 1)[1].split("\n# ====", 1)[0]
    assert "env -i" in block and "scripts/deploy.sh" in block
    assert 'PATH="$$PATH"' in block and "DOCKER_HOST" in block
    assert "docker compose" not in block
    assert "DEPLOY_COMPOSE" not in MAKEFILE
    assert ".deploy-previous-head" not in MAKEFILE + SCRIPT
    for v in "DEPLOY_BASE DEPLOY_REF NO_PULL BUILD_LIVE SSH_AUTH_SOCK GIT_SSH_COMMAND".split():
        assert v in block, v


def test_script_is_strict_and_valid_bash():
    assert "set -euo pipefail" in SCRIPT and SCRIPT.startswith("#!/usr/bin/env bash")


def test_no_unfiltered_restart_or_zero_scale():
    assert "compose restart" not in CODE
    assert not re.search(r"docker restart(?! \$ids)", CODE)
    assert "RUNNING[$s]:-0}\" -gt 0" in CODE  # scale only for running services
    assert not re.search(r"--scale[ =\"'$a-z{}/_-]*=0\b", CODE)
    assert "ps failed" in CODE and "--status running" in CODE


def test_managed_services_are_never_upped_directly():
    assert "/var/lib/ingestify-engine-agent" in SCRIPT
    # overlay-based detection is primary; the static list is only the unreadable-dir fallback
    assert 'MANAGED=" "' in CODE
    m = re.search(r'\n\s*MANAGED=" \$MANAGED_STATIC "', CODE)
    assert m and CODE.rfind("else", 0, m.start()) > CODE.rfind('-r "$AGENT_DIR"', 0, m.start())
    assert CODE.count('MANAGED=" $MANAGED_STATIC "') == 1
    # worker-live is only ever built
    assert not re.search(r"up .*worker-live", CODE)
    assert "--no-build --no-deps" in CODE
    # the only restart acts on running ids; managed ones are restarted only on the code path
    assert "docker restart $ids" in CODE
    assert "restart_running $UNMANAGED_RUNNING $MANAGED_RUNNING" in CODE
    code_branch = CODE.split('elif [ "$CODE" = 1 ]', 1)[1].split("\nfi", 1)[0]
    assert "restart_running" in code_branch
    image_branch = CODE.split('if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then\n  if [ -n "$UNMANAGED_RUNNING" ]', 1)[1].split('elif [ "$CODE"', 1)[0]
    # managed services are restarted (never up'd) here, and only when no new image is involved
    up_part, restart_part = image_branch.split('if [ "$IMAGES" = 0 ] && [ -n "$MANAGED_RUNNING" ]', 1)
    assert not re.search(r"(?<!UN)MANAGED_RUNNING", up_part) and "docker restart" not in up_part
    assert "restart_running $MANAGED_RUNNING" in restart_part and "compose up" not in restart_part


def test_detection_is_anchored_on_last_success_marker():
    assert "deploy-last-success" in SCRIPT
    code = CODE.splitlines()
    write = [i for i, l in enumerate(code) if 'git rev-parse HEAD >"$LAST_FILE"' in l]
    health = [i for i, l in enumerate(code) if "curl -s -m 5" in l]
    assert write and health and write[0] > health[0]
    assert "git diff --name-only \"$BASE\" \"$NEWHEAD\"" in CODE
    assert "git diff --name-only \"$OLD_HEAD\" \"$NEWHEAD\"" in CODE  # failed HEAD stays covered


def test_no_marker_aborts_before_any_git_change():
    assert "|| CODE=1" not in CODE and "git pull" not in CODE
    assert CODE.index("no deploy marker") < CODE.index("git fetch") < CODE.index("git merge --ff-only")


def test_rollback_and_worker_live_gates():
    assert 'git merge-base --is-ancestor "$DEPLOY_REF" origin/main' in CODE
    assert 'git reset --keep "$NEWHEAD"' in CODE and "reset --hard" not in CODE
    assert CODE.count("build worker-live") == 1
    assert re.search(r'if \[ "\$BUILD_LIVE" = 1 \]; then\s+log [^\n]*\s+run compose build worker-live', CODE)


def test_inventory_hardening_and_notices():
    assert "config --quiet" in CODE and "NOT in COMPOSE_FILE" in CODE
    assert "inspect active -d " in CODE and "ingestify-worker" in CODE and "ingestify-audio" in CODE
    assert "REGISTERED_MANIFEST_CHANGED" in CODE and "engine-control-bootstrap" in CODE
    assert 'AGENT_DIR="${DEPLOY_AGENT_DIR:-/var/lib/ingestify-engine-agent}"' in CODE


def test_health_check_parameters():
    assert "port api 8000" in CODE
    assert "seq 1 40" in CODE and "sleep 3" in CODE
    assert "HTTP 200" in CODE and '"status":"healthy"' in CODE and "API_VERSION" in CODE
    assert re.search(r'"\\"version\\":\\"\$EXPECTED\\""', CODE)


def test_image_regex_covers_every_copied_file():
    rx = _regex("IMAGE_RE")
    for path in [
        "backend/requirements.txt",
        "backend/requirements-whisperx-cuda.lock",
        "backend/requirements-live-whisperx-cuda.lock",
        "docker/Dockerfile.api",
        "docker/Dockerfile.live-whisperx",
        "docker/entrypoint.sh",
        "scripts/make_admin.py",
        "scripts/engines.py",
        "scripts/seed_execution_profiles.py",
    ]:
        assert rx.match(path), path
    assert not rx.match("backend/api/routes.py")
    live = _regex("LIVE_RE")
    assert live.match("docker/Dockerfile.live-whisperx")
    assert live.match("backend/requirements-diart-cuda.lock")
    assert _regex("COMPOSE_RE").match("docker-compose.gpu.yml")


def test_regex_matches_what_dockerfiles_copy():
    rx = _regex("IMAGE_RE")
    copied = set()
    for df in (ROOT / "docker").glob("Dockerfile.*"):
        for line in df.read_text().splitlines():
            m = re.match(r"COPY\s+(?!--)(.+)\s+\S+\s*$", line)
            if m:
                copied.update(m.group(1).split())
    for src in copied:
        if src.startswith("scripts/") and not src.endswith("/"):
            assert rx.match(src), f"{src} is copied into an image but not in IMAGE_RE"
