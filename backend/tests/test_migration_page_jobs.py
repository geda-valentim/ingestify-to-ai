"""Legacy schema accepts Redis-only PAGE ids after the targeted migration."""
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, inspect, text

from shared.migration_page_jobs import upgrade


def test_removes_only_page_job_fk_preserving_existing_pages():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("jobs", metadata, Column("id", String, primary_key=True))
    Table("pages", metadata, Column("id", String, primary_key=True),
          Column("job_id", String, ForeignKey("jobs.id", name="owner_fk", ondelete="CASCADE")),
          Column("page_job_id", String, ForeignKey("jobs.id", name="legacy_page_fk")),
          Column("page_number", Integer))
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.execute(text("INSERT INTO jobs VALUES ('main')"))
        db.execute(text("INSERT INTO pages VALUES ('existing', 'main', NULL, 1)"))
    assert upgrade(engine) == ["legacy_page_fk"]
    with engine.begin() as db:
        db.execute(text("INSERT INTO pages VALUES ('new', 'main', 'redis-only-page', 2)"))
        assert db.execute(text("SELECT count(*) FROM pages")).scalar() == 2
    assert [fk["constrained_columns"] for fk in inspect(engine).get_foreign_keys("pages")] == [["job_id"]]
    assert upgrade(engine) == []


def test_fresh_schema_without_legacy_fk_needs_no_change():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("pages", metadata, Column("id", String, primary_key=True), Column("page_job_id", String))
    metadata.create_all(engine)
    assert upgrade(engine) == []
