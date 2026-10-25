"""
Engine capacity (spec 0003, slice 3a): bindings, the VRAM guard, admin views, heartbeats.

A binding says how a feature runs on an engine; capacity = workers x executions
per worker. A configuration that would not fit in GPU memory is refused, with
the arithmetic - summed over every feature sharing a local card.
"""

import asyncio
import subprocess
from types import SimpleNamespace

import fakeredis
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import engine_admin_routes as routes
from shared.database import Base
from shared.engines import capacity, features, liveness, store
from shared.engines.capacity import Binding, CapacityError, validate_engine_config
from shared.models import AdminAudit, Engine
from workers.engines import heartbeat

GPU0 = {"ref": "gpu0", "name": "RTX 5060 Ti", "vram_gb": 16, "vram_reserve_gb": 1.0}


def _local(**feature_bindings):
    return {"gpus": [GPU0], "features": feature_bindings}


# --- the VRAM guard --------------------------------------------------------------------


def test_the_spec_example_fits_with_three_whisper_replicas():
    config = _local(
        transcription={"gpu_ref": "gpu0", "workers": 3},
        vision={"gpu_ref": "gpu0", "workers": 1},
        document_conversion={"gpu_ref": "gpu0", "workers": 1},
    )
    [use] = validate_engine_config("local", config)
    assert use.budgeted_gb == 13.3 and use.fits  # 9.0 + 1.8 + 1.5 + reserve 1.0


def test_a_fourth_whisper_replica_is_refused_with_the_arithmetic():
    config = _local(
        transcription={"gpu_ref": "gpu0", "workers": 4},
        vision={"gpu_ref": "gpu0", "workers": 1},
        document_conversion={"gpu_ref": "gpu0", "workers": 1},
    )
    with pytest.raises(CapacityError) as exc:
        validate_engine_config("local", config)
    [line] = exc.value.lines
    assert "transcription 4x1x3" in line and "= 16.3 GB of 16 GB - does NOT fit" in line


def test_florence_large_counts_double():
    config = _local(transcription={"gpu_ref": "gpu0", "workers": 3}, vision={"gpu_ref": "gpu0", "workers": 1})
    [use] = validate_engine_config("local", config, vision_model_id="microsoft/Florence-2-large-ft")
    assert use.budgeted_gb == 13.8


def test_an_override_replaces_the_default_footprint():
    config = _local(transcription={"gpu_ref": "gpu0", "workers": 4, "vram_override_gb": 2.2})
    [use] = validate_engine_config("local", config)
    assert use.budgeted_gb == 9.8


def test_a_local_gpu_process_runs_one_execution():
    with pytest.raises(CapacityError, match="add workers"):
        validate_engine_config("local", _local(transcription={"gpu_ref": "gpu0", "workers": 1, "executions_per_worker": 2}))


def test_local_cpu_work_takes_any_concurrency_and_no_vram():
    [use] = validate_engine_config("local", _local(document_conversion={"workers": 1, "executions_per_worker": 10}))
    assert use.used_gb == 0


def test_an_undeclared_gpu_is_refused():
    with pytest.raises(CapacityError, match="not declared"):
        validate_engine_config("local", _local(transcription={"gpu_ref": "gpu9", "workers": 1}))


def test_modal_runs_one_execution_per_container_for_now():
    with pytest.raises(CapacityError, match="T4/T8"):
        validate_engine_config("modal", {"features": {"transcription": {"gpu_type": "L4", "workers": 2, "executions_per_worker": 2}}})


def test_modal_gpu_must_be_offered_and_within_the_account_limit():
    with pytest.raises(CapacityError, match="gpu_type must be one of"):
        validate_engine_config("modal", {"features": {"transcription": {"gpu_type": "RTX9090", "workers": 1}}})
    with pytest.raises(CapacityError, match="account_max_gpus=10"):
        validate_engine_config("modal", {"features": {"transcription": {"gpu_type": "T4", "workers": 11}}})
    validate_engine_config("modal", {"account_max_gpus": 12, "features": {"transcription": {"gpu_type": "T4", "workers": 11}}})


def test_modal_runs_only_what_its_adapter_supports():
    with pytest.raises(CapacityError, match="cannot run vision"):
        validate_engine_config("modal", {"features": {"vision": {"gpu_type": "L4", "workers": 1}}})


def test_capacity_and_deploy_state():
    binding = Binding(gpu_type="L4", workers=3, executions_per_worker=1)
    assert binding.capacity == 3
    assert capacity.deploy_state("local", {}, "transcription", binding) == "local"
    assert capacity.deploy_state("modal", {}, "transcription", binding) == "not_deployed"
    deployed = {"transcription": {"binding": binding.model_dump(exclude_none=True)}}
    assert capacity.deploy_state("modal", deployed, "transcription", binding) == "deployed"
    bigger = Binding(gpu_type="L4", workers=4)
    assert capacity.deploy_state("modal", deployed, "transcription", bigger) == "needs_redeploy"


# --- store: versioned, audited changes --------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_the_local_engine_exists_once(db):
    first = store.ensure_local_engine(db)
    assert store.ensure_local_engine(db).id == first.id
    assert first.is_system and first.status == "active" and first.adapter_type == "local"


def test_capacity_changes_are_validated_versioned_and_audited(db):
    local = store.ensure_local_engine(db)
    store.set_local_gpus(db, local, [GPU0], version=0, actor_user_id="admin", auth_method="cli")
    store.set_binding(db, local, "transcription", Binding(gpu_ref="gpu0", workers=2), version=1,
                      actor_user_id="admin", auth_method="jwt", ip="10.0.0.1")

    assert local.version == 2
    assert local.config["features"]["transcription"] == {"gpu_ref": "gpu0", "workers": 2, "executions_per_worker": 1}
    with pytest.raises(store.VersionConflict):
        store.set_binding(db, local, "transcription", Binding(gpu_ref="gpu0", workers=3), version=1,
                          actor_user_id="admin", auth_method="jwt")
    with pytest.raises(CapacityError):
        store.set_binding(db, local, "transcription", Binding(gpu_ref="gpu0", workers=6), version=2,
                          actor_user_id="admin", auth_method="jwt")
    db.rollback()
    assert db.get(Engine, local.id).config["features"]["transcription"]["workers"] == 2

    actions = [(a.action, a.auth_method) for a in db.query(AdminAudit).order_by(AdminAudit.id)]
    assert actions == [("engine.set_gpus", "cli"), ("engine.set_capacity", "jwt")]


def test_removing_the_gpu_a_binding_uses_is_refused(db):
    local = store.ensure_local_engine(db)
    store.set_local_gpus(db, local, [GPU0], version=None, actor_user_id=None, auth_method="cli")
    store.set_binding(db, local, "transcription", Binding(gpu_ref="gpu0", workers=1), version=None,
                      actor_user_id=None, auth_method="cli")
    with pytest.raises(CapacityError, match="not declared"):
        store.set_local_gpus(db, local, [], version=None, actor_user_id=None, auth_method="cli")


def test_the_engine_view_shows_capacity_and_liveness_but_no_secret(db):
    local = store.ensure_local_engine(db)
    store.set_local_gpus(db, local, [GPU0], version=None, actor_user_id=None, auth_method="cli")
    store.set_binding(db, local, "transcription", Binding(gpu_ref="gpu0", workers=2), version=None,
                      actor_user_id=None, auth_method="cli")
    modal = Engine(slug="modal_1", display_name="Modal 1", adapter_type="modal", config={"features": {}},
                   deployments={}, credentials_sealed=b"ING1sealed", credentials_key_id="abc",
                   credentials_masked={"token_id": {"is_set": True, "hint": "6DEi"}, "fingerprint": "f00"})
    db.add(modal)
    db.commit()

    view = store.engine_view(db, local, alive_by_feature={"transcription": [{"hostname": "a"}]})
    t = view["features"]["transcription"]
    assert (t["capacity"], t["in_flight"], t["workers_alive"], t["workers_configured"]) == (2, 0, 1, 2)
    assert t["scale_hint"] == "AUDIO_WORKER_REPLICAS=2 docker compose up -d worker-audio"
    assert view["gpu_budget"][0]["budgeted_gb"] == 7.0

    modal_view = store.engine_view(db, modal, alive_by_feature={})
    assert modal_view["credentials"] == {"token_id": {"is_set": True, "hint": "6DEi"}}
    assert "sealed" not in str(modal_view) and "f00" not in str(modal_view)


# --- admin API ---------------------------------------------------------------------------------


def _request(headers):
    return SimpleNamespace(headers={k.lower(): v for k, v in headers.items()}, client=SimpleNamespace(host="10.0.0.1"))


@pytest.mark.parametrize("headers", [{"X-API-Key": "k"}, {}, {"Authorization": "Basic x"}],
                         ids=["api-key", "nothing", "basic"])
def test_engine_changes_need_a_login_session(headers):
    with pytest.raises(HTTPException) as exc:
        routes.require_admin_session(_request(headers), admin_user=SimpleNamespace(id="a"))
    assert exc.value.status_code == 403


def test_a_session_is_accepted():
    admin = SimpleNamespace(id="a")
    assert routes.require_admin_session(_request({"Authorization": "Bearer t"}), admin_user=admin) is admin


def test_put_capacity_answers_422_with_the_vram_arithmetic(db, monkeypatch):
    monkeypatch.setattr(routes, "_alive_by_feature", lambda: {})
    local = store.ensure_local_engine(db)
    store.set_local_gpus(db, local, [GPU0], version=None, actor_user_id=None, auth_method="cli")

    body = routes.BindingUpdate(gpu_ref="gpu0", workers=6)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.put_engine_feature("local", "transcription", body, _request({"Authorization": "Bearer t"}),
                                              admin_user=SimpleNamespace(id="a"), db=db))
    assert exc.value.status_code == 422
    assert "does NOT fit" in exc.value.detail["vram"][0]

    ok = asyncio.run(routes.put_engine_feature("local", "transcription", routes.BindingUpdate(gpu_ref="gpu0", workers=2),
                                               _request({"Authorization": "Bearer t"}),
                                               admin_user=SimpleNamespace(id="a"), db=db))
    assert ok["features"]["transcription"]["capacity"] == 2


# --- heartbeats ----------------------------------------------------------------------------------


def test_queues_map_to_feature_lanes():
    settings = SimpleNamespace(transcription_queue="ingestify-audio", celery_task_default_queue="ingestify",
                               vision_queue="ingestify-vision")
    assert features.feature_for_queue("ingestify-audio", settings) == "transcription"
    assert features.feature_for_queue("ingestify", settings) == "document_conversion"
    assert features.feature_for_queue("ingestify-vision", settings) == "vision"
    assert features.feature_for_queue("other", settings) is None


def test_gpu_facts_come_from_nvidia_smi(monkeypatch):
    out = "GPU-0b6f0e1c-aaaa, NVIDIA GeForce RTX 5060 Ti, 16311, 5120\n"
    monkeypatch.setattr(heartbeat.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=out))
    assert heartbeat.detect_gpu() == {"gpu_uuid": "GPU-0b6f0e1c-aaaa", "gpu_name": "NVIDIA GeForce RTX 5060 Ti",
                                      "vram_total_gb": "15.93", "vram_used_gb": "5.00"}

    def missing(*a, **k):
        raise FileNotFoundError("nvidia-smi")
    monkeypatch.setattr(heartbeat.subprocess, "run", missing)
    assert heartbeat.detect_gpu() is None


def test_heartbeats_expire_and_are_listed_per_worker(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(heartbeat, "detect_gpu", lambda: None)
    heartbeat.publish(["transcription"], "ingestify-audio@a", client)
    heartbeat.publish(["transcription"], "ingestify-audio@b", client)

    workers = liveness.alive("transcription", client)
    assert [w["hostname"] for w in workers] == ["ingestify-audio@a", "ingestify-audio@b"]
    assert workers[0]["device"] == "cpu"
    assert 0 < client.ttl(liveness.KEY.format(feature="transcription", hostname="ingestify-audio@a")) <= 30
    assert liveness.alive("vision", client) == []


# --- heartbeat concurrency and the (still unused) ready-slots observation -----------------------


def test_heartbeat_publishes_concurrency_only_when_known(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(heartbeat, "detect_gpu", lambda: None)
    heartbeat.publish(["transcription"], "w@a", client, concurrency=2)
    heartbeat.publish(["transcription"], "w@b", client)
    by_host = {w["hostname"]: w for w in liveness.alive("transcription", client)}
    assert by_host["w@a"]["concurrency"] == "2"
    assert "concurrency" not in by_host["w@b"]


def test_start_passes_pool_concurrency_to_the_loop(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, args, name, daemon):
            started.update(target=target, args=args)

        def start(self):
            started["started"] = True

    monkeypatch.setattr(heartbeat.threading, "Thread", FakeThread)
    sender = SimpleNamespace(task_consumer=SimpleNamespace(queues=[SimpleNamespace(name="ingestify-audio")]),
                             controller=SimpleNamespace(concurrency=3), hostname="ingestify-audio@a")
    heartbeat._start(sender=sender)
    assert started["started"] and started["target"] is heartbeat._loop
    assert started["args"] == (["transcription"], "ingestify-audio@a", 3)

    assert heartbeat._pool_concurrency(SimpleNamespace(pool=SimpleNamespace(num_processes=4))) == 4
    assert heartbeat._pool_concurrency(SimpleNamespace()) is None


def _beat(client, feature, host, **extra):
    key = liveness.KEY.format(feature=feature, hostname=host)
    client.hset(key, mapping={"device": "cpu", **extra})
    client.expire(key, 30)


def test_observed_ready_slots_sums_concurrency_per_feature():
    liveness.reset_cache()
    client = fakeredis.FakeRedis()
    _beat(client, "transcription", "w@a", concurrency="1")
    _beat(client, "transcription", "w@b", concurrency="2")
    _beat(client, "vision", "v@a", concurrency="5")
    assert liveness.observed_ready_slots("transcription", client) == (3, 2, None)
    assert liveness.observed_ready_slots("vision", client) == (5, 1, None)
    liveness.reset_cache()


def test_observed_ready_slots_degrades_with_a_reason():
    liveness.reset_cache()
    client = fakeredis.FakeRedis()
    assert liveness.observed_ready_slots("transcription", client) == (1, 0, "no_ready_workers")
    liveness.reset_cache()
    _beat(client, "transcription", "w@a", concurrency="2")
    _beat(client, "transcription", "w@old")
    _beat(client, "transcription", "w@bad", concurrency="x")
    assert liveness.observed_ready_slots("transcription", client) == (4, 3, "concurrency_unreported")
    liveness.reset_cache()

    class Broken:
        def scan_iter(self, **k):
            raise ConnectionError("down")
    assert liveness.observed_ready_slots("transcription", Broken()) == (1, 0, "observation_failed")
    liveness.reset_cache()


def test_observed_ready_slots_is_cached_for_ten_seconds():
    liveness.reset_cache()
    scans = []

    class Counting(fakeredis.FakeRedis):
        def scan_iter(self, *a, **k):
            scans.append(1)
            return super().scan_iter(*a, **k)

    client = Counting()
    _beat(client, "transcription", "w@a", concurrency="2")
    now = [100.0]
    clock = lambda: now[0]
    for _ in range(3):
        assert liveness.observed_ready_slots("transcription", client, clock=clock).slots == 2
    assert len(scans) == 1
    now[0] += liveness.READY_CACHE_SECONDS + 1
    liveness.observed_ready_slots("transcription", client, clock=clock)
    assert len(scans) == 2
    liveness.reset_cache()
