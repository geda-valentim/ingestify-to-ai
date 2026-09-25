from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from shared.config import get_settings

settings = get_settings()

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=settings.environment == "development",  # Log SQL in dev
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session.

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables.
    Called during app startup.
    """
    from shared.models import User, APIKey, Job, Page  # Import models to register them
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# Columns added to existing tables after they were first created. create_all() only
# creates missing tables, so existing databases need these ALTERs (otherwise every
# query on the model fails with "Unknown column"). Plain ADD COLUMN works on both
# MySQL and MariaDB. Keep in sync with backend/migrations/*.sql.
_ADDED_COLUMNS = {
    "jobs": {
        "crawler_config": "JSON NULL",  # migrations/002_add_crawler_fields.sql
        "crawler_schedule": "JSON NULL",
    },
}


def _add_missing_columns(bind=None) -> None:
    """Add columns from _ADDED_COLUMNS that an existing table does not have yet"""
    from sqlalchemy import inspect, text

    bind = bind or engine
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    with bind.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for column, ddl in columns.items():
                if column not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
