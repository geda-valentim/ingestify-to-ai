"""Spec 0020: default execution profiles created by the root at installation.

Runs on a throwaway SQLite database with the real local/Modal descriptors and
drivers; nothing calls Docker, Modal or a paid service.
"""

import asyncio
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared import rate_limit, root
from shared.config import get_settings
from shared.database import Base
from shared.models import ROOT_SLOT, AdminAudit, Engine, EngineUsage, User
from shared.access import contracts as C, policy, seed, service
from shared.access.models import (
    AuthorizationEpoch,
    EffectAdmission,
    EngineAttributes,
    ExecutionProfile,
    ExecutionRevision,
)
from shared.engine_control import catalog
from shared.engine_control import service as control
from shared.engine_control.models import (
    ControlAdmission,
    ControlHost,
    EngineOperation,
    OperationOutbox,
    OperationPlan,
    RuntimeProfile,
)
from shared.engines.capacity import Binding

MODAL_BINDING = {"gpu_type": "L4", "workers": 2, "executions_per_worker": 1}
LOCAL_BINDING = {"gpu_ref": "gpu0", "workers": 1, "executions_per_worker": 1}
INVENTORY = {
    "services": ["worker", "worker-audio", "worker-vision", "worker-live"],
    "gpu_uuids": ["GPU-1"],
    "manifest_hash": "manifest-1",
}


def _engine(id, adapter, features, **config):
    return Engine(
        id=id,
        slug=id,
        display_name=id,
        adapter_type=adapter,
        config={"features": features, **config},
        deployments={},
        version=0,
        limit_usd=10,
        min_remaining_usd=0,
    )


@pytest.fixture(autouse=True)
def _fresh_host_rate_limit():
    seed._host_seeded_at.clear()
    yield
    seed._host_seeded_at.clear()


@pytest.fixture
def Session(monkeypatch):
    sql = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(sql)
    factory = sessionmaker(bind=sql)
    s = get_settings()
    monkeypatch.setattr(s, "engine_access_enabled", True)
    monkeypatch.setattr(s, "iam_mode", "enforce")
    monkeypatch.setattr(s, "admin_user_ids", "")
    monkeypatch.setattr(s, "environment", "development")
    monkeypatch.setattr(s, "whisper_model", "turbo")
    monkeypatch.setattr(s, "audio_transcriber_provider", "faster-whisper")
    monkeypatch.setattr(s, "live_transcription_enabled", False)
    with factory() as db:
        db.add(AuthorizationEpoch(id=1, version=0))
        db.add(
            User(
                id="root",
                username="root",
                email="root@example.test",
                hashed_password="unused",
                is_admin=True,
                is_active=True,
                root_slot=ROOT_SLOT,
            )
        )
        db.add(
            User(
                id="plain",
                username="plain",
                email="plain@example.test",
                hashed_password="unused",
                is_active=True,
            )
        )
        db.add(
            _engine(
                "local",
                "local",
                {"transcription": dict(LOCAL_BINDING)},
                gpus=[{"ref": "gpu0", "name": "GPU", "uuid": "GPU-1", "vram_gb": 16}],
            )
        )
        db.add(
            _engine(
                "modal_1",
                "modal",
                {"transcription": dict(MODAL_BINDING)},
                control_identity="ap-1",
            )
        )
        db.add(_engine("modal_2", "modal", {"transcription": dict(MODAL_BINDING)}))
        db.add(_engine("modal_3", "modal", {}))
        db.add(ControlHost(id="host-1", inventory=INVENTORY, seen_at=datetime.utcnow()))
        db.commit()
    yield factory
    sql.dispose()


def run(Session, **kw):
    with Session() as db:
        return seed.seed_execution_profiles(db, actor_id="root", **kw)


def profiles(db):
    return {p.name: p for p in db.query(ExecutionProfile)}


def latest(db, p):
    return db.get(ExecutionRevision, p.latest_published_revision_id)


def set_(binding):
    return {k: v for k, v in binding.items() if v is not None}


def keys(report):
    return [(r["key"], r["stage"], r["reason"]) for r in report.skipped]


def physical_rows(db):
    return [
        db.query(m).count()
        for m in (
            OperationPlan,
            EngineOperation,
            OperationOutbox,
            ControlAdmission,
            EffectAdmission,
            EngineUsage,
        )
    ]


def approved_catalog():
    return [
        (m, a) for m in catalog.profiles() if m["approved"] for a in m["adapters"]
    ]


# --- CA1 ----------------------------------------------------------------------------------------


def test_every_approved_catalog_model_gets_a_published_default_profile(Session):
    report = run(Session)
    with Session() as db:
        by_name = profiles(db)
        for m, adapter in approved_catalog():
            p = by_name[f"Padrão — {m['title']}"]
            assert (p.status, p.adapter_type, p.feature) == (
                "published",
                adapter,
                m["feature"],
            )
            assert p.created_by == "root" and p.environment == "development"
            s = latest(db, p).settings
            assert s["model_profile_id"] == m["id"]
            assert s["min_ready_replicas"] == 0 and s["memory_mb"] is None
            assert s["binding"]["workers"] == s["max_replicas"] == 1
            assert s["binding"].get("cpu") is None
            if adapter == "local":
                assert s["provider_settings"] == {"host_id": "host-1"}
            else:
                assert s["provider_settings"] == {}
                assert s["binding"]["gpu_type"] == "L4"
    unapproved = {f"catalog:{m['id']}:{a}" for m in catalog.profiles() if not m["approved"] for a in m["adapters"]}
    assert unapproved  # live-local with live transcription off
    assert {r["key"] for r in report.skipped if r["reason"] == "MODEL_NOT_APPROVED"} == unapproved


def test_a_fresh_install_without_a_host_agent_skips_local_catalog_profiles(Session):
    with Session() as db:
        db.query(ControlHost).delete()
        db.commit()
    report = run(Session)
    locals_ = {f"catalog:{m['id']}:local" for m, a in approved_catalog() if a == "local"}
    assert locals_ <= {r["key"] for r in report.skipped if r["reason"] == "NO_REGISTERED_HOST"}
    with Session() as db:
        assert {p.adapter_type for p in db.query(ExecutionProfile)} == {"modal"}
        db.add(ControlHost(id="host-2", inventory=INVENTORY, seen_at=datetime.utcnow()))
        db.commit()
    again = run(Session)
    assert locals_ <= {r["key"] for r in again.created}


# --- CA2, CA3 -----------------------------------------------------------------------------------


def test_engine_profiles_reproduce_the_configuration_and_are_bound(Session):
    report = run(Session)
    with Session() as db:
        by_name = profiles(db)
        local = latest(db, by_name["local — transcription"]).settings
        assert set_(local["binding"]) == LOCAL_BINDING
        assert (local["desired_replicas"], local["max_replicas"], local["min_ready_replicas"]) == (1, 1, 0)
        assert local["provider_settings"] == {"host_id": "host-1"}
        modal = latest(db, by_name["modal_1 — transcription"]).settings
        assert set_(modal["binding"]) == MODAL_BINDING and modal["memory_mb"] is None
        assert (modal["desired_replicas"], modal["max_replicas"]) == (2, 2)
        assert "modal_3 — transcription" not in by_name  # nothing configured
        for engine_id in ("local", "modal_1"):
            rp = control.latest_profile(db, engine_id, "transcription")
            assert rp.source_profile_revision_id == by_name[f"{engine_id} — transcription"].latest_published_revision_id
            assert rp.applied_at is None  # desired only, never applied
            assert db.get(EngineAttributes, engine_id).environment == "development"
        assert control.latest_profile(db, "modal_2", "transcription") is None
    assert {(r["engine_id"], r["feature"]) for r in report.bound} == {
        ("local", "transcription"),
        ("modal_1", "transcription"),
    }
    failed = [r for r in report.skipped if r["stage"] == "bind"]
    assert [(r["key"], r["reason"]) for r in failed] == [
        ("engine:modal_2:transcription", "TEST_CONNECTION_FIRST")
    ]
    assert "Testar conexão" in failed[0]["message"]


def test_the_seeded_modal_profile_keeps_the_deployment_fingerprint(Session):
    from workers.engines.modal_apps.fingerprint import deploy_spec

    run(Session)
    with Session() as db:
        engine = db.get(Engine, "modal_1")
        rp = control.latest_profile(db, "modal_1", "transcription").profile
        # What the control path would deploy (planner) vs the engine's current binding.
        config = dict(engine.config, control_fingerprint_version=2, control_memory_mb=rp["memory_mb"])
        current = dict(engine.config, control_fingerprint_version=2, control_memory_mb=None)
        assert deploy_spec("transcription", config, Binding(**rp["binding"]))["fingerprint"] == deploy_spec(
            "transcription", current, Binding(**engine.config["features"]["transcription"])
        )["fingerprint"]


def test_a_legacy_runtime_profile_is_imported_by_whitelist_and_never_rebound(Session):
    with Session() as db:
        db.add(
            RuntimeProfile(
                engine_id="modal_3",
                feature="transcription",
                revision=1,
                profile=dict(
                    adapter_version=1,
                    schema_version=1,
                    binding={"gpu_type": "T4", "workers": 1, "executions_per_worker": 1},
                    model_profile_id="whisper-turbo-modal",
                    desired_replicas=1,
                    max_replicas=1,
                    min_ready_replicas=0,
                    idle_timeout_seconds=120,
                    memory_mb=None,
                    warmup_mode="manual",
                    warm_until=None,
                    provider_settings={},
                    model={"resolved": True},
                    manifest_hash="x",
                ),
            )
        )
        db.commit()
    report = run(Session)
    with Session() as db:
        s = latest(db, profiles(db)["modal_3 — transcription"]).settings
        assert s["binding"]["gpu_type"] == "T4" and s["idle_timeout_seconds"] == 120
        assert "model" not in s and "manifest_hash" not in s
        assert db.query(RuntimeProfile).filter_by(engine_id="modal_3").count() == 1
    assert ("engine:modal_3:transcription", "bind", "RUNTIME_PROFILE_EXISTS") in keys(report)


# --- CA4 ----------------------------------------------------------------------------------------


def test_seeding_again_creates_nothing_and_picks_up_new_configuration(Session):
    first = run(Session)
    with Session() as db:
        counts = (
            db.query(ExecutionProfile).count(),
            db.query(ExecutionRevision).count(),
            db.query(RuntimeProfile).count(),
        )
    second = run(Session)
    assert (second.created, second.published, second.bound) == ([], [], [])
    with Session() as db:
        assert counts == (
            db.query(ExecutionProfile).count(),
            db.query(ExecutionRevision).count(),
            db.query(RuntimeProfile).count(),
        )
        # A connection test qualifies modal_2 and a new engine is configured later.
        engine = db.get(Engine, "modal_2")
        engine.config = dict(engine.config, control_identity="ap-2")
        db.add(_engine("modal_4", "modal", {"transcription": dict(MODAL_BINDING)}, control_identity="ap-4"))
        db.commit()
    third = run(Session)
    assert [r["key"] for r in third.created] == ["engine:modal_4:transcription"]
    assert {r["engine_id"] for r in third.bound} == {"modal_2", "modal_4"}
    assert len(first.created) == len(first.published)


def test_an_archived_or_renamed_seeded_profile_is_not_recreated(Session):
    run(Session)
    with Session() as db:
        p = profiles(db)["modal_2 — transcription"]
        service.metadata(db, p.id, C.MetadataUpdate(version=p.version, name="Renamed", description=""), "root")
        p = db.get(ExecutionProfile, p.id)
        service.archive(db, p.id, p.version, "root")
        total = db.query(ExecutionProfile).count()
    report = run(Session)
    assert report.created == []
    assert ("engine:modal_2:transcription", "create", "PROFILE_ARCHIVED") in keys(report)
    with Session() as db:
        assert db.query(ExecutionProfile).count() == total


def test_dry_run_reports_the_plan_and_writes_nothing(Session):
    report = run(Session, dry_run=True)
    assert report.dry_run and report.created and len(report.created) == len(report.published)
    assert {r["engine_id"] for r in report.bound} == {"local", "modal_1"}
    assert ("engine:modal_2:transcription", "bind", "TEST_CONNECTION_FIRST") in keys(report)
    with Session() as db:
        assert db.query(ExecutionProfile).count() == 0
        assert db.query(RuntimeProfile).count() == 0
        assert db.query(EngineAttributes).count() == 0
        assert db.query(AdminAudit).count() == 0
    real = run(Session)
    assert [r["key"] for r in real.created] == [r["key"] for r in report.created]
    assert [r["key"] for r in real.bound] == [r["key"] for r in report.bound]


# --- CA5 ----------------------------------------------------------------------------------------


def test_root_registration_seeds_in_the_background_and_a_seeding_failure_never_fails_it(Session, monkeypatch):
    monkeypatch.setattr(rate_limit, "hit", lambda *a, **k: None)
    from fastapi import BackgroundTasks
    from api import auth_routes
    from shared.schemas import UserCreate

    with Session() as db:
        db.query(User).delete()
        db.commit()

    def register(db, name, tasks):
        body = UserCreate(email=f"{name}@example.com", username=name, password="Secret123")
        req = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.9"))
        return asyncio.run(auth_routes.register(body, req, db, tasks))

    calls = []
    real = seed.seed_execution_profiles
    monkeypatch.setattr(
        seed, "seed_execution_profiles", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    with Session() as db:
        tasks = BackgroundTasks()
        created = register(db, "alice", tasks)
        assert created.is_root
        # Registration returns before seeding: the seed is only scheduled.
        assert calls == [] and len(tasks.tasks) == 1
        assert db.query(ExecutionProfile).count() == 0
        asyncio.run(tasks())
        assert calls == [1]
    with Session() as db:
        assert {p.created_by for p in db.query(ExecutionProfile)} == {str(created.id)}
        assert db.query(RuntimeProfile).count() == 2
        plain = BackgroundTasks()
        register(db, "bruno", plain)  # a plain account does not seed again
        assert plain.tasks == []
        assert db.query(AdminAudit).filter(AdminAudit.action == "execution_profile.created").count() == db.query(ExecutionProfile).count()

    with Session() as db:
        db.query(User).delete()
        db.commit()
    monkeypatch.setattr(seed, "seed_execution_profiles", lambda *a, **k: 1 / 0)
    with Session() as db:
        tasks = BackgroundTasks()
        assert register(db, "carol", tasks).is_root
        asyncio.run(tasks())  # best effort: never raises


def test_make_admin_root_seeds(Session, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "make_admin.py"
    spec = importlib.util.spec_from_file_location("make_admin_seed_test", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "SessionLocal", Session)
    with Session() as db:
        db.get(User, "root").root_slot = None
        db.commit()
    assert script.make_admin(user_id="plain", assume_yes=True, as_root=True) == 0
    with Session() as db:
        assert {p.created_by for p in db.query(ExecutionProfile)} == {"plain"}


def test_boot_seeds_only_with_a_root_and_never_raises(Session):
    with Session() as db:
        db.get(User, "root").root_slot = None
        db.commit()
    assert seed.seed_on_boot(Session) is None
    with Session() as db:
        assert db.query(ExecutionProfile).count() == 0
        db.get(User, "root").root_slot = ROOT_SLOT
        db.commit()
    assert seed.seed_on_boot(Session).created

    def broken():
        raise RuntimeError("database down")

    assert seed.seed_on_boot(broken) is None


def test_engine_access_off_skips_the_seeding(Session, monkeypatch):
    monkeypatch.setattr(get_settings(), "engine_access_enabled", False)
    monkeypatch.setattr(get_settings(), "iam_mode", "off")
    report = run(Session)
    assert keys(report) == [("*", "seed", "ACCESS_NOT_ENABLED")]
    assert "IAM_MODE" in report.skipped[0]["message"]
    with Session() as db:
        assert db.query(ExecutionProfile).count() == 0


def test_only_a_bootstrap_actor_seeds(Session):
    with Session() as db:
        report = seed.seed_execution_profiles(db, actor_id="plain")
        assert keys(report) == [("*", "seed", "BOOTSTRAP_ACTOR_REQUIRED")]
        assert db.query(ExecutionProfile).count() == 0


# --- CA6, CA7, CA8 ------------------------------------------------------------------------------


@pytest.mark.parametrize("iam_mode", ["off", "shadow", "enforce"])
def test_root_lists_reads_revises_publishes_archives_and_binds_every_seeded_profile(Session, monkeypatch, iam_mode):
    monkeypatch.setattr(get_settings(), "iam_mode", iam_mode)
    run(Session)
    with Session() as db:
        db.get(User, "root").is_admin = False  # root stays bootstrap (spec 0019)
        db.commit()
        seeded = db.query(ExecutionProfile).all()
        assert {v["id"] for v in service.list_profiles(db, "root")} == {p.id for p in seeded}
        for p in seeded:
            assert set(service.view(db, p, "root")["permissions"]) == {"read", "update", "publish", "archive"}
        p = profiles(db)["modal_2 — transcription"]
        r = latest(db, p)
        body = C.RevisionCreate(version=p.version, settings=r.settings, warm_for_seconds=None)
        view = service.revise(db, p.id, body, "root")
        new = next(x for x in view["revisions"] if x["revision"] == 2)
        view = service.publish(db, p.id, C.Publish(version=view["version"], revision_id=new["id"]), "root")
        engine = db.get(Engine, "modal_2")
        engine.config = dict(engine.config, control_identity="ap-2")
        db.commit()
        db.add(EngineAttributes(engine_id="modal_2", environment="development"))
        db.commit()
        engine = db.get(Engine, "modal_2")
        service.bind(db, engine, C.Bind(version=engine.version, feature="transcription", revision_id=new["id"]), "root")
        service.archive(db, p.id, view["version"], "root")
        assert db.get(ExecutionProfile, p.id).status == "archived"


def test_seeding_creates_no_operation_outbox_plan_or_reservation(Session):
    run(Session)
    run(Session)
    with Session() as db:
        assert physical_rows(db) == [0] * 6
        assert db.query(RuntimeProfile).filter(RuntimeProfile.applied_at.isnot(None)).count() == 0


def test_every_seeded_change_is_audited_with_origin_seed(Session):
    report = run(Session)
    with Session() as db:
        rows = db.query(AdminAudit).all()
        seeded = [r for r in rows if (r.after or {}).get("origin") == "seed"]
        by_action = {}
        for r in seeded:
            by_action.setdefault(r.action, []).append(r)
        assert len(by_action["execution_profile.created"]) == len(report.created)
        assert len(by_action["execution_profile.published"]) == len(report.published)
        assert len(by_action["engine.profile_created"]) == len(report.bound) == 2
        assert len(by_action["access.engine_classified"]) == 2
        assert {r.actor_user_id for r in seeded} == {"root"}
        assert {r.after["seed_key"] for r in by_action["execution_profile.created"]} == {
            r["key"] for r in report.created
        }


# --- transient bind failures and late host registration (owner clarification) ---------------


def test_a_bind_refused_by_a_stale_host_agent_is_retried_on_the_next_run(Session):
    with Session() as db:
        db.get(ControlHost, "host-1").seen_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    first = run(Session)
    assert ("engine:local:transcription", "bind", "HOST_AGENT_NOT_READY") in keys(first)
    assert "heartbeat" in next(r for r in first.skipped if r["reason"] == "HOST_AGENT_NOT_READY")["message"]
    with Session() as db:
        assert control.latest_profile(db, "local", "transcription") is None
        assert db.get(EngineAttributes, "local") is None  # not classified on the way to failing
        db.get(ControlHost, "host-1").seen_at = datetime.utcnow()
        db.commit()
    second = run(Session)
    assert second.created == []
    assert ("local", "transcription") in {(r["engine_id"], r["feature"]) for r in second.bound}


def test_a_host_registering_after_root_creation_triggers_the_seeding(Session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import engine_control_routes as routes
    from shared.database import get_db

    with Session() as db:
        db.query(ControlHost).delete()
        db.commit()
    run(Session)  # root created on a fresh install: no host yet
    with Session() as db:
        assert control.latest_profile(db, "local", "transcription") is None

    app = FastAPI()
    app.include_router(routes.host_router)

    def db_override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    original = routes.host_identity
    routes.host_identity = lambda host_id, request: host_id
    try:
        client = TestClient(app)
        assert client.post("/internal/engine-hosts/host-1/heartbeat", json={"inventory": INVENTORY}).status_code == 200
        with Session() as db:
            rp = control.latest_profile(db, "local", "transcription")
            assert rp is not None and rp.profile["provider_settings"] == {"host_id": "host-1"}
            assert db.query(ExecutionProfile).filter_by(adapter_type="local").count() > 1
            count = db.query(AdminAudit).count()
        # A steady heartbeat does not seed again.
        client.post("/internal/engine-hosts/host-1/heartbeat", json={"inventory": INVENTORY})
        with Session() as db:
            assert db.query(AdminAudit).count() == count
    finally:
        routes.host_identity = original


def test_host_readiness_rule():
    now = datetime.utcnow()
    inv = {"manifest_hash": "m"}
    assert seed.host_became_ready(None, None, inv, now)
    assert seed.host_became_ready(now - timedelta(minutes=1), "m", inv, now)
    assert seed.host_became_ready(now, "old", inv, now)
    assert not seed.host_became_ready(now - timedelta(seconds=5), "m", inv, now)


def test_host_readiness_is_rate_limited_per_host_for_manifest_changes():
    t0 = datetime.utcnow()

    def beat(host, seconds, previous, current, gap=5):
        now = t0 + timedelta(seconds=seconds)
        return seed.host_became_ready(now - timedelta(seconds=gap), previous, {"manifest_hash": current}, now, host_id=host)

    assert seed.host_became_ready(None, None, {"manifest_hash": "a"}, t0, host_id="h1")
    # A host that flips its manifest_hash on every heartbeat seeds at most once a minute.
    assert not beat("h1", 10, "a", "b")
    assert not beat("h1", 59, "b", "c")
    assert beat("h1", 61, "c", "d")
    assert not beat("h1", 70, "d", "e")
    # Other hosts are independent; a host back from stale always seeds.
    assert beat("h2", 10, "a", "b")
    assert beat("h1", 75, "e", "e", gap=300)
    # Steady heartbeats never do.
    assert not beat("h1", 500, "e", "e")


# --- review fixes: drift, host choice, environment, classification, cooldown window ---------


def _qualify(db, engine_id, **config):
    engine = db.get(Engine, engine_id)
    engine.config = dict(engine.config, control_identity=f"ap-{engine_id}", **config)
    db.commit()


def test_a_seed_owned_profile_that_drifted_from_the_engine_is_revised_before_binding(Session):
    first = run(Session)  # modal_2 is seeded with workers=2 but cannot bind yet
    assert ("engine:modal_2:transcription", "bind", "TEST_CONNECTION_FIRST") in keys(first)
    retuned = dict(MODAL_BINDING, gpu_type="A10G", workers=4)
    with Session() as db:
        _qualify(db, "modal_2", features={"transcription": dict(retuned)})
    second = run(Session)
    with Session() as db:
        p = profiles(db)["modal_2 — transcription"]
        r = latest(db, p)
        assert r.revision == 2 and set_(r.settings["binding"]) == retuned
        assert r.settings["max_replicas"] == 4
        rp = control.latest_profile(db, "modal_2", "transcription")
        assert rp.source_profile_revision_id == r.id and rp.profile["binding"]["workers"] == 4
        audits = db.query(AdminAudit).filter(AdminAudit.target_id == p.id).all()
        assert {a.after["origin"] for a in audits} == {"seed"}
    refreshed = [x for x in second.published if x.get("refreshed")]
    assert [x["key"] for x in refreshed] == ["engine:modal_2:transcription"]
    assert second.created == []


def test_a_drifted_seeded_profile_touched_by_a_human_is_not_overwritten(Session):
    run(Session)
    with Session() as db:
        p = profiles(db)["modal_2 — transcription"]
        body = C.RevisionCreate(version=p.version, settings=latest(db, p).settings, warm_for_seconds=None)
        view = service.revise(db, p.id, body, "root")  # a human revision (no seed origin)
        new = next(x for x in view["revisions"] if x["revision"] == 2)
        service.publish(db, p.id, C.Publish(version=view["version"], revision_id=new["id"]), "root")
        _qualify(db, "modal_2", features={"transcription": dict(MODAL_BINDING, workers=4)})
        revisions = db.query(ExecutionRevision).filter_by(profile_id=p.id).count()
    report = run(Session)
    stale = next(r for r in report.skipped if r["reason"] == "SEEDED_PROFILE_STALE")
    assert (stale["key"], stale["stage"]) == ("engine:modal_2:transcription", "bind")
    assert "alterado por um administrador" in stale["message"]
    with Session() as db:
        assert db.query(ExecutionRevision).filter_by(profile_id=p.id).count() == revisions
        assert control.latest_profile(db, "modal_2", "transcription") is None
        assert db.get(EngineAttributes, "modal_2") is None


def test_an_unchanged_engine_binds_the_existing_revision(Session):
    run(Session)
    with Session() as db:
        _qualify(db, "modal_2")
    report = run(Session)
    assert report.published == [] and {r["engine_id"] for r in report.bound} == {"modal_2"}
    with Session() as db:
        assert latest(db, profiles(db)["modal_2 — transcription"]).revision == 1


def test_local_profiles_name_the_host_that_serves_the_feature_and_gpu(Session):
    with Session() as db:
        # Seen more recently, but serves no audio and holds another GPU.
        db.add(ControlHost(id="host-0", inventory={"services": ["worker"], "gpu_uuids": ["GPU-9"], "manifest_hash": "m"}, seen_at=datetime.utcnow() + timedelta(seconds=1)))
        db.commit()
    run(Session)
    with Session() as db:
        assert latest(db, profiles(db)["local — transcription"]).settings["provider_settings"] == {"host_id": "host-1"}
        assert control.latest_profile(db, "local", "transcription").profile["provider_settings"] == {"host_id": "host-1"}


def test_two_hosts_serving_the_feature_are_ambiguous(Session):
    with Session() as db:
        db.add(ControlHost(id="host-2", inventory=dict(INVENTORY, gpu_uuids=["GPU-2"]), seen_at=datetime.utcnow()))
        db.commit()
    report = run(Session)
    locals_ = {f"catalog:{m['id']}:local" for m, a in approved_catalog() if a == "local"}
    # Catalog profiles pin no GPU: both hosts qualify. The engine pins GPU-1: host-1 only.
    assert locals_ <= {r["key"] for r in report.skipped if r["reason"] == "HOST_AMBIGUOUS"}
    assert ("local", "transcription") in {(r["engine_id"], r["feature"]) for r in report.bound}
    with Session() as db:
        # A stale duplicate does not make the choice ambiguous.
        db.get(ControlHost, "host-2").seen_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()
    again = run(Session)
    assert not [r for r in again.skipped if r["reason"] == "HOST_AMBIGUOUS"]
    assert locals_ <= {r["key"] for r in again.created}


@pytest.mark.parametrize(
    "value, expected",
    [("dev", "development"), ("LOCAL", "development"), ("staging", "staging"), ("prod", "production"), ("production", "production"), ("qa", None), ("", None)],
)
def test_environment_is_mapped_explicitly(monkeypatch, value, expected):
    monkeypatch.setattr(get_settings(), "environment", value)
    assert seed.installation_environment() == expected


def test_an_unknown_environment_seeds_and_classifies_nothing(Session, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "qa")
    report = run(Session)
    assert report.created == [] and report.bound == [] and report.classified == []
    assert {r["reason"] for r in report.skipped} >= {"ENVIRONMENT_UNKNOWN"}
    with Session() as db:
        assert db.query(EngineAttributes).count() == 0
        assert db.query(ExecutionProfile).count() == 0


def test_classification_is_reported_and_rolled_back_with_a_refused_bind(Session, monkeypatch):
    real_bind = service.bind

    def refuse(db, engine, *a, **k):
        if engine.id == "modal_1":
            raise control.ControlError("OPERATION_CONFLICT")
        return real_bind(db, engine, *a, **k)

    monkeypatch.setattr(service, "bind", refuse)
    report = run(Session)
    assert ("engine:modal_1:transcription", "bind", "OPERATION_CONFLICT") in keys(report)
    assert [(r["engine_id"], r["environment"]) for r in report.classified] == [("local", "development")]
    with Session() as db:
        assert db.get(EngineAttributes, "modal_1") is None  # same transaction as the bind
        assert db.get(EngineAttributes, "local").environment == "development"
        assert not db.query(AdminAudit).filter_by(action="access.engine_classified", target_id="modal_1").count()


def test_the_seeded_profile_uses_the_engine_scaledown_window(Session):
    from workers.engines.modal_apps.fingerprint import deploy_spec

    with Session() as db:
        for engine_id, window in (("modal_1", 300), ("modal_2", 99999)):
            engine = db.get(Engine, engine_id)
            engine.config = dict(engine.config, scaledown_window=window)
        db.commit()
    run(Session)
    with Session() as db:
        by_name = profiles(db)
        assert latest(db, by_name["modal_1 — transcription"]).settings["idle_timeout_seconds"] == 300
        assert latest(db, by_name["modal_2 — transcription"]).settings["idle_timeout_seconds"] == 3600
        assert latest(db, by_name["local — transcription"]).settings["idle_timeout_seconds"] == 60
        engine = db.get(Engine, "modal_1")
        rp = control.latest_profile(db, "modal_1", "transcription").profile
        assert rp["idle_timeout_seconds"] == 300
        config = dict(engine.config, control_fingerprint_version=2, control_memory_mb=rp["memory_mb"])
        current = dict(engine.config, control_fingerprint_version=2, control_memory_mb=None)
        assert deploy_spec("transcription", config, Binding(**rp["binding"]))["fingerprint"] == deploy_spec(
            "transcription", current, Binding(**engine.config["features"]["transcription"])
        )["fingerprint"]
