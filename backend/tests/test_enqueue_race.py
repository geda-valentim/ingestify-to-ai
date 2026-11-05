"""The same idempotency key raced by two requests (spec 0007 §4.3, §4.5).

Each request checks the key under its own engine lock, so two requests on different engines can
both miss the other's row; the unique key then refuses the second INSERT. The loser answers the
idempotent outcome (a replay or IDEMPOTENCY_CONFLICT), never a 500, whether the database refuses
it on the flush or on the commit.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from shared.engine_control import force_cancel, service
from shared.engine_control.contracts import PlanRequest
from shared.engine_control.models import ControlAdmission, EngineOperation
from shared.models import Engine
from tests.test_engine_control import prepared
from tests.test_engine_control import world  # noqa: F401  (fixture)

FIELDS = ("engine_id", "actor_id", "plan_id", "idempotency_key", "request_hash", "deadline", "reserved_usd")


def _race(db, monkeypatch, winner_state="queued"):
    """The first flush carrying an operation hits the unique key: another request committed the
    same key in between. After the loser's rollback, that winner is what the database holds."""
    flush, rollback, seen = db.flush, db.rollback, {}

    def racing_flush(*a, **kw):
        op = next((o for o in db.new if isinstance(o, EngineOperation)), None)
        if op is not None and not seen:
            seen.update({f: getattr(op, f) for f in FIELDS})
            raise IntegrityError("INSERT INTO engine_operations", {}, Exception("uq_operation_idempotency"))
        return flush(*a, **kw)

    def rollback_then_winner():
        rollback()
        if seen and not db.query(EngineOperation).filter_by(idempotency_key=seen["idempotency_key"]).count():
            db.add(EngineOperation(id=str(uuid4()), state=winner_state, **seen))
            db.commit()

    monkeypatch.setattr(db, "flush", racing_flush)
    monkeypatch.setattr(db, "rollback", rollback_then_winner)
    return seen


def test_a_raced_key_replays_the_winner_in_the_generic_enqueue(world, monkeypatch):  # noqa: F811
    p = prepared(world)
    with world() as db:
        seen = _race(db, monkeypatch)
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        assert seen  # the flush did refuse the key
        winner = db.query(EngineOperation).filter_by(idempotency_key="key").one()
        assert op["operation_id"] == winner.id


@pytest.fixture
def probe():
    before = force_cancel._probe
    force_cancel.set_holder_probe(lambda holders: {h: {"verdict": "unknown", "pid": None, "host": None}
                                                   for h in holders})
    yield
    force_cancel.set_holder_probe(before)


def test_a_raced_key_is_an_idempotency_conflict_in_force_cancel(world, probe, monkeypatch):  # noqa: F811
    prepared(world)
    with world() as db:
        db.add(ControlAdmission(id="t1", resource_key="vm:test-account:allocation-one", holder="task:legacy",
                                created_at=datetime.utcnow() - timedelta(minutes=30)))
        db.commit()
        e = db.get(Engine, "e")
        plan = service.create_plan(db, e, PlanRequest(type="force_cancel", engine_version=e.version), "admin")
        seen = _race(db, monkeypatch, winner_state="succeeded")
        with pytest.raises(service.ControlError) as err:
            service.enqueue(db, plan["plan_id"], plan["plan_hash"], "k", "admin", confirm_force_cancel="test-vm:1")
        assert seen and err.value.code == "IDEMPOTENCY_CONFLICT"
        assert db.get(ControlAdmission, "t1").released_at is None  # nothing of the loser stayed
