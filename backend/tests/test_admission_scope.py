"""Admission of a feature without a runtime profile on the local engine (spec 0007 §4.6).

Without a profile, a feature is admitted only on its own services (any host, no GPU key): a
document conversion is not refused, nor does it hold a drain, because transcription's dedicated
service is in maintenance. A feature with a profile keeps the profile's keys.
"""
from datetime import datetime, timedelta

import pytest

from shared.engine_control import admission
from shared.engine_control.models import (ControlAdmission, ControlResource, EngineOperation, OperationPlan,
                                          RuntimeProfile)
from shared.models import Engine
from tests.test_engine_control import world  # noqa: F401  (fixture)

ROWS = ["local:h1:service:worker", "local:h1:service:worker-audio", "local:h1:service:worker-vision",
        "local:h2:service:worker", "local:h2:service:worker-audio", "local:h1:gpu:GPU-0",
        "local:h:3:service:worker"]  # a host id with ":" is still a host


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
        assert _keys(db, "document_conversion") == ["local:h1:service:worker", "local:h2:service:worker",
                                                    "local:h:3:service:worker"]
        assert _keys(db, "transcription") == ["local:h1:service:worker", "local:h1:service:worker-audio",
                                              "local:h2:service:worker", "local:h2:service:worker-audio",
                                              "local:h:3:service:worker"]
        # h2 and h:3 have no worker-vision row yet: every row there (its first profile's drain)
        assert _keys(db, "vision") == ["local:h1:service:worker", "local:h1:service:worker-vision",
                                       "local:h2:service:worker", "local:h2:service:worker-audio",
                                       "local:h:3:service:worker"]


def test_a_feature_without_a_service_of_its_own_keeps_every_row(local):
    with local() as db:
        assert _keys(db, "unknown-feature") == sorted(ROWS)  # no fail-open


def test_a_document_is_admitted_while_the_audio_service_drains(local):
    with local() as db:
        _close(db, "local:h1:service:worker-audio")
        assert admission.admission_refusal(db, "document_conversion", "l") is None
        assert not admission.placement_blocked(db, db.get(Engine, "l"), "document_conversion")
        assert admission.admission_refusal(db, "transcription", "l") == "ENGINE_MAINTENANCE"
    tickets = admission.acquire("document_conversion", "task:doc", "l", local)
    assert len(tickets) == 3  # one per host's generic worker, none on the audio service


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


def _operation(db, feature, trigger=None, plan=True):
    """An operation of `feature` holding every row, as a local plan locks all its keys."""
    body = {"type": "cooldown", **({"feature": feature} if feature else {}),
            **({"trigger": trigger} if trigger else {})}
    at = datetime(2026, 10, 28)
    if plan:
        db.add(OperationPlan(id="p", engine_id="l", actor_id="a", engine_version=0, body=body, hash="h",
                             expires_at=at + timedelta(hours=1)))
        db.add(EngineOperation(id="op", engine_id="l", actor_id="a", plan_id="p", idempotency_key="k",
                               request_hash="r", deadline=at + timedelta(hours=1), reserved_usd=0))
    for r in db.query(ControlResource):
        r.operation_id = "op"  # without a plan: a lock with no operation behind it (a CLI deploy's)
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


@pytest.mark.parametrize("kwargs", [{"feature": None, "trigger": "idle_policy"}, {"feature": "transcription",
                                                                              "trigger": "idle_policy", "plan": False}])
def test_a_lock_without_a_readable_automatic_plan_still_blocks_placement(local, kwargs):
    with local() as db:
        _operation(db, **kwargs)
        assert admission.placement_blocked(db, db.get(Engine, "l"), "document_conversion")


def test_without_its_service_row_yet_a_feature_keeps_every_row(world):  # noqa: F811
    """Only the live profile's rows exist: a document holds a ticket on every row, the GPU
    included, so the drain of its first profile's apply waits for it."""
    with world() as db:
        db.add(Engine(id="l", slug="local", display_name="Local", adapter_type="local",
                      config={"features": {}, "gpus": [{"ref": "g0", "uuid": "GPU-0"}]}, deployments={}, version=0))
        for key in ("local:h1:gpu:GPU-0", "local:h1:service:worker-live"):
            db.add(ControlResource(key=key, owner_engine_id="l"))
        db.commit()
        assert _keys(db, "document_conversion") == ["local:h1:gpu:GPU-0", "local:h1:service:worker-live"]
    tickets = admission.acquire("document_conversion", "task:doc", "l", world)
    with world() as db:
        held = {t.resource_key for t in db.query(ControlAdmission).filter(ControlAdmission.id.in_(tickets))}
    assert "local:h1:gpu:GPU-0" in held


def test_a_host_without_the_canonical_row_keeps_every_row_of_that_host(world):  # noqa: F811
    """The canonical row exists on another host only (a CLI deploy's `unregistered`): on h1 the
    document still holds the GPU, which the drain of its first profile on h1 waits for."""
    with world() as db:
        db.add(Engine(id="l", slug="local", display_name="Local", adapter_type="local",
                      config={"features": {}}, deployments={}, version=0))
        for key in ("local:unregistered:service:worker", "local:h1:gpu:G", "local:h1:service:worker-live",
                    "legacy-key"):
            db.add(ControlResource(key=key, owner_engine_id="l"))
        db.commit()
        assert _keys(db, "document_conversion") == ["legacy-key", "local:h1:gpu:G", "local:h1:service:worker-live",
                                                    "local:unregistered:service:worker"]  # no fail-open


def test_the_host_of_a_key():
    from shared.engine_control.local_services import key_host

    assert [key_host(k) for k in ("local:h1:gpu:G", "local:h:3:service:worker", "LOCAL:h:service:w", "x")] == \
        ["h1", "h:3", None, None]
