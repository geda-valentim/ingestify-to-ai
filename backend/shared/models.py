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
# default, so create_all (dev/CI) and scripts/migrate_0004_projects.py agree.
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
    # No ForeignKey on purpose (spec 0004 § 4.2): the binding is checked by the
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

    # Immutable transcription decisions resolved at admission (spec 0006).
    # Unknown remote sources keep a candidate snapshot until media detection.
    transcription_profile = Column(JSON, nullable=True)
    transcription_profile_hash = Column(String(64), nullable=True, index=True)
    transcript_attempt_id = Column(String(36), nullable=True)

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
    A user's project. Every MAIN job belongs to exactly one (spec 0004).

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
    """Markers of one-shot data migrations (e.g. "0004_backfill", "0004_tail")."""
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


# ============================================================================
# Execution engines (spec 0003): where each feature's work runs, what it costs
# ============================================================================
#
# Money is DECIMAL(12,6), rates DECIMAL(14,10). Timestamps that order claims and
# heartbeats keep microseconds on MySQL. No column holds a secret in clear: engine
# credentials are sealed (shared/engines/sealing.py) and only worker-remote can open them.

from sqlalchemy import Date, Index, LargeBinary, Numeric, SmallInteger, UniqueConstraint  # noqa: E402
from sqlalchemy.dialects import mysql  # noqa: E402

Micros = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
Money = Numeric(12, 6)
Rate = Numeric(14, 10)


def _enum(name, *values):
    return Enum(*values, name=name)


class Engine(Base):
    """One place a feature can run: the local GPU workers, or a remote account (e.g. a Modal workspace)"""
    __tablename__ = "engines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    slug = Column(String(64), nullable=False, unique=True)  # ^[a-z0-9][a-z0-9_-]*$, e.g. "modal_1"
    display_name = Column(String(255), nullable=False)
    adapter_type = Column(String(32), nullable=False)  # local | modal | ...
    # Not secret; validated per adapter: features/bindings (gpu, workers, executions per
    # worker), declared GPUs, prices, speeds, timeouts
    config = Column(JSON, nullable=False, default=dict)
    deployments = Column(JSON, nullable=False, default=dict)  # {feature: {fingerprint, protocol, verified_at}}
    status = Column(_enum("engine_status", "active", "paused", "disabled"), nullable=False, default="paused")
    health = Column(
        _enum("engine_health", "unknown", "healthy", "degraded", "unhealthy", "exhausted"),
        nullable=False, default="unknown",
    )
    health_reason = Column(Text)  # redacted
    health_until = Column(DateTime)
    consecutive_failures = Column(Integer, nullable=False, default=0)

    # Budget for the whole account, per period (the user sets the ceiling)
    limit_usd = Column(Money)
    min_remaining_usd = Column(Money, nullable=False, default=0.5)
    soft_pct = Column(SmallInteger, nullable=False, default=80)
    period_tz = Column(String(64), nullable=False, default="UTC", server_default="UTC")
    period_anchor_day = Column(SmallInteger, nullable=False, default=1, server_default="1")  # 1-28
    alerted_soft_period = Column(Date)
    alerted_hard_period = Column(Date)

    # What the provider itself reports as spent this period
    provider_reported_usd = Column(Money)
    provider_reported_period = Column(Date)
    provider_reported_at = Column(DateTime)

    # Credentials: sealed, write-only; `credentials_masked` is all the API ever shows
    credentials_sealed = Column(LargeBinary)
    credentials_key_id = Column(String(16))
    credentials_masked = Column(JSON, nullable=False, default=dict)
    credentials_updated_at = Column(DateTime)
    credentials_updated_by = Column(String(36))

    is_system = Column(Boolean, nullable=False, default=False)  # the built-in local engine
    version = Column(Integer, nullable=False, default=0)  # optimistic concurrency for PUTs
    created_by = Column(String(36))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class FeatureRoute(Base):
    """The user's ordered rule for one feature; the dispatcher places each queued item by it"""
    __tablename__ = "feature_routes"

    feature = Column(String(40), primary_key=True)
    state = Column(_enum("route_state", "active", "draining"), nullable=False, default="active")
    # [{position, engine_ids[], group_strategy (priority|fill_first), scale_out_after_seconds?,
    #   when?: {min_wait_seconds?, min_backlog?}, spend_cap?: {usd, window: day|period}}]
    steps = Column(JSON, nullable=False, default=list)
    on_no_engine = Column(_enum("route_on_no_engine", "hold", "fail"), nullable=False, default="hold")
    fail_after_seconds = Column(Integer)
    max_attempts = Column(Integer, nullable=False, default=3)
    remote_allowed_for = Column(_enum("route_remote_allowed_for", "admins", "all"), nullable=False, default="admins")
    user_period_limit_usd = Column(Money)
    remote_data_notice = Column(Text)
    dispatcher_fallback = Column(
        _enum("route_dispatcher_fallback", "local_direct", "hold"), nullable=False, default="local_direct"
    )
    dispatcher_down_seconds = Column(Integer, nullable=False, default=120)
    version = Column(Integer, nullable=False, default=0)
    updated_by = Column(String(36))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EngineUsage(Base):
    """
    The ledger: one row per attempt to run one item on one engine (kind=job), plus
    idle tails, probes and benchmarks. Reserved at placement, settled at the end.
    """
    __tablename__ = "engine_usage"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    kind = Column(_enum("usage_kind", "job", "idle_tail", "probe", "benchmark"), nullable=False, default="job")
    engine_id = Column(String(36), ForeignKey("engines.id", ondelete="RESTRICT"), nullable=False)
    feature = Column(String(40), nullable=False)
    subject_type = Column(_enum("usage_subject_type", "job", "page", "vision_request"))
    subject_id = Column(String(64))
    attempt = Column(Integer)
    job_id = Column(String(36))  # no FK: the cost history outlives deleted jobs
    user_id = Column(String(36))
    period_start = Column(Date, nullable=False)
    status = Column(
        _enum("usage_status", "reserved", "spawning", "running", "settled", "released"),
        nullable=False, default="reserved",
    )
    outcome = Column(_enum("usage_outcome", "succeeded", "failed", "cancelled", "lost"))
    counts_toward_attempts = Column(Boolean, nullable=False, default=True)
    placed_by = Column(_enum("usage_placed_by", "dispatcher", "watchdog", "fallback", "cli"))
    dispatch_epoch = Column(BigInteger)
    gpu_type = Column(String(32))
    executions_per_worker = Column(SmallInteger)
    container_id = Column(String(128))
    segment_start = Column(Micros)  # idle_tail only
    exec_started_at = Column(Micros)
    exec_ended_at = Column(Micros)
    shared_seconds = Column(Numeric(12, 3))
    cold_start_seconds = Column(Numeric(9, 3))
    estimated_usd = Column(Money, nullable=False, default=0)
    reserved_usd = Column(Money, nullable=False, default=0)
    actual_usd = Column(Money)
    cost_basis = Column(_enum("usage_cost_basis", "measured", "reported", "shared", "reserved"))
    reported_seconds = Column(Numeric(12, 3))
    measured_seconds = Column(Numeric(12, 3))
    rate_usd_per_s = Column(Rate, nullable=False, default=0)
    price_snapshot = Column(JSON)
    units = Column(JSON)
    fingerprint = Column(String(64))
    attempt_key = Column(String(36))
    provider_call_id = Column(String(128))
    holder = Column(String(128))
    heartbeat_at = Column(Micros)
    published_at = Column(Micros)
    spawned_at = Column(Micros)
    deadline_at = Column(Micros)
    output_persisted_at = Column(Micros)
    republish_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(32))
    error_detail = Column(Text)  # redacted
    created_at = Column(Micros, default=datetime.utcnow, nullable=False)
    finished_at = Column(Micros)

    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "attempt", name="uq_usage_subject_attempt"),
        UniqueConstraint("container_id", "kind", "segment_start", name="uq_usage_container_segment"),
        Index("ix_usage_engine_period_status", "engine_id", "period_start", "status"),
        Index("ix_usage_engine_feature_kind_status", "engine_id", "feature", "kind", "status"),
        Index("ix_usage_speed_key", "engine_id", "feature", "gpu_type", "executions_per_worker", "status", "finished_at"),
        Index("ix_usage_container", "container_id"),
        Index("ix_usage_status_heartbeat", "status", "heartbeat_at"),
        Index("ix_usage_user_period", "user_id", "period_start"),
        Index("ix_usage_job", "job_id"),
    )


class JobDispatch(Base):
    """The durable backlog: one row per routed item waiting for, or placed on, an engine"""
    __tablename__ = "job_dispatches"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    feature = Column(String(40), nullable=False)
    subject_type = Column(_enum("dispatch_subject_type", "job", "page", "vision_request"), nullable=False)
    subject_id = Column(String(64), nullable=False)
    job_id = Column(String(36))
    user_id = Column(String(36))
    remote_allowed = Column(Boolean, nullable=False, default=False)
    state = Column(
        _enum("dispatch_state", "probing", "waiting", "assigned", "running", "done", "failed", "bypassed"),
        nullable=False, default="probing",
    )
    version = Column(Integer, nullable=False, default=0)
    priority = Column(SmallInteger, nullable=False, default=5)
    not_before = Column(Micros)
    placements = Column(Integer, nullable=False, default=0)
    job_failures = Column(Integer, nullable=False, default=0)
    skip_count = Column(Integer, nullable=False, default=0)
    blocked_engine_id = Column(String(36))
    solo = Column(Boolean, nullable=False, default=False)
    exclude_engines = Column(JSON, nullable=False, default=list)  # [{engine_id, until}]
    payload = Column(JSON, nullable=False, default=dict)  # per-feature allowlisted schema, never secrets
    media_seconds = Column(Numeric(12, 3))
    media_bytes = Column(BigInteger)
    usage_id = Column(BigInteger)
    engine_id = Column(String(36))
    placed_step = Column(SmallInteger)
    place_reason = Column(String(64))
    enqueued_at = Column(Micros, default=datetime.utcnow, nullable=False)
    unplaceable_since = Column(Micros)
    assigned_at = Column(Micros)
    error_code = Column(String(32))
    updated_at = Column(Micros, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", name="uq_dispatch_subject"),
        Index("ix_dispatch_feature_state_order", "feature", "state", "priority", "enqueued_at"),
        Index("ix_dispatch_feature_state_remote_order", "feature", "state", "remote_allowed", "priority", "enqueued_at"),
    )


class DispatcherLease(Base):
    """Single row: who places items now, and the epoch every placement is fenced by"""
    __tablename__ = "dispatcher_lease"

    id = Column(SmallInteger, primary_key=True, default=1)
    epoch = Column(BigInteger, nullable=False, default=0)
    holder = Column(String(128))
    holder_kind = Column(_enum("lease_holder_kind", "dispatcher", "watchdog"))
    renewed_at = Column(Micros)
    dispatcher_seen_at = Column(Micros)


class EngineFeatureState(Base):
    """Per engine and feature: since when it is full, temporary capacity penalties"""
    __tablename__ = "engine_feature_state"

    engine_id = Column(String(36), ForeignKey("engines.id", ondelete="CASCADE"), primary_key=True)
    feature = Column(String(40), primary_key=True)
    full_since = Column(Micros)
    capacity_penalty = Column(Integer, nullable=False, default=0)
    penalty_until = Column(Micros)
    alive_below_configured_since = Column(Micros)
    # Last time the dispatcher saw a live local worker of this feature; with none for
    # local_unhealthy_after_seconds the local binding is unhealthy (spec 0003, 4.6.7)
    workers_seen_at = Column(Micros)
    updated_at = Column(Micros, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AdminAudit(Base):
    """Every admin change to engines, routes, budgets and credentials (never secret values)"""
    __tablename__ = "admin_audit"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    actor_user_id = Column(String(36))
    auth_method = Column(_enum("audit_auth_method", "jwt", "cli"), nullable=False)
    ip = Column(String(45))
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=False)
    before = Column(JSON)
    after = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_audit_target", "target_type", "target_id", "created_at"),)


class LiveSession(Base):
    """Connection facts; ownership/location/results remain on Job."""
    __tablename__ = 'live_sessions'
    __table_args__ = (Index('ix_live_sessions_state_audio', 'state', 'last_audio_at'), _UTF8MB4_TABLE)
    job_id = Column(String(36), ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    state = Column(String(20), nullable=False, default='created')
    backend = Column(String(40), nullable=False)
    model = Column(String(255), nullable=False)
    language = Column(String(12), nullable=False)
    sample_rate = Column(Integer, nullable=False, default=16000)
    worker_id = Column(String(100), nullable=False)
    generation = Column(BigInteger, nullable=False)
    audio_samples = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    connected_at = Column(DateTime)
    last_audio_at = Column(DateTime)
    ended_at = Column(DateTime)
    error_code = Column(String(100))

# Spec 0007: explicit migration; SDK-free control models share this metadata.
from shared.engine_control.models import (RuntimeProfile, ControlResource, OperationPlan,
    EngineOperation, OperationEvent, OperationOutbox, ControlAdmission, ControlHost)  # noqa: E402,F401
