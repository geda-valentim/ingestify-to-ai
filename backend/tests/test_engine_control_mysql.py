"""InnoDB concurrency gates; run only against a disposable, explicitly named DB."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from shared.config import get_settings
from shared.database import Base
from shared.engine_control import admission, registry, service
from shared.engine_control.contracts import PlanRequest
from shared.engine_control.models import (
    ControlAdmission,
    ControlResource,
    OperationOutbox,
)
from shared.models import Engine


@pytest.fixture
def mysql_world(monkeypatch):
    url = os.environ.get("ENGINE_CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires disposable InnoDB database")
    if not (make_url(url).database or "").startswith("engine_control_test_"):
        pytest.fail("Refusing to touch a non-test database")
    bind = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind)
    Session = sessionmaker(bind=bind)
    monkeypatch.setattr(get_settings(), "engine_control_enabled", True)

    class Adapter:
        def validate(self, engine, feature, profile, db):
            return profile

        def resource_keys(self, engine, feature, profile):
            return ["test:single-resource"]

        def plan(self, engine, req, profile, db):
            return dict(
                drain=True, stages=["draining", "applying"], estimated_max_usd="0"
            )

    registry.register(
        "innodb-test",
        dict(
            type="innodb-test",
            execution_mode="remote_runner",
            features=["transcription"],
            actions=["scale"],
            credential_fields=[],
        ),
        Adapter,
    )
    with Session() as db:
        db.add(
            Engine(
                id="mysql-engine",
                slug="mysql-engine",
                display_name="Disposable",
                adapter_type="innodb-test",
                config={"features": {}},
                deployments={},
                version=0,
                limit_usd=1,
                min_remaining_usd=0,
            )
        )
        db.commit()
        raw = dict(
            adapter_version=1,
            schema_version=1,
            binding={"workers": 1},
            model_profile_id="fixture",
            desired_replicas=1,
            max_replicas=1,
            min_ready_replicas=0,
            provider_settings={},
        )
        service.save_profile(
            db, db.get(Engine, "mysql-engine"), "transcription", raw, 0, "admin"
        )
        plan = service.create_plan(
            db,
            db.get(Engine, "mysql-engine"),
            PlanRequest(type="scale", engine_version=1),
            "admin",
        )
    yield Session, plan
    registry._registry.pop(("innodb-test", 1))
    Base.metadata.drop_all(bind)
    bind.dispose()


def test_concurrent_same_request_returns_one_operation(mysql_world):
    Session, plan = mysql_world
    barrier = Barrier(2)

    def accept():
        with Session() as db:
            barrier.wait(timeout=10)
            return service.enqueue(
                db, plan["plan_id"], plan["plan_hash"], "same", "admin"
            )["operation_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(accept)
        two = pool.submit(accept)
        assert one.result(timeout=15) == two.result(timeout=15)
    with Session() as db:
        assert db.query(OperationOutbox).count() == 1


def test_concurrent_distinct_requests_have_one_resource_owner(mysql_world):
    Session, plan = mysql_world
    barrier = Barrier(2)

    def accept(key):
        with Session() as db:
            barrier.wait(timeout=10)
            try:
                return service.enqueue(
                    db, plan["plan_id"], plan["plan_hash"], key, "admin"
                )["operation_id"]
            except service.ControlError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(accept, "a")
        b = pool.submit(accept, "b")
        values = [a.result(timeout=15), b.result(timeout=15)]
    assert values.count("OPERATION_CONFLICT") == 1
    with Session() as db:
        assert db.query(OperationOutbox).count() == 1
        assert db.get(ControlResource, plan["resources"][0]).operation_id in values


def test_gate_and_direct_admission_are_serialized(mysql_world):
    Session, plan = mysql_world
    barrier = Barrier(2)

    def admit():
        barrier.wait(timeout=10)
        try:
            return admission.acquire(
                "transcription", "legacy-job", "mysql-engine", Session
            )
        except service.ControlError as exc:
            assert exc.code == "ENGINE_MAINTENANCE"
            return []

    def close_gate():
        with Session() as db:
            barrier.wait(timeout=10)
            service.locked_engine(db, "mysql-engine")
            resource = (
                db.query(ControlResource)
                .filter_by(key=plan["resources"][0])
                .with_for_update()
                .one()
            )
            resource.gate_closed = True
            db.flush()
            admitted = (
                db.query(ControlAdmission)
                .filter(ControlAdmission.released_at.is_(None))
                .count()
            )
            db.commit()
            return admitted

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(admit)
        b = pool.submit(close_gate)
        ids, in_flight = a.result(timeout=15), b.result(timeout=15)
    assert in_flight == len(ids)
    with pytest.raises(service.ControlError, match="ENGINE_MAINTENANCE"):
        admission.acquire("transcription", "later-job", "mysql-engine", Session)
    admission.release(ids, Session)
