"""Smoke checks of scripts/deploy.sh and the Makefile `deploy` target (behavioural harness: PR-c)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "scripts" / "deploy.sh").exists() or not (ROOT / "Makefile").exists():
    pytest.skip("repo root (scripts/, Makefile) not mounted", allow_module_level=True)
SCRIPT = (ROOT / "scripts" / "deploy.sh").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()
CODE = "\n".join(l for l in SCRIPT.splitlines() if not l.lstrip().startswith("#"))


def test_makefile_runs_script_with_clean_env():
    block = MAKEFILE.split("\ndeploy:", 1)[1].split("\n# ====", 1)[0]
    assert "env -i" in block and "scripts/deploy.sh" in block and "docker compose" not in block
    assert all(v in block for v in "DEPLOY_BASE DEPLOY_REF NO_PULL BUILD_LIVE SSH_AUTH_SOCK".split())


def test_safety_rules():
    assert "set -euo pipefail" in CODE and "compose restart" not in CODE and "git pull" not in CODE
    assert not re.search(r"docker restart(?! \$ids)", CODE) and not re.search(r"up .*worker-live", CODE)
    assert CODE.index("no deploy marker") < CODE.index("git fetch") < CODE.index("git merge --ff-only")
    assert CODE.index("curl -s -m 5") < CODE.index('>"$LAST_FILE"')  # marker only after health


def test_image_regex_excludes_frontend_and_covers_backend_dockerfiles():
    rx = re.compile(re.search(r"^IMAGE_RE='(.*)'$", SCRIPT, re.M).group(1))
    for df in (ROOT / "docker").glob("Dockerfile.*"):
        assert bool(rx.match(f"docker/{df.name}")) == (df.name != "Dockerfile.frontend"), df.name


def test_interrupted_deploy_state_is_persisted_and_restored():
    assert 'for c in "$OLD_HEAD" "$NEWHEAD"' in CODE and 'git diff --no-renames --name-only "$c" "$NEWHEAD"' in CODE
    assert '[ ! -s "$INV_FILE" ]' in CODE and "RUNNING[$s]=\"$n\"" in CODE  # original inventory wins on retry
    assert CODE.index('>"$LAST_FILE"') < CODE.index('rm -f "$PENDING_FILE" "$INV_FILE"')


def test_register_script_can_record_the_built_image():
    reg = (ROOT / "scripts" / "register_engine_host.py").read_text()
    assert "--use-built-image" in reg and 'f"{args.project}-{service}"' in reg
    assert "--use-built-image" in SCRIPT  # the post-deploy notice tells the operator
