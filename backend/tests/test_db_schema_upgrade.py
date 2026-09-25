"""Existing databases get columns added after their tables were created (create_all does not)."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from shared import database
from shared.models import Job, User  # noqa: F401  (register models)


@pytest.fixture
def old_database(tmp_path):
    """A database created before the crawler columns existed"""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    database.Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE jobs DROP COLUMN crawler_config"))
        conn.execute(text("ALTER TABLE jobs DROP COLUMN crawler_schedule"))
    return engine


def job_columns(engine):
    return {col["name"] for col in inspect(engine).get_columns("jobs")}


def test_old_database_breaks_job_queries_without_upgrade(old_database):
    session = sessionmaker(bind=old_database)()
    with pytest.raises(Exception, match="crawler_config"):
        session.query(Job).first()


def test_missing_columns_are_added_and_queries_work(old_database):
    database._add_missing_columns(old_database)

    assert {"crawler_config", "crawler_schedule"} <= job_columns(old_database)
    session = sessionmaker(bind=old_database)()
    assert session.query(Job).first() is None


def test_upgrade_is_idempotent(old_database):
    database._add_missing_columns(old_database)
    database._add_missing_columns(old_database)  # no "duplicate column" error
    assert {"crawler_config", "crawler_schedule"} <= job_columns(old_database)
