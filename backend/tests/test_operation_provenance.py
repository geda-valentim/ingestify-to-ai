"""Provenance in the runtime status and the operation view (spec 0007).

A resource can serve several features (the local worker serves transcription and vision), and
a test or reconcile of one feature records its observation on the shared resource without
publishing an applied revision. The status must say which feature and operation type each
observation came from, and which operation locks a resource, even on a feature's very first
operation, when nothing was applied yet.
"""
from datetime import datetime

from shared.engine_control import service
from shared.engine_control.models import ControlResource, EngineOperation, OperationPlan
from shared.engine_control.operation_view import SOURCE, resource_views
from shared.models import Engine
from tests.test_engine_control import prepared
from tests.test_engine_control import world  # noqa: F401  (fixture)


def test_the_first_operation_of_a_feature_says_what_locks_the_resource(world):  # noqa: F811
    p = prepared(world)
    with world() as db:
        service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        status = service.runtime_status(db, db.get(Engine, "e"))
    (resource,) = status["resources"]
    assert resource["applied"] == {}  # nothing applied yet: the lock is the only clue
    assert (resource["operation_feature"], resource["operation_type"]) == ("transcription", "scale")


def test_a_finished_operation_tags_its_observation_and_the_view_names_feature_and_type(world):  # noqa: F811
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "key", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        view = service.finish(db, op["operation_id"], gen, "succeeded", {"ready_replicas": 2}, safe=True)
        status = service.runtime_status(db, db.get(Engine, "e"))
    assert (view["feature"], view["type"]) == ("transcription", "scale")
    (resource,) = status["resources"]
    assert resource["observed"] == {"ready_replicas": 2}  # the tag is not part of what was observed
    assert (resource["observed_feature"], resource["observed_operation_type"]) == ("transcription", "scale")
    assert resource["observed_operation_id"] == op["operation_id"]
    assert resource["operation_feature"] is None  # unlocked


def _locked_by(db, op_id, feature, type_):
    plan = OperationPlan(engine_id="e", actor_id="a", engine_version=0, body={"feature": feature, "type": type_},
                         hash="h", expires_at=datetime(2026, 10, 27))
    db.add(plan)
    db.flush()
    db.add(EngineOperation(id=op_id, engine_id="e", actor_id="a", plan_id=plan.id, idempotency_key=op_id,
                           request_hash="r", deadline=datetime(2026, 10, 27)))


def test_a_test_of_vision_on_a_shared_resource_reads_as_vision_not_transcription(world):  # noqa: F811
    with world() as db:
        db.add(ControlResource(key="local:host:worker", owner_engine_id="e", observed={
            "ready_replicas": 1, SOURCE: {"operation_id": "v1", "feature": "vision", "type": "test"}}))
        db.commit()
        (view,) = resource_views(db, db.query(ControlResource).all())
    assert (view["observed_feature"], view["observed_operation_type"]) == ("vision", "test")


def test_an_observation_stored_before_the_source_was_kept_is_unknown(world):  # noqa: F811
    with world() as db:
        db.add(ControlResource(key="old", owner_engine_id="e", observed={"ready_replicas": 1}))
        _locked_by(db, "op-1", "vision", "cooldown")
        db.add(ControlResource(key="locked", owner_engine_id="e", operation_id="op-1"))
        db.commit()
        views = {v["key"]: v for v in resource_views(db, db.query(ControlResource).all())}
    assert views["old"]["observed"] == {"ready_replicas": 1}
    assert views["old"]["observed_feature"] is None and views["old"]["observed_operation_type"] is None
    assert (views["locked"]["operation_feature"], views["locked"]["operation_type"]) == ("vision", "cooldown")


def test_end_to_end_a_vision_test_on_the_shared_resource_keeps_the_transcription_row(world, monkeypatch):  # noqa: F811
    # the test adapter maps every feature to the same resource: a second feature, test-only
    from shared.engine_control import registry

    d = registry.descriptor("test-vm")
    monkeypatch.setitem(d, "features", ["transcription", "vision"])
    monkeypatch.setitem(d, "actions", ["scale", "drain_stop", "test"])
    p = prepared(world)
    with world() as db:
        op = service.enqueue(db, p["plan_id"], p["plan_hash"], "scale", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.publish_applied(db, op["operation_id"], gen, {})
        service.finish(db, op["operation_id"], gen, "succeeded", {"ready_replicas": 2}, safe=True)
        e = db.get(Engine, "e")
        from shared.engine_control.contracts import PlanRequest

        t = service.create_plan(db, e, PlanRequest(type="test", feature="vision", engine_version=e.version,
                                                   max_usd="0.1"), "admin")
        op = service.enqueue(db, t["plan_id"], t["plan_hash"], "vision-test", "admin", True)
        gen = service.claim(db, op["operation_id"], "one")
        service.publish_applied(db, op["operation_id"], gen, {})  # test: publishes nothing
        service.finish(db, op["operation_id"], gen, "succeeded", {"ready_replicas": 7}, safe=True)
        (resource,) = service.runtime_status(db, db.get(Engine, "e"))["resources"]
    assert resource["applied"]["feature"] == "transcription"  # the applied revision did not move
    assert resource["observed"] == {"ready_replicas": 7}
    assert (resource["observed_feature"], resource["observed_operation_type"]) == ("vision", "test")
