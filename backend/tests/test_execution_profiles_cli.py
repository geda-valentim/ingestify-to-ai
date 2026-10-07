"""Admission/fencing at actual Modal CLI and RPC boundaries, using a fake SDK."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from shared.access import legacy, policy, service
from shared.access.models import AuthorizationEpoch, EffectAdmission, ServicePrincipal
from shared.config import get_settings
from shared.engine_control import registry, service as control
from shared.engine_control.models import ControlResource, EngineOperation, OperationPlan
from shared.models import Engine, AdminAudit
from workers.engines import modal_deploy, remote
from workers.engines.modal_apps import protocol
from tests.test_execution_profiles import world, grant, constraints, RESOURCE
from tests.test_execution_profiles_migration import mysql_world

PRINCIPAL = "test-installation-principal"


@pytest.fixture(params=["sqlite", "mysql"])
def modal_world(request, world, monkeypatch):
    factory = (
        world if request.param == "sqlite" else request.getfixturevalue("mysql_world")
    )
    calls, available = [], []
    hooks = {"build": None, "meta": None, "record": None, "admit_build": None}
    fingerprint = "fake-reviewed-artifact"
    spec = {
        "decorator": {"gpu": "L4", "max_containers": 1},
        "fingerprint": fingerprint,
        "protocol": protocol.PROTOCOL_VERSION,
    }
    with factory() as db:
        e = db.get(Engine, "engine-a")
        e.adapter_type = "modal"
        e.config = {
            "features": {
                "transcription": {
                    "workers": 1,
                    "executions_per_worker": 1,
                    "gpu_type": "L4",
                }
            }
        }
        db.add(ServicePrincipal(id=PRINCIPAL, purpose="installation_cli", active=True))
        db.commit()
    monkeypatch.setattr(get_settings(), "engine_installation_principal_id", PRINCIPAL)
    context_token = legacy.installation_context.set(PRINCIPAL)

    def assert_available(stage):
        # A separate InnoDB connection would time out if the CLI kept its epoch
        # or principal lock across build or an SDK call.
        with factory() as db:
            if db.get_bind().dialect.name == "mysql":
                db.execute(text("SET SESSION innodb_lock_wait_timeout=1"))
            policy.epoch(db, True)
            db.query(ServicePrincipal).filter_by(id=PRINCIPAL).with_for_update().one()
            db.commit()
        available.append(stage)

    class SDK:
        def subprocess_env(self, home, extra):
            return dict(extra)

        def deployed_meta(self):
            assert_available("meta")
            calls.append("meta")
            if hooks["meta"]:
                hooks["meta"]()
            return {"fingerprint": fingerprint, "protocol": protocol.PROTOCOL_VERSION}

        def record_deployment(self, record):
            assert_available("record")
            calls.append("record")
            if hooks["record"]:
                hooks["record"]()

    sdk = SDK()
    original_create = registry.create

    def create(adapter, *args, **kwargs):
        if adapter == "modal":
            return SimpleNamespace(
                resource_keys=lambda engine, feature, profile: [RESOURCE]
            )
        return original_create(adapter, *args, **kwargs)

    def fake_plan(engine, feature):
        return {
            "engine": engine.slug,
            "feature": feature,
            "binding": engine.config["features"][feature],
            "spec": spec,
            "hashed": True,
            "command": "fake modal deploy",
        }

    def open_credentials(engine):
        # The engine must remain readable after SQL commit/expunge.
        assert engine.slug == "engine-a" and engine.adapter_type == "modal"
        assert engine.config["features"]["transcription"]["workers"] == 1
        return {}

    def run(*args, **kwargs):
        if hooks["admit_build"]:
            hooks["admit_build"]()
        assert_available("build")
        calls.append("build")
        if hooks["build"]:
            hooks["build"]()
        return SimpleNamespace(returncode=0, stdout="fake build complete", stderr="")

    monkeypatch.setattr(registry, "create", create)
    monkeypatch.setattr(modal_deploy, "plan", fake_plan)
    monkeypatch.setattr(remote, "open_credentials", open_credentials)
    monkeypatch.setattr(remote, "adapter_factory", lambda engine, credentials: sdk)
    yield SimpleNamespace(
        Session=factory,
        calls=calls,
        hooks=hooks,
        run=run,
        available=available,
        fingerprint=fingerprint,
        dialect=request.param,
    )
    legacy.installation_context.reset(context_token)


def deploy(env, **kwargs):
    return modal_deploy.deploy(
        "engine-a",
        session_factory=env.Session,
        run=env.run,
        out=lambda line: None,
        **kwargs
    )


def revoke_principal(env):
    with env.Session() as db:
        authority = policy.epoch(db, True)
        db.query(ServicePrincipal).filter_by(
            id=PRINCIPAL
        ).with_for_update().one().active = False
        authority.version += 1
        db.commit()


def test_cli_success_releases_sql_before_sdk_and_confirms_fences_atomically(
    modal_world,
):
    env = modal_world
    result = deploy(env)
    assert result["fingerprint"] == env.fingerprint
    assert env.calls == ["build", "meta", "record"]
    assert env.available == env.calls
    with env.Session() as db:
        rows = db.query(EffectAdmission).all()
        assert {r.step for r in rows} == {"cli:deploy", "cli:meta", "cli:record"}
        assert {r.state for r in rows} == {"confirmed"}
        assert {r.actor_id for r in rows} == {PRINCIPAL}
        assert all(
            r.action == "deploy"
            and r.targets == [RESOURCE]
            and r.valid_until > r.created_at
            for r in rows
        )
        assert all(r.decision == {"installation_principal": PRINCIPAL} for r in rows)
        resource = db.get(ControlResource, RESOURCE)
        assert resource.operation_id is None and not resource.gate_closed
        e = db.get(Engine, "engine-a")
        assert (
            e.version == 1
            and e.deployments["transcription"]["fingerprint"] == env.fingerprint
        )
        assert (
            db.query(AdminAudit).filter_by(action="engine.cli_deploy_admitted").count()
            == 1
        )


@pytest.mark.parametrize("revoke_at", ["build", "meta"])
def test_cli_revocation_stops_next_rpc_and_preserves_uncertain_locks(
    modal_world, revoke_at
):
    env = modal_world
    env.hooks[revoke_at] = lambda: revoke_principal(env)
    with pytest.raises(control.ControlError, match="INSTALLATION_PRINCIPAL_REQUIRED"):
        deploy(env)
    assert env.calls == (["build"] if revoke_at == "build" else ["build", "meta"])
    with env.Session() as db:
        resource = db.get(ControlResource, RESOURCE)
        operation_id = resource.operation_id
        assert operation_id and resource.gate_closed
        assert db.get(Engine, "engine-a").deployments == {}
        assert {r.state for r in db.query(EffectAdmission)} == {"uncertain"}
        assert db.query(EffectAdmission).count() == (1 if revoke_at == "build" else 2)
        db.get(ServicePrincipal, PRINCIPAL).active = True
        db.commit()
    # Restoring installation authority cannot replay an uncertain physical effect.
    with pytest.raises(Exception, match="RESOURCE_LOCKED|OPERATION_CONFLICT"):
        deploy(env)
    with env.Session() as db:
        with pytest.raises(control.ControlError, match="RESOURCE_LOCKED"):
            legacy.admit_cli_deploy(db, db.get(Engine, "engine-a"), "transcription")
        db.rollback()
        assert db.get(ControlResource, RESOURCE).operation_id == operation_id


def operation(env, action="deploy"):
    with env.Session() as db:
        g = grant(db, scope=constraints(adapters=["modal"]))
        body = {
            "type": action,
            "feature": "transcription",
            "engine_id": "engine-a",
            "profile": {},
            "resources": [RESOURCE],
            "max_usd": "0.1",
            "authorization": {"grant_id": g["id"]},
        }
        plan = OperationPlan(
            engine_id="engine-a",
            actor_id="operator",
            engine_version=0,
            body=body,
            hash=control.digest(body),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(plan)
        db.flush()
        op = EngineOperation(
            engine_id="engine-a",
            actor_id="operator",
            plan_id=plan.id,
            idempotency_key=str(uuid4()),
            request_hash="test",
            state="running",
            generation=1,
            holder="fake-executor",
            lease_until=datetime.utcnow() + timedelta(minutes=5),
            deadline=datetime.utcnow() + timedelta(minutes=10),
        )
        db.add(op)
        db.flush()
        db.get(ControlResource, RESOURCE).operation_id = op.id
        db.get(ControlResource, RESOURCE).gate_closed = True
        op_id = op.id
        db.commit()

    def admit(step):
        with env.Session() as db:
            control.admit_effect(db, op_id, 1, step)
            db.commit()

    env.hooks["admit_build"] = lambda: admit("deploy:build")
    return g, op_id, admit


@pytest.mark.parametrize("revoke_at", ["build", "meta"])
def test_operation_revocation_reauthorizes_before_each_modal_rpc(
    modal_world, revoke_at
):
    env = modal_world
    g, op_id, admit = operation(env)

    def revoke():
        with env.Session() as db:
            service.revoke(db, g["id"], 0, "bootstrap")

    env.hooks[revoke_at] = revoke
    with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
        deploy(env, operation_id=op_id, effect_admission=admit)
    assert env.calls == (["build"] if revoke_at == "build" else ["build", "meta"])
    with env.Session() as db:
        rows = db.query(EffectAdmission).all()
        expected = (
            {"deploy:build"}
            if revoke_at == "build"
            else {"deploy:build", "deploy:meta"}
        )
        assert {r.step for r in rows} == expected
        assert all(
            r.actor_id == "operator"
            and r.targets == [RESOURCE]
            and r.action == "deploy"
            for r in rows
        )
        assert {r.state for r in rows} == {"uncertain"}
        assert db.get(ControlResource, RESOURCE).operation_id == op_id
        assert db.get(Engine, "engine-a").deployments == {}


def test_operation_requires_effect_callback_before_build(modal_world):
    env = modal_world
    _, op_id, _ = operation(env)
    with pytest.raises(
        modal_deploy.DeployError, match="OPERATION_EFFECT_ADMISSION_REQUIRED"
    ):
        deploy(env, operation_id=op_id)
    assert env.calls == []


@pytest.mark.parametrize(
    "change", ["after_connection", "during_hydrate", "generation", "cancel", "deadline"]
)
def test_modal_identity_hydration_and_publication_keep_current_authority(
    modal_world, monkeypatch, change
):
    from workers.engine_control.modal import ModalControlAdapter
    from workers.engine_control.runner import Cancelled
    from workers.engines import remote_tasks

    env = modal_world
    g, op_id, admit = operation(env, action="test")
    calls = []

    def mutate():
        with env.Session() as db:
            if change in ("after_connection", "during_hydrate"):
                service.revoke(db, g["id"], 0, "bootstrap")
            else:
                op = db.get(EngineOperation, op_id)
                if change == "generation":
                    op.generation += 1
                if change == "cancel":
                    op.cancel_requested = True
                if change == "deadline":
                    op.deadline = datetime.utcnow() - timedelta(seconds=1)
                db.commit()

    def connection(*args, **kwargs):
        calls.append("connection")
        if change == "after_connection":
            mutate()
        return {"ok": True}

    def hydrate(**kwargs):
        calls.append("hydrate")
        mutate()
        return SimpleNamespace(object_id="must-not-be-published")

    sdk = SimpleNamespace(
        client=lambda: object(), _state=lambda: SimpleNamespace(hydrate=hydrate)
    )
    monkeypatch.setattr(remote_tasks, "test_engine_now", connection)
    monkeypatch.setattr(ModalControlAdapter, "_adapter", lambda self, engine: sdk)
    ctx = SimpleNamespace(
        Session=env.Session, op_id=op_id, generation=1, admit_effect=admit
    )
    with env.Session() as db:
        body = db.get(OperationPlan, db.get(EngineOperation, op_id).plan_id).body
    expected = (
        Cancelled
        if change == "cancel"
        else TimeoutError if change == "deadline" else control.ControlError
    )
    with pytest.raises(expected):
        ModalControlAdapter().apply(body, ctx)
    assert calls == (
        ["connection"] if change == "after_connection" else ["connection", "hydrate"]
    )
    with env.Session() as db:
        engine = db.get(Engine, "engine-a")
        assert engine.version == 0 and "control_identity" not in engine.config
        assert db.get(ControlResource, RESOURCE).operation_id == op_id
        admissions = db.query(EffectAdmission).all()
        assert {a.state for a in admissions} == {"uncertain"}
        assert {a.step for a in admissions} == (
            {"test:connection"}
            if change == "after_connection"
            else {"test:connection", "test:identity"}
        )
