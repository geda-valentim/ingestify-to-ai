"""
Slice 4c of spec 0003: several accounts. fill_first stickiness per period and
its refusals, full_since, budget alerts and exhaustion until the next period,
the spend reconciliation's fail-closed rules, cheap health probes and doing
every account in turn (deploy, test) - against a fake `modal`, never the network.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import json
import pytest
from fastapi import HTTPException

from api import engine_admin_routes as engines_api
from shared.engines import alerts, budget, budget_watch, sealing, store
from shared.engines.capacity import Binding
from shared.models import Engine, EngineFeatureState, EngineUsage
from tests._engines_world import ROOT
from tests.test_remote_engine import L4, MODAL, TOKEN_ID, _request, add_modal, call, world  # noqa: F401
from workers.engines import modal_deploy, remote, remote_tasks
from workers.engines.adapters.modal import ModalAdapter
from workers.engines.modal_apps import fingerprint, protocol


@pytest.fixture
def sent(monkeypatch):
    """Alerts POSTed to a configured webhook"""
    posts = []
    from shared.config import get_settings
    monkeypatch.setattr(get_settings(), "engine_alert_webhook_url", "https://hooks.example/engines")
    monkeypatch.setattr(alerts, "_post", lambda url, body: posts.append((url, json.loads(body))))
    return posts


def placed_on(world, item):
    return world.item(item).engine_id


def job_row(world, engine_id, *, at=None, actual="0.300000", period=None, i=0, outcome="succeeded"):
    at = at or world.now - timedelta(minutes=5)
    with world.Session() as db:
        engine = db.get(Engine, engine_id)
        db.add(EngineUsage(kind="job", engine_id=engine_id, feature="transcription", subject_type="job",
                           subject_id=f"row-{engine_id}-{i}-{at.timestamp()}", attempt=1,
                           period_start=period or budget.period_start(engine, at), status="settled", outcome=outcome,
                           actual_usd=Decimal(actual), created_at=at, finished_at=at, heartbeat_at=at,
                           gpu_type="L4", executions_per_worker=1))
        db.commit()


# --- fill_first ------------------------------------------------------------------------------------


def test_fill_first_current_account_is_the_latest_job_of_this_period(world):
    first = world.add_remote("fake_1")
    second = world.add_remote("fake_2")
    last_month = world.now - timedelta(days=40)
    job_row(world, second, at=last_month)  # an older period does not make it current
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first"})
    item = world.add_item(user=ROOT, remote_allowed=True, media=10)
    world.tick()
    assert placed_on(world, item) == first

    job_row(world, second, i=1, at=world.now + timedelta(seconds=30))  # this period's latest job: second's
    other = world.add_item(user=ROOT, remote_allowed=True, media=10)
    world.tick(world.now + timedelta(seconds=60))
    assert placed_on(world, other) == second


def test_fill_first_moves_on_at_once_on_a_spend_cap_refusal(world):
    first = world.add_remote("fake_1")
    second = world.add_remote("fake_2")
    job_row(world, first, actual="0.030000", at=datetime(world.now.year, world.now.month, world.now.day))
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first",
                     "spend_cap": {"usd": "0.05", "window": "day"}})
    item = world.add_item(user=ROOT, remote_allowed=True, media=40)  # 0.04: 0.03 + 0.04 > 0.05 on the current
    world.tick()
    assert placed_on(world, item) == second


def test_fill_first_moves_on_at_once_when_the_media_is_too_large_for_the_current(world):
    first = world.add_remote("fake_1", config={"max_input_bytes": 1024})
    second = world.add_remote("fake_2")
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first"})
    item = world.add_item(user=ROOT, remote_allowed=True, media=10, media_bytes=4096)
    world.tick()
    assert placed_on(world, item) == second


def test_a_current_account_with_room_forgets_an_old_full_since(world):
    first = world.add_remote("fake_1", limit_usd="0.55")  # room for 0.05
    second = world.add_remote("fake_2")
    with world.Session() as db:
        db.add(EngineFeatureState(engine_id=first, feature="transcription",
                                  full_since=world.now - timedelta(hours=2), updated_at=world.now))
        db.commit()
    world.set_route({"engine_ids": [first, second], "group_strategy": "fill_first"})
    item = world.add_item(user=ROOT, remote_allowed=True, media=100)  # 0.10: budget refusal
    world.tick()
    assert placed_on(world, item) == second
    with world.Session() as db:
        assert db.get(EngineFeatureState, (first, "transcription")).full_since is None


# --- budget: alerts and exhaustion -------------------------------------------------------------------


def test_the_period_ends_at_the_next_anchor_midnight_in_the_engines_zone():
    engine = SimpleNamespace(period_tz="America/Sao_Paulo", period_anchor_day=5)
    now = datetime(2026, 10, 5, 2, 0)  # 23:00 on Oct 4 in Sao Paulo
    assert budget.period_start(engine, now) == date(2026, 9, 5)
    assert budget.period_end(engine, now) == datetime(2026, 10, 5, 3, 0)
    assert budget.period_end(SimpleNamespace(period_tz="UTC", period_anchor_day=1),
                             datetime(2026, 12, 20)) == datetime(2027, 1, 1)


def test_soft_and_hard_alerts_fire_once_per_period_and_exhaustion_lasts_until_the_next(world, sent):
    fake = world.add_remote("fake_1", limit_usd="1.60", soft_pct=50)
    for i in range(3):
        job_row(world, fake, i=i)  # 0.90 spent: past 50 %; 1.60 - 0.50 - 0.90 = 0.20 left, below one item (0.30)
    raised = budget_watch.check(fake, session_factory=world.Session, now=world.now)
    assert [a["event"] for a in raised] == ["budget_soft", "budget_exhausted"]
    assert budget_watch.check(fake, session_factory=world.Session, now=world.now) == []  # once per period
    assert [p["event"] for _, p in sent] == ["budget_soft", "budget_exhausted"]
    url, payload = sent[1]
    assert url == "https://hooks.example/engines" and payload["engine"] == "fake_1"
    assert payload["details"]["median_item_usd"] == 0.3 and "user" not in json.dumps(payload)

    with world.Session() as db:
        engine = db.get(Engine, fake)
        assert engine.health == "exhausted" and engine.health_until == budget.period_end(engine, world.now)
        until = engine.health_until
    world.set_route([fake], ["eng-local"])
    item = world.add_item(user=ROOT, remote_allowed=True, media=10)
    world.tick()
    assert placed_on(world, item) == "eng-local"  # exhausted: the route goes on

    later = world.add_item(user=ROOT, remote_allowed=True, media=10, wait=0)
    with world.Session() as db:  # the local step is full by then
        db.get(Engine, "eng-local").config = {**db.get(Engine, "eng-local").config,
                                              "features": {"transcription": {"gpu_ref": "gpu0", "workers": 0}}}
        db.commit()
    world.tick(until + timedelta(seconds=1))
    assert placed_on(world, later) == fake  # a new period: the old spend no longer counts


def test_raising_the_limit_clears_exhausted(world):
    fake = world.add_remote("fake_1", limit_usd="1.00")
    for i in range(3):
        job_row(world, fake, i=i)
    budget_watch.check(fake, session_factory=world.Session, now=world.now)
    with world.Session() as db:
        engine = db.get(Engine, fake)
        assert engine.health == "exhausted"
        store.set_budget(db, engine, limit_usd=5, version=None, actor_user_id=None, auth_method="cli")
        assert engine.health == "unknown"
    assert budget_watch.check(fake, session_factory=world.Session, now=world.now) == []  # alerted this period already


def test_quota_exhausted_from_the_provider_alerts_once_per_period(world, sent):
    fake = world.add_remote("fake_1")
    budget_watch.quota_exhausted(fake, "spending limit reached", session_factory=world.Session, now=world.now)
    budget_watch.quota_exhausted(fake, "spending limit reached", session_factory=world.Session, now=world.now)
    assert [p["event"] for _, p in sent] == ["quota_exhausted"]


def test_an_unreachable_webhook_never_breaks_the_caller(world, monkeypatch):
    from shared.config import get_settings
    monkeypatch.setattr(get_settings(), "engine_alert_webhook_url", "https://hooks.example/down")

    def down(url, body):
        raise OSError("connection refused")
    monkeypatch.setattr(alerts, "_post", down)
    assert alerts.alert("budget_soft", "fake_1", "x")["event"] == "budget_soft"


# --- several Modal accounts ----------------------------------------------------------------------------


def add_account(world, n, *, status="active", token=None):
    engine_id = f"eng-modal_{n}"
    config = {"features": {"transcription": dict(L4)}}
    fp = fingerprint.expected_fingerprint("transcription", config, Binding(**L4))
    token = token or f"ak-Account{n}Token0123456"
    blob, kid = sealing.seal({"token_id": token, "token_secret": f"as-Account{n}Secret0123456789"}, world.public,
                             engine_id)
    with world.Session() as db:
        db.add(Engine(id=engine_id, slug=f"modal_{n}", display_name=f"Modal {n}", adapter_type="modal",
                      config=config, status=status, health="healthy", credentials_sealed=blob,
                      credentials_key_id=kid, credentials_masked={},
                      deployments={"transcription": {"binding": dict(L4), "protocol": protocol.PROTOCOL_VERSION,
                                                     "fingerprint": fp}},
                      limit_usd=Decimal("30"), min_remaining_usd=Decimal("0.5")))
        db.commit()
    world.fake.account(token).state[protocol.DEPLOYMENT_KEY] = {"fingerprint": fp}
    return engine_id, token


def health(world, engine_id):
    with world.Session() as db:
        engine = db.get(Engine, engine_id)
        return engine.health, engine.health_reason or ""


def test_probes_check_only_accounts_used_in_24h_without_a_container(world, sent):
    one, token1 = add_account(world, 1)
    two, _ = add_account(world, 2)
    job_row(world, one, at=datetime.utcnow() - timedelta(hours=2))
    out = remote_tasks.probe_engines_now(session_factory=world.Session)
    assert out["modal_1"]["ok"] is True and out["modal_2"].startswith("skipped")
    assert world.fake.account(token1).spawned == []  # no container, no GPU
    assert world.count(EngineUsage, kind="probe") == 0  # free: nothing to put in the ledger

    world.fake.account(token1).auth_error = "Token is invalid"
    remote_tasks.probe_engines_now(session_factory=world.Session)
    state, reason = health(world, one)
    assert state == "unhealthy" and reason.startswith("PROBE AUTH")
    assert [p["event"] for _, p in sent] == ["engine_probe_failed"]

    world.fake.account(token1).auth_error = None
    remote_tasks.probe_engines_now(session_factory=world.Session)
    assert health(world, one)[0] == "healthy"

    world.fake.account(token1).state[protocol.DEPLOYMENT_KEY] = {"fingerprint": "someone-else-deployed"}
    remote_tasks.probe_engines_now(session_factory=world.Session)
    state, reason = health(world, one)
    assert state == "unhealthy" and "DEPLOY_CHANGED" in reason


def test_a_transient_probe_error_changes_nothing(world, monkeypatch):
    one, token1 = add_account(world, 1)
    job_row(world, one, at=datetime.utcnow() - timedelta(hours=1))
    world.fake.account(token1).auth_error = None

    class Flaky(ModalAdapter):
        def test_connection(self):
            from workers.engines.base import HealthReport
            return HealthReport(False, "TRANSIENT", "connection reset")
    monkeypatch.setattr(remote, "adapter_factory", lambda engine, creds: Flaky(remote.snapshot(engine), creds,
                                                                               modal_module=world.fake))
    out = remote_tasks.probe_engines_now(session_factory=world.Session)
    assert out["modal_1"]["ok"] is None and health(world, one)[0] == "healthy"


def test_every_account_is_tested_in_turn_and_a_bad_one_does_not_stop_the_rest(world):
    one, _ = add_account(world, 1)
    two, token2 = add_account(world, 2, status="paused")
    world.fake.account(token2).auth_error = "Token is invalid"
    results = remote_tasks.test_all_now(session_factory=world.Session)
    assert results["modal_1"]["ok"] is True and results["modal_2"]["code"] == "AUTH"
    with world.Session() as db:
        assert db.get(Engine, one).config["last_test"]["ok"] is True
        assert db.get(Engine, two).config["last_test"]["ok"] is False


def test_deploy_all_goes_through_every_account_and_reports_each(world):
    add_account(world, 1)
    add_account(world, 2)
    add_account(world, 3)
    with world.Session() as db:  # an account without a binding is not deployed
        db.get(Engine, "eng-modal_3").config = {"features": {}}
        db.commit()
    done, lines = [], []

    def deploy_one(slug, feature, **kwargs):
        done.append(slug)
        if slug == "modal_1":
            raise modal_deploy.DeployError("modal deploy failed (exit 1)")
        return {"fingerprint": "abcdef0123456789"}

    summary = modal_deploy.deploy_all(session_factory=world.Session, out=lines.append, deploy_one=deploy_one)
    assert done == ["modal_1", "modal_2"]
    assert summary == {"modal_1": "FAILED: modal deploy failed (exit 1)", "modal_2": "deployed abcdef012345"}


def test_reconcile_fails_closed_on_a_zero_report_that_lasts_and_reports_unattributed(world, monkeypatch, sent):
    one, token1 = add_account(world, 1)
    base = datetime(2026, 10, 10, 12, 0)
    for i in range(2):
        job_row(world, one, at=base - timedelta(hours=1), actual="0.300000", i=i)
    reports = iter(["[]", "[]", "[{\"cost\": \"0.70\"}]"])
    monkeypatch.setattr(remote, "adapter_factory", lambda engine, creds: ModalAdapter(
        remote.snapshot(engine), creds, modal_module=world.fake,
        run=lambda command, env, **kw: SimpleNamespace(returncode=0, stdout=next(reports), stderr="")))

    out = remote_tasks.reconcile_now(session_factory=world.Session, now=base)
    assert out["modal_1"]["reported_usd"] == "0" and "error" not in out["modal_1"]
    assert health(world, one)[0] == "healthy"  # not yet: the report lags

    out = remote_tasks.reconcile_now(session_factory=world.Session, now=base + timedelta(hours=4))
    assert "US$ 0 for over 3 h" in out["modal_1"]["error"]
    assert health(world, one)[0] == "degraded"
    assert "billing_degraded" in [p["event"] for _, p in sent]

    out = remote_tasks.reconcile_now(session_factory=world.Session, now=base + timedelta(hours=5))
    assert out["modal_1"]["unattributed_usd"] == "0.100000" and health(world, one)[0] == "healthy"
    with world.Session() as db:
        assert "billing_zero_since" not in db.get(Engine, one).config


def test_admin_lists_benchmarks_and_speed_and_tests_all_accounts(world, monkeypatch):
    add_modal(world)
    with world.Session() as db:
        db.add(EngineUsage(kind="benchmark", engine_id=MODAL, feature="transcription", period_start=world.now.date(),
                           status="settled", outcome="succeeded", gpu_type="T4", executions_per_worker=1,
                           actual_usd=Decimal("0.02"), reserved_usd=Decimal("0.3"), placed_by="cli",
                           units={"result": {"speed_per_item": 22.0}, "contended": False}, created_at=world.now))
        db.commit()
    view = call(world, engines_api.engine_benchmarks, "modal_1")
    assert view["benchmarks"][0]["result"] == {"speed_per_item": 22.0}
    assert [(k["gpu"], k["source"]) for k in view["speed"]] == [("L4", "default"), ("T4", "benchmark")]

    monkeypatch.setattr(engines_api, "_remote_worker_alive", lambda: False)
    with pytest.raises(HTTPException) as e:
        call(world, engines_api.test_all_engines, _request())
    assert e.value.status_code == 409
    monkeypatch.setattr(engines_api, "_remote_worker_alive", lambda: True)
    monkeypatch.setattr(engines_api, "_send_control",
                        lambda task, args, timeout: remote_tasks.test_all_now(session_factory=world.Session))
    assert call(world, engines_api.test_all_engines, _request())["results"]["modal_1"]["ok"] is True
