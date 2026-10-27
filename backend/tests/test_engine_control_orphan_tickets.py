"""
Spec 0007 CA6: an admission ticket whose process died must not hold a drain
until DRAIN_TIMEOUT - and nothing but evidence about that process may free it.

A killed worker child never reaches the `finally` that releases its ticket. The
drain asks the Celery node that ran the task; only a node that answers without
that task in that process proves the ticket is orphaned. Silence, an unparseable
holder or age alone keep it.
"""

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.config import get_settings
from shared.database import Base
from shared.engine_control import registry, service
from shared.engine_control.contracts import PlanRequest
from shared.engine_control.models import ControlAdmission, OperationEvent, OperationPlan
from shared.models import Engine
from workers.engine_control import orphan_tickets, runner
from workers.engine_control.orphan_tickets import (
    parse_task_holder,
    release_dead,
    task_holder,
)

RESOURCE = "vm:orphan-test:one"
NODE = "ingestify-audio@abc123"


class Adapter:
    def validate(self, engine, feature, profile, db):
        return profile

    def resource_keys(self, engine, feature, profile):
        return [RESOURCE]

    def plan(self, engine, req, profile, db):
        return {"stages": ["draining"], "drain": True, "estimated_max_usd": "0"}


@pytest.fixture
def Session(monkeypatch):
    bind = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind)
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)
    registry.register(
        "orphan-vm",
        dict(type="orphan-vm", actions=["scale"], features=["transcription"],
             execution_mode="remote_runner", credential_fields=[], fields=[], provider_fields=[]),
        Adapter,
    )
    with factory() as db:
        db.add(Engine(id="e", slug="orphan-vm", display_name="VM", adapter_type="orphan-vm",
                      config={"features": {}}, deployments={}, limit_usd=1, min_remaining_usd=0, version=0))
        db.commit()
    yield factory
    registry._registry.pop(("orphan-vm", 1))
    bind.dispose()


def _ticket(Session, holder, resource=RESOURCE, age_seconds=120):
    with Session() as db:
        row = ControlAdmission(resource_key=resource, holder=holder,
                               created_at=datetime.utcnow() - timedelta(seconds=age_seconds))
        db.add(row)
        db.commit()
        return row.id


def _open(Session):
    with Session() as db:
        return {
            row.id
            for row in db.query(ControlAdmission).filter(ControlAdmission.released_at.is_(None))
        }


class TestHolder:
    def test_round_trip_names_the_task_process_and_node(self):
        holder = task_holder("t-1", NODE, pid=4242)

        assert holder == f"task:t-1|4242|{NODE}"
        assert parse_task_holder(holder) == ("t-1", 4242, NODE)

    @pytest.mark.parametrize("task_id,hostname", [(None, NODE), ("t-1", None), ("t-1", "")])
    def test_without_a_process_identity_the_holder_stays_plain(self, task_id, hostname):
        holder = task_holder(task_id, hostname, pid=1)

        assert holder == f"task:{task_id}"
        assert parse_task_holder(holder) is None

    def test_a_holder_that_would_be_truncated_stays_plain(self):
        """A cut-off node name would never answer; better not to pretend."""
        holder = task_holder("t-1", "n@" + "x" * 200, pid=1)

        assert holder == "task:t-1"

    @pytest.mark.parametrize(
        "holder", ["task:t-1", "live:job-1", "existing", "task:t-1|nan|node", "task:|1|node", "task:t-1|²|node"]
    )
    def test_other_holders_are_not_reconcilable(self, holder):
        assert parse_task_holder(holder) is None


def _judge(Session, inspector, first_seen=None, keys=(RESOURCE,)):
    """One reconcile pass with every ticket already seen for longer than the grace."""
    first_seen = {} if first_seen is None else first_seen
    release_dead(Session, list(keys), first_seen, inspector, clock=lambda: 0.0)
    return release_dead(Session, list(keys), first_seen, inspector,
                        clock=lambda: float(orphan_tickets.ACCEPT_GRACE_SECONDS))


class TestReleaseDead:
    def test_a_task_its_node_no_longer_runs_is_released(self, Session):
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        assert _judge(Session, lambda nodes: {NODE: []}) == [task_holder("t-1", NODE, pid=10)]
        assert ticket not in _open(Session)

    def test_a_task_still_active_in_the_same_process_is_kept(self, Session):
        """A slow or hung task is in flight; the default never drops in-flight work."""
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        assert _judge(Session, lambda nodes: {NODE: [("t-1", 10)]}) == []
        assert ticket in _open(Session)

    def test_the_same_task_redelivered_to_another_process_frees_the_dead_one(self, Session):
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        assert _judge(Session, lambda nodes: {NODE: [("t-1", 11)]}) == [task_holder("t-1", NODE, pid=10)]
        assert ticket not in _open(Session)

    def test_a_ticket_released_meanwhile_is_not_reported_as_ours(self, Session):
        """The audit trail lists only what the drain released."""
        mine = _ticket(Session, task_holder("t-1", NODE, pid=10))
        theirs = _ticket(Session, task_holder("t-2", NODE, pid=11))

        def inspector(nodes):
            with Session() as db:  # t-2's own `finally` runs between the look and the release
                db.get(ControlAdmission, theirs).released_at = datetime.utcnow()
                db.commit()
            return {NODE: []}

        assert _judge(Session, inspector) == [task_holder("t-1", NODE, pid=10)]
        assert mine not in _open(Session)

    def test_a_reply_without_the_process_id_does_not_clear_the_task(self, Session):
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        assert _judge(Session, lambda nodes: {NODE: [("t-1", None)]}) == []
        assert ticket in _open(Session)

    def test_a_node_that_does_not_answer_proves_nothing(self, Session):
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        assert _judge(Session, lambda nodes: {}) == []
        assert ticket in _open(Session)

    def test_no_broker_means_no_evidence(self, Session):
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))

        def unreachable(nodes):
            raise ConnectionError("broker down")

        assert _judge(Session, unreachable) == []
        assert ticket in _open(Session)

    def test_age_alone_never_releases(self, Session):
        """Plain, live and unparseable holders stay, however old."""
        kept = {
            _ticket(Session, "task:legacy", age_seconds=86400),
            _ticket(Session, "live:job-1", age_seconds=86400),
            _ticket(Session, "existing", age_seconds=86400),
        }
        asked = []

        def inspector(nodes):
            asked.append(nodes)
            return {NODE: []}

        assert _judge(Session, inspector) == []
        assert kept <= _open(Session)
        assert asked == []

    def test_a_ticket_is_judged_only_after_this_drain_saw_it_for_the_grace(self, Session):
        """Measured by the drain's own clock, so a skewed worker clock cannot shorten it."""
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10), age_seconds=86400)
        first_seen, asked = {}, []

        def inspector(nodes):
            asked.append(nodes)
            return {NODE: []}

        grace = orphan_tickets.ACCEPT_GRACE_SECONDS
        assert release_dead(Session, [RESOURCE], first_seen, inspector, clock=lambda: 100.0) == []
        assert release_dead(Session, [RESOURCE], first_seen, inspector, clock=lambda: 100.0 + grace - 1) == []
        assert asked == [] and ticket in _open(Session)

        released = release_dead(Session, [RESOURCE], first_seen, inspector, clock=lambda: 100.0 + grace)
        assert released == [task_holder("t-1", NODE, pid=10)]
        assert ticket not in _open(Session)

    def test_only_the_drained_resources_are_touched(self, Session):
        other = _ticket(Session, task_holder("t-2", NODE, pid=10), resource="vm:other")

        assert _judge(Session, lambda nodes: {NODE: []}) == []
        assert other in _open(Session)

    def test_only_the_holders_nodes_are_asked(self, Session):
        _ticket(Session, task_holder("t-1", NODE, pid=10))
        _ticket(Session, task_holder("t-2", "ingestify-vision@def456", pid=20))
        asked = []

        def inspector(nodes):
            asked.append(set(nodes))
            return {}

        _judge(Session, inspector)

        assert asked == [{NODE, "ingestify-vision@def456"}]


class TestActiveByNode:
    """The reply shape of Celery's `inspect().active()`, Celery 5.3."""

    def _inspect(self, monkeypatch, replies):
        from workers.celery_app import celery_app

        calls = []

        class Inspect:
            def __init__(self, destination, timeout):
                calls.append((destination, timeout))

            def active(self):
                return replies

        monkeypatch.setattr(celery_app.control, "inspect", Inspect)
        return calls

    def test_answers_become_task_and_process_pairs(self, monkeypatch):
        calls = self._inspect(monkeypatch, {
            NODE: [{"id": "t-1", "name": "x", "worker_pid": 10, "hostname": NODE}],
            "other@n": [],
        })

        assert orphan_tickets.active_by_node({NODE, "other@n"}) == {NODE: [("t-1", 10)], "other@n": []}
        assert calls == [(sorted({NODE, "other@n"}), 1.0)]

    def test_an_error_reply_is_no_answer(self, monkeypatch):
        self._inspect(monkeypatch, {NODE: {"error": "boom"}})

        assert orphan_tickets.active_by_node({NODE}) == {}

    def test_nobody_answering_is_no_answer(self, monkeypatch):
        self._inspect(monkeypatch, None)

        assert orphan_tickets.active_by_node({NODE}) == {}


def test_the_residual_report_lists_each_holder_once(Session):
    """A task holds one ticket per resource; the report names holders, not tickets."""
    one, two = task_holder("t-1", NODE, pid=10), task_holder("t-2", NODE, pid=11)
    for holder, resource in ((one, RESOURCE), (one, "vm:other"), (two, RESOURCE)):
        _ticket(Session, holder, resource=resource)

    assert orphan_tickets.residual(Session, [RESOURCE, "vm:other"]) == (3, [one, two])


class TestDrain:
    def _operation(self, Session, timeout_seconds):
        with Session() as db:
            saved = service.save_profile(
                db, db.get(Engine, "e"), "transcription",
                dict(adapter_version=1, schema_version=1, binding={"workers": 1}, model_profile_id="m",
                     desired_replicas=1, max_replicas=1, min_ready_replicas=0, provider_settings={}),
                0, "admin",
            )
            e = db.get(Engine, "e")
            plan = service.create_plan(
                db, e, PlanRequest(type="scale", engine_version=e.version,
                                   profile_revision=saved["revision"], max_usd="0"), "admin",
            )
            op = service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", True)
            generation = service.claim(db, op["operation_id"], "test")
            body = dict(db.get(OperationPlan, plan["plan_id"]).body)
        body["drain_timeout_seconds"] = timeout_seconds
        assert body["resources"] == [RESOURCE]
        return runner.Context(op["operation_id"], generation, Session), body

    def test_a_ticket_of_a_dead_process_does_not_hold_the_drain(self, Session, monkeypatch):
        """Before the reconcile, this drain waited the whole timeout and failed DRAIN_TIMEOUT."""
        holder = task_holder("t-1", NODE, pid=10)
        ticket = _ticket(Session, holder)
        monkeypatch.setattr(orphan_tickets, "ACCEPT_GRACE_SECONDS", 0)
        monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {NODE: []})
        ctx, plan = self._operation(Session, timeout_seconds=5)
        try:
            ctx.drain(plan)
        finally:
            ctx.close()

        assert ticket not in _open(Session)
        with Session() as db:
            messages = [str(e.payload) for e in db.query(OperationEvent).filter_by(operation_id=ctx.op_id)]
        assert any("Liberados" in m and holder in m for m in messages), "a release must be auditable"

    def test_the_drain_keeps_counting_the_grace_across_passes(self, Session, monkeypatch):
        """A drain that forgot when it first saw a ticket would never get past the grace."""
        ticket = _ticket(Session, task_holder("t-1", NODE, pid=10))
        monkeypatch.setattr(orphan_tickets, "ACCEPT_GRACE_SECONDS", 1)
        monkeypatch.setattr(runner, "ORPHAN_RECONCILE_SECONDS", 0)
        monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {NODE: []})
        ctx, plan = self._operation(Session, timeout_seconds=5)
        try:
            ctx.drain(plan)
        finally:
            ctx.close()

        assert ticket not in _open(Session)

    def test_a_failing_residual_report_never_replaces_drain_timeout(self, Session, monkeypatch):
        _ticket(Session, task_holder("t-1", NODE, pid=10))
        monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {})

        def broken(*args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("database went away"))

        monkeypatch.setattr(orphan_tickets, "residual", broken)
        ctx, plan = self._operation(Session, timeout_seconds=1)
        try:
            with pytest.raises(TimeoutError, match="DRAIN_TIMEOUT"):
                ctx.drain(plan)
        finally:
            ctx.close()

    def test_a_ticket_of_a_silent_node_still_times_out_and_is_reported(self, Session, monkeypatch):
        """A recreated container leaves a node that never answers: the admin needs the holder."""
        holder = task_holder("t-1", NODE, pid=10)
        ticket = _ticket(Session, holder)
        monkeypatch.setattr(orphan_tickets, "ACCEPT_GRACE_SECONDS", 0)
        monkeypatch.setattr(orphan_tickets, "active_by_node", lambda nodes: {})
        ctx, plan = self._operation(Session, timeout_seconds=1)
        try:
            with pytest.raises(TimeoutError, match="DRAIN_TIMEOUT"):
                ctx.drain(plan)
        finally:
            ctx.close()

        assert ticket in _open(Session)
        with Session() as db:
            messages = [str(e.payload) for e in db.query(OperationEvent).filter_by(operation_id=ctx.op_id)]
        assert any("1 tickets abertos" in m and holder in m for m in messages)


def test_a_managed_task_names_its_process_in_the_ticket(monkeypatch):
    """The holder written at admission is what the drain later reconciles."""
    from celery import Celery

    from shared.engine_control import admission
    from workers.engine_control import readiness
    from workers.engine_control.task_base import ManagedTask

    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)
    holders = []
    monkeypatch.setattr(admission, "acquire", lambda feature, holder, engine_id=None: holders.append(holder) or [])
    monkeypatch.setattr(admission, "release", lambda tickets: None)
    monkeypatch.setattr(readiness, "ensure", lambda: None)

    app = Celery("orphan-ticket-test")

    @app.task(base=ManagedTask, bind=True, name="workers.tasks.convert_page_task")
    def convert(self):
        return "ok"

    convert.push_request(id="t-9", hostname=NODE)
    try:
        assert convert() == "ok"
    finally:
        convert.pop_request()

    assert parse_task_holder(holders[0]) == ("t-9", os.getpid(), NODE)
