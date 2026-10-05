"""
Remote engines end to end (spec 0003, slice 4a), with a fake `modal` and the
SQLite world of the routing tests: placement on a Modal engine reserves the
worst case, worker-remote claims it (CHECK 2), spawns with the bytes, records
the call before waiting, cancels at deadline_at, finishes through
finish_transcription and settles max(reported, measured) x rate (CHECK 3).
Engine errors send the item elsewhere without counting an attempt; the sweeper
republishes silent attempts and never settles a call that may still finish.
Plus the admin lifecycle (credentials, test, budget, activate) and remote routes.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import engine_admin_routes as engines_api
from api import routing_admin_routes as routing_api
from shared.config import get_settings
from shared.engines import ledger, pricing, routing, sealing
from shared.engines.capacity import Binding
from shared.models import AdminAudit, Engine, EngineUsage, FeatureRoute, Job, JobDispatch, JobStatus, User
from tests._engines_world import ALICE, ROOT, World
from tests._fake_modal import Clock, FakeModal, response_for
from workers.engines import remote, remote_tasks, sweeper
from workers.engines.adapters.modal import ModalAdapter
from workers.engines.modal_apps import fingerprint, protocol

TOKEN_ID = "ak-RemoteTestToken0123456"
TOKEN_SECRET = "as-RemoteTestSecret0123456789xyz"
L4 = {"gpu_type": "L4", "workers": 1, "executions_per_worker": 1}
MODAL = "eng-modal_1"


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    public, private = sealing.generate_keypair()
    settings = get_settings()
    monkeypatch.setattr(settings, "engine_secrets_public_key", public)
    monkeypatch.setattr(settings, "engine_secrets_private_keys", private)
    monkeypatch.setattr(settings, "engine_secrets_private_keys_file", "")
    monkeypatch.setattr(settings, "temp_storage_path", str(tmp_path))  # a cleared settings cache elsewhere
    monkeypatch.setattr(engines_api.settings, "engine_secrets_public_key", public)  # the API's own reference
    w.public = public
    w.fake = FakeModal()
    w.clock = Clock(start=1_000_000.0)
    w.fake.account(TOKEN_ID).clock = w.clock
    monkeypatch.setattr(remote, "adapter_factory", lambda engine, creds: ModalAdapter(
        remote.snapshot(engine), creds, modal_module=w.fake, clock=w.clock))
    remote._fingerprint.cache_clear()
    w.finished = []
    yield w
    w.close()


def add_modal(world, status="active", deployed=True, limit_usd="30", health="healthy"):
    config = {"features": {"transcription": dict(L4)}}
    deployments = {}
    if deployed:
        deployments["transcription"] = {
            "binding": dict(L4), "protocol": protocol.PROTOCOL_VERSION,
            "fingerprint": fingerprint.expected_fingerprint("transcription", config, Binding(**L4)),
        }
    blob, kid = sealing.seal({"token_id": TOKEN_ID, "token_secret": TOKEN_SECRET}, world.public, MODAL)
    with world.Session() as db:
        db.add(Engine(id=MODAL, slug="modal_1", display_name="Modal 1", adapter_type="modal", config=config,
                      deployments=deployments, status=status, health=health,
                      credentials_sealed=blob, credentials_key_id=kid,
                      credentials_masked={"token_id": {"is_set": True, "hint": TOKEN_ID[-4:]}},
                      credentials_updated_at=datetime.utcnow() - timedelta(hours=1),
                      limit_usd=Decimal(limit_usd) if limit_usd else None, min_remaining_usd=Decimal("0.5")))
        db.commit()
    return MODAL


def place_remote(world, media=600):
    add_modal(world)
    world.set_route({"engine_ids": [MODAL]}, ["eng-local"])
    item = world.add_item(user=ROOT, remote_allowed=True, media=media)
    result = world.tick()
    assert result.placed == [(item, "modal_1", 1)]
    return item, world.item(item).usage_id


def finish(world):
    def done(job_id, result, **kwargs):
        world.finished.append((job_id, result, kwargs))
        with world.Session() as db:
            job = db.get(Job, job_id)
            job.status, job.completed_at = JobStatus.COMPLETED, datetime.utcnow()
            db.commit()
    return done


def run(world, usage_id, **kwargs):
    return remote.run(usage_id, session_factory=world.Session, celery=world.celery, redis_client=world.redis,
                      es_client=None, finish=finish(world), **kwargs)


# --- placement and the happy path ------------------------------------------------------------


def test_placement_reserves_the_worst_case_and_publishes_to_worker_remote(world):
    item, usage_id = place_remote(world, media=1980)
    usage = world.usage(usage_id)
    binding = Binding(**L4)
    assert usage.reserved_usd == pricing.hold_usd({}, binding, 1980)
    assert Decimal(str(usage.rate_usd_per_s)) == pricing.rate_usd_per_s({}, binding)
    assert usage.fingerprint == fingerprint.expected_fingerprint("transcription", {"features": {"transcription": L4}},
                                                                 binding)
    assert usage.price_snapshot["gpu_type"] == "L4"
    sent = world.celery.named(remote.EXECUTE_TASK)
    assert [(s.args, s.queue) for s in sent] == [([usage_id], "ingestify-remote")]


def test_a_remote_item_runs_finishes_like_local_and_settles_the_larger_of_reported_and_measured(world):
    item, usage_id = place_remote(world)
    account = world.fake.account(TOKEN_ID)
    account.behaviour = lambda request: (2, response_for(request, started=world.clock.now + 5, cold=8.0,
                                                         exec_seconds=100.0))
    assert run(world, usage_id) == "succeeded"

    request = account.spawned[0]
    assert request["media"].startswith(b"ID3") and request["options"] == {}
    usage = world.usage(usage_id)
    rate = Decimal(str(usage.rate_usd_per_s))
    assert usage.status == "settled" and usage.outcome == "succeeded" and usage.output_persisted_at is not None
    assert usage.provider_call_id == "fc-1" and usage.container_id == "ta-container-1"
    assert float(usage.reported_seconds) == 105.0  # exec 100 + cold clamped to 5 (spawn -> exec start)
    assert usage.actual_usd == pricing.settle_usd(105.0, float(usage.measured_seconds), rate)
    assert usage.deadline_at == usage.spawned_at + timedelta(seconds=pricing.deadline_seconds(usage.reserved_usd, rate))
    assert world.item(item).state == "done"
    job_id, result, kwargs = world.finished[0]
    assert result["text"] == "olá mundo" and result["device"] == "modal:L4"
    assert kwargs["compute_type"] == "float16" and kwargs["file_path"].name == "aula.mp3"
    with world.Session() as db:
        assert db.get(Engine, MODAL).health == "healthy"

    assert run(world, usage_id) == "skipped"  # a redelivered message never runs twice
    assert len(account.spawned) == 1


# --- deadline, errors, claim -------------------------------------------------------------------


def test_a_call_that_never_returns_is_cancelled_at_deadline_and_charged_at_most_one_poll_more(world):
    item, usage_id = place_remote(world)
    account = world.fake.account(TOKEN_ID)
    account.behaviour = lambda request: (None, None)
    assert run(world, usage_id) == "failed:TIMEOUT"

    usage = world.usage(usage_id)
    rate = Decimal(str(usage.rate_usd_per_s))
    assert account.calls["fc-1"].cancelled
    assert usage.outcome == "failed" and usage.error_code == "TIMEOUT" and usage.counts_toward_attempts
    assert usage.actual_usd <= usage.reserved_usd + pricing.round_up(Decimal("15") * rate)
    d = world.item(item)
    assert d.state == "waiting" and d.job_failures == 1 and d.not_before is not None  # counted, with backoff


def test_auth_errors_send_the_item_elsewhere_without_counting(world):
    item, usage_id = place_remote(world)
    world.fake.account(TOKEN_ID).spawn_error = world.fake.exception.AuthError("Token is invalid")
    assert run(world, usage_id) == "failed:AUTH"

    usage = world.usage(usage_id)
    assert usage.actual_usd == 0 and not usage.counts_toward_attempts
    d = world.item(item)
    assert d.state == "waiting" and d.job_failures == 0 and d.not_before is None
    assert [e["engine_id"] for e in d.exclude_engines] == [MODAL]
    with world.Session() as db:
        engine = db.get(Engine, MODAL)
        assert engine.health == "unhealthy" and TOKEN_SECRET not in (engine.health_reason or "")

    world.tick(at=world.now + timedelta(seconds=1))  # the route goes on to the local step
    assert world.item(item).engine_id == "eng-local"


def test_input_rejected_fails_the_job_at_once(world):
    item, usage_id = place_remote(world)
    world.fake.account(TOKEN_ID).behaviour = lambda request: (0, protocol.InputRejected("bad media"))
    assert run(world, usage_id) == "failed:INPUT_REJECTED"
    assert world.item(item).state == "failed"
    assert world.job(world.item(item).job_id).status == JobStatus.FAILED


@pytest.mark.parametrize("change, reason", [
    (dict(status="paused"), "ENGINE_PAUSED"),
    (dict(health="unhealthy"), "ENGINE_UNHEALTHY"),
    (dict(deployments={}), "NEEDS_REDEPLOY"),
    (dict(provider_reported_usd=Decimal("29.99")), "BUDGET"),
])
def test_the_claim_rechecks_the_engine_and_hands_the_item_back(world, change, reason):
    item, usage_id = place_remote(world)
    with world.Session() as db:
        engine = db.get(Engine, MODAL)
        if "provider_reported_usd" in change:
            from shared.engines.budget import period_start
            engine.provider_reported_period = period_start(engine, datetime.utcnow())
        for k, v in change.items():
            setattr(engine, k, v)
        db.commit()
    assert run(world, usage_id) == f"refused:{reason}"
    assert world.usage(usage_id).status == "released"
    assert world.item(item).state == "waiting"
    assert world.fake.account(TOKEN_ID).spawned == []


def test_a_new_worker_resumes_a_recorded_call_instead_of_spawning_again(world):
    item, usage_id = place_remote(world)
    account = world.fake.account(TOKEN_ID)
    # A first worker claimed, spawned and recorded the call, then died
    ledger.claim_remote(usage_id, "dead:1", "attempt-x", lambda db, u, e: None, session_factory=world.Session)
    adapter = ModalAdapter({"slug": "modal_1"}, {"token_id": TOKEN_ID, "token_secret": TOKEN_SECRET},
                           modal_module=world.fake, clock=world.clock)
    call = adapter._runner().transcribe.spawn(protocol.build_request(
        attempt_key="attempt-x", media=b"ID3", suffix=".mp3", options={}, deadline_unix=world.clock.now + 600))
    spawned = datetime.utcnow() - timedelta(minutes=5)
    ledger.record_call(usage_id, "dead:1", call.object_id, spawned, spawned + timedelta(minutes=30),
                       session_factory=world.Session)
    with world.Session() as db:
        db.get(EngineUsage, usage_id).heartbeat_at = datetime.utcnow() - timedelta(minutes=3)
        db.commit()

    assert run(world, usage_id) == "succeeded"
    assert len(account.spawned) == 1  # resumed, not spawned again
    assert world.usage(usage_id).outcome == "succeeded"


def test_a_live_holder_is_left_alone(world):
    item, usage_id = place_remote(world)
    ledger.claim_remote(usage_id, "alive:1", "attempt-y", lambda db, u, e: None, session_factory=world.Session)
    assert run(world, usage_id) == "busy"


# --- sweeper --------------------------------------------------------------------------------------


def test_the_sweeper_republishes_silent_remote_attempts_and_finally_gives_them_up(world):
    item, usage_id = place_remote(world)
    ledger.claim_remote(usage_id, "dead:1", "attempt-z", lambda db, u, e: None, session_factory=world.Session)
    world.celery.sent.clear()
    later = datetime.utcnow() + timedelta(minutes=3)
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, now=later, redis_client=world.redis)
    assert counts["remote_republished"] == 1
    assert [s.args for s in world.celery.named(remote.EXECUTE_TASK)] == [[usage_id]]
    assert world.usage(usage_id).status == "spawning"  # never settled while it may still finish

    with world.Session() as db:
        db.get(EngineUsage, usage_id).republish_count = 5
        db.commit()
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, now=later + timedelta(minutes=5),
                           redis_client=world.redis)
    usage = world.usage(usage_id)
    assert counts["lost"] == 1 and usage.outcome == "lost" and usage.actual_usd == usage.reserved_usd
    assert world.item(item).state == "waiting" and world.item(item).job_failures == 0


def test_the_sweeper_asks_worker_remote_to_cancel_a_call_past_its_deadline(world):
    item, usage_id = place_remote(world)
    ledger.claim_remote(usage_id, "w:1", "attempt-c", lambda db, u, e: None, session_factory=world.Session)
    now = datetime.utcnow()
    ledger.record_call(usage_id, "w:1", "fc-9", now - timedelta(minutes=10), now - timedelta(minutes=2),
                       session_factory=world.Session)
    with world.Session() as db:
        db.get(EngineUsage, usage_id).published_at = now - timedelta(minutes=11)
        db.commit()
    world.celery.sent.clear()
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, now=now, redis_client=world.redis)
    assert counts["remote_cancelled"] == 1
    assert [(s.args, s.queue) for s in world.celery.named(remote.CANCEL_TASK)] == [([usage_id], "ingestify-remote-ctl")]
    counts = sweeper.sweep(celery=world.celery, session_factory=world.Session, now=now + timedelta(seconds=30),
                           redis_client=world.redis)
    assert counts["remote_cancelled"] == 0  # once per 2 minutes, not every sweep


# --- admin lifecycle -------------------------------------------------------------------------------


def _request(headers=None):
    return SimpleNamespace(headers=headers or {"authorization": "Bearer t"}, client=SimpleNamespace(host="10.0.0.1"))


def call(world, endpoint, *args, **kwargs):
    db = world.Session()
    try:
        return asyncio.run(endpoint(*args, admin_user=db.get(User, ROOT), db=db, **kwargs))
    finally:
        db.close()


def test_credentials_need_the_password_and_a_public_key_and_are_never_echoed(world, monkeypatch):
    add_modal(world, status="paused")
    body = engines_api.CredentialsUpdate(fields={"token_id": "ak-NewToken0123456789", "token_secret": "as-NewSecret0123456789"},
                                         current_password="wrong")
    with pytest.raises(HTTPException) as exc:
        call(world, engines_api.put_engine_credentials, "modal_1", body, _request())
    assert exc.value.status_code == 403

    body.current_password = "pw"
    view = call(world, engines_api.put_engine_credentials, "modal_1", body, _request())
    assert "as-NewSecret0123456789" not in str(view) and view["credentials"]["token_id"]["hint"] == "6789"
    with world.Session() as db:
        audit = db.query(AdminAudit).filter(AdminAudit.action == "engine.set_credentials").one()
        assert "NewSecret" not in str(audit.after) and "NewToken" not in str(audit.after)
        engine = db.get(Engine, MODAL)
        assert sealing.open_sealed(engine.credentials_sealed, [get_settings().engine_secrets_private_keys], MODAL,
                                   engine.credentials_key_id)["token_secret"] == "as-NewSecret0123456789"

    monkeypatch.setattr(engines_api.settings, "engine_secrets_public_key", "")
    with pytest.raises(HTTPException) as exc:
        call(world, engines_api.put_engine_credentials, "modal_1", body, _request())
    assert exc.value.status_code == 409


def test_activation_needs_a_test_a_budget_and_a_deploy(world, monkeypatch):
    add_modal(world, status="paused", deployed=False, limit_usd=None)
    with pytest.raises(HTTPException) as exc:
        call(world, engines_api.activate_engine, "modal_1", _request())
    assert exc.value.status_code == 409
    problems = " ".join(exc.value.detail["problems"])
    assert "connection test" in problems and "budget" in problems and "not_deployed" in problems

    monkeypatch.setattr(engines_api, "_remote_worker_alive", lambda: True)
    monkeypatch.setattr(engines_api, "_send_test", lambda engine_id: remote_tasks.test_engine_now(
        engine_id, session_factory=world.Session))
    report = call(world, engines_api.test_engine, "modal_1", _request())
    assert report["ok"] and report["deployed"] is True

    call(world, engines_api.put_engine_budget, "modal_1", engines_api.BudgetUpdate(limit_usd=Decimal("30")), _request())
    with world.Session() as db:
        engine = db.get(Engine, MODAL)
        engine.deployments = {"transcription": {"binding": dict(L4), "protocol": protocol.PROTOCOL_VERSION,
                                                "fingerprint": remote.expected_fingerprint(engine, "transcription",
                                                                                           Binding(**L4))}}
        db.commit()
    view = call(world, engines_api.activate_engine, "modal_1", _request())
    assert view["status"] == "active"
    assert view["features"]["transcription"]["deploy_state"] == "deployed"

    view = call(world, engines_api.pause_engine, "modal_1", _request())
    assert view["status"] == "paused"
    with world.Session() as db:
        actions = [a.action for a in db.query(AdminAudit).order_by(AdminAudit.id)]
    assert actions == ["engine.test", "engine.set_budget", "engine.activate", "engine.pause"]


def test_an_active_remote_engine_keeps_a_budget(world):
    add_modal(world)
    with pytest.raises(HTTPException) as exc:
        call(world, engines_api.put_engine_budget, "modal_1", engines_api.BudgetUpdate(limit_usd=None), _request())
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        call(world, engines_api.put_engine_budget, "modal_1",
             engines_api.BudgetUpdate(limit_usd=Decimal("30"), period_tz="Mars/Olympus"), _request())
    assert exc.value.status_code == 422


def test_api_keys_cannot_change_engines(world):
    with pytest.raises(HTTPException) as exc:
        engines_api.require_admin_session(_request({"x-api-key": "k", "authorization": "Bearer t"}),
                                          admin_user=SimpleNamespace(id=ROOT))
    assert exc.value.status_code == 403


# --- remote routes -------------------------------------------------------------------------------


def put_route(world, **body):
    db = world.Session()
    try:
        return asyncio.run(routing_api.put_route("transcription", routing_api.RouteUpdate(**body), _request(),
                                                 admin_user=db.get(User, ROOT), db=db))
    finally:
        db.close()


def test_a_ready_remote_engine_can_be_routed_once_worker_remote_is_alive(world, monkeypatch):
    add_modal(world)
    steps = [{"engine_ids": ["local"]}, {"engine_ids": ["modal_1"], "when": {"min_wait_seconds": 600}}]
    monkeypatch.setattr(routing_api, "_remote_worker_alive", lambda: False)
    with pytest.raises(HTTPException) as exc:
        put_route(world, steps=steps)
    assert exc.value.status_code == 409 and "worker-remote" in exc.value.detail

    monkeypatch.setattr(routing_api, "_remote_worker_alive", lambda: True)
    view = put_route(world, steps=steps)
    assert view["steps"][1]["engine_ids"] == [MODAL]


@pytest.mark.parametrize("change, message", [
    (dict(status="paused"), "not active"),
    (dict(deployments={}), "not_deployed"),
    (dict(limit_usd=None), "no budget"),
])
def test_an_unready_remote_engine_cannot_be_routed(world, monkeypatch, change, message):
    add_modal(world)
    with world.Session() as db:
        engine = db.get(Engine, MODAL)
        for k, v in change.items():
            setattr(engine, k, v)
        db.commit()
    monkeypatch.setattr(routing_api, "_remote_worker_alive", lambda: True)
    with pytest.raises(HTTPException) as exc:
        put_route(world, steps=[{"engine_ids": ["local"]}, {"engine_ids": ["modal_1"]}])
    assert exc.value.status_code == 409 and message in exc.value.detail
    assert world.count(FeatureRoute) == 0


def test_remote_capacity_is_bounded_by_worker_remote_threads(world, monkeypatch):
    add_modal(world)
    monkeypatch.setattr(get_settings(), "remote_worker_concurrency", 2)  # 0 threads left after control
    monkeypatch.setattr(routing_api, "_remote_worker_alive", lambda: True)
    with pytest.raises(HTTPException) as exc:
        put_route(world, steps=[{"engine_ids": ["local"]}, {"engine_ids": ["modal_1"]}])
    assert exc.value.status_code == 409 and "REMOTE_WORKER_CONCURRENCY" in exc.value.detail


# --- zero-config -----------------------------------------------------------------------------------


def test_no_process_imports_modal_by_loading_the_remote_code():
    import workers.celery_app  # noqa: F401
    import workers.engines.modal_deploy  # noqa: F401
    import workers.engines.remote_tasks  # noqa: F401
    from workers.engines import executors
    assert executors.get("modal").remote
    assert "modal" not in sys.modules


def test_the_reconcile_keeps_the_larger_report_and_fails_closed(world, monkeypatch):
    add_modal(world)
    reports = iter(["[{\"cost\": \"4.25\"}]", "[{\"cost\": \"3.00\"}]", "[{\"amount\": \"9\"}]"])

    def fake_run(command, env, **kwargs):
        return SimpleNamespace(returncode=0, stdout=next(reports), stderr="")

    monkeypatch.setattr(remote, "adapter_factory", lambda engine, creds: ModalAdapter(
        remote.snapshot(engine), creds, modal_module=world.fake, run=fake_run))
    remote_tasks.reconcile_now(session_factory=world.Session)
    remote_tasks.reconcile_now(session_factory=world.Session)  # a smaller report never lowers it
    with world.Session() as db:
        assert db.get(Engine, MODAL).provider_reported_usd == Decimal("4.25")
    out = remote_tasks.reconcile_now(session_factory=world.Session)  # a missing field: degraded, never 0
    assert "error" in out["modal_1"]
    with world.Session() as db:
        engine = db.get(Engine, MODAL)
        assert engine.health == "degraded" and engine.provider_reported_usd == Decimal("4.25")


def test_media_too_large_to_send_stays_on_local_steps(world):
    add_modal(world)
    world.set_route({"engine_ids": [MODAL]}, ["eng-local"])
    item = world.add_item(user=ROOT, remote_allowed=True, media=600, media_bytes=600 * 1024 * 1024)
    world.tick()
    assert world.item(item).engine_id == "eng-local"
