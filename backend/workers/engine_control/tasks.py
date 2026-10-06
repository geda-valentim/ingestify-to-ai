from workers.celery_app import celery_app
from shared.config import get_settings


@celery_app.task(
    name="workers.engine_control.tasks.execute",
    acks_late=True,
    soft_time_limit=5400,
    time_limit=5430,
)
def execute(operation_id):
    from workers.engine_control.runner import run

    return run(operation_id)


@celery_app.task(name="workers.engine_control.tasks.sweep")
def sweep():
    from workers.engine_control.runner import sweep

    return sweep(celery_app)
