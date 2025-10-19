from celery import Celery
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

# Auto-discover tasks
celery_app.autodiscover_tasks(["workers"])
