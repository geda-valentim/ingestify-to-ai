"""The actual executing task obtains a ticket, including legacy/unrouted tasks."""

import inspect
from celery import Task
from celery.exceptions import Reject
from shared.engine_control import admission
from shared.engine_control.service import ControlError


class ManagedTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        feature = None
        if self.name.startswith("workers.vision_tasks."):
            feature = "vision"
        elif self.name in (
            "workers.tasks.convert_page_task",
            "workers.tasks.process_page",
            "workers.tasks.split_pdf_task",
        ):
            feature = "document_conversion"
        elif self.name == "workers.tasks.process_conversion":
            bound = inspect.signature(self.run).bind_partial(*args, **kwargs).arguments
            opts = bound.get("options") or {}
            feature = (
                "transcription"
                if opts.get("is_audio") or opts.get("is_video") or bound.get("usage_id")
                else "document_conversion"
            )
        elif self.name == "workers.engines.remote_tasks.execute_remote":
            feature = "transcription"
        if feature is None:
            return super().__call__(*args, **kwargs)
        bound = inspect.signature(self.run).bind_partial(*args, **kwargs).arguments
        usage_id = bound.get("usage_id")
        engine_id = None
        if usage_id is not None:
            from shared.database import SessionLocal
            from shared.models import EngineUsage

            with SessionLocal() as db:
                usage = db.get(EngineUsage, usage_id)
                engine_id = usage.engine_id if usage else None
        try:
            tickets = admission.acquire(feature, f"task:{self.request.id}", engine_id)
        except Exception as exc:
            # Reject/requeue before executing; never turn an authority failure into local fallback.
            raise Reject("Maintenance admission unavailable", requeue=True) from exc
        try:
            from workers.engine_control.readiness import ensure

            ensure()
            return super().__call__(*args, **kwargs)
        finally:
            admission.release(tickets)
