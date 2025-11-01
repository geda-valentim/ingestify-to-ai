from celery import Celery
from celery.schedules import crontab
from shared.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "doc2md",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
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
        'health-check': {
            'task': 'workers.monitoring.health_check',
            'schedule': crontab(minute='*/1'),  # Every minute (verify beat is running)
            'options': {'expires': 60}
        },
    }

# Auto-discover tasks
celery_app.autodiscover_tasks(["workers"])

# Explicitly import monitoring tasks to ensure they're registered
# This is needed because Beat scheduler needs to see these tasks
if settings.monitoring_enabled:
    import workers.monitoring  # noqa: F401
