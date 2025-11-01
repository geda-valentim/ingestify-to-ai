from pydantic_settings import BaseSettings
from functools import lru_cache


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
    minio_endpoint: str = "minio:9000"  # Internal Docker network address
    minio_public_endpoint: str = "localhost:9000"  # Public-facing address for URLs
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False  # True for HTTPS in production
    minio_bucket_uploads: str = "ingestify-uploads"
    minio_bucket_pages: str = "ingestify-pages"
    minio_bucket_audio: str = "ingestify-audio"
    minio_bucket_results: str = "ingestify-results"

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60  # 1 hour

    # Authentication
    auth_enabled: bool = True  # Feature flag to enable/disable auth

    # Rate Limiting
    rate_limit_per_minute: int = 10

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
