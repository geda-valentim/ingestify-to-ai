"""Human guidance for engine-control / access / IAM refusals (spec 0009 CA1).

- every error code raised in those modules has a Portuguese catalog entry;
- a Modal engine without a desired profile says what to do (test connection,
  bind/create a profile) and disables the operations that cannot be planned;
- cooldown with no profile is NOTHING_TO_COOL_DOWN, not a setup error;
- wrapped adapter gates surface as `cause` with their own message.
"""

import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException, APIRouter
from fastapi.testclient import TestClient

from shared import error_catalog
from shared.engine_control import service
from shared.engine_control.contracts import PlanRequest
from shared.engine_control.models import ControlHost
from shared.models import Engine
from tests.test_engine_control import world  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SCANNED = [
    "shared/engine_control",
    "shared/access",
    "shared/iam",
    "shared/root.py",
    "workers/engine_control",
    "api/engine_control_routes.py",
    "api/access_routes.py",
    "api/access_deps.py",
    "api/iam_routes.py",
    "api/iam_deps.py",
]
# Any string literal that is (or starts with) an UPPER_SNAKE code: "CODE",
# "CODE: detail", f"CODE:{n}" — raised directly, picked by a conditional or put in
# a {"code": ...} detail. Environment variable names are the only other such literals.
_RAISED = re.compile(r"""["']([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+)(?=["':])""")
NOT_ERROR_CODES = {"ENGINE_CONTROL_ENABLED"}
NOT_ERROR_PREFIXES = ("INGESTIFY_",)


def _files():
    for rel in SCANNED:
        path = BACKEND / rel
        yield from ([path] if path.is_file() else sorted(path.rglob("*.py")))
    agent = REPO / "scripts" / "engine_host_agent.py"
    if agent.exists():
        yield agent


def raised_codes():
    found = {}
    for path in _files():
        for m in _RAISED.finditer(path.read_text()):
            code = m.group(1)
            if code in NOT_ERROR_CODES or code.startswith(NOT_ERROR_PREFIXES):
                continue
            found.setdefault(code, set()).add(path.name)
    return found


def test_every_raised_code_has_a_portuguese_message():
    found = raised_codes()
    assert len(found) > 80, "the scan must actually find the codes"
    missing = {c: sorted(f) for c, f in found.items() if c not in error_catalog.CATALOG}
    assert not missing, f"add these codes to shared/error_catalog.py: {missing}"


def test_catalog_entries_use_the_closed_next_step_vocabulary():
    for code, (message, steps) in error_catalog.CATALOG.items():
        assert message and message != code, code
        assert set(steps) <= error_catalog.NEXT_STEPS, code


def test_the_frontend_labels_every_next_step():
    labels = REPO / "frontend" / "lib" / "admin-errors.ts"
    if not labels.exists():
        pytest.skip("frontend not mounted")
    text = labels.read_text()
    for step in error_catalog.NEXT_STEPS:
        assert re.search(rf"\b{step}\s*:", text), step


def test_detail_surfaces_a_wrapped_gate_as_cause():
    seen = datetime.utcnow() - timedelta(minutes=7)
    d = error_catalog.detail(
        "INVALID_CONFIGURATION",
        text="HOST_AGENT_NOT_READY",
        context={"host": "dev-host", "seen_at": seen},
    )
    assert d["code"] == "INVALID_CONFIGURATION"
    assert d["cause"] == "HOST_AGENT_NOT_READY"
    assert "há 7 minutos" in d["message"] and "dev-host" in d["message"]
    assert "journalctl -u ingestify-engine-host-agent" in d["message"]
    assert d["next_steps"] == ["check_host"]
    # Unknown free text stays visible as technical detail.
    d = error_catalog.detail("INVALID_OPERATION", text="A janela exige US$ 1.2")
    assert d["technical"] == "A janela exige US$ 1.2" and d["message"] != d["code"]


def test_enrich_keeps_code_and_extra_keys_and_ignores_plain_details():
    assert error_catalog.enrich("Engine not found") == "Engine not found"
    out = error_catalog.enrich({"code": "VERSION_CONFLICT", "current_version": 3})
    assert out["code"] == "VERSION_CONFLICT" and out["current_version"] == 3
    assert out["next_steps"] == ["reload"] and "Recarregue" in out["message"]
    unknown = {"code": "SOMETHING_ELSE", "message": "x"}
    assert error_catalog.enrich(unknown) == unknown


def test_guided_route_enriches_dependency_refusals():
    from api.error_guidance import GuidedRoute

    def deny():
        raise HTTPException(403, detail={"code": "ACCESS_DENIED"})

    router = APIRouter(route_class=GuidedRoute, dependencies=[Depends(deny)])

    @router.get("/x")
    def x():
        return {}

    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).get("/x").json()["detail"]
    assert body["code"] == "ACCESS_DENIED"
    assert body["message"] != "ACCESS_DENIED" and body["next_steps"] == ["request_access"]


def test_invoke_reports_adapter_gate_with_host_age(world):  # noqa: F811
    from api.engine_control_routes import invoke

    def refuse():
        raise error_catalog.Gate(
            "HOST_AGENT_NOT_READY",
            **error_catalog.host_context("h1", ControlHost(id="h1", inventory={}, seen_at=datetime.utcnow() - timedelta(minutes=12))),
        )

    with pytest.raises(HTTPException) as exc:
        invoke(refuse)
    d = exc.value.detail
    assert exc.value.status_code == 422
    assert (d["code"], d["cause"]) == ("INVALID_CONFIGURATION", "HOST_AGENT_NOT_READY")
    assert "há 12 minutos" in d["message"]
    # str() of the gate stays the bare code for callers that match on it.
    with pytest.raises(ValueError, match="^HOST_AGENT_NOT_READY$"):
        refuse()


@pytest.fixture
def modal(world):  # noqa: F811
    Session = world
    with Session() as db:
        db.add(
            Engine(
                id="m2",
                slug="modal_2",
                display_name="Modal 2",
                adapter_type="modal",
                status="active",
                config={"features": {"transcription": {"gpu_type": "L4", "workers": 1, "executions_per_worker": 1}}},
                deployments={"transcription": {"fingerprint": "f"}},
                credentials_sealed=b"sealed",
                limit_usd=10,
                min_remaining_usd=0,
                version=5,
            )
        )
        db.commit()
    return Session


def test_modal_without_profile_explains_setup_and_disables_unplannable_actions(modal):
    with modal() as db:
        caps = service.capabilities(db, db.get(Engine, "m2"), "transcription")
    actions = {a["type"]: a for a in caps["actions"]}
    assert actions["test"]["enabled"] and actions["reconcile"]["enabled"]
    assert actions["cooldown"]["reason"] == "NOTHING_TO_COOL_DOWN"
    for kind in ("deploy", "start", "warmup", "scale", "apply_profile", "restart", "drain_stop"):
        assert not actions[kind]["enabled"]
        assert actions[kind]["reason"] == "RUNTIME_PROFILE_REQUIRED"
        assert "transcription" in actions[kind]["message"]
        assert actions[kind]["next_steps"][0] == "test_connection"
    setup = caps["setup"]
    assert setup["code"] == "RUNTIME_PROFILE_REQUIRED"
    assert setup["profile_bound"] is False and setup["connection_verified"] is False
    assert setup["next_steps"] == ["test_connection", "bind_profile", "create_profile"]
    assert "Testar" in setup["message"]


def test_modal_verified_identity_drops_the_test_connection_step(modal):
    with modal() as db:
        e = db.get(Engine, "m2")
        e.config = dict(e.config, control_identity="ap-1")
        db.commit()
        caps = service.capabilities(db, e, "transcription")
    assert caps["setup"]["connection_verified"] is True
    assert caps["setup"]["next_steps"] == ["bind_profile", "create_profile"]


def _plan(kind):
    return PlanRequest(
        type=kind,
        feature="transcription",
        engine_version=5,
        max_usd=Decimal("0.10"),
        drain_timeout_seconds=900,
    )


def test_cooldown_without_profile_is_nothing_to_cool_down(modal):
    """The reported request: cooldown, transcription, no profile, no identity."""
    with modal() as db:
        with pytest.raises(service.ControlError) as exc:
            service.create_plan(db, db.get(Engine, "m2"), _plan("cooldown"), "root")
    assert (exc.value.code, exc.value.status) == ("NOTHING_TO_COOL_DOWN", 409)
    d = exc.value.detail()
    assert d["message"].startswith("Nada para liberar para transcription")
    assert d["next_steps"] == ["test_connection", "bind_profile"]


def test_operations_without_profile_keep_the_code_and_gain_guidance(modal):
    with modal() as db:
        with pytest.raises(service.ControlError) as exc:
            service.create_plan(db, db.get(Engine, "m2"), _plan("scale"), "root")
    assert (exc.value.code, exc.value.status) == ("RUNTIME_PROFILE_REQUIRED", 422)
    assert str(exc.value) == "RUNTIME_PROFILE_REQUIRED"
    d = exc.value.detail()
    assert d["message"].startswith(
        "Esta engine ainda não tem perfil de execução vinculado para transcription."
    )
    assert d["next_steps"] == ["test_connection", "bind_profile", "create_profile"]


def test_http_plan_refusal_carries_message_and_next_steps(modal):
    from api.engine_control_routes import invoke

    with modal() as db:
        with pytest.raises(HTTPException) as exc:
            invoke(service.create_plan, db, db.get(Engine, "m2"), _plan("cooldown"), "root")
    body = json.loads(json.dumps(exc.value.detail))
    assert body["code"] == "NOTHING_TO_COOL_DOWN" and body["message"] != body["code"]


# -- host scripts (the agent runs on the host, outside the backend package) ----------


def _scripts():
    import sys

    path = str(REPO / "scripts")
    if not (REPO / "scripts" / "engine_host_agent.py").exists():
        pytest.skip("scripts not mounted")
    if path not in sys.path:
        sys.path.insert(0, path)


def test_agent_logs_the_refusal_code_with_a_hint_and_never_the_token():
    _scripts()
    import io
    import urllib.error
    from engine_host_agent import describe_failure

    line = describe_failure(ValueError("REGISTERED_MANIFEST_CHANGED"))
    assert line.startswith("ValueError: REGISTERED_MANIFEST_CHANGED") and "re-register" in line
    http = urllib.error.HTTPError(
        "u", 403, "Forbidden", {}, io.BytesIO(b'{"detail":{"code":"HOST_IDENTITY_REQUIRED"}}')
    )
    assert "HTTP 403 HOST_IDENTITY_REQUIRED" in describe_failure(http)
    assert "s3cr3t-token" not in describe_failure(RuntimeError("boom s3cr3t-token"), "s3cr3t-token")


def test_register_rewrites_identities_in_place_keeping_mode(tmp_path):
    _scripts()
    import os
    from register_engine_host import write_identities

    path = tmp_path / "ids.json"
    path.write_text("{}")
    os.chmod(path, 0o640)
    inode = path.stat().st_ino
    write_identities(path, {"h": "x" * 64})
    assert json.loads(path.read_text()) == {"h": "x" * 64}
    assert (path.stat().st_mode & 0o777, path.stat().st_ino) == (0o640, inode)
    fresh = tmp_path / "new.json"
    write_identities(fresh, {})
    assert fresh.stat().st_mode & 0o777 == 0o600


def test_register_keeps_a_backup_and_never_leaves_temp_files(tmp_path):
    _scripts()
    import os
    from register_engine_host import write_identities

    path = tmp_path / "ids.json"
    path.write_text('{"old": "' + "a" * 64 + '"}')
    os.chmod(path, 0o640)
    inode = path.stat().st_ino
    write_identities(path, {"old": "a" * 64, "new": "b" * 64})
    backup = tmp_path / "ids.json.bak"
    assert json.loads(backup.read_text()) == {"old": "a" * 64}
    assert backup.stat().st_mode & 0o777 == 0o640
    # A shorter rewrite leaves no stale tail behind (write + truncate, same inode).
    write_identities(path, {})
    assert path.read_text() == "{}" and path.stat().st_ino == inode
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ids.json", "ids.json.bak"]
    # Invalid input never touches the target.
    with pytest.raises((ValueError, TypeError)):
        write_identities(path, ["not", "an", "object"])
    with pytest.raises((ValueError, TypeError)):
        write_identities(path, {"h": object()})
    assert path.read_text() == "{}"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ids.json", "ids.json.bak"]


def test_register_creates_a_new_identities_file_exclusively_with_the_group(tmp_path):
    _scripts()
    import os
    from register_engine_host import write_identities

    fresh = tmp_path / "new.json"
    write_identities(fresh, {"h": "x" * 64}, group=os.getgid())
    assert fresh.stat().st_mode & 0o777 == 0o640 and fresh.stat().st_gid == os.getgid()
    assert not (tmp_path / "new.json.bak").exists()


def test_host_identity_retries_once_on_a_partial_identities_file(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    from fastapi import HTTPException
    from api import engine_control_routes as routes

    token = "t" * 40
    good = json.dumps({"host-1": hashlib.sha256(token.encode()).hexdigest()})
    path = tmp_path / "ids.json"
    path.write_text(good)
    settings = SimpleNamespace(engine_control_enabled=True, engine_host_identities_file=str(path))
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "IDENTITIES_RETRY_SECONDS", 0)
    request = SimpleNamespace(headers={"x-engine-host-token": token})
    reads = []
    real = Path.read_text

    def flaky(self, *a, **k):
        reads.append(self)
        return good[: len(good) // 2] if len(reads) == 1 else real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert routes.host_identity("host-1", request) == "host-1" and len(reads) == 2
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: good[:5])
    with pytest.raises(HTTPException) as exc:
        routes.host_identity("host-1", request)
    assert exc.value.detail == {"code": "HOST_IDENTITY_REQUIRED"}
