from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Enum
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
    source_type = Column(String(50))  # file, url, gdrive, dropbox
    source_url = Column(Text)  # For URL/cloud sources
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))

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
    job_type = Column(String(20))  # MAIN, SPLIT, PAGE, MERGE, DOWNLOAD

    # Result metadata (content is in Elasticsearch)
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
    page_job_id = Column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"))  # Reference to PAGE job

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    error_message = Column(Text)

    # Result metadata (content is in Elasticsearch)
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
