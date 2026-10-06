import ssl
from celery import Celery
from celery.schedules import crontab
from shared.config import get_settings, redis_url_with_password
from shared.engines.redact import install_log_redaction

# No provider token or JWT in any log line or traceback (spec 0003); the record
# factory is process-wide, so it covers the forked pool children too
install_log_redaction()

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "doc2md",
    broker=redis_url_with_password(settings.celery_broker_url, settings.redis_password),
    backend=redis_url_with_password(settings.celery_result_backend, settings.redis_password),
)

# Certificate validation is mandatory for every TLS broker/backend connection.
redis_tls = {"ssl_cert_reqs": ssl.CERT_REQUIRED, "ssl_check_hostname": True}
if settings.redis_ssl_ca_certs:
    redis_tls["ssl_ca_certs"] = settings.redis_ssl_ca_certs
if settings.celery_broker_url.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = redis_tls.copy()
if settings.celery_result_backend.startswith("rediss://"):
    celery_app.conf.redis_backend_use_ssl = redis_tls.copy()

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.conversion_timeout_seconds,
    task_soft_time_limit=settings.conversion_timeout_seconds - 30,
    broker_connection_retry_on_startup=True,
    # Above every task time limit, so a long task is never redelivered while it runs;
    # a message whose worker died is caught sooner by workers.monitoring.check_broker_unacked
    broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout_seconds},
    # Isolation settings
    task_default_queue=settings.celery_task_default_queue,  # Fila isolada
    worker_name=settings.celery_worker_name,  # Hostname único
)

# Configure Celery Beat periodic tasks schedule
if settings.monitoring_enabled:
    celery_app.conf.beat_schedule = {
        'detect-stuck-jobs': {
            'task': 'workers.monitoring.detect_stuck_jobs',
            'schedule': crontab(minute=f'*/{settings.monitoring_check_interval_minutes}'),  # Every N minutes
            'options': {'expires': settings.monitoring_check_interval_minutes * 60}
        },
        'auto-retry-failed-pages': {
            'task': 'workers.monitoring.auto_retry_failed_pages',
            'schedule': crontab(minute=f'*/{settings.monitoring_check_interval_minutes}'),  # Every N minutes
            'options': {'expires': settings.monitoring_check_interval_minutes * 60}
        },
        'cleanup-old-jobs': {
            'task': 'workers.monitoring.cleanup_old_jobs',
            'schedule': crontab(hour='2', minute='0'),  # Daily at 2 AM UTC
            'options': {'expires': 3600}  # Expire after 1 hour if not picked up
        },
        'cleanup-stale-files': {
            'task': 'workers.monitoring.cleanup_stale_files',
            'schedule': crontab(hour='3', minute='0'),  # Daily at 3 AM UTC
            'options': {'expires': 3600}
        },
        'check-broker-unacked': {
            'task': 'workers.monitoring.check_broker_unacked',
            'schedule': crontab(minute=f'*/{settings.monitoring_check_interval_minutes}'),
            'options': {'expires': settings.monitoring_check_interval_minutes * 60}
        },
        'health-check': {
            'task': 'workers.monitoring.health_check',
            'schedule': crontab(minute='*/1'),  # Every minute (verify beat is running)
            'options': {'expires': 60}
        },
    }

# Auto-discover tasks
celery_app.autodiscover_tasks(["workers"])

# autodiscover_tasks() only finds modules literally named `tasks`, so the vision
# tasks must be imported explicitly. Unconditional on purpose: importing them is
# free (the vision package pulls in no torch, transformers or PIL until a model
# is actually loaded), and an unregistered task name under task_acks_late +
# task_reject_on_worker_lost is redelivered forever rather than failing once.
import workers.vision_tasks  # noqa: F401,E402

# Local workers announce which feature lane they serve and the GPU they see
# (spec 0003); signal handlers only, nothing runs at import
import workers.engines.heartbeat  # noqa: F401,E402

# The vision endpoints answer synchronously, so they cannot queue behind the
# general work: `ingestify` has 10 slots that multi-minute PDF page jobs can all
# occupy, and a 60s request behind those would time out for reasons that have
# nothing to do with vision.
celery_app.conf.task_routes = {
    "workers.vision_tasks.*": {"queue": settings.vision_queue},
    # The dispatcher's own tasks (spec 0003): only published once a feature has a route
    "workers.engines.tasks.*": {"queue": settings.dispatch_queue},
    # worker-remote (spec 0003, slice 4a): attempts on one queue, control on another,
    # so a test or a cancel never waits behind long remote transcriptions
    "workers.engines.remote_tasks.execute_remote": {"queue": settings.remote_queue},
    "workers.engines.remote_tasks.*": {"queue": settings.remote_ctl_queue},
}

# Dispatcher tasks (probe, tick, sweeper); importing them loads no media library
import workers.engines.tasks  # noqa: F401,E402

# Remote engine tasks (worker-remote); importing them loads no provider SDK
import workers.engines.remote_tasks  # noqa: F401,E402

# Only worker-dispatch (compose profile `engines`) runs these, with its embedded
# beat (`celery worker -B`, ENGINES_DISPATCH_BEAT=true): the shared beat must not
# fill a queue that installs without the profile never consume
if settings.engines_dispatch_beat:
    celery_app.conf.beat_schedule = {
        **(celery_app.conf.beat_schedule or {}),
        'engines-dispatch-tick': {
            'task': 'workers.engines.tasks.dispatch_tick',
            'schedule': 5.0,
            'options': {'queue': settings.dispatch_queue, 'expires': 5},
        },
        'engines-sweep-usage': {
            'task': 'workers.engines.tasks.sweep_usage',
            'schedule': 30.0,
            'options': {'queue': settings.dispatch_queue, 'expires': 30},
        },
        # Learned speed per (engine, feature, gpu, E), cached 1 h for the estimate (slice 4b)
        'engines-refresh-speed': {
            'task': 'workers.engines.tasks.refresh_speed',
            'schedule': 600.0,
            'options': {'queue': settings.dispatch_queue, 'expires': 600},
        },
    }

# Only worker-remote (ENGINES_REMOTE_BEAT=true, embedded beat): the provider's own
# spend report and the accounts' cheap health probe, every 10 minutes (spec 0003, 4.8)
if settings.engines_remote_beat:
    celery_app.conf.beat_schedule = {
        **(celery_app.conf.beat_schedule or {}),
        'engines-reconcile-spend': {
            'task': 'workers.engines.remote_tasks.reconcile_spend',
            'schedule': 600.0,
            'options': {'queue': settings.remote_ctl_queue, 'expires': 600},
        },
        # Cheap health of the accounts used in the last 24 h: no container, no GPU (slice 4c)
        'engines-probe': {
            'task': 'workers.engines.remote_tasks.probe_engines',
            'schedule': 600.0,
            'options': {'queue': settings.remote_ctl_queue, 'expires': 600},
        },
    }

# Explicitly import monitoring tasks to ensure they're registered
# This is needed because Beat scheduler needs to see these tasks
if settings.monitoring_enabled:
    import workers.monitoring  # noqa: F401
