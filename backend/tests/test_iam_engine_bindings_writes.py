"""
Spec 0018 slice 2: the 0009 grants read and written on `iam_bindings`.

- CA2: no module reads `RoleGrant` outside the migration, the rollback mirror and
  the frozen copy of CA4;
- CA5/CA7/CA9: the single write service bumps the epoch, keeps the delegation
  (parent = the delegate's `access_admin` binding) and mirrors every write into
  `access_role_grants` in the same transaction;
- CA10/CA15: `IAM_MODE` is the flag, `ENGINE_ACCESS_ENABLED` a deprecated alias;
- CA13: a child whose parent is revoked contributes nothing to the navigation, and
  engines bindings never reach the platform family;
- §4.2.3: reconciliation at every API boot.
"""

import ast
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from shared.access import contracts as C, policy, service
from shared.access.models import AuthorizationEpoch, RoleGrant
from shared.config import Settings
from shared.engine_control import service as control
from shared.iam import bindings, engine_equivalence, migration
from shared.iam.decide import Decider, principal_for_user
from shared.iam.models import IamBinding
from shared.models import AdminAudit, Engine, User
from tests.test_execution_profiles import constraints, grant, world  # noqa: F401
from tests.test_iam_engine_equivalence import legacy_revoke, legacy_state

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def _epoch(db):
    return db.get(AuthorizationEpoch, 1).version


def _legacy_row(db, grant_id):
    """The mirror row, read the way only tests and the migration may (CA2)."""
    return db.execute(
        select(RoleGrant.__table__).where(RoleGrant.__table__.c.id == grant_id)
    ).mappings().first()


def _envelope():
    return C.Delegation(
        permissions=sorted(policy.ROLES["observer"]),
        constraints=constraints(),
        max_grant_seconds=1800,
    )


def _soon(minutes=10):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


# -- CA2 --------------------------------------------------------------------------

# The only modules allowed to name RoleGrant / access_role_grants in code: the
# model, the registration of the FK graph, the 0018 migration, the rollback mirror
# (write-only by id) and the frozen copy of CA4.
CA2_ALLOWED = {
    "shared/access/models.py",
    "shared/models.py",
    "shared/iam/migration.py",
    "shared/iam/engine_mirror.py",
    "shared/iam/engine_equivalence.py",
}


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _legacy_references(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    docs = _docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "RoleGrant":
            found.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "RoleGrant":
            found.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and any(a.name == "RoleGrant" for a in node.names):
            found.append(node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
            and "access_role_grants" in node.value
        ):
            found.append(node.lineno)
    return found


def test_ca2_no_module_reads_role_grant_outside_migration_mirror_and_frozen_copy():
    sources = [
        p for d in ("shared", "api", "workers") for p in (BACKEND / d).rglob("*.py")
    ] + list((ROOT / "scripts").rglob("*.py"))
    offenders = {}
    for path in sources:
        rel = path.relative_to(BACKEND).as_posix() if BACKEND in path.parents else path.relative_to(ROOT).as_posix()
        if rel in CA2_ALLOWED:
            continue
        lines = _legacy_references(path)
        if lines:
            offenders[rel] = lines
    assert offenders == {}
    # The checker is not vacuous.
    assert _legacy_references(BACKEND / "shared/iam/engine_mirror.py")


def test_the_mirror_never_reads_access_role_grants():
    tree = ast.parse((BACKEND / "shared/iam/engine_mirror.py").read_text())
    calls = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert not calls & {"select", "query", "get"}


# -- writes: binding + epoch + mirror ------------------------------------------------


def test_a_grant_is_a_binding_mirrored_with_the_same_id_and_bumps_the_epoch(world):  # noqa: F811
    with world() as db:
        before = _epoch(db)
        g = grant(db, actor="observer", role="observer")
        assert _epoch(db) > before
        b = db.get(IamBinding, g["id"])
        assert (b.subject_type, b.subject_id, b.role, b.scope_type) == ("user", "observer", "observer", "platform")
        assert b.permissions == sorted(policy.ROLES["observer"])
        assert b.condition_ref == g["policy_revision_id"]
        row = _legacy_row(db, g["id"])
        for mine, theirs in migration._SAME:
            assert getattr(b, mine) == row[theirs], mine
        assert (row["expires_at"], row["revoked_at"], row["version"]) == (b.expires_at, None, 0)
        migration.verify_engine_bindings(db.connection())


def test_a_revocation_reaches_the_mirror_so_the_frozen_legacy_reader_denies(world):  # noqa: F811
    """CA9 (a): after a rollback the pre-0018 code sees the revocation."""
    with world() as db:
        g = grant(db, actor="observer", role="observer")
        assert [x.id for x in engine_equivalence.legacy_grants(db, "observer")] == [g["id"]]
        before = _epoch(db)
        out = service.revoke(db, g["id"], 0, "bootstrap")
        assert out["version"] == 1 and out["revoked_at"] is not None
        assert _epoch(db) == before + 1
        b = db.get(IamBinding, g["id"])
        assert b.revoked_by == "bootstrap"
        assert _legacy_row(db, g["id"])["revoked_at"] == b.revoked_at
        assert _legacy_row(db, g["id"])["version"] == 1
        assert engine_equivalence.legacy_grants(db, "observer") == []
        assert not policy.allowed(db, "observer", "engines.read", engine=db.get(Engine, "engine-a"))
        # The 0009 contract: re-revoking is accepted and bumps the version, but it
        # never rewrites who revoked the binding, or when.
        first = b.revoked_at
        assert service.revoke(db, g["id"], 1, "bootstrap")["version"] == 2
        assert _legacy_row(db, g["id"])["version"] == 2
        db.refresh(b)
        assert (b.revoked_at, b.revoked_by) == (first, "bootstrap")
        assert _legacy_row(db, g["id"])["revoked_at"] == first


def test_the_unified_revoke_semantics(world):  # noqa: F811
    with world() as db:
        g = grant(db, actor="observer", role="observer")
        bindings.revoke_engine(db, "bootstrap", g["id"], 0, strict=True)
        with pytest.raises(control.ControlError) as refused:
            bindings.revoke_engine(db, "bootstrap", g["id"], 1, strict=True)
        assert (refused.value.code, refused.value.status) == ("ALREADY_REVOKED", 409)
        db.rollback()
        with pytest.raises(control.ControlError) as refused:
            bindings.revoke_engine(db, "bootstrap", "nope", 0, strict=True)
        assert (refused.value.code, refused.value.status) == ("BINDING_NOT_FOUND", 404)
        db.rollback()
        with pytest.raises(control.ControlError) as refused:
            service.revoke(db, "nope", 0, "bootstrap")
        assert (refused.value.code, refused.value.status) == ("GRANT_NOT_FOUND", 404)


def test_a_failing_mirror_aborts_the_grant(world, monkeypatch):  # noqa: F811
    from shared.iam import engine_mirror

    def broken(db, b):
        raise RuntimeError("mirror down")

    monkeypatch.setattr(engine_mirror, "mirror", broken)
    with world() as db:
        p = service.create_policy(db, C.PolicyCreate(name="p", constraints=constraints()), "bootstrap")
        before = _epoch(db)
        with pytest.raises(RuntimeError, match="mirror down"):
            service.create_grant(
                db,
                C.GrantCreate(user_id="observer", role="observer",
                              policy_revision_id=p["revisions"][0]["id"], expires_at=_soon()),
                "bootstrap",
            )
        db.rollback()
        assert db.query(IamBinding).filter_by(subject_id="observer").count() == 0
        assert _epoch(db) == before


def test_self_grant_of_an_engines_role_is_refused(world):  # noqa: F811
    """The one intentional deviation from 0009 (0013 §4 rule 6)."""
    with world() as db:
        with pytest.raises(control.ControlError) as refused:
            grant(db, actor="bootstrap", role="observer")
        assert (refused.value.code, refused.value.status) == ("SELF_GRANT", 422)


def test_several_bindings_of_the_same_role_for_one_user_are_valid(world):  # noqa: F811
    with world() as db:
        a = grant(db, actor="operator", role="engine_operator",
                  permissions=sorted(policy.READ | {"engine_operations.plan"}))
        b = grant(db, actor="operator", role="engine_operator",
                  scope=constraints(engine_ids=["engine-b"]))
        assert {g.id for g in policy.grants(db, "operator")} == {a["id"], b["id"]}


# -- CA7: delegation ------------------------------------------------------------------


def test_delegation_links_the_child_to_the_parent_binding_and_dies_with_it(world):  # noqa: F811
    with world() as db:
        parent = grant(db, actor="delegate", role="access_admin", delegation=_envelope())
        child = grant(db, actor="observer", role="observer", creator="delegate", expires=_soon())
        assert child["parent_id"] == parent["id"]
        assert db.get(IamBinding, child["id"]).parent_id == parent["id"]
        assert _legacy_row(db, child["id"])["parent_id"] == parent["id"]
        # The delegate lists only what its envelope covers, never a platform binding.
        db.add(IamBinding(id="platform-1", subject_type="user", subject_id="observer",
                          role="platform_auditor", granted_by="bootstrap",
                          expires_at=datetime.utcnow() + timedelta(days=1)))
        db.commit()
        listed = {g["id"] for g in service.list_grants(db, "delegate")}
        assert listed == {child["id"]}
        assert "platform-1" not in {g["id"] for g in service.list_grants(db, "bootstrap")}
        with pytest.raises(control.ControlError, match="GRANT_NOT_FOUND"):
            service.revoke(db, "platform-1", 0, "bootstrap")
        db.rollback()
        user = db.get(User, "observer")
        assert policy.navigation(db, user)["permissions"] == sorted(policy.ROLES["observer"])

        service.revoke(db, parent["id"], 0, "bootstrap")
        # CA13: the child contributes nothing, neither to engines nor to the platform.
        assert policy.navigation(db, user)["permissions"] == []
        assert not policy.allowed(db, "observer", "engines.read", engine=db.get(Engine, "engine-a"))
        assert Decider(db).platform_roles(principal_for_user(user)) == ["platform_auditor"]


def test_without_an_envelope_a_delegate_grants_nothing(world):  # noqa: F811
    with world() as db:
        grant(db, actor="delegate", role="access_admin")
        with pytest.raises(control.ControlError) as refused:
            grant(db, actor="observer", role="observer", creator="delegate", expires=_soon())
        assert refused.value.code == "DELEGATION_EXCEEDED"


# -- the platform family stays apart -----------------------------------------------


def test_a_platform_grant_ignores_engines_bindings_and_leaves_the_epoch_alone(world):  # noqa: F811
    with world() as db:
        grant(db, actor="observer", role="observer")
        before = _epoch(db)
        b = bindings.grant(db, db.get(User, "bootstrap"), subject_type="user",
                           subject_id="observer", role="platform_auditor",
                           expires_at=datetime.utcnow() + timedelta(days=1), decider=Decider(db))
        assert b.permissions is None and b.condition_ref is None
        assert _epoch(db) == before
        assert db.query(AdminAudit).filter_by(target_type="iam_binding", target_id=b.id).count() == 1


def test_the_platform_locking_read_is_pinned_to_the_role_index(world):  # noqa: F811
    """§4.3: on MySQL the BINDING_EXISTS read never scans the subject's engines rows."""
    from sqlalchemy.dialects import mysql

    from shared.iam.models import IamBinding as Model

    assert bindings.INDEX_SUBJECT_ROLE == migration.INDEX_0018
    assert migration.INDEX_0018 in {i.name for i in Model.__table__.indexes}
    with world() as db:
        q = bindings._active_platform_binding(db, "user", "observer", "platform_auditor", datetime.utcnow())
        sql = str(q.statement.compile(dialect=mysql.dialect()))
        assert f"iam_bindings FORCE INDEX ({migration.INDEX_0018})" in sql
        assert sql.rstrip().endswith("FOR UPDATE")
        assert "FORCE INDEX" not in str(q.statement.compile(dialect=db.get_bind().dialect))


# -- §4.2.3: reconciliation at boot ---------------------------------------------------


def test_reconciliation_runs_at_boot_and_brings_back_a_legacy_revocation(world):  # noqa: F811
    with world() as db:
        ids = legacy_state(db)
    engine = world.kw["bind"]
    migration.upgrade_0018(engine)
    with world() as db:
        legacy_revoke(db, ids["op_plan"], "bootstrap")
        assert ids["op_plan"] in {g.id for g in policy.grants(db, "operator")}
    assert migration.reconcile_on_boot(engine) == {"copied": 0, "restricted": 1}
    assert migration.reconcile_on_boot(engine) == {"copied": 0, "restricted": 0}
    with world() as db:
        assert ids["op_plan"] not in {g.id for g in policy.grants(db, "operator")}


def test_every_worker_reconciles_at_boot_before_deciding(world, monkeypatch):  # noqa: F811
    """§4.2.3: a worker booting before any api still sees a rollback revocation."""
    import shared.database
    from workers.celery_app import reconcile_engine_grants_on_boot

    with world() as db:
        ids = legacy_state(db)
    engine = world.kw["bind"]
    migration.upgrade_0018(engine)
    with world() as db:
        legacy_revoke(db, ids["op_plan"], "bootstrap")
    disposed = []
    monkeypatch.setattr(engine, "dispose", lambda: disposed.append(True))  # keep StaticPool's db
    monkeypatch.setattr(shared.database, "engine", engine)
    reconcile_engine_grants_on_boot()
    assert disposed == [True]
    with world() as db:
        assert ids["op_plan"] not in {g.id for g in policy.grants(db, "operator")}

    def broken(bind):
        raise RuntimeError("db down")

    monkeypatch.setattr(migration, "reconcile_on_boot", broken)
    with pytest.raises(SystemExit, match="db down"):
        reconcile_engine_grants_on_boot()
    from shared.config import get_settings

    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    reconcile_engine_grants_on_boot()  # engines are bootstrap-only: nothing to reconcile


def test_reconciliation_at_boot_skips_a_fresh_or_pre_0018_database():
    from shared.database import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)  # a fresh install: no epoch row, no grants
    assert migration.reconcile_on_boot(engine) == {"copied": 0, "restricted": 0}
    assert migration.reconcile_on_boot(create_engine("sqlite://")) == {"copied": 0, "restricted": 0}


# -- CA10: the flag -------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["off", "shadow", "enforce"])
@pytest.mark.parametrize("alias", [None, "", "true", "false"])
def test_iam_mode_is_the_flag_and_engine_access_enabled_a_deprecated_alias(monkeypatch, caplog, mode, alias):
    monkeypatch.setenv("IAM_MODE", mode)
    if alias is None:
        monkeypatch.delenv("ENGINE_ACCESS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ENGINE_ACCESS_ENABLED", alias)
    with caplog.at_level(logging.INFO, logger="shared.config"):
        s = Settings(_env_file=None)
    explicit = alias in ("true", "false")
    expected = alias == "true" if explicit else mode == "enforce"
    assert s.engine_access_enabled is expected
    assert ("ENGINE_ACCESS_ENABLED=" in caplog.text and "deprecated" in caplog.text) is explicit
    assert f"engine_access_enabled={expected}" in caplog.text


@pytest.mark.parametrize("alias", [None, "true"])
def test_every_process_reports_the_effective_flag_before_logging_is_configured(alias):
    """CA15: Settings is built at import time, before any logging setup."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "IAM_MODE": "enforce"}
    env.pop("ENGINE_ACCESS_ENABLED", None)
    if alias is not None:
        env["ENGINE_ACCESS_ENABLED"] = alias
    out = subprocess.run(
        [sys.executable, "-c", "from shared.config import Settings; Settings(_env_file=None)"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    source = "ENGINE_ACCESS_ENABLED" if alias else "IAM_MODE=enforce"
    assert f"engine_access_enabled=True ({source})" in out.stderr


# -- CA15: compose ---------------------------------------------------------------------


def _environment(service):
    env = service.get("environment") or {}
    if isinstance(env, list):
        return dict(e.split("=", 1) if "=" in e else (e, None) for e in env)
    return env


def _compose_files():
    """
    The repository's docker-compose*.yml: the git-tracked ones only, so a local,
    untracked overlay (a tunnel or a dev override next to the checkout) never
    decides this test. Without git (or outside a work tree, e.g. a container
    that mounts the code but not the .git it points to): every file on disk.
    """
    import subprocess

    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "docker-compose*.yml"],
                             capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return sorted(ROOT.glob("docker-compose*.yml"))
    names = [name for name in out.decode().split("\0") if name and "/" not in name]
    if not names:  # an export without tracked files: what is on disk
        return sorted(ROOT.glob("docker-compose*.yml"))
    return sorted(ROOT / name for name in names)


def test_compose_passes_iam_mode_wherever_engine_access_enabled_goes():
    yaml = pytest.importorskip("yaml")
    seen = set()
    for path in _compose_files():
        services = (yaml.safe_load(path.read_text()) or {}).get("services") or {}
        for name, service in services.items():
            env = _environment(service)
            if "ENGINE_ACCESS_ENABLED" not in env:
                continue
            seen.add(name)
            assert "IAM_MODE" in env, f"{path.name}: {name}"
            value = str(env["ENGINE_ACCESS_ENABLED"])
            assert ":-false" not in value and value.lower() != "false", f"{path.name}: {name}"
    # Every process importing shared.access.policy (spec 0018 CA15).
    assert {
        "api", "worker", "worker-audio", "worker-vision", "worker-remote", "worker-dispatch",
        "worker-control", "worker-control-watchdog", "beat",
    } <= seen
