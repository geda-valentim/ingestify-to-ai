from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from shared.database import Base


def generate_uuid():
    """Generate UUID as string"""
    return str(uuid.uuid4())


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

    # Relationship
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey(id={self.id}, user_id={self.user_id}, name={self.name})>"


class Job(Base):
    """Job model - stores metadata about conversion jobs"""
    __tablename__ = "jobs"

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

    def __repr__(self):
        return f"<Job(id={self.id}, status={self.status}, filename={self.filename})>"


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
    size_bytes = Column(Integer, default=0)

    # MinIO storage
    minio_path = Column(String(1024))  # crawled/{execution_id}/files/...
    minio_bucket = Column(String(255), default="ingestify-crawled")
    public_url = Column(Text)

    # Status tracking
    status = Column(Enum(FileStatus), default=FileStatus.PENDING, nullable=False, index=True)
    error_message = Column(Text)

    # Timestamps
    downloaded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship
    execution = relationship("Job", foreign_keys=[execution_id], overlaps="crawled_files")

    def __repr__(self):
        return f"<CrawledFile(id={self.id}, execution_id={self.execution_id}, filename={self.filename}, status={self.status})>"
