"""Forced cancel of admission tickets (spec 0007 §4.5).

The plan freezes a feature's open tickets with what the holder looks like and the ledger rows it
seems to hold; executing it, after a typed confirmation, releases only those tickets, in one
transaction, with the reason. No ledger effect, no job change, no other operation's resources.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from shared.engine_control import force_cancel, service
from shared.engine_control.contracts import ACTIONS, PlanRequest
from shared.engine_control.models import ControlAdmission, ControlResource, EngineOperation
from shared.models import AdminAudit, Engine, EngineUsage
from tests.test_engine_control import prepared
from tests.test_engine_control import world  # noqa: F401  (fixture)
from tests.test_execution_profiles import constraints, grant
from tests.test_execution_profiles import prepared as iam_prepared
from tests.test_execution_profiles import world as iam_world  # noqa: F401  (fixture)

KEY = "vm:test-account:allocation-one"  # the test adapter's only resource


@pytest.fixture
def probe():
    seen = {}

    def fake(holders):
        return {h: seen.get(h, {"verdict": "unknown", "pid": None, "host": None}) for h in holders}

    before = force_cancel._probe
    force_cancel.set_holder_probe(fake)
    yield seen
    force_cancel.set_holder_probe(before)


def _ticket(db, id_, holder, minutes_ago=30, released=False):
    db.add(ControlAdmission(id=id_, resource_key=KEY, holder=holder,
                            created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
                            released_at=datetime.utcnow() if released else None))


def _usage(db, holder, heartbeat_seconds_ago, job_id="job-1"):
    db.add(EngineUsage(engine_id="e", feature="transcription", period_start=date.today(), status="running",
                       holder=holder, job_id=job_id, subject_type="job", subject_id=job_id,
                       heartbeat_at=datetime.utcnow() - timedelta(seconds=heartbeat_seconds_ago)))


def _reason(db, ticket_id):
    t = ControlAdmission.__table__  # not mapped on the model (deploy-order independence)
    return db.execute(select(t.c.release_reason).where(t.c.id == ticket_id)).scalar()


def _plan(db):
    e = db.get(Engine, "e")
    return service.create_plan(db, e, PlanRequest(type="force_cancel", engine_version=e.version), "admin")


def test_the_plan_lists_tickets_verdicts_and_heuristic_usages_and_no_ledger_effect(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "t-dead", "task:abc|4242|celery@worker-1")
        _ticket(db, "t-old", "task:legacy", minutes_ago=60)
        _ticket(db, "t-elsewhere", "task:x|1|n@h", released=True)
        _usage(db, "worker-1:4242", heartbeat_seconds_ago=10)
        db.commit()
        probe["task:abc|4242|celery@worker-1"] = {"verdict": "absent", "pid": 4242, "host": "worker-1"}
        probe["task:legacy"] = {"verdict": "legacy_holder", "pid": None, "host": None}
        plan = _plan(db)
    assert [t["ticket_id"] for t in plan["tickets"]] == ["t-old", "t-dead"]  # oldest first, open only
    dead = plan["tickets"][1]
    assert dead["verdict"] == "absent" and dead["usages"][0]["status"] == "running"
    assert dead["usages"][0]["looks_alive"] is True and plan["looks_like_live_work"] is True
    assert plan["tickets"][0]["verdict"] == "legacy_holder" and plan["tickets"][0]["usages"] == []
    assert plan["ledger_effect"] == "none" and plan["usage_link"].startswith("heuristic")
    assert plan["confirmation"] == "test-vm:2"


def test_without_open_tickets_there_is_nothing_to_plan(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        with pytest.raises(service.ControlError) as e:
            _plan(db)
    assert (e.value.code, e.value.status) == ("FORCE_CANCEL_NOTHING_TO_RELEASE", 422)


def test_a_resource_held_by_an_operation_refuses_plan_and_execution(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "t1", "task:legacy")
        db.commit()
        plan = _plan(db)
        db.get(ControlResource, KEY).operation_id = "running-op"
        db.commit()
        with pytest.raises(service.ControlError) as e:
            service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:1")
        assert e.value.code == "OPERATION_CONFLICT"
        with pytest.raises(service.ControlError) as e:
            _plan(db)
        assert e.value.code == "OPERATION_CONFLICT"
        assert db.get(ControlAdmission, "t1").released_at is None


@pytest.mark.parametrize("confirm", [None, "", "test-vm:2", "other:1", "test-vm"])
def test_execution_needs_the_exact_typed_confirmation(world, probe, confirm):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "t1", "task:legacy")
        db.commit()
        plan = _plan(db)
        with pytest.raises(service.ControlError) as e:
            service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel=confirm)
        assert (e.value.code, e.value.status) == ("FORCE_CANCEL_CONFIRMATION_REQUIRED", 422)
        assert db.get(ControlAdmission, "t1").released_at is None
        assert db.query(EngineOperation).count() == 0


def test_execution_releases_only_the_frozen_tickets_with_the_reason_and_touches_no_ledger(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "t1", "task:legacy")
        _ticket(db, "t2", "task:abc|4242|celery@worker-1")
        _usage(db, "worker-1:4242", heartbeat_seconds_ago=600)
        db.commit()
        probe["task:abc|4242|celery@worker-1"] = {"verdict": "absent", "pid": 4242, "host": "worker-1"}
        plan = _plan(db)
        db.get(ControlAdmission, "t2").released_at = datetime.utcnow()  # its finally ran meanwhile
        _ticket(db, "t3", "task:new|1|celery@worker-2", minutes_ago=0)  # opened after the plan
        db.commit()
        op = service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:2")
        assert op["state"] == "succeeded" and not op["can_cancel"]
        assert op["result"] == {"released": ["t1"], "already_released": ["t2"], "ledger_effect": "none"}
        assert _reason(db, "t1") == "force_cancel:" + op["operation_id"]
        assert _reason(db, "t2") is None  # released normally, untouched
        assert db.get(ControlAdmission, "t3").released_at is None  # not in the plan
        usage = db.query(EngineUsage).one()
        assert (usage.status, usage.holder) == ("running", "worker-1:4242")
        audit = db.query(AdminAudit).filter_by(action="engine.force_cancel").one()
        assert audit.after["confirmation"] == "test-vm:2" and audit.after["released"] == ["t1"]
        assert [t["ticket_id"] for t in audit.after["tickets"]] == ["t1", "t2"]
        again = service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:2")
        assert again["operation_id"] == op["operation_id"]  # idempotent


def test_force_cancel_is_no_adapter_action_and_in_no_role():
    from shared.access import policy

    assert "force_cancel" not in ACTIONS
    assert force_cancel.PERMISSION in policy.PERMISSIONS
    assert all(force_cancel.PERMISSION not in perms for perms in policy.ROLES.values())


def test_no_grant_can_carry_the_force_cancel_permission(iam_world):  # noqa: F811
    # a binding's permissions must lie inside its role, and no role holds force_cancel
    with iam_world() as db:
        with pytest.raises(Exception) as e:
            grant(db, permissions=[force_cancel.PERMISSION])
        assert "PERMISSIONS_OUTSIDE_ROLE" in str(getattr(e.value, "code", e.value))


def test_with_iam_on_an_engine_operator_cannot_plan_it_and_the_platform_admin_can(iam_world):  # noqa: F811
    with iam_world() as db:
        iam_prepared(db)  # operator: engine_operator on engine-a
        e = db.get(Engine, "engine-a")
        with pytest.raises(service.ControlError) as err:
            service.create_plan(db, e, PlanRequest(type="force_cancel", engine_version=e.version), "operator")
        assert (err.value.code, err.value.status) == ("ACCESS_DENIED", 403)
        with pytest.raises(service.ControlError) as err:  # authorized; only nothing to release
            service.create_plan(db, e, PlanRequest(type="force_cancel", engine_version=e.version), "bootstrap")
        assert err.value.code == "FORCE_CANCEL_NOTHING_TO_RELEASE"


# --- the API's holder probe (drain rule, 2 s inspect) ------------------------------------------

def test_holder_verdicts(monkeypatch):
    import workers.engine_control.orphan_tickets as g1
    from api.force_cancel_probe import INSPECT_TIMEOUT_SECONDS, holder_verdicts

    asked = {}

    def active(nodes, timeout):
        asked.update(nodes=set(nodes), timeout=timeout)
        return {"celery@a": [("alive", 11), ("blind", None)], "celery@b": []}

    monkeypatch.setattr(g1, "active_by_node", active)
    holders = ["task:alive|11|celery@a", "task:blind|12|celery@a", "task:gone|13|celery@b",
               "task:x|14|celery@silent", "task:legacy", "live:job-9"]
    v = {h: r["verdict"] for h, r in holder_verdicts(holders).items()}
    assert v == {"task:alive|11|celery@a": "alive", "task:blind|12|celery@a": "alive",  # no pid: cannot clear
                 "task:gone|13|celery@b": "absent", "task:x|14|celery@silent": "node_silent",
                 "task:legacy": "legacy_holder", "live:job-9": "unknown"}
    assert asked == {"nodes": {"celery@a", "celery@b", "celery@silent"}, "timeout": 2.0}
    assert INSPECT_TIMEOUT_SECONDS == 2.0  # spec 0007 §4.5
    assert holder_verdicts(["task:gone|13|celery@b"])["task:gone|13|celery@b"]["host"] == "b"


def test_no_broker_answer_is_unknown_never_absent(monkeypatch):
    import workers.engine_control.orphan_tickets as g1
    from api.force_cancel_probe import holder_verdicts

    def down(nodes, timeout):
        raise ConnectionError("broker down")

    monkeypatch.setattr(g1, "active_by_node", down)
    assert holder_verdicts(["task:gone|13|celery@b"])["task:gone|13|celery@b"]["verdict"] == "unknown"


def test_an_absent_holder_within_the_drain_grace_reads_as_unknown(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "young", "task:abc|1|celery@w", minutes_ago=0)
        db.commit()
        probe["task:abc|1|celery@w"] = {"verdict": "absent", "pid": 1, "host": "w"}
        (ticket,) = _plan(db)["tickets"]
    assert ticket["verdict"] == "unknown"  # a prefork child may not be in `inspect active` yet


def test_the_usage_link_matches_the_exact_host_and_this_engine_only(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        db.add(Engine(id="other", slug="other", display_name="Other", adapter_type="test-vm",
                      config={"features": {}}, deployments={}, version=0, limit_usd=10, min_remaining_usd=0))
        _ticket(db, "t1", "task:abc|42|celery@w_1")
        _usage(db, "w_1:42", heartbeat_seconds_ago=5, job_id="mine")
        _usage(db, "wX1:42:7", heartbeat_seconds_ago=5, job_id="wildcard")  # `_` must not match any char
        db.add(EngineUsage(engine_id="other", feature="transcription", period_start=date.today(), status="running",
                           holder="w_1:42:9", job_id="other-engine", subject_type="job", subject_id="x",
                           heartbeat_at=datetime.utcnow()))
        db.commit()
        probe["task:abc|42|celery@w_1"] = {"verdict": "absent", "pid": 42, "host": "w_1"}
        (ticket,) = _plan(db)["tickets"]
    assert [u["job_id"] for u in ticket["usages"]] == ["mine"]


def test_a_delegation_envelope_cannot_carry_force_cancel(iam_world):  # noqa: F811
    from shared.access import contracts as C

    with iam_world() as db:
        with pytest.raises(Exception) as e:
            grant(db, role="access_admin", delegation=C.Delegation(
                permissions=[force_cancel.PERMISSION], constraints=constraints()))
        assert "DELEGATION_INVALID" in str(getattr(e.value, "code", e.value))


@pytest.fixture
def old_schema():
    """A database the additive migration has not reached yet: admissions without release_reason."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from shared.database import Base

    sql = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(sql)
    with sql.begin() as conn:
        conn.execute(text("DROP TABLE engine_control_admissions"))
        conn.execute(text("CREATE TABLE engine_control_admissions (id VARCHAR(36) PRIMARY KEY, "
                          "resource_key VARCHAR(200) NOT NULL, holder VARCHAR(128) NOT NULL, "
                          "created_at DATETIME NOT NULL, released_at DATETIME)"))
    yield sessionmaker(bind=sql)
    sql.dispose()


def test_admission_and_the_drain_keep_working_before_the_migration(old_schema):
    from shared.engine_control import admission
    from workers.engine_control.orphan_tickets import open_tickets

    with old_schema() as db:  # acquire's insert, the drain's count, the G1 read
        db.add(ControlAdmission(id="t1", resource_key=KEY, holder="task:x|1|n@h"))
        db.commit()
        assert db.query(ControlAdmission).filter(ControlAdmission.released_at.is_(None)).count() == 1
        assert [row.id for row in open_tickets(db, [KEY])] == ["t1"]
    admission.release(["t1"], session_factory=old_schema)
    with old_schema() as db:
        assert db.get(ControlAdmission, "t1").released_at is not None


def test_force_cancel_is_unavailable_until_the_migration_runs(old_schema):
    with old_schema() as db:
        with pytest.raises(service.ControlError) as e:
            force_cancel.create_plan(db, None, PlanRequest(type="force_cancel", engine_version=0), "admin")
        assert (e.value.code, e.value.status) == ("ENGINE_CONTROL_MIGRATION_REQUIRED", 503)


@pytest.mark.parametrize("holder", ["task:abc|42|celery@w-1", "task:abc", "task:abc|x|n@h", "task:|1|n@h",
                                    "task:abc|1|", "live:job-1", "task", "task:a|1|n@h|extra"])
def test_the_plan_parses_holders_exactly_like_the_drain(holder):
    from workers.engine_control.orphan_tickets import parse_task_holder

    assert force_cancel.parse_holder(holder) == parse_task_holder(holder)


def test_without_a_probe_answer_the_linked_usage_and_its_warning_stay(world):  # noqa: F811
    def broken(holders):
        raise ConnectionError("no broker")

    before = force_cancel._probe
    force_cancel.set_holder_probe(broken)
    try:
        prepared(world)
        with world() as db:
            _ticket(db, "t1", "task:abc|4242|celery@worker-1")
            _usage(db, "worker-1:4242", heartbeat_seconds_ago=5)
            db.commit()
            plan = _plan(db)
    finally:
        force_cancel.set_holder_probe(before)
    (ticket,) = plan["tickets"]
    assert ticket["verdict"] == "unknown" and [u["status"] for u in ticket["usages"]] == ["running"]
    assert plan["looks_like_live_work"] is True


def test_release_reason_is_in_the_table_but_in_no_orm_statement():
    from sqlalchemy import insert as sa_insert

    from shared.database import SessionLocal  # noqa: F401  (models imported)

    assert "release_reason" in ControlAdmission.__table__.c  # create_all makes it on a new install
    select_sql = str(select(ControlAdmission).compile())
    assert "release_reason" not in select_sql  # the ORM never selects it...
    assert "release_reason" not in ControlAdmission.__mapper__.columns.keys()  # ...nor inserts it
    assert "release_reason" in str(sa_insert(ControlAdmission.__table__).compile())  # only __table__ does


def test_an_alive_holder_without_usage_still_warns_of_live_work(world, probe):  # noqa: F811
    # images and legacy paths hold a ticket with no ledger row: the verdict is the strongest proof
    prepared(world)
    with world() as db:
        _ticket(db, "t1", "task:img|7|celery@w")
        db.commit()
        probe["task:img|7|celery@w"] = {"verdict": "alive", "pid": 7, "host": "w"}
        plan = _plan(db)
    assert plan["tickets"][0]["usages"] == [] and plan["looks_like_live_work"] is True


def test_a_live_session_ticket_lists_its_usage_on_whatever_engine(world, probe):  # noqa: F811
    prepared(world)
    with world() as db:
        db.add(Engine(id="gpu-2", slug="gpu-2", display_name="GPU 2", adapter_type="test-vm",
                      config={"features": {}}, deployments={}, version=0, limit_usd=10, min_remaining_usd=0))
        _ticket(db, "t1", "live:job-9")
        db.add(EngineUsage(engine_id="gpu-2", feature="live-transcription", period_start=date.today(),
                           status="running", holder="x", job_id="job-9", subject_type="job", subject_id="job-9",
                           heartbeat_at=datetime.utcnow()))
        db.commit()
        (ticket,) = _plan(db)["tickets"]
    assert [u["job_id"] for u in ticket["usages"]] == ["job-9"] and ticket["job_id"] == "job-9"


def test_the_migration_required_message_names_the_explicit_migration():
    from shared import error_catalog

    for lang in ("pt", "en"):
        message = error_catalog.detail("ENGINE_CONTROL_MIGRATION_REQUIRED", lang=lang)["message"]
        # what runbook step 2 runs inside the API container (the script is not in that image)
        assert "engine-control-bootstrap" in message and "shared.engine_control.migration" in message, lang
        assert "scripts/" not in message, lang


def test_a_hung_broker_ends_the_probe_within_its_deadline(monkeypatch):
    import time

    import workers.engine_control.orphan_tickets as g1
    from api.force_cancel_probe import INSPECT_TIMEOUT_SECONDS, holder_verdicts

    def hung(nodes, timeout):
        time.sleep(INSPECT_TIMEOUT_SECONDS + 3)  # a broker that never answers, whatever the timeout says
        return {}

    monkeypatch.setattr(g1, "active_by_node", hung)
    started = time.monotonic()
    v = holder_verdicts(["task:x|1|celery@a"])
    assert time.monotonic() - started < INSPECT_TIMEOUT_SECONDS + 0.5
    assert v["task:x|1|celery@a"]["verdict"] == "unknown"


def test_a_replay_is_authorized_before_it_returns_the_operation(world, probe, monkeypatch):  # noqa: F811
    prepared(world)
    with world() as db:
        _ticket(db, "t1", "task:legacy")
        db.commit()
        plan = _plan(db)
        service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:1")

    def denied(db, engine, feature, actor):
        raise service.ControlError("ACCESS_DENIED", 403)

    monkeypatch.setattr(force_cancel, "_authorize", denied)  # the actor lost the permission since
    with world() as db:
        with pytest.raises(service.ControlError) as e:
            service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:1")
    assert e.value.code == "ACCESS_DENIED"  # not the earlier operation's view
