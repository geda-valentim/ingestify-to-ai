"""Helpers for the spec 0004 migration tests: a database in the pre-0004 schema."""
from datetime import datetime

from sqlalchemy import create_engine, event, text

from shared.database import Base
from shared.models import APIKey, Job, User

T0 = datetime(2026, 9, 1, 12, 0, 0)


def sqlite_engine(path, foreign_keys=True):
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
    if foreign_keys:
        @event.listens_for(engine, "connect")
        def _pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def make_legacy_database(path):
    """The schema as the old code left it: no 0004 tables, columns or index."""
    engine = sqlite_engine(path)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_jobs_user_type_project_folder"))
        conn.execute(text("ALTER TABLE jobs DROP COLUMN project_id"))
        conn.execute(text("ALTER TABLE jobs DROP COLUMN folder_id"))
        conn.execute(text("ALTER TABLE api_keys DROP COLUMN project_id"))
        conn.execute(text("DROP TABLE folders"))
        conn.execute(text("DROP TABLE projects"))
        conn.execute(text("DROP TABLE app_migrations"))
    return engine


def add_user(conn, user_id):
    conn.execute(User.__table__.insert().values(
        id=user_id, email=f"{user_id}@example.com", username=user_id, hashed_password="x",
    ))


def add_job(conn, job_id, user_id, job_type="MAIN", created_at=T0):
    # Core insert: only the columns given (plus Python defaults) - works on the old schema.
    conn.execute(Job.__table__.insert().values(
        id=job_id, user_id=user_id, job_type=job_type, name=job_id, created_at=created_at,
    ))


def add_key(conn, key_id, user_id, name=None, created_at=T0):
    conn.execute(APIKey.__table__.insert().values(
        id=key_id, user_id=user_id, key_hash=f"hash-{key_id}", name=name or key_id,
        created_at=created_at,
    ))


def column(engine, table, column_name, row_id):
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT {column_name} FROM {table} WHERE id = :id"), {"id": row_id}
        ).scalar()
