"""Checks of scripts/deploy.sh and the Makefile `deploy` target: static guarantees plus a behaviour harness."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "scripts" / "deploy.sh").exists() or not (ROOT / "Makefile").exists():
    pytest.skip("repo root (scripts/, Makefile) not mounted", allow_module_level=True)
SCRIPT = (ROOT / "scripts" / "deploy.sh").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()
CODE = "\n".join(l for l in SCRIPT.splitlines() if not l.lstrip().startswith("#"))


def _regex(name):
    return re.compile(re.search(rf"^{name}='(.*)'$", SCRIPT, re.M).group(1))


def test_makefile_runs_script_with_clean_env():
    block = MAKEFILE.split("\ndeploy:", 1)[1].split("\n# ====", 1)[0]
    assert "env -i" in block and "scripts/deploy.sh" in block and "docker compose" not in block
    assert all(v in block for v in "DEPLOY_BASE DEPLOY_REF NO_PULL BUILD_LIVE SSH_AUTH_SOCK".split())


def test_makefile_env_allowlist():
    block = MAKEFILE.split("\ndeploy:", 1)[1].split("\n# ====", 1)[0]
    assert 'PATH="$$PATH"' in block and "HOME" in block and "DEPLOY_COMPOSE" not in MAKEFILE
    assert all(v in block for v in "DOCKER_HOST DRY_RUN FORCE_REBUILD GIT_SSH_COMMAND DEPLOY_AGENT_DIR DEPLOY_ENGINE_HOST_CONFIG DOCKER_TLS_VERIFY DOCKER_CERT_PATH".split())


def test_safety_rules():
    assert "set -euo pipefail" in CODE and "compose restart" not in CODE and "git pull" not in CODE
    assert not re.search(r"docker restart(?! \$ids)", CODE) and not re.search(r"up .*worker-live", CODE)
    assert CODE.index("no deploy marker") < CODE.index("git fetch") < CODE.index("git merge --ff-only")
    assert CODE.index("curl -s -m 5") < CODE.index('>"$LAST_FILE"')  # marker only after health


def test_scale_and_restart_are_filtered():
    assert 'RUNNING[$s]:-0}" -gt 0' in CODE and "ps failed" in CODE and "--status running" in CODE


def test_managed_services_are_never_upped_directly():
    assert 'AGENT_DIR="${DEPLOY_AGENT_DIR:-/var/lib/ingestify-engine-agent}"' in CODE
    assert re.search(r'elif \[ -e "\$AGENT_DIR" \] \|\| \[ -e "\$HOST_CFG" \][^\n]*\n\s*die ', CODE)
    assert "engine control not installed" in CODE and "--no-build --no-deps" in CODE
    image_branch = CODE.split('if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then\n  if [ -n "$UNMANAGED_RUNNING" ]', 1)[1].split('elif [ "$CODE"', 1)[0]
    up_part, restart_part = image_branch.split('if [ "$IMAGES" = 0 ] && [ -n "$MANAGED_RUNNING" ]', 1)
    assert not re.search(r"(?<!UN)MANAGED_RUNNING", up_part) and "restart_running $MANAGED_RUNNING" in restart_part
    assert "compose up" not in restart_part


def test_rollback_and_worker_live_gates():
    assert 'git merge-base --is-ancestor "$DEPLOY_REF" origin/main' in CODE and "reset --hard" not in CODE
    assert 'git reset --keep "$NEWHEAD"' in CODE and 'is-ancestor HEAD "$NEWHEAD"' in CODE
    assert CODE.count("build worker-live") == 1 and 'if [ "$BUILD_LIVE" = 1 ]; then' in CODE


def test_worker_live_is_addressed_outside_the_active_profiles():
    # COMPOSE_PROFILES may leave `profiles: [live]` out of $CONF: no worker-live gate may read it.
    assert 'in_list worker-live "$CONF"' not in CODE and "compose --profile live build worker-live" in CODE
    assert "compose --profile live config --services" in CODE and "no worker-live service" in CODE
    # inventory, restore and the live stage go through the profile-aware helpers (the harness needs git)
    assert 'declared "$s" || continue' in CODE and 'svc_compose "$s" ps --status running -q "$s"' in CODE
    assert 'compose --profile live "$@"' in CODE and '&& declared "$s" &&' in CODE
    assert "if declared worker-live; then" in CODE


def test_inventory_hardening_and_health_parameters():
    assert "config --quiet" in CODE and "NOT in COMPOSE_FILE" in CODE and "inspect active -d " in CODE
    assert "REGISTERED_MANIFEST_CHANGED" in CODE and "engine-control-bootstrap" in CODE
    assert "--no-build --no-deps --force-recreate" in CODE and "port api 8000" in CODE
    assert "seq 1 40" in CODE and "sleep 3" in CODE and '"status":"healthy"' in CODE and "HTTP 200" in CODE
    assert re.search(r'"\\"version\\":\\"\$EXPECTED\\""', CODE)


def test_image_regex_excludes_frontend_and_covers_backend_dockerfiles():
    rx = _regex("IMAGE_RE")
    for df in (ROOT / "docker").glob("Dockerfile.*"):
        assert bool(rx.match(f"docker/{df.name}")) == (df.name != "Dockerfile.frontend"), df.name


def test_image_regex_covers_every_copied_file():
    rx, live = _regex("IMAGE_RE"), _regex("LIVE_RE")
    for path in ("backend/requirements.txt", "backend/requirements-whisperx-cuda.lock", "docker/Dockerfile.api",
                 "docker/entrypoint.sh", "scripts/make_admin.py", "scripts/engines.py", "scripts/seed_execution_profiles.py"):
        assert rx.match(path), path
    assert not rx.match("backend/api/routes.py") and live.match("docker/Dockerfile.live-whisperx")
    assert _regex("COMPOSE_RE").match("docker-compose.gpu.yml")
    copied = set()
    for df in (ROOT / "docker").glob("Dockerfile.*"):
        for line in df.read_text().splitlines():
            m = re.match(r"COPY\s+(?!--)(.+)\s+\S+\s*$", line)
            copied.update(m.group(1).split() if m else [])
    for src in copied:
        if src.startswith("scripts/") and not src.endswith("/"):
            assert rx.match(src), f"{src} is copied into an image but not in IMAGE_RE"


def test_interrupted_deploy_state_is_persisted_and_restored():
    assert 'for c in "$OLD_HEAD" "$NEWHEAD"' in CODE and 'git diff --no-renames --name-only "$c" "$NEWHEAD"' in CODE
    assert '[ ! -s "$INV_FILE" ]' in CODE and "RUNNING[$s]=\"$n\"" in CODE  # original inventory wins on retry
    assert '[ "$s" = worker-live ] || is_managed "$s"' in CODE and '[ "$COMPOSE_CHG" = 0 ] || LIVE=1' in CODE
    assert CODE.index('>"$LAST_FILE"') < CODE.index('rm -f "$PENDING_FILE" "$INV_FILE"')


def test_register_script_can_record_the_built_image():
    reg = (ROOT / "scripts" / "register_engine_host.py").read_text()
    assert "--use-built-image" in reg and 'f"{args.project}-{service}"' in reg
    assert "--use-built-image" in SCRIPT  # the post-deploy notice tells the operator


# --------------------------------------------------------------- behaviour harness
# The real deploy.sh and the real VCS in a temp repo; docker/curl/sleep are stubs that log their calls.
DOCKER_STUB = """#!/bin/bash
echo "$*" >> "$STUB_LOG"
[ "$1" = compose ] || exit 0
shift
args=(); live=0
while [ $# -gt 0 ]; do
  if [ "$1" = --profile ]; then [ "$2" != live ] || live=1; shift 2; else args+=("$1"); shift; fi
done
set -- "${args[@]}"
case "$1 $2" in
  "config --services") printf '%s\\n' $STUB_SERVICES; [ "$live" = 0 ] || printf '%s\\n' ${STUB_LIVE_SERVICES-};;
  "ps --status") v="STUB_RUN_${5//-/_}"; [ -z "${!v-}" ] || printf '%s\\n' "${!v}";;
  "port api") echo 0.0.0.0:8000;;
esac
"""
CURL_STUB = '#!/bin/bash\necho "{\\"status\\":\\"healthy\\",\\"version\\":\\"$STUB_VERSION\\"} HTTP 200"\n'
SERVICES = "api worker worker-audio worker-live frontend"
RUNNING = {"api": "a1", "worker": "w1\nw2", "worker_audio": "u1", "worker_live": "l1", "frontend": "f1"}


class Deploy:
    def __init__(self, tmp):
        for tool in ("git", "bash", "timeout", "comm"):
            if not shutil.which(tool):
                pytest.skip(f"{tool} not available: the deploy harness needs it")
        self.tmp, self.work, self.log = tmp, tmp / "work", tmp / "calls.log"
        self.env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}
        (tmp / "agent").mkdir()
        (tmp / "bin").mkdir()
        for name, body in (("docker", DOCKER_STUB), ("curl", CURL_STUB), ("sleep", "#!/bin/bash\n")):
            (tmp / "bin" / name).write_text(body)
            (tmp / "bin" / name).chmod(0o755)
        self.vcs(tmp, "init", "-q", "--bare", "origin.git")
        self.vcs(tmp, "clone", "-q", "origin.git", "work")
        self.vcs(self.work, "symbolic-ref", "HEAD", "refs/heads/main")
        (self.work / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "deploy.sh", self.work / "scripts" / "deploy.sh")
        self.write("backend/api/openapi_docs.py", 'API_VERSION = "1.0.0"\n')
        for f in ("backend/api/x.py", "docker-compose.yml", "frontend/x"):
            self.write(f, "0\n")
        self.base = self.commit("base")
        self.vcs(self.work, "push", "-q", "origin", "main")
        self.state("deploy-last-success").write_text(self.base + "\n")

    def vcs(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout.strip()

    def write(self, rel, text):
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg):
        self.vcs(self.work, "add", "-A")
        self.vcs(self.work, "commit", "-q", "-m", msg)
        return self.head()

    def publish(self, rel):
        """Commit a change to `rel`, push it, then put the work tree back on the marker."""
        self.write(rel, "1\n")
        sha = self.commit("change " + rel)
        self.vcs(self.work, "push", "-q", "origin", "main")
        self.vcs(self.work, "reset", "-q", "--hard", self.base)
        return sha

    def run(self, version="1.0.0", running=RUNNING, **flags):
        env = {**self.env, "PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "STUB_LOG": str(self.log),
               "STUB_SERVICES": SERVICES, "STUB_VERSION": version, "DEPLOY_AGENT_DIR": str(self.tmp / "agent"),
               **{f"STUB_RUN_{k}": v for k, v in running.items()}, **flags}
        self.log.write_text("")
        p = subprocess.run(["bash", "scripts/deploy.sh"], cwd=self.work, env=env, capture_output=True, text=True, timeout=120)
        return p, self.log.read_text().splitlines()

    def state(self, name):
        return self.work / ".git" / name

    def head(self):
        return self.vcs(self.work, "rev-parse", "HEAD")


@pytest.fixture
def dep(tmp_path):
    return Deploy(tmp_path)


def mutating(calls):
    return [c for c in calls if re.match(r"(compose (--profile \S+ )*(build|up)|restart)\b", c)]


def test_no_marker_aborts_before_any_change(dep):
    dep.state("deploy-last-success").unlink()
    dep.publish("backend/api/x.py")
    p, calls = dep.run()
    assert p.returncode != 0 and "no deploy marker" in p.stderr and dep.head() == dep.base and not mutating(calls)


def test_retry_restores_inventory_but_never_worker_live(dep):
    target = dep.publish("backend/api/x.py")
    p, calls = dep.run(version="9.9.9")  # code-only deploy whose health check fails
    assert p.returncode != 0 and "stage: health" in p.stderr and dep.head() == target
    assert "worker 2" in dep.state("deploy-pending-inventory").read_text()
    degraded = {**RUNNING, "worker": "w1", "worker_live": ""}  # one worker replica and worker-live are down
    p, calls = dep.run(running=degraded)
    assert p.returncode == 0, p.stderr
    assert "compose up -d --no-build --no-deps --scale worker=2 worker" in calls
    assert not any(c.startswith("compose up") and "worker-live" in c for c in calls)
    assert "worker-live ran 1 replica" in p.stderr and "re-apply its profile" in p.stderr
    assert dep.state("deploy-last-success").read_text().strip() == target
    assert not dep.state("deploy-pending-inventory").exists() and not dep.state("deploy-pending").exists()


def test_compose_only_change_warns_about_live_image(dep):
    (dep.tmp / "agent" / "worker-audio.json").write_text("{}")  # engine-managed
    dep.publish("docker-compose.yml")
    p, calls = dep.run()
    assert p.returncode == 0, p.stderr
    assert "worker-live inputs changed" in p.stderr and "REGISTERED_MANIFEST_CHANGED" in p.stderr
    assert "restart u1" in calls and not any(c.startswith("compose up") and "worker-audio" in c for c in calls)
    assert not any("worker-live" in c for c in mutating(calls))
    assert any("--force-recreate" in c for c in calls)


def test_marker_is_written_only_after_healthy_response(dep):
    target = dep.publish("backend/api/x.py")
    p, calls = dep.run(version="9.9.9")
    assert p.returncode != 0 and "another version" in p.stderr
    assert dep.state("deploy-last-success").read_text().strip() == dep.base
    p, _ = dep.run()
    assert p.returncode == 0 and dep.state("deploy-last-success").read_text().strip() == target


def test_dry_run_writes_no_state_and_changes_nothing(dep):
    dep.publish("docker-compose.yml")
    p, calls = dep.run(DRY_RUN="1")
    assert p.returncode == 0, p.stderr
    assert dep.head() == dep.base and dep.state("deploy-last-success").read_text().strip() == dep.base
    assert not dep.state("deploy-pending").exists() and not dep.state("deploy-pending-inventory").exists()
    assert not mutating(calls) and "[dry-run] compose build" in p.stdout


# worker-live is `profiles: [live]`: a COMPOSE_PROFILES without `live` drops it from `config --services`.
LIVE_OFF = {"STUB_SERVICES": "api worker worker-audio frontend", "STUB_LIVE_SERVICES": "worker-live"}


def test_build_live_builds_worker_live_outside_the_active_profiles(dep):
    dep.publish("backend/api/x.py")
    p, calls = dep.run(BUILD_LIVE="1", **LIVE_OFF)
    assert p.returncode == 0, p.stderr
    assert "compose --profile live build worker-live" in calls
    assert "compose --profile live ps --status running -q worker-live" in calls  # inventoried as well
    assert "worker-live" in p.stderr and "--use-built-image" in p.stderr


def test_build_live_fails_loudly_when_compose_has_no_worker_live(dep):
    dep.publish("backend/api/x.py")
    p, calls = dep.run(BUILD_LIVE="1", STUB_SERVICES=LIVE_OFF["STUB_SERVICES"], STUB_LIVE_SERVICES="")
    assert p.returncode != 0 and "no worker-live service" in p.stderr and "stage: inventory" in p.stderr
    assert not mutating(calls)


def test_stale_live_image_warning_survives_an_inactive_live_profile(dep):
    dep.publish("backend/shared/x.py")
    p, calls = dep.run(**LIVE_OFF)
    assert p.returncode == 0, p.stderr
    assert "worker-live inputs changed" in p.stderr and "BUILD_LIVE=1" in p.stderr
    assert not any("worker-live" in c for c in mutating(calls))
