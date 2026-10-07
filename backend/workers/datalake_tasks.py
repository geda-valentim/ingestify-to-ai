"""Delivery retries run independently; inference never needs to repeat."""
from datetime import datetime, timedelta

from shared.database import SessionLocal
from shared.models import Job, JobDatalakeExport, JobStatus
from shared.datalake import service
from workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=4, name="workers.datalake_tasks.export_result")
def export_result(self, job_id):
    try:
        service.export_result(job_id)
    except RuntimeError as exc:
        raise self.retry(exc=exc, countdown=min(30 * 2 ** self.request.retries, 600))


@celery_app.task(name="workers.datalake_tasks.reconcile")
def reconcile():
    with SessionLocal() as db:
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        rows = db.query(JobDatalakeExport).join(Job, Job.id == JobDatalakeExport.job_id).filter(
            Job.status.in_([JobStatus.COMPLETED, JobStatus.PARTIAL]),
            JobDatalakeExport.status.in_(["pending", "failed"]), JobDatalakeExport.attempts < 5,
            JobDatalakeExport.updated_at < cutoff).limit(100).all()
        job_ids = [row.job_id for row in rows]
    for job_id in job_ids:
        export_result.delay(job_id)
    return {"queued": len(job_ids)}
