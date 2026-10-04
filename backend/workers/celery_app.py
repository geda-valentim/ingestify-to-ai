from celery import Celery
from celery.schedules import crontab
from shared.config import get_settings, redis_url_with_password

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "doc2md",
    broker=redis_url_with_password(settings.celery_broker_url, settings.redis_password),
    backend=redis_url_with_password(settings.celery_result_backend, settings.redis_password),
)

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

# The vision endpoints answer synchronously, so they cannot queue behind the
# general work: `ingestify` has 10 slots that multi-minute PDF page jobs can all
# occupy, and a 60s request behind those would time out for reasons that have
# nothing to do with vision.
celery_app.conf.task_routes = {
    "workers.vision_tasks.*": {"queue": settings.vision_queue},
}

# Explicitly import monitoring tasks to ensure they're registered
# This is needed because Beat scheduler needs to see these tasks
if settings.monitoring_enabled:
    import workers.monitoring  # noqa: F401
