from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from shared.database import Base
from shared.models import Engine
from shared.engine_control import service, registry, admission
from shared.engine_control.models import (
    ControlResource,
    EngineOperation,
    OperationPlan,
    OperationEvent,
    OperationOutbox,
    RuntimeProfile,
    ControlHost,
)
from shared.engine_control.contracts import PlanRequest
from shared.config import get_settings
from shared.engines import budget, store


class VMAdapter:
    def validate(self, engine, feature, p, db):
        assert p["provider_settings"] == {"zone": "test-a"}
        return p

    def resource_keys(self, engine, feature, p):
        return ["vm:test-account:allocation-one"]

    def plan(self, engine, req, p, db):
        return {
            "stages": ["allocating", "booting"],
            "drain": True,
            "destructive": True,
            "estimated_max_usd": "0.1",
        }


@pytest.fixture
def world(monkeypatch):
    e = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(e)
    Session = sessionmaker(bind=e)
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)
    d = dict(
        type="test-vm",
        actions=["scale", "drain_stop"],
        features=["transcription"],
        execution_mode="remote_runner",
        credential_fields=[],
        fields=[],
        provider_fields=[],
    )
    registry.register("test-vm", d, VMAdapter)
    with Session() as db:
        db.add(
            Engine(
                id="e",
                slug="test-vm",
                display_name="VM",
                adapter_type="test-vm",
                config={"features": {}},
                deployments={},
                limit_usd=10,
                min_remaining_usd=0,
                version=0,
            )
        )
        db.commit()
    yield Session
    registry._registry.pop(("test-vm", 1))
    e.dispose()


def profile():
    return dict(
        adapter_version=1,
        schema_version=1,
        binding={"workers": 2, "executions_per_worker": 1},
        model_profile_id="test-model",
        desired_replicas=1,
        max_replicas=2,
        min_ready_replicas=0,
        idle_timeout_seconds=60,
        warmup_mode="manual",
        provider_settings={"zone": "test-a"},
    )


def prepared(Session):
    with Session() as db:
        saved = service.save_profile(
            db, db.get(Engine, "e"), "transcription", profile(), 0, "admin"
        )
        e = db.get(Engine, "e")
        assert e.config["features"] == {}, "desired must not alter effective binding"
        p = service.create_plan(
            db,
            e,
            PlanRequest(
                type="scale",
                engine_version=e.version,
                profile_revision=saved["revision"],
                max_usd="0.1",
            ),
            "admin",
        )
        return p


def test_third_adapter_desired_plan_outbox_idempotence_budget(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        replay = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        assert replay["operation_id"] == op["operation_id"]
        assert db.query(OperationOutbox).count() == 1
        assert budget.reserved(
            db, "e", budget.period_start(db.get(Engine, "e"), datetime.utcnow())
        ) == Decimal("0.1")
        assert (
            db.get(ControlResource, "vm:test-account:allocation-one").operation_id
            == op["operation_id"]
        )
        with pytest.raises(service.ControlError, match="IDEMPOTENCY_CONFLICT"):
            service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", False)


def test_stale_preview_and_conflicting_alias(world):
    p = prepared(world)
    with world() as db:
        e = db.get(Engine, "e")
        e.version += 1
        db.commit()
        with pytest.raises(service.ControlError, match="PLAN_STALE"):
            service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        db.rollback()
        db.add(
            Engine(
                id="alias",
                slug="alias",
                display_name="Alias",
                adapter_type="test-vm",
                config={},
                deployments={},
                version=0,
            )
        )
        db.commit()
        with pytest.raises(service.ControlError, match="RESOURCE_OWNED"):
            service.save_profile(
                db, db.get(Engine, "alias"), "transcription", profile(), 0, "admin"
            )


def test_old_executor_cannot_publish_and_crash_never_replays_effect(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        assert service.claim(db, op["operation_id"], "two") is None
        service.event(db, op["operation_id"], gen, "deploying", effect=True)
        row = db.get(EngineOperation, op["operation_id"])
        row.lease_until = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        assert service.claim(db, op["operation_id"], "two") is None
        assert db.get(EngineOperation, op["operation_id"]).state == "needs_attention"
        with pytest.raises(service.ControlError, match="LEASE_LOST"):
            service.finish(db, op["operation_id"], gen, "succeeded", safe=True)
        assert (
            db.get(ControlResource, p["resources"][0]).operation_id
            == op["operation_id"]
        )


def test_gate_and_tickets_share_resource_authority(world):
    p = prepared(world)
    ids = admission.acquire("transcription", "existing", "e", world)
    assert len(ids) == 1
    with world() as db:
        row = db.get(ControlResource, p["resources"][0])
        row.gate_closed = True
        db.commit()
    with pytest.raises(service.ControlError, match="ENGINE_MAINTENANCE"):
        admission.acquire("transcription", "new", "e", world)
    admission.release(ids, world)
    with world() as db:
        from shared.engine_control.models import ControlAdmission

        assert (
            db.query(ControlAdmission)
            .filter(ControlAdmission.released_at.is_(None))
            .count()
            == 0
        )


def test_cancel_before_effect_restores_gate_and_releases_reserve(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        r = db.get(ControlResource, p["resources"][0])
        r.gate_closed = True
        db.commit()
        service.request_cancel(db, op["operation_id"])
        result = service.finish(db, op["operation_id"], gen, "cancelled", safe=True)
        assert Decimal(result["reserved_usd"]) == 0
        assert not r.gate_closed and not r.operation_id


def test_redaction_and_bounds_before_persistence(world):
    from shared.engines.redact import register_secret

    secret = "secret-value-registered-987654321"
    register_secret(secret)
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.event(
            db,
            op["operation_id"],
            gen,
            "build",
            {"message": secret + "\x1b[31m", "token": secret},
            kind="log",
        )
        data = service.events(db, op["operation_id"])
        assert secret not in str(data)
        assert "token" not in str(data)
        db.get(EngineOperation, op["operation_id"]).log_bytes = 1048576
        db.commit()
        n = db.query(OperationEvent).count()
        service.event(
            db, op["operation_id"], gen, "build", {"message": "suppressed"}, kind="log"
        )
        assert db.query(OperationEvent).count() == n
        service.event(
            db, op["operation_id"], gen, "verifying", {"message": "preserved"}
        )
        assert db.query(OperationEvent).count() == n + 1


def test_legacy_writer_cannot_bypass_managed_profile(world):
    prepared(world)
    with world() as db:
        from shared.engines.capacity import Binding

        with pytest.raises(store.VersionConflict, match="RUNTIME_OPERATION_REQUIRED"):
            store.set_binding(
                db,
                db.get(Engine, "e"),
                "transcription",
                Binding(workers=3),
                version=1,
                actor_user_id="admin",
                auth_method="jwt",
            )


def test_streamed_secret_split_across_chunks_is_never_persisted(tmp_path):
    import sys
    from workers.engine_control.process import stream_run
    from shared.engines.redact import register_secret

    value = "registered-long-secret-abcdef12345"
    register_secret(value)

    class C:
        lines = []

        def check(self):
            pass

        def log(self, line):
            self.lines.append(line)

    c = C()
    result = stream_run(
        [
            sys.executable,
            "-c",
            "import sys,time;sys.stdout.write('registered-long-');sys.stdout.flush();time.sleep(.1);print('secret-abcdef12345')",
        ],
        env={},
        cwd=str(tmp_path),
        context=c,
    )
    assert result.returncode == 0
    assert value not in str(c.lines)
    assert "[REDACTED]" in str(c.lines)


def test_pool_stats_sdk_compatibility_never_invents_zero():
    from types import SimpleNamespace
    from workers.engine_control.modal import pool_count

    assert pool_count(SimpleNamespace(num_total_runners=2)) == 2
    assert pool_count(SimpleNamespace(num_total_containers=3)) == 3
    with pytest.raises(RuntimeError, match="OBSERVATION_UNAVAILABLE"):
        pool_count(SimpleNamespace())


def test_dynamic_policy_does_not_invalidate_control_deployment():
    from shared.engines.capacity import Binding, deploy_state

    old = Binding(workers=1, gpu_type="L4")
    new = Binding(workers=3, gpu_type="L4")
    deployed = {
        "transcription": {
            "binding": old.model_dump(exclude_none=True),
            "fingerprint": "code",
            "control_protocol": 1,
        }
    }
    assert deploy_state("modal", deployed, "transcription", new, "code") == "deployed"
    assert (
        deploy_state("modal", deployed, "transcription", new, "new-code")
        == "needs_redeploy"
    )
    legacy = {
        "transcription": {
            "binding": old.model_dump(exclude_none=True),
            "fingerprint": "code",
        }
    }
    assert (
        deploy_state("modal", legacy, "transcription", new, "code") == "needs_redeploy"
    )


def test_paid_pool_credential_delete_guard(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        row = db.get(EngineOperation, op["operation_id"])
        row.state = "succeeded"
        row.handles = {"maintenance": {"cleanup_required": True}}
        db.get(ControlResource, p["resources"][0]).operation_id = None
        db.commit()
        with pytest.raises(store.VersionConflict, match="CLEANUP_CREDENTIAL_REQUIRED"):
            store.clear_credentials(
                db,
                db.get(Engine, "e"),
                version=1,
                actor_user_id="admin",
                auth_method="jwt",
            )


def test_admin_api_jwt_only_and_non_admin_denied(world):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from api.engine_control_routes import router
    from shared.database import get_db
    from shared.auth import get_current_active_user

    app = FastAPI()
    app.include_router(router)

    def db_override():
        with world() as db:
            yield db

    user = SimpleNamespace(id="admin", is_admin=True, is_active=True)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = lambda: user
    with TestClient(app) as c:
        path = "/admin/engines/e/capabilities"
        assert c.get(path, headers={"X-API-Key": "a-key"}).status_code == 403
        assert c.get(path).status_code == 403
        assert (
            c.get(path, headers={"Authorization": "Bearer test-session"}).status_code
            == 200
        )
        user.is_admin = False
        assert (
            c.get(path, headers={"Authorization": "Bearer test-session"}).status_code
            == 403
        )


def test_finished_operation_does_not_erase_uncertain_financial_exposure(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.event(db, op["operation_id"], gen, "scaling", effect=True)
        finished = service.finish(
            db, op["operation_id"], gen, "succeeded", {"replicas_alive": 2}, safe=True
        )
        assert Decimal(finished["reserved_usd"]) == Decimal("0.1")
        assert not finished["cost_confirmed"]
        assert db.get(ControlResource, p["resources"][0]).operation_id is None


def test_runtime_contract_rejects_nested_extra_fields():
    from pydantic import ValidationError
    from shared.engine_control.contracts import RuntimeSettings

    raw = profile()
    raw["binding"]["command"] = "arbitrary shell"
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(raw)
    from shared.engine_control.contracts import utc_deadline

    assert utc_deadline("2026-10-06T15:00:00-03:00") == datetime(2026, 10, 6, 18, 0)
    raw = profile()
    raw["warm_until"] = "2026-10-06T15:00:00"
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(raw)


def test_provider_catalog_is_exposed_without_new_api_conditionals(world):
    from shared.engine_control import catalog
    from api.engine_admin_routes import list_engine_adapters
    import asyncio

    custom = dict(
        id="vm-profile",
        title="Approved VM model",
        feature="transcription",
        adapters=["test-vm"],
        approved=True,
        model="approved-model",
        footprint_gb=None,
    )
    registry.descriptor("test-vm")["model_profiles"] = [custom]
    assert catalog.get("vm-profile", "test-vm", "transcription") == custom
    metadata = asyncio.run(list_engine_adapters(admin_user=None))
    assert any(item["type"] == "test-vm" for item in metadata)


def test_uncertain_effect_prevents_new_desired_revision(world):
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.event(db, op["operation_id"], gen, "applying", effect=True)
        service.finish(db, op["operation_id"], gen, "needs_attention", safe=False)
        with pytest.raises(service.ControlError, match="RESOURCE_LOCKED"):
            service.save_profile(
                db, db.get(Engine, "e"), "transcription", profile(), 1, "admin"
            )


def test_stop_publishes_zero_capacity_and_refuses_direct_admission(world):
    prepared(world)
    with world() as db:
        e = db.get(Engine, "e")
        p = service.create_plan(
            db,
            e,
            PlanRequest(type="drain_stop", engine_version=e.version, max_usd="0.1"),
            "admin",
        )
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "stop", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.event(db, op["operation_id"], gen, "applying", effect=True)
        service.publish_applied(
            db, op["operation_id"], gen, {"replicas_alive": 0, "ready_replicas": 0}
        )
        service.finish(db, op["operation_id"], gen, "succeeded", safe=True)
        assert db.get(Engine, "e").config["features"]["transcription"]["workers"] == 0
        assert (
            service.latest_profile(db, "e", "transcription").profile["binding"][
                "workers"
            ]
            == 2
        )
        assert admission.placement_blocked(db, db.get(Engine, "e"), "transcription")
    with pytest.raises(service.ControlError, match="ENGINE_NOT_RUNNING"):
        admission.acquire("transcription", "direct-legacy", "e", world)


def test_recovery_requires_neutralized_executor_and_never_repeats_apply(
    world, monkeypatch
):
    from workers.engine_control.runner import run

    calls = []

    class Recoverable(VMAdapter):
        def apply(self, plan, ctx):
            calls.append("apply")
            raise AssertionError("An external effect must never be replayed")

        def observe(self, engine, feature, p, ctx):
            calls.append("observe")
            return {"replicas_alive": 1, "ready_replicas": 1}

        def reconcile(self, op, observed):
            return {"desired_applied": True, "safe_to_unlock": True}

    registry.register("test-vm", registry.descriptor("test-vm"), Recoverable)
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.event(db, op["operation_id"], gen, "applying", effect=True)
        service.finish(db, op["operation_id"], gen, "needs_attention", safe=False)
        with pytest.raises(service.ControlError, match="EXECUTOR_NOT_NEUTRALIZED"):
            service.request_recovery(db, op["operation_id"])
        row = db.get(EngineOperation, op["operation_id"])
        row.handles = {"executor_exited": True}
        db.commit()
        service.request_recovery(db, op["operation_id"])
    run(op["operation_id"], world)
    with world() as db:
        row = db.get(EngineOperation, op["operation_id"])
        assert row.state == "succeeded" and row.generation == gen + 1
        assert calls == ["observe"]
        assert db.get(ControlResource, p["resources"][0]).operation_id is None
        assert (
            not row.cost_confirmed
        ), "Recovery cannot invent provider billing confirmation"
