"""Admission of a feature without a runtime profile on the local engine (spec 0007 §4.6).

Without a profile, a feature is admitted only on its own services (any host, no GPU key): a
document conversion is not refused, nor does it hold a drain, because transcription's dedicated
service is in maintenance. A feature with a profile keeps the profile's keys.
"""
from datetime import datetime, timedelta

import pytest

from shared.engine_control import admission
from shared.engine_control.models import ControlResource, EngineOperation, OperationPlan, RuntimeProfile
from shared.models import Engine
from tests.test_engine_control import world  # noqa: F401  (fixture)

ROWS = ["local:h1:service:worker", "local:h1:service:worker-audio", "local:h1:service:worker-vision",
        "local:h2:service:worker", "local:h2:service:worker-audio", "local:h1:gpu:GPU-0",
        "local:a:b:service:worker", "LOCAL:h3:service:worker"]  # match the LIKE, not the key shape


@pytest.fixture
def local(world):  # noqa: F811
    with world() as db:
        db.add(Engine(id="l", slug="local", display_name="Local", adapter_type="local",
                      config={"features": {}, "gpus": [{"ref": "g0", "uuid": "GPU-0"}]}, deployments={}, version=0))
        for key in ROWS:
            db.add(ControlResource(key=key, owner_engine_id="l"))
        db.commit()
    return world


def _keys(db, feature):
    return sorted(r.key for r in admission.resource_rows(db, db.get(Engine, "l"), feature, lock=False))


def _close(db, key):
    db.get(ControlResource, key).gate_closed = True
    db.commit()


def test_without_a_profile_a_feature_is_admitted_on_its_own_services_only(local):
    with local() as db:
        assert _keys(db, "document_conversion") == ["local:h1:service:worker", "local:h2:service:worker"]
        assert _keys(db, "transcription") == ["local:h1:service:worker", "local:h1:service:worker-audio",
                                              "local:h2:service:worker", "local:h2:service:worker-audio"]
        assert _keys(db, "vision") == ["local:h1:service:worker", "local:h1:service:worker-vision",
                                       "local:h2:service:worker"]


def test_a_document_is_admitted_while_the_audio_service_drains(local):
    with local() as db:
        _close(db, "local:h1:service:worker-audio")
        assert admission.admission_refusal(db, "document_conversion", "l") is None
        assert not admission.placement_blocked(db, db.get(Engine, "l"), "document_conversion")
        assert admission.admission_refusal(db, "transcription", "l") == "ENGINE_MAINTENANCE"
    tickets = admission.acquire("document_conversion", "task:doc", "l", local)
    assert len(tickets) == 2  # one per host's generic worker, none on the audio service


def test_a_document_is_refused_while_the_generic_worker_drains(local):
    with local() as db:
        _close(db, "local:h2:service:worker")
        assert admission.admission_refusal(db, "document_conversion", "l") == "ENGINE_MAINTENANCE"
        assert admission.placement_blocked(db, db.get(Engine, "l"), "document_conversion")


def test_a_feature_with_a_profile_keeps_its_profile_keys(local):
    with local() as db:
        db.add(RuntimeProfile(engine_id="l", feature="transcription", revision=1, created_at=datetime(2026, 10, 28),
                              profile={"provider_settings": {"host_id": "h1"}, "binding": {"gpu_ref": "g0"}}))
        db.commit()
        assert _keys(db, "transcription") == ["local:h1:gpu:GPU-0", "local:h1:service:worker",
                                              "local:h1:service:worker-audio"]


def test_the_service_map_moved_to_shared_keeps_its_old_path():
    from shared.engine_control import local_services
    from workers.engine_control import local

    assert local.SERVICES is local_services.SERVICES


def _operation(db, feature, trigger=None):
    """An operation of `feature` holding every row, as a local plan locks all its keys."""
    body = {"feature": feature, "type": "cooldown", **({"trigger": trigger} if trigger else {})}
    at = datetime(2026, 10, 28)
    db.add(OperationPlan(id="p", engine_id="l", actor_id="a", engine_version=0, body=body, hash="h",
                         expires_at=at + timedelta(hours=1)))
    db.add(EngineOperation(id="op", engine_id="l", actor_id="a", plan_id="p", idempotency_key="k",
                           request_hash="r", deadline=at + timedelta(hours=1), reserved_usd=0))
    for r in db.query(ControlResource):
        r.operation_id = "op"
    db.commit()


def test_an_automatic_operation_of_another_feature_does_not_block_placement(local):
    with local() as db:
        _operation(db, "transcription", trigger="idle_policy")
        e = db.get(Engine, "l")
        assert not admission.placement_blocked(db, e, "document_conversion")
        assert admission.placement_blocked(db, e, "transcription")


def test_a_human_operation_of_another_feature_still_blocks_placement(local):
    with local() as db:
        _operation(db, "transcription")
        assert admission.placement_blocked(db, db.get(Engine, "l"), "document_conversion")
