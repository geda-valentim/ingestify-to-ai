import logging
import re
from functools import lru_cache
from typing import List, Literal, Optional
from urllib.parse import quote

from pydantic import Field, ValidationError, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Minimum length for the HMAC key used to sign JWTs (HS256).
JWT_SECRET_MIN_LENGTH = 32

# Accepted values for the single DEVICE knob: auto | cpu | cuda | cuda:N.
_DEVICE_PATTERN = re.compile(r"^(auto|cpu|cuda(:\d+)?)$")

# Default Florence-2 repo and the commit sha pinned for it. Kept as module
# constants so the model_validator can tell "still the default pin" from
# "deliberately re-pinned for another repo".
DEFAULT_VISION_MODEL_ID = "florence-community/Florence-2-base-ft"
DEFAULT_VISION_MODEL_REVISION = "0b03b6f15a4a211370fb204aee4e7dd48887ea37"

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
    # With acks_late, the Redis broker hands a message that is still unacknowledged
    # after this long to another worker - even while the first is still running it.
    # Must exceed the longest task time limit of ANY worker (worker-audio allows
    # 10,800 s), and must be the same on every service, since any consumer restores
    # every queue's stale messages. Kombu's default is 3,600 s.
    celery_visibility_timeout_seconds: int = 14400

    # Conversion Settings
    max_file_size_mb: int = 50
    conversion_timeout_seconds: int = 300
    temp_storage_path: str = "/tmp/ingestify"

    # Docling Performance Settings
    docling_enable_ocr: bool = False  # Disable for digital PDFs (10x faster)
    docling_enable_table_structure: bool = True  # Disable if no tables needed
    docling_enable_images: bool = False  # Disable image extraction for speed (text-only conversion)
    docling_use_v2_backend: bool = True  # Use beta backend (10x faster)
    # Passed explicitly into docling's AcceleratorOptions(num_threads=...).
    # NOTE: the name collides with docling's own DOCLING_-prefixed BaseSettings
    # field, so docling reads the same DOCLING_NUM_THREADS variable. The
    # collision is benign: both objects resolve to the same number. Exists so
    # 5 worker replicas x concurrency 2 stop oversubscribing the CPU.
    docling_num_threads: int = 4

    # Image assets of a document conversion (image_mode=referenced / page_images=true
    # on /upload and /convert; shared/conversion_assets.py). Not DOCLING_-prefixed on
    # purpose: docling's own BaseSettings reads that prefix.
    conversion_images_scale: float = 2.0  # docling picture images: 1.0 = 72 DPI, 2.0 = 144 DPI
    conversion_page_image_dpi: int = 150  # page renders (pypdfium2)
    conversion_asset_min_px: int = 32  # pictures narrower or shorter than this are skipped
    conversion_asset_max_count: int = 500  # per job, pictures + pages
    conversion_asset_max_total_mb: int = 200  # per job, PNG bytes, pictures + pages
    # With purge_source=true the assets outlive the job's settlement by this much,
    # so the client can download them; then the periodic beat deletes them
    asset_retention_seconds: int = 3600

    # Device / GPU
    # THE single device knob for the whole stack (Docling, Whisper, Florence-2).
    # Accepted: auto | cpu | cuda | cuda:N.
    #   auto -> CUDA when torch reports a usable device, else CPU, silently.
    #   cuda -> hard error when it cannot be satisfied (never a silent downgrade).
    # Resolution lives in shared/device.py; nothing else may probe torch.
    # DOCLING_DEVICE is ignored from now on: we pass this value explicitly into
    # AcceleratorOptions(device=...), and an init kwarg outranks the environment.
    device: str = "auto"

    # Audio Transcription Settings
    # Live input is opt-in and separate from the file queues/budget ledger.
    live_transcription_enabled: bool = False
    live_worker_url: str = "ws://worker-live:8091/internal/stream"
    live_worker_id: str = "live-local"
    live_gpu_ref: str = "gpu0"
    live_internal_token: str = ""
    live_max_sessions: int = Field(1, ge=1, le=8)
    live_max_duration_seconds: int = Field(1800, ge=1, le=1800)
    live_max_audio_backlog_seconds: float = Field(2, gt=0, le=2)
    live_vram_footprint_gb: float = Field(3, gt=0)
    live_vram_reserve_gb: float = Field(3.2, ge=0)

    audio_transcriber_provider: str = "faster-whisper"  # faster-whisper, openai-whisper, openai-api
    # Canary only: enable readiness after offline weights and target gates pass.
    live_diarization_enabled: bool = False
    live_diarization_qualified: bool = False
    live_diarization_python: str = ""
    live_diarization_manifest: str = ""
    live_diarization_gpu_gb: float = 3.0
    whisperx_diarization_default: bool = False
    whisperx_diarization_ready: bool = False
    whisperx_batch_size: int = 1
    whisperx_model_dir: str = "/models/whisperx"
    whisperx_diarization_model: str = "pyannote/speaker-diarization-community-1"
    whisperx_diarization_revision: str = ""
    whisperx_asr_revision: str = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
    whisperx_vad_revision: str = "unqualified"
    whisperx_aligner_manifest: str = "{}"
    whisperx_max_audio_seconds: int = 7200
    whisper_model: str = "turbo"  # tiny, base, small, medium, large, turbo
    # CHANGED (was "cpu"): empty means "inherit DEVICE". Any non-empty value is
    # a per-component override that wins over DEVICE and is logged on every boot.
    whisper_device: str = ""
    # CHANGED (was "int8"): empty means "derive from the resolved audio device"
    # (float16 on cuda, int8 on cpu). Stops a device flip leaving CTranslate2 on
    # a CPU-shaped int8 quantisation it silently downgrades rather than rejects.
    whisper_compute_type: str = ""  # "auto" is accepted as a synonym of empty
    enable_audio_transcription: bool = True  # Feature flag to enable/disable audio transcription
    max_audio_file_size_mb: int = 50  # Maximum audio file size
    max_video_file_size_mb: int = 500  # Maximum video file size (only the audio track is transcribed)
    max_audio_duration_seconds: int = 3600  # Maximum audio duration (1 hour)
    # Transcriptions go to their own queue, consumed by the worker-audio service
    # (GPU replicas in docker-compose.gpu.yml), so a batch of long recordings never
    # blocks document conversion. Its time limit is that worker's
    # CONVERSION_TIMEOUT_SECONDS (set from TRANSCRIPTION_TIMEOUT_SECONDS in compose).
    transcription_queue: str = "ingestify-audio"
    openai_api_key: str = ""  # Required for openai-api provider

    # Vision Settings (Florence-2)
    # ONE flag covers /images/describe and /images/ocr: they are one model
    # behind one loader, and two flags would allow a state that cannot exist.
    enable_image_description: bool = True
    vision_provider: str = "florence2"  # florence2 | stub
    # The florence-community conversions are weights-only (safetensors + configs,
    # no .py files, no `custom_code` tag) and load through transformers' NATIVE
    # Florence2ForConditionalGeneration - that is what makes trust_remote_code
    # unnecessary. base-ft (0.23B) over large-ft (0.77B) so a CPU laptop stays
    # inside the 60s sync budget. Do NOT default this to a microsoft/Florence-2-* repo.
    vision_model_id: str = DEFAULT_VISION_MODEL_ID
    # Commit sha, never a branch name. Passed as revision= to every
    # from_pretrained and snapshot_download call.
    vision_model_revision: str = DEFAULT_VISION_MODEL_REVISION
    # Escape hatch for the original microsoft/Florence-2-* repos, which execute
    # Hub-supplied Python inside the worker process. Never inferred, never
    # auto-enabled as a retry after a load failure.
    vision_trust_remote_code: bool = False
    vision_model_cache_dir: str = "/models/huggingface"
    # False maps to local_files_only=True on every load (air-gapped / CI).
    vision_allow_model_download: bool = True
    # True makes a @worker_process_init handler load the weights up front.
    vision_preload_model: bool = False
    # Its own limit: images do NOT inherit max_file_size_mb.
    vision_max_image_size_mb: int = 10
    # Decompression-bomb guard. A 10MB PNG can expand to tens of gigabytes, so
    # the byte limit alone does not protect the worker.
    vision_max_image_pixels: int = 50_000_000
    # API-side deadline only; must stay below any reverse-proxy read timeout.
    vision_request_timeout_seconds: int = 60
    # Per-task time_limit, deliberately double the request timeout so a request
    # that 504s leaves a task still running to completion.
    face_analysis_enabled: bool = False
    face_model_cache_dir: str = "/models/faces"
    vision_full_task_timeout_seconds: int = 900
    datalake_encryption_key: str = ""

    vision_task_timeout_seconds: int = 120
    vision_max_new_tokens: int = 1024
    vision_num_beams: int = 3  # 1 roughly halves CPU latency at some quality cost
    vision_caption_task: str = "<MORE_DETAILED_CAPTION>"
    # auto | float32 | float16 | bfloat16. auto = float16 on cuda, float32 on cpu
    # (float16 on CPU is slow and numerically unstable for this model).
    vision_torch_dtype: str = "auto"
    # Dedicated Celery queue: on the shared queue a 60s request would sit behind
    # a 10-minute PDF merge and 504 for reasons unrelated to vision.
    vision_queue: str = "ingestify-vision"

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
    # An unacknowledged broker message that no live worker holds is orphaned (its
    # worker died) and would otherwise wait out the whole visibility timeout. Flag it
    # once it is this old, so a message just delivered is never mistaken for one.
    monitoring_unacked_grace_seconds: int = 600
    temp_files_retention_hours: int = 72  # Delete leftover local files (failed jobs, aborted uploads) after X hours

    # Google Drive (optional)
    google_drive_credentials_path: str = "/secrets/gdrive.json"

    # Dropbox (optional)
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""

    # Database (MySQL)
    database_url: str = "mysql+pymysql://root:root@localhost/ingestify"
    # SQLAlchemy pool per process (API, each worker). A connection is held for a whole
    # request; long waits must release it (see api/image_routes.py _run_vision).
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout: int = 15  # seconds a request waits for a free connection

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
    minio_bucket_crawled: str = "ingestify-crawled"  # Crawler files storage

    # Crawler Configuration
    crawler_enabled: bool = True
    crawler_max_concurrent_downloads: int = 5  # Max parallel file downloads
    crawler_max_concurrent_assets: int = 10  # Max parallel asset downloads
    crawler_download_timeout_seconds: int = 60  # Timeout for single file download
    crawler_user_agent: str = "IngestifyBot/1.0 (+https://ingestify.ai/bot)"
    crawler_respect_robots_txt: bool = True  # Respect robots.txt rules
    crawler_rate_limit_per_second: int = 2  # Max requests per second per domain

    # Crawler Engine Defaults
    crawler_default_engine: str = "beautifulsoup"  # beautifulsoup or playwright

    # Playwright Configuration
    playwright_headless: bool = True  # Run browser in headless mode
    playwright_timeout_seconds: int = 30  # Page load timeout
    playwright_wait_for_selector: str = ""  # Optional: wait for specific selector before extract
    playwright_browser_type: str = "chromium"  # chromium, firefox, or webkit

    # Proxy Configuration
    proxy_enabled: bool = False  # Enable proxy support
    proxy_pool_enabled: bool = False  # Enable proxy pool rotation
    proxy_rotation_strategy: str = "round_robin"  # round_robin or random

    # Retry Configuration
    crawler_retry_enabled: bool = True  # Enable automatic retries on failure
    crawler_max_retries: int = 3  # Maximum retry attempts
    crawler_retry_delay_base_seconds: int = 5  # Base delay between retries (exponential backoff)
    crawler_retry_strategy_default: str = "conservative"  # conservative or aggressive

    # JWT Authentication
    # REQUIRED - intentionally no default. A hardcoded default here would be a
    # published signing key: anyone with the source could forge valid tokens.
    jwt_secret_key: str = Field(..., min_length=JWT_SECRET_MIN_LENGTH)
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60  # 1 hour

    # Authentication
    auth_enabled: bool = True  # Feature flag to enable/disable auth
    # Comma-separated user IDs (UUIDs) allowed to use /admin endpoints. Empty = no admins.
    # IDs are used instead of emails because registration does not verify email ownership.
    admin_user_ids: str = ""
    # Spec 0019: one-time token required to create the root user (the first account of an
    # installation without root). Mandatory when ENVIRONMENT=production; optional
    # elsewhere (if set, it is required everywhere). Generate with `openssl rand -hex 32`
    # and remove it once root exists.
    root_setup_token: str = Field(default="", repr=False)

    # IAM decision core (spec 0014 §4.11). off: legacy decides, bindings are inert.
    # shadow: both decide, legacy answers, divergences are logged. enforce: IAM answers.
    iam_mode: Literal["off", "shadow", "enforce"] = "off"

    # Execution engines (spec 0003). Remote engine credentials are sealed to the
    # public key; only worker-remote is given the private keys (a list, for
    # rotation; or a file with one per line). No defaults: without the public key
    # credentials cannot be stored, without a private key no remote engine runs.
    # Generate a pair with: python scripts/engines.py keygen
    engine_secrets_public_key: str = ""
    engine_secrets_private_keys: str = ""
    engine_secrets_private_keys_file: str = ""

    # Spec 0007 is opt-in after scripts/migrate_0007_engine_control.py.
    engine_control_enabled: bool = False
    # Engine RBAC/ABAC (spec 0009) is governed by IAM_MODE since spec 0018 §4.4:
    # unset (or empty) -> on only when IAM_MODE=enforce (shadow does not turn it on).
    # ENGINE_ACCESS_ENABLED is a deprecated alias that still wins when set, true or
    # false; `false` stays the emergency lever (engines back to bootstrap only).
    # Always a bool once Settings is built (see _derive_engine_access_enabled).
    engine_access_enabled: Optional[bool] = None
    engine_installation_principal_id: str = ""
    engine_control_queue: str = "ingestify-engine-control"
    engine_control_beat: bool = False
    # Root-owned JSON {host_id: sha256(machine_token)}. Separate from admin JWT.
    engine_host_identities_file: str = ""

    # Routing (spec 0003, slice 3b). Only used once a feature has a route; with no
    # row in feature_routes nothing here is read and no dispatcher is needed.
    # The dispatcher's queue, consumed by the optional worker-dispatch service
    # (compose profile `engines`)
    dispatch_queue: str = "ingestify-dispatch"
    # True only in worker-dispatch: its embedded beat (celery worker -B) ticks the
    # dispatcher every 5 s and the sweeper every 30 s. Never in the shared beat,
    # which would fill a queue nobody consumes on installs without the profile
    engines_dispatch_beat: bool = False
    # The API's watchdog loop (places routed local work while the dispatcher is
    # down); with no route it only reads feature_routes every 15 s
    engines_watchdog_enabled: bool = True
    # The media probe reads at most this many bytes of an upload, for at most this long
    probe_max_bytes: int = 8 * 1024 * 1024
    probe_timeout_seconds: int = 10

    # Remote engines (spec 0003, slice 4a): the optional worker-remote service
    # (compose profile `engines`, thread pool) consumes both queues; it alone holds
    # the private keys. Nothing is published to them without a remote route.
    remote_queue: str = "ingestify-remote"
    remote_ctl_queue: str = "ingestify-remote-ctl"
    # Threads of worker-remote: each in-flight remote item holds one while it waits.
    # Sum of remote capacity in routes must stay <= this - 2 (control tasks)
    remote_worker_concurrency: int = 16
    # Media sent at once (bytes go in the call: MinIO is not reachable from Modal)
    remote_max_concurrent_uploads: int = 4
    # True only in worker-remote: its embedded beat reconciles provider spend
    engines_remote_beat: bool = False
    # Engine alerts (budget soft/hard, exhaustion, billing unreadable, dispatcher down,
    # cost divergence) are always logged; with a URL they are also POSTed as a small
    # generic JSON body - engine slug, event, numbers; never secrets or user data
    engine_alert_webhook_url: str = ""

    def engine_private_keys(self) -> List[str]:
        """Private keys from ENGINE_SECRETS_PRIVATE_KEYS (comma-separated) and/or the _FILE"""
        keys = [k.strip() for k in self.engine_secrets_private_keys.split(",") if k.strip()]
        if self.engine_secrets_private_keys_file:
            with open(self.engine_secrets_private_keys_file) as f:
                keys += [line.strip() for line in f if line.strip() and not line.startswith("#")]
        return keys

    # CORS
    # Comma-separated list of origins allowed to call the API from a browser.
    # Defaults cover local development only (Next.js frontend on :3000 and the
    # API's own docs on :8000 in Docker / :8080 via scripts/dev/run_api.sh).
    # Production MUST override this with the real frontend origin(s).
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )

    # Projects and folders (spec 0004)
    # Ceilings against client bugs (e.g. sending the file name as the project),
    # not quotas.
    max_projects_per_user: int = 200
    max_folders_per_project: int = 500
    # Emergency valve, EMPTY by default (= project is mandatory). When set, an
    # upload that names no project (and whose API key is not bound to one) goes
    # to this project (get-or-add) instead of answering 422, with a WARNING log.
    upload_fallback_project: str = ""

    # Rate Limiting
    rate_limit_per_minute: int = 10  # Login attempts per client IP per minute
    login_max_failed_attempts: int = 5  # Failed logins per account before a temporary lockout
    login_lockout_seconds: int = 900  # Lockout window (counted from the first failure)
    register_limit_per_hour: int = 5  # Registrations per client IP per hour

    # Environment
    # "production" unless explicitly set: development mode returns exception
    # messages to clients and skips the startup fail-fast checks
    environment: str = "production"
    sql_echo: bool = False  # Log every SQL statement with its parameters (debug only)
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

    @field_validator("device")
    @classmethod
    def _validate_device(cls, value: str) -> str:
        device = value.strip().lower()
        if not _DEVICE_PATTERN.match(device):
            raise ValueError(
                f"DEVICE={value!r} is not a valid device. "
                "Accepted values: 'auto' (CUDA when available, otherwise CPU), "
                "'cpu', 'cuda', or 'cuda:N' for a specific GPU index."
            )
        return device

    @field_validator("whisper_device")
    @classmethod
    def _warn_whisper_device_override(cls, value: str, info: ValidationInfo) -> str:
        # Reconciliation is explicit, not silent: an existing .env keeps its
        # exact current behaviour AND says so on every boot.
        device = value.strip()
        if device:
            logger.warning(
                "WHISPER_DEVICE=%s overrides DEVICE=%s for audio transcription only; "
                "unset it to follow DEVICE",
                device,
                info.data.get("device", "auto"),
            )
        return device

    @field_validator("whisper_compute_type")
    @classmethod
    def _log_whisper_compute_type_override(cls, value: str) -> str:
        compute_type = value.strip()
        if compute_type:
            logger.info(
                "WHISPER_COMPUTE_TYPE=%s overrides the value derived from the "
                "resolved audio device; unset it to derive it automatically",
                compute_type,
            )
        return compute_type

    @field_validator("vision_torch_dtype")
    @classmethod
    def _validate_vision_torch_dtype(cls, value: str) -> str:
        dtype = value.strip().lower()
        allowed = {"auto", "float32", "float16", "bfloat16"}
        if dtype not in allowed:
            raise ValueError(
                f"VISION_TORCH_DTYPE={value!r} is not valid. "
                f"Accepted values: {', '.join(sorted(allowed))}."
            )
        return dtype

    @field_validator("engine_access_enabled", mode="before")
    @classmethod
    def _empty_engine_access_is_unset(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _derive_engine_access_enabled(self) -> "Settings":
        # Every process that imports shared.access.policy builds Settings once at
        # boot, so this is where each of them reports the effective value (CA15).
        # That happens at import time, before api.main or Celery configure logging,
        # so the report is a WARNING: Python's last-resort handler drops INFO.
        explicit = self.engine_access_enabled is not None
        if explicit:
            logger.warning(
                "ENGINE_ACCESS_ENABLED=%s is deprecated (spec 0018): IAM_MODE governs "
                "engine access; unset it to follow IAM_MODE=%s",
                str(self.engine_access_enabled).lower(),
                self.iam_mode,
            )
        else:
            self.engine_access_enabled = self.iam_mode == "enforce"
        logger.warning(
            "engine_access_enabled=%s (%s)",
            self.engine_access_enabled,
            "ENGINE_ACCESS_ENABLED" if explicit else f"IAM_MODE={self.iam_mode}",
        )
        return self

    @model_validator(mode="after")
    def _reject_partial_vision_model_override(self) -> "Settings":
        # Stops a floating-branch pull sneaking in through a partial override:
        # a new model id left paired with the pin for the default model.
        if (
            self.vision_model_id != DEFAULT_VISION_MODEL_ID
            and self.vision_model_revision == DEFAULT_VISION_MODEL_REVISION
        ):
            raise ValueError(
                f"VISION_MODEL_ID was changed to {self.vision_model_id} but "
                "VISION_MODEL_REVISION is still the pin for the default model. "
                "Look the sha up at "
                f"https://huggingface.co/{self.vision_model_id}/commits/main "
                "and set VISION_MODEL_REVISION=<sha>."
            )
        return self

    @model_validator(mode="after")
    def _visibility_timeout_must_outlast_tasks(self) -> "Settings":
        # Otherwise a task still inside its time limit is redelivered to a second
        # worker and runs twice (Celery's Redis broker, with task_acks_late)
        if self.celery_visibility_timeout_seconds <= self.conversion_timeout_seconds:
            raise ValueError(
                f"CELERY_VISIBILITY_TIMEOUT_SECONDS ({self.celery_visibility_timeout_seconds}) must be "
                f"greater than CONVERSION_TIMEOUT_SECONDS ({self.conversion_timeout_seconds}), or a task "
                "still running would be handed to a second worker. Raise it on every service."
            )
        return self

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


def redis_url_with_password(url: str, password: str) -> str:
    """Add REDIS_PASSWORD to a redis:// URL that has no credentials (for Celery broker/backend)"""
    if not password or not url.startswith(("redis://", "rediss://")):
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest.split("/", 1)[0]:
        return url  # credentials already in the URL
    return f"{scheme}://:{quote(password, safe='')}@{rest}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(_format_settings_error(exc)) from exc
