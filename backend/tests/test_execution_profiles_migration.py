"""Additive 0009 upgrade and InnoDB authorization ordering on disposable SQL."""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.access import migration, service, policy
from shared.access.models import AuthorizationEpoch, EffectAdmission
from shared.engine_control import service as control
from tests.test_execution_profiles import world, prepared, grant_row


def mysql_url():
    url = os.environ.get("ENGINE_CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires disposable InnoDB database")
    if not (make_url(url).database or "").startswith("engine_control_test_"):
        pytest.fail("Refusing to touch a non-test database")
    return url


@pytest.fixture(params=["sqlite", "mysql"])
def database(request):
    sql = create_engine("sqlite://" if request.param == "sqlite" else mysql_url())
    yield sql
    Base.metadata.drop_all(sql)
    sql.dispose()


@pytest.mark.parametrize("connection", [False, True])
def test_upgrade_retains_old_profiles_operations_and_unqualified_resources(
    database, connection
):
    # Legacy columns deliberately predate 0009. Minimal parent tables satisfy
    # the new foreign keys without copying any production database.
    with database.begin() as db:
        for ddl in [
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)",
            "CREATE TABLE engines (id VARCHAR(36) PRIMARY KEY)",
            "CREATE TABLE engine_runtime_profiles (id VARCHAR(36) PRIMARY KEY, profile JSON, applied_at DATETIME)",
            "CREATE TABLE engine_operations (id VARCHAR(36) PRIMARY KEY, actor_id VARCHAR(36), state VARCHAR(40), effect_started BOOLEAN)",
            "CREATE TABLE engine_control_resources (`key` VARCHAR(200) PRIMARY KEY, operation_id VARCHAR(36), gate_closed BOOLEAN)",
        ]:
            db.execute(text(ddl))
        db.execute(
            text(
                'INSERT INTO engine_runtime_profiles (id,profile,applied_at) VALUES (\'legacy\',\'{"service":"worker","gpu_uuid":"GPU-old"}\',\'2026-01-01 00:00:00\')'
            )
        )
        db.execute(
            text(
                "INSERT INTO engine_operations (id,actor_id,state,effect_started) VALUES ('active','original','needs_attention',1)"
            )
        )
        db.execute(
            text(
                "INSERT INTO engine_control_resources (`key`,operation_id,gate_closed) VALUES ('shared','active',1)"
            )
        )
    if connection:
        with database.begin() as db:
            migration.upgrade(db)
            migration.upgrade(db)
    else:
        migration.upgrade(database)
        migration.upgrade(database)
    migration.validate_schema(database)
    with database.connect() as db:
        row = db.execute(text("SELECT * FROM engine_runtime_profiles")).mappings().one()
        assert "GPU-old" in str(row["profile"])
        assert row["applied_at"] is not None
        assert row["source_profile_revision_id"] is None and row["source_hash"] is None
        op = db.execute(text("SELECT * FROM engine_operations")).mappings().one()
        assert op["actor_id"] == "original" and op["state"] == "needs_attention"
        assert (
            op["effect_started"]
            and op["cancel_requested_by"] is None
            and op["recovery_requested_by"] is None
        )
        resource = (
            db.execute(text("SELECT * FROM engine_control_resources")).mappings().one()
        )
        assert resource["operation_id"] == "active" and resource["gate_closed"]
        assert (
            db.execute(text("SELECT count(*) FROM access_resource_scopes")).scalar()
            == 0
        )
        assert db.execute(text("SELECT count(*) FROM execution_profiles")).scalar() == 0
        assert (
            db.execute(
                text("SELECT version FROM access_authorization_epoch WHERE id=1")
            ).scalar()
            == 0
        )


def test_migration_requires_control_and_rollback_retains_history(database):
    with pytest.raises(RuntimeError, match="0007"):
        migration.upgrade(database)
    with pytest.raises(RuntimeError, match="retained"):
        migration.downgrade(database)


def test_schema_validation_detects_missing_authority_epoch(database):
    Base.metadata.create_all(database)
    with pytest.raises(RuntimeError, match="epoch"):
        migration.validate_schema(database)
    migration.upgrade(database)
    migration.validate_schema(database)


def test_early_0009_admission_metadata_upgrade_preserves_uncertain_history(database):
    Base.metadata.create_all(database)
    with database.begin() as db:
        db.execute(text("DROP TABLE access_effect_admissions"))
        db.execute(text("""CREATE TABLE access_effect_admissions (
            id VARCHAR(36) PRIMARY KEY, operation_id VARCHAR(36) NOT NULL,
            generation INTEGER NOT NULL, step VARCHAR(100) NOT NULL,
            actor_id VARCHAR(80) NOT NULL, executor VARCHAR(100) NOT NULL,
            epoch INTEGER NOT NULL, state VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            UNIQUE(operation_id,generation,step))"""))
        db.execute(
            text(
                """INSERT INTO access_effect_admissions
            (id,operation_id,generation,step,actor_id,executor,epoch,state,created_at)
            VALUES ('early','in-flight',3,'build','original-actor','host-a',12,'uncertain','2026-01-01 00:00:00')"""
            )
        )
    with pytest.raises(RuntimeError, match="0009"):
        migration.validate_schema(database)
    migration.upgrade(database)
    migration.upgrade(database)
    migration.validate_schema(database)
    with database.connect() as db:
        row = db.execute(EffectAdmission.__table__.select()).mappings().one()
        assert row["operation_id"] == "in-flight" and row["generation"] == 3
        assert row["actor_id"] == "original-actor" and row["epoch"] == 12
        assert row["state"] == "uncertain"
        assert (
            row["action"] == "effect" and row["targets"] == [] and row["decision"] == {}
        )
        assert row["valid_until"] is None


@pytest.fixture
def mysql_world(world):
    sql = create_engine(mysql_url(), pool_pre_ping=True)
    Base.metadata.create_all(sql)
    factory = sessionmaker(bind=sql)
    # Reuse the third-provider fixture's synthetic users, engines and scopes.
    with world() as source, sql.begin() as target:
        for table in Base.metadata.sorted_tables:
            rows = source.execute(table.select()).mappings().all()
            if rows:
                target.execute(table.insert(), [dict(row) for row in rows])
    yield factory
    Base.metadata.drop_all(sql)
    sql.dispose()


def test_innodb_revocation_committed_before_admission_denies_cached_actor(mysql_world):
    with mysql_world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        gen = control.claim(db, op["operation_id"], "executor")
    started = Event()
    with mysql_world() as revoker, ThreadPoolExecutor(max_workers=1) as pool:
        policy.epoch(revoker, True)

        def effect():
            with mysql_world() as db:
                # Hold an old identity snapshot before waiting on the SQL epoch.
                assert grant_row(db, g["id"]).revoked_at is None
                started.set()
                try:
                    control.admit_effect(
                        db, op["operation_id"], gen, "sdk:after-revoke"
                    )
                    db.commit()
                    return "admitted"
                except control.ControlError as exc:
                    db.rollback()
                    return exc.code

        future = pool.submit(effect)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        service.revoke(revoker, g["id"], 0, "bootstrap")
        assert future.result(timeout=5) == "ACCESS_DENIED"
    with mysql_world() as db:
        assert db.query(EffectAdmission).count() == 0


def test_innodb_admission_before_revoke_is_durable_and_later_effect_is_denied(
    mysql_world,
):
    with mysql_world() as db:
        g, p = prepared(db)
        op = control.enqueue(db, p["plan_id"], p["plan_hash"], "once", "operator", True)
        gen = control.claim(db, op["operation_id"], "executor")
    started = Event()
    with mysql_world() as executor, ThreadPoolExecutor(max_workers=1) as pool:
        control.admit_effect(
            executor, op["operation_id"], gen, "sdk:accepted-before-revoke"
        )

        def revoke():
            with mysql_world() as db:
                started.set()
                return service.revoke(db, g["id"], 0, "bootstrap")

        future = pool.submit(revoke)
        assert started.wait(3)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.15)
        executor.commit()
        assert future.result(timeout=5)["revoked_at"] is not None
    with mysql_world() as db:
        first = db.query(EffectAdmission).one()
        assert first.state == "uncertain"
        assert first.epoch < db.get(AuthorizationEpoch, 1).version
        with pytest.raises(control.ControlError, match="ACCESS_DENIED"):
            control.admit_effect(db, op["operation_id"], gen, "sdk:next")
