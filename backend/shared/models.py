from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, BigInteger, Enum, JSON, Index, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from shared.database import Base


def generate_uuid():
    """Generate UUID as string"""
    return str(uuid.uuid4())


# Column type of a project/folder `name_key` (see shared/projects.py).
#
# Binary collation on MariaDB: the unique index must compare exactly what the
# Python normalisation computed. With utf8mb4_general_ci it would consider equal
# keys that name_key() keeps apart (e.g. Cyrillic "й"/"и"), the INSERT would
# collide and the Python-equality re-read would never find the row.
# With mysql+pymysql the dialect is called "mysql" even against MariaDB; the
# "mariadb" variant covers a mariadb+pymysql URL.
_BINARY_KEY = mysql.VARCHAR(200, charset="utf8mb4", collation="utf8mb4_bin")
KEY_TYPE = String(200).with_variant(_BINARY_KEY, "mysql").with_variant(_BINARY_KEY, "mariadb")

# New tables state charset/collation explicitly instead of inheriting the schema
# default, so create_all (dev/CI) and scripts/migrate_0003_projects.py agree.
_UTF8MB4_TABLE = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"}

# Name of the composite index on jobs used by project counts and GET /jobs filters.
JOBS_PROJECT_INDEX = "ix_jobs_user_type_project_folder"
JOBS_PROJECT_INDEX_COLUMNS = ("user_id", "job_type", "project_id", "folder_id", "status", "created_at")


class JobStatus(str, enum.Enum):
    """Job status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FileStatus(str, enum.Enum):
    """File status enum for crawled files"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class User(Base):
    """User model for authentication"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Admin flag - grants access to /admin/* endpoints. Promote users with scripts/make_admin.py
    is_admin = Column(Boolean, default=False, server_default="0", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class APIKey(Base):
    """API Key model for token-based authentication"""
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(String(255), nullable=False, index=True)
    name = Column(String(100))  # User-friendly name for the key
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Project that uploads made with this key go to when the request names none.
    # No ForeignKey on purpose (spec 0003 § 4.2): the binding is checked by the
    # application when it is written and again when it is used.
    project_id = Column(String(36), nullable=True)

    # Relationship
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey(id={self.id}, user_id={self.user_id}, name={self.name})>"


class Job(Base):
    """Job model - stores metadata about conversion jobs"""
    __tablename__ = "jobs"
    __table_args__ = (
        # Covers the per-project counts (GROUP BY project_id, folder_id, status)
        # and GET /jobs filtered by project/folder ordered by date. The migration
        # script creates the same index under the same name.
        Index(JOBS_PROJECT_INDEX, *JOBS_PROJECT_INDEX_COLUMNS),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)  # job_id
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)

    # File information
    filename = Column(String(255))
    name = Column(String(1000))  # User-friendly job name (up to 1000 chars)
    source_type = Column(String(50))  # file, url, gdrive, dropbox
    source_url = Column(Text)  # For URL/cloud sources
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    file_checksum = Column(String(64), index=True)  # SHA256 hash for deduplication

    # MinIO storage paths
    minio_upload_path = Column(String(500))  # Path to uploaded file in MinIO
    minio_result_path = Column(String(500))  # Path to result markdown in MinIO

    # Job status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text)

    # PDF-specific
    total_pages = Column(Integer)  # NULL for non-PDF
    pages_completed = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)

    # Hierarchical job tracking
    parent_job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"))
    job_type = Column(String(20))  # MAIN, SPLIT, PAGE, MERGE, DOWNLOAD, CRAWLER

    # Location (MAIN jobs only; children inherit through the parent). No
    # ForeignKey on purpose: adding one to `jobs` rebuilds the table
    # (ALGORITHM=COPY) on MariaDB. Integrity is kept by the application.
    project_id = Column(String(36), nullable=True)
    folder_id = Column(String(36), nullable=True)

    # Crawler-specific fields (STI pattern - only for job_type='crawler')
    crawler_config = Column(JSON, nullable=True)  # CrawlerConfig (mode, engine, retry, assets, proxy)
    crawler_schedule = Column(JSON, nullable=True)  # CrawlerSchedule (cron, timezone, next_runs)

    # Result metadata (content is in Elasticsearch and MySQL for pages)
    char_count = Column(Integer)  # Total characters in result
    has_elasticsearch_result = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="jobs")
    pages = relationship("Page", back_populates="job", foreign_keys="Page.job_id", cascade="all, delete-orphan")
    crawled_files = relationship("CrawledFile", foreign_keys="CrawledFile.execution_id", cascade="all, delete-orphan")
    child_jobs = relationship(
        "Job",
        backref="parent",
        remote_side=[id],
        foreign_keys=[parent_job_id],
        cascade="all, delete-orphan",
        single_parent=True
    )

    tag_rows = relationship(
        "JobTag",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="JobTag.tag",
    )

    @property
    def tags(self):
        """The job's tags, normalised and sorted (see shared/tags.py)."""
        return [row.tag for row in self.tag_rows]

    def __repr__(self):
        return f"<Job(id={self.id}, status={self.status}, filename={self.filename})>"


class JobTag(Base):
    """
    A user-defined label on a job. One row per (job, tag).

    A table rather than a JSON column so "every job tagged X" is an indexed
    lookup and GET /tags can count tags with a GROUP BY.
    """
    __tablename__ = "job_tags"

    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    tag = Column(String(50), primary_key=True, index=True)

    job = relationship("Job", back_populates="tag_rows")


class Project(Base):
    """
    A user's project. Every MAIN job belongs to exactly one (spec 0003).

    `name` is the display name (case and accents kept); `name_key` is the
    normalised, immutable identity used by get-or-add (shared/projects.py).
    """
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_projects_user_key"),
        _UTF8MB4_TABLE,
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    name_key = Column(KEY_TYPE, nullable=False)
    description = Column(Text)
    archived_at = Column(DateTime)  # phase 2; the column exists from the start
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Project(id={self.id}, user_id={self.user_id}, name={self.name})>"


class Folder(Base):
    """A folder inside a project (one level only; '/' is reserved in names)."""
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("project_id", "name_key", name="uq_folders_project_key"),
        _UTF8MB4_TABLE,
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # Denormalised from the project so ownership checks are a single lookup.
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    name_key = Column(KEY_TYPE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Folder(id={self.id}, project_id={self.project_id}, name={self.name})>"


class AppMigration(Base):
    """Markers of one-shot data migrations (e.g. "0003_backfill", "0003_tail")."""
    __tablename__ = "app_migrations"
    __table_args__ = (_UTF8MB4_TABLE,)

    name = Column(String(64), primary_key=True)
    applied_at = Column(DateTime, nullable=False)  # UTC, application clock


class Page(Base):
    """Page model - stores metadata about individual PDF pages"""
    __tablename__ = "pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)  # 1-indexed

    # Page job reference
    page_job_id = Column(String(36))  # Reference to PAGE job (no FK constraint - job may not exist yet)

    # MinIO storage path
    minio_page_path = Column(String(500))  # Path to split page PDF in MinIO

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0, nullable=False)  # Track retry attempts (max 3)

    # Result metadata and content
    markdown_content = Column(Text)  # Full markdown content for this page
    char_count = Column(Integer)
    has_elasticsearch_result = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    job = relationship("Job", back_populates="pages", foreign_keys=[job_id])

    def __repr__(self):
        return f"<Page(id={self.id}, job_id={self.job_id}, page_number={self.page_number}, status={self.status})>"


class CrawledFile(Base):
    """CrawledFile model - stores individual files downloaded by crawler"""
    __tablename__ = "crawled_files"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    execution_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    url = Column(Text, nullable=False)
    filename = Column(String(512))

    # File metadata
    file_type = Column(String(50))  # pdf, jpg, css, js, etc.
    mime_type = Column(String(255))  # application/pdf, image/jpeg, etc.
    size_bytes = Column(BigInteger, default=0)

    # MinIO storage
    minio_path = Column(String(1024))  # crawled/{execution_id}/files/...
    minio_bucket = Column(String(255), default="ingestify-crawled")
    public_url = Column(Text)

    # Status tracking
    # Store the lowercase values ('pending', ...) as in migrations/003_add_crawled_files_table.sql
    status = Column(
        Enum(FileStatus, values_callable=lambda enum: [member.value for member in enum]),
        default=FileStatus.PENDING, nullable=False, index=True,
    )
    error_message = Column(Text)

    # Timestamps
    downloaded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship
    execution = relationship("Job", foreign_keys=[execution_id], overlaps="crawled_files")

    def __repr__(self):
        return f"<CrawledFile(id={self.id}, execution_id={self.execution_id}, filename={self.filename}, status={self.status})>"
