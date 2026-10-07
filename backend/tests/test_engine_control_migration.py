"""Retain existing resource ownership when upgrading an early control schema."""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from shared.engine_control.migration import TABLES, upgrade
from shared.engine_control.models import ControlResource


@pytest.fixture(params=["sqlite", "mysql"])
def database(request):
    url = "sqlite://"
    if request.param == "mysql":
        url = os.environ.get("ENGINE_CONTROL_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Requires disposable InnoDB database")
        if not (make_url(url).database or "").startswith("engine_control_test_"):
            pytest.fail("Refusing to touch a non-test database")
    engine = create_engine(url)
    yield engine
    for table in reversed(TABLES):
        table.drop(engine, checkfirst=True)
    engine.dispose()


@pytest.mark.parametrize("use_connection", [False, True])
def test_upgrade_early_schema_retains_resources_and_is_repeatable(database, use_connection):
    with database.begin() as conn:
        conn.execute(text("""
            CREATE TABLE engine_control_resources (
                `key` VARCHAR(200) PRIMARY KEY,
                owner_engine_id VARCHAR(36) NOT NULL,
                operation_id VARCHAR(36),
                gate_closed BOOLEAN NOT NULL,
                applied JSON NOT NULL,
                observed JSON NOT NULL,
                observed_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO engine_control_resources
                (`key`, owner_engine_id, operation_id, gate_closed, applied, observed)
            VALUES ('local:host:worker', 'engine', 'in-flight', 1, '{}', '{}')
        """))
    if use_connection:
        with database.begin() as conn:
            upgrade(conn)
            upgrade(conn)
    else:
        upgrade(database)
        upgrade(database)
    with database.connect() as conn:
        row = conn.execute(ControlResource.__table__.select()).mappings().one()
        assert row["owner_engine_id"] == "engine"
        assert row["operation_id"] == "in-flight"
        assert row["gate_closed"] is True
        assert row["maintenance_operation_id"] is None
    indexes = {i["name"] for i in inspect(database).get_indexes("engine_control_resources")}
    assert "ix_engine_control_resources_maintenance_operation_id" in indexes


def test_upgrade_restores_missing_maintenance_index(database):
    upgrade(database)
    index = next(i for i in ControlResource.__table__.indexes if "maintenance_operation_id" in i.columns)
    index.drop(database)
    upgrade(database)
    assert index.name in {i["name"] for i in inspect(database).get_indexes(index.table.name)}
