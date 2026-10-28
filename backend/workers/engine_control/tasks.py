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


@celery_app.task(name="workers.engine_control.tasks.idle_policy")
def idle_policy():
    from workers.engine_control.idle_policy import tick

    return tick()


_settings = get_settings()
if _settings.engine_control_enabled and _settings.engine_control_beat:
    # Kept next to the task: local idle cooldown and standby wakeup (spec 0007, 4.6).
    celery_app.conf.beat_schedule = {
        **(celery_app.conf.beat_schedule or {}),
        "engine-control-idle-policy": {
            "task": "workers.engine_control.tasks.idle_policy",
            "schedule": 15.0,
            "options": {"queue": _settings.engine_control_queue, "expires": 15},
        },
    }
