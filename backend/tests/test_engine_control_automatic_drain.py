"""
Spec 0007, section 4.6: an automatic plan (idle cooldown, wakeup) drains only its
feature's dedicated service key. The generic worker's and the shared GPU's keys also
admit document conversions, which the idle policy must not hold up; legacy media on
the generic worker still takes the dedicated key and stays refused. A human plan
still drains every key of the plan.
"""

from datetime import date

import pytest

from shared.engine_control import admission, registry, service
from shared.engine_control.contracts import PlanRequest
from shared.engine_control.models import ControlResource, OperationPlan
from shared.models import Engine, EngineUsage
from tests.test_engine_control_orphan_tickets import Session, _open, _ticket  # noqa: F401  (fixture)
from workers.engine_control import orphan_tickets, runner

AUDIO = "local:h:service:worker-audio"
GENERIC = "local:h:service:worker"
GPU = "local:h:gpu:GPU-1"
KEYS = {"transcription": [AUDIO, GENERIC, GPU], "document_conversion": [GENERIC, GPU]}
PROFILE = dict(adapter_version=1, schema_version=1, binding={"workers": 1}, model_profile_id="m",
               desired_replicas=1, max_replicas=1, min_ready_replicas=0, provider_settings={})


class Adapter:
    """The local adapter's key layout: legacy media also on the generic worker, a shared GPU."""

    def validate(self, engine, feature, profile, db):
        return profile

    def resource_keys(self, engine, feature, profile):
        return KEYS[feature]

    def plan(self, engine, req, profile, db):
        return {"stages": ["draining"], "drain": True, "estimated_max_usd": "0"}


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {})


@pytest.fixture
def local(Session):
    registry.register(
        "drain-local",
        dict(type="drain-local", actions=["scale"], features=list(KEYS), execution_mode="remote_runner",
             credential_fields=[], fields=[], provider_fields=[]),
        Adapter,
    )
    with Session() as db:
        db.get(Engine, "e").adapter_type = "drain-local"
        db.commit()
        for feature in KEYS:
            e = db.get(Engine, "e")
            service.save_profile(db, e, feature, dict(PROFILE), e.version, "admin")
    yield Session
    registry._registry.pop(("drain-local", 1))


def _drain(Session, trigger, timeout_seconds=2):
    """A transcription plan's real drain; `trigger` makes its body automatic."""
    with Session() as db:
        e = db.get(Engine, "e")
        plan = service.create_plan(db, e, PlanRequest(type="scale", engine_version=e.version, profile_revision=1,
                                                      max_usd="0"), "admin")
        op = service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", True)
        generation = service.claim(db, op["operation_id"], "test")
        body = dict(db.get(OperationPlan, plan["plan_id"]).body, drain_timeout_seconds=timeout_seconds)
    assert sorted(body["resources"]) == sorted(KEYS["transcription"])
    if trigger:
        body["trigger"] = trigger
    ctx = runner.Context(op["operation_id"], generation, Session)
    try:
        ctx.drain(body)
    finally:
        ctx.close()


def _usage(Session, feature, status):
    with Session() as db:
        row = EngineUsage(engine_id="e", feature=feature, status=status, period_start=date(2026, 10, 1))
        db.add(row)
        db.commit()
        return row.id


def _gates(Session):
    with Session() as db:
        return {r.key: r.gate_closed for r in db.query(ControlResource)}


class TestAutomaticPlan:
    def test_it_closes_only_the_dedicated_gate_and_documents_keep_flowing(self, local):
        document = _ticket(local, "task:doc", resource=GENERIC)
        _usage(local, "document_conversion", "running")

        _drain(local, "idle_policy")  # before: DRAIN_TIMEOUT, waiting on the document

        assert _gates(local) == {AUDIO: True, GENERIC: False, GPU: False}
        assert document in _open(local), "the drain neither waits for nor touches the document's ticket"
        assert admission.acquire("document_conversion", "task:doc-2", "e", local)
        with pytest.raises(service.ControlError) as refused:
            admission.acquire("transcription", "task:legacy-audio", "e", local)
        assert refused.value.code == "ENGINE_MAINTENANCE", "legacy media on the generic worker stays out"

    def test_it_waits_for_its_own_feature(self, local):
        _ticket(local, "task:audio", resource=AUDIO)

        with pytest.raises(TimeoutError, match="DRAIN_TIMEOUT"):
            _drain(local, "wakeup", timeout_seconds=1)

    def test_it_releases_only_its_feature_s_reservations(self, local, monkeypatch):
        released = []
        monkeypatch.setattr("shared.engines.ledger.release", lambda usage_id, **kw: released.append(usage_id))
        _usage(local, "document_conversion", "reserved")
        audio = _usage(local, "transcription", "reserved")

        _drain(local, "idle_policy")

        assert released == [audio]

    def test_a_running_usage_of_its_feature_holds_it(self, local):
        _usage(local, "transcription", "running")

        with pytest.raises(TimeoutError, match="DRAIN_TIMEOUT"):
            _drain(local, "idle_policy", timeout_seconds=1)


    def test_a_dead_process_s_tickets_are_freed_on_every_key(self, local, monkeypatch):
        """Waits only on the dedicated key, but a provably dead task's other tickets go too."""
        node = "ingestify-audio@abc"
        holder = orphan_tickets.task_holder("t-1", node, pid=10)
        tickets = [_ticket(local, holder, resource=key) for key in KEYS["transcription"]]
        monkeypatch.setattr(orphan_tickets, "ACCEPT_GRACE_SECONDS", 0)
        monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {node: []})

        _drain(local, "idle_policy")

        assert not set(tickets) & _open(local)


class TestHumanPlan:
    def test_it_still_drains_every_key(self, local):
        _ticket(local, "task:doc", resource=GENERIC)

        with pytest.raises(TimeoutError, match="DRAIN_TIMEOUT"):
            _drain(local, None, timeout_seconds=1)
        assert _gates(local) == {AUDIO: True, GENERIC: True, GPU: True}


def test_without_a_dedicated_key_the_automatic_plan_drains_everything():
    """Fail closed: a plan whose feature has no dedicated key among its resources."""
    plan = {"trigger": "idle_policy", "feature": "transcription", "resources": [GENERIC, GPU]}

    assert runner.drain_scope(plan) == ([GENERIC, GPU], None)
