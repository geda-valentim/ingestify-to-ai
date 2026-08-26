from functools import lru_cache
from typing import List

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Minimum length for the HMAC key used to sign JWTs (HS256).
JWT_SECRET_MIN_LENGTH = 32

# Placeholder values that used to ship as defaults in this file. They are now
# rejected explicitly so an old .env cannot silently reintroduce them.
_INSECURE_SECRETS = {
    "your-secret-key-change-in-production-min-32-chars",
    "change-me",
    "changeme",
    "secret",
}

_INSECURE_MINIO_CREDENTIALS = {"minioadmin"}

# Actionable setup instructions, shown when a required setting is missing or invalid.
# Keys are Settings field names.
_SETUP_HINTS = {
    "jwt_secret_key": (
        "JWT_SECRET_KEY is required and must be at least "
        f"{JWT_SECRET_MIN_LENGTH} characters.\n"
        "    Generate one with:  openssl rand -hex 32\n"
        "    Then set it in your .env file (see .env.example):\n"
        "        JWT_SECRET_KEY=<generated value>"
    ),
    "minio_access_key": (
        "MINIO_ACCESS_KEY is required (no default is provided).\n"
        "    It must match the MinIO server's MINIO_ROOT_USER.\n"
        "    Set it in your .env file (see .env.example):\n"
        "        MINIO_ACCESS_KEY=<minio root user>"
    ),
    "minio_secret_key": (
        "MINIO_SECRET_KEY is required (no default is provided).\n"
        "    It must match the MinIO server's MINIO_ROOT_PASSWORD.\n"
        "    Generate one with:  openssl rand -hex 24\n"
        "    Then set it in your .env file (see .env.example):\n"
        "        MINIO_SECRET_KEY=<generated value>"
    ),
}


class Settings(BaseSettings):
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # Celery Configuration
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    celery_task_default_queue: str = "ingestify"  # Namespace para isolar filas
    celery_worker_name: str = "ingestify-worker"  # Hostname único

    # Conversion Settings
    max_file_size_mb: int = 50
    conversion_timeout_seconds: int = 300
    temp_storage_path: str = "/tmp/ingestify"

    # Docling Performance Settings
    docling_enable_ocr: bool = False  # Disable for digital PDFs (10x faster)
    docling_enable_table_structure: bool = True  # Disable if no tables needed
    docling_enable_images: bool = False  # Disable image extraction for speed (text-only conversion)
    docling_use_v2_backend: bool = True  # Use beta backend (10x faster)

    # Audio Transcription Settings
    audio_transcriber_provider: str = "faster-whisper"  # faster-whisper, openai-whisper, openai-api
    whisper_model: str = "turbo"  # tiny, base, small, medium, large, turbo
    whisper_device: str = "cpu"  # cpu or cuda
    whisper_compute_type: str = "int8"  # int8, float16, float32 (for faster-whisper)
    enable_audio_transcription: bool = True  # Feature flag to enable/disable audio transcription
    max_audio_file_size_mb: int = 50  # Maximum audio file size
    max_audio_duration_seconds: int = 3600  # Maximum audio duration (1 hour)
    openai_api_key: str = ""  # Required for openai-api provider

    # Storage Settings
    result_ttl_seconds: int = 3600
    cleanup_interval_hours: int = 24

    # Monitoring & Recovery Settings
    monitoring_enabled: bool = True  # Enable/disable automatic monitoring
    monitoring_stuck_job_threshold_minutes: int = 30  # Mark jobs as stuck after X minutes in "processing"
    monitoring_cleanup_days: int = 7  # Delete completed jobs from Redis after X days
    monitoring_auto_retry_enabled: bool = True  # Automatically retry failed pages
    monitoring_max_retry_count: int = 3  # Maximum retry attempts per page
    monitoring_check_interval_minutes: int = 5  # How often to run monitoring tasks
    monitoring_batch_size: int = 100  # Max jobs to process per monitoring cycle

    # Google Drive (optional)
    google_drive_credentials_path: str = "/secrets/gdrive.json"

    # Dropbox (optional)
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""

    # Database (MySQL)
    database_url: str = "mysql+pymysql://root:root@localhost/ingestify"

    # Elasticsearch
    elasticsearch_url: str = "http://elasticsearch:9200"
    elasticsearch_user: str = ""  # Leave empty for no auth
    elasticsearch_password: str = ""
    elasticsearch_verify_certs: bool = False

    # MinIO Object Storage
    minio_endpoint: str = "127.0.0.1:9000"  # MinIO running on local machine
    minio_public_endpoint: str = "127.0.0.1:9000"  # Public-facing address for URLs
    # REQUIRED - intentionally no default so a missing value fails at startup
    # instead of silently falling back to the well-known "minioadmin" credentials.
    minio_access_key: str = Field(..., min_length=1)
    minio_secret_key: str = Field(..., min_length=1)
    minio_secure: bool = False  # True for HTTPS in production
    minio_bucket_uploads: str = "ingestify-uploads"
    minio_bucket_pages: str = "ingestify-pages"
    minio_bucket_audio: str = "ingestify-audio"
    minio_bucket_results: str = "ingestify-results"

    # JWT Authentication
    # REQUIRED - intentionally no default. A hardcoded default here would be a
    # published signing key: anyone with the source could forge valid tokens.
    jwt_secret_key: str = Field(..., min_length=JWT_SECRET_MIN_LENGTH)
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60  # 1 hour

    # Authentication
    auth_enabled: bool = True  # Feature flag to enable/disable auth

    # CORS
    # Comma-separated list of origins allowed to call the API from a browser.
    # Defaults cover local development only (Next.js frontend on :3000 and the
    # API's own docs on :8000 in Docker / :8080 via run_api.sh).
    # Production MUST override this with the real frontend origin(s).
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )

    # Rate Limiting
    rate_limit_per_minute: int = 10

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret_key(cls, value: str) -> str:
        secret = value.strip()
        if secret.lower() in _INSECURE_SECRETS:
            raise ValueError(
                "refuses to use a well-known placeholder value"
            )
        if len(secret) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"must be at least {JWT_SECRET_MIN_LENGTH} characters"
            )
        return secret

    @field_validator("minio_access_key", "minio_secret_key")
    @classmethod
    def _validate_minio_credentials(cls, value: str) -> str:
        credential = value.strip()
        if not credential:
            raise ValueError("must not be empty")
        return credential

    @model_validator(mode="after")
    def _reject_default_minio_credentials_in_production(self) -> "Settings":
        # The well-known "minioadmin" credentials are tolerated for local
        # development (the dev MinIO container is provisioned with them) but
        # never in production.
        if self.environment.strip().lower() == "production":
            for field in ("minio_access_key", "minio_secret_key"):
                if getattr(self, field).lower() in _INSECURE_MINIO_CREDENTIALS:
                    raise ValueError(
                        f"{field.upper()} uses the default MinIO credential "
                        "'minioadmin', which is not allowed when "
                        "ENVIRONMENT=production. Rotate the MinIO credentials "
                        "and update MINIO_ROOT_USER / MINIO_ROOT_PASSWORD and "
                        f"{field.upper()}."
                    )
        return self

    @property
    def cors_origins(self) -> List[str]:
        """CORS allowlist parsed from the comma-separated setting."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


def _format_settings_error(exc: ValidationError) -> str:
    """Turn a Pydantic ValidationError into actionable setup instructions."""
    lines = [
        "Invalid application configuration - refusing to start.",
        "",
    ]
    for error in exc.errors():
        loc = error.get("loc") or ()
        field = str(loc[0]) if loc else ""
        message = error.get("msg", "invalid value")
        hint = _SETUP_HINTS.get(field)
        if hint:
            lines.append(f"  - {hint}")
        elif field:
            lines.append(f"  - {field.upper()}: {message}")
        else:
            # Model-level validation error (no field location).
            lines.append(f"  - {message.removeprefix('Value error, ')}")
        lines.append("")
    lines.append(
        "See .env.example for the full list of required environment variables."
    )
    return "\n".join(lines)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(_format_settings_error(exc)) from exc
