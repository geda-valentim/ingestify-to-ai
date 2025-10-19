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
    celery_task_default_queue: str = "doc2md"  # Namespace para isolar filas
    celery_worker_name: str = "doc2md-worker"  # Hostname único

    # Conversion Settings
    max_file_size_mb: int = 50
    conversion_timeout_seconds: int = 300
    temp_storage_path: str = "/tmp/doc2md"

    # Docling Performance Settings
    docling_enable_ocr: bool = False  # Disable for digital PDFs (10x faster)
    docling_enable_table_structure: bool = True  # Disable if no tables needed
    docling_use_v2_backend: bool = True  # Use beta backend (10x faster)

    # Storage Settings
    result_ttl_seconds: int = 3600
    cleanup_interval_hours: int = 24

    # Google Drive (optional)
    google_drive_credentials_path: str = "/secrets/gdrive.json"

    # Dropbox (optional)
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""

    # Database (MySQL)
    database_url: str = "mysql+pymysql://root:root@localhost/doc2md"

    # Elasticsearch
    elasticsearch_url: str = "http://elasticsearch:9200"
    elasticsearch_user: str = ""  # Leave empty for no auth
    elasticsearch_password: str = ""
    elasticsearch_verify_certs: bool = False

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
