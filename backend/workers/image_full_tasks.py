"""Full image batches, durable checkpoints and outbox/watchdog recovery."""
import io
import logging
import math
import hashlib
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from celery.worker.request import Request
from shared.database import SessionLocal
from shared.models import Job, ImageAnalysisRun as Run, ImageAnalysisStep as Step, EngineUsage
from shared.config import get_settings
from shared.minio_client import get_minio_client
from shared.image_analysis import claim, guard, next_step, save_step, resolve, finish, locked, LostLease, TERMINAL
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class DeadlineRequest(Request):
    """Set the pool's hard timer after queue wait, before pool execution."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_remaining()

    def limit_remaining(self):
        with SessionLocal() as db:
            run = db.get(Run, self.kwargs['job_id'])
            remaining = max(1, math.ceil((run.deadline_at-datetime.utcnow()).total_seconds())) if run else 1
        self.time_limits = (remaining, max(1, remaining-10))



class Control:
    def __init__(self, job_id, holder, fence):
        self.job_id, self.holder, self.fence = job_id, holder, fence
        self.reason = None
        self.last = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.renew, daemon=True)

    def check(self, force=False):
        if self.reason:
            return False
        if force or time.monotonic()-self.last > .5:
            try:
                guard(self.job_id, self.holder, self.fence)
                self.last = time.monotonic()
            except LostLease as exc:
                self.reason = str(exc)
            except Exception:
                self.reason = 'authority_unavailable'
        return self.reason is None

    def renew(self):
        while not self.stop.wait(5):
            if not self.check(True):
                return
            with SessionLocal() as db:
                run = db.get(Run, self.job_id)
                usage_id = run.usage_id if run else None
            if usage_id:
                from shared.engines import ledger
                if not ledger.heartbeat(usage_id, self.holder):
                    self.reason = 'accounting_claim_lost'
                    return


@celery_app.task(bind=True, max_retries=0, name='workers.vision_tasks.run_full_image_task',
                 Request=DeadlineRequest, time_limit=900, soft_time_limit=890)
def run_full_image_task(self, job_id, usage_id=None):
    storage = get_minio_client()
    holder = str(uuid4())
    claimed = claim(job_id, holder)
    if not claimed:
        return
    fence, options, source, deadline, usage_id = claimed
    model = None
    control = Control(job_id, holder, fence)
    started = time.monotonic()
    accounting_claimed = False
    path = None
    try:
        if usage_id:
            from shared.engines import ledger
            outcome, _ = ledger.claim(usage_id, holder)
            if outcome != ledger.CLAIMED:
                raise LostLease('accounting_claim_lost')
            accounting_claimed = True
        if not control.check(True):
            raise LostLease(control.reason)
        control.thread.start()
        from workers.vision.factory import get_image_describer
        model = get_image_describer()
        settings = get_settings()
        if options['provider'] != settings.vision_provider or options['model']['model_id'] != settings.vision_model_id or options['model']['revision'] != settings.vision_model_revision:
            raise LostLease('model_configuration_changed')
        # The durable source, not a vanished handoff, is the authority.
        path = Path(settings.temp_storage_path) / 'images' / job_id / holder / 'full-source'
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = storage.download_file(storage.bucket_results, source)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            expected = job.file_checksum if job else None
        if not expected or hashlib.sha256(raw).hexdigest() != expected:
            raise LostLease('source_checksum_mismatch')
        path.write_bytes(raw)
        if hasattr(model, 'prepare_full'):
            bitmap, width, height = model.prepare_full(path, control.check)
        else:
            from PIL import Image
            with Image.open(path) as opened:
                bitmap = opened.convert('RGB')
            width, height = bitmap.size
            if width * height > settings.vision_max_image_pixels:
                bitmap.close()
                raise LostLease('image_pixel_limit')
        preview = io.BytesIO()
        bitmap.save(preview, format='PNG')
        preview_data = preview.getvalue()
        preview_path = f'images/{job_id}/preview/{fence}-{__import__("hashlib").sha256(preview_data).hexdigest()}.png'
        if not storage.upload_file(bucket_name=storage.bucket_results, object_name=preview_path, file_data=preview_data, content_type='image/png'):
            raise RuntimeError('Preview persistence unavailable')
        with SessionLocal() as db:
            job, run = locked(db, job_id)
            from shared.image_analysis import check
            check(db, job, run, holder, fence)
            run.width, run.height = width, height
            run.preview_path = preview_path
            run.options = {**run.options, 'model': model.info()}
            db.commit()
        while True:
            if not control.check(True):
                raise LostLease(control.reason)
            item = next_step(job_id, holder, fence)
            if item == 'limit':
                continue
            if item is None:
                if resolve(job_id, holder, fence, storage):
                    continue
                break
            native = {'task': item['task'], 'generation': options['full_options']['generation']}
            native.update({key: item['input'][key] for key in ('text_input', 'region') if key in item['input']})
            try:
                output = model.analyze(path, native)
                if not control.check(True):
                    raise LostLease(control.reason)
                save_step(job_id, holder, fence, item, output, storage)
            except LostLease:
                raise
            except Exception as exc:
                # Preserve other independent outputs, without exposing exception internals.
                logger.warning('Full vision step failed: job=%s task=%s type=%s', job_id, item['task'], type(exc).__name__)
                save_step(job_id, holder, fence, item, {}, storage, reason=getattr(exc, 'error_code', 'inference_failed'))
        payload = finish(job_id, holder, fence, storage)
        return {'job_id': job_id, 'status': payload['image']['analysis_status'] if payload else 'unknown'}
    except BaseException as exc:
        reason = str(exc) if isinstance(exc, LostLease) else 'execution_interrupted'
        try:
            if reason == 'accounting_claim_lost':
                with SessionLocal() as db:
                    job, run = locked(db, job_id)
                    if run and run.holder == holder and run.fence == fence and run.status not in TERMINAL:
                        run.holder, run.lease_until = None, None
                        run.dispatch_after = datetime.utcnow() + timedelta(seconds=5)
                        db.commit()
            else:
                finish(job_id, holder, fence, storage, reason=reason)
        except Exception:
            logger.exception('Full vision awaits durable recovery: job=%s', job_id)
        return {'job_id': job_id, 'reason_code': reason}
    finally:
        control.stop.set()
        if control.thread.is_alive():
            control.thread.join(timeout=2)
        if model and hasattr(model, 'close_full'):
            model.close_full()
        if usage_id and accounting_claimed:
            from shared.engines import ledger
            with SessionLocal() as db:
                usage = db.get(EngineUsage, usage_id)
                ours = usage and usage.status == 'running' and usage.holder == holder
                job = db.get(Job, job_id)
                run = db.get(Run, job_id)
                persisted = bool(job and job.minio_result_path and run and run.status in TERMINAL)
                status = run.status if persisted else None
                ended_at = job.completed_at if persisted else None
            if ours:
                seconds = round(time.monotonic()-started, 3)
                if persisted and status == 'completed':
                    ledger.settle_succeeded(usage_id, holder, measured_seconds=seconds)
                else:
                    ledger.settle_failed(usage_id, holder, error_code=(control.reason or status or 'OUTPUT_UNAVAILABLE')[:32],
                        outcome='cancelled' if status == 'cancelled' else 'failed', counts=status != 'cancelled',
                        measured_seconds=seconds, output_persisted_at=ended_at)
        if path:
            shutil.rmtree(path.parent, ignore_errors=True)
        # A deleted job has no selected objects; clean this holder's late writes.
        with SessionLocal() as db:
            deleted = db.get(Job, job_id) is None
        if deleted:
            storage.delete_folder(storage.bucket_results, f'images/{job_id}/')


def dispatch(job_id):
    with SessionLocal() as db:
        job, run = locked(db, job_id)
        now = datetime.utcnow()
        if not run or run.status in TERMINAL or run.dispatch_after > now or (run.lease_until and run.lease_until > now):
            return
        from shared.engines import dispatch as engine_dispatch, routing
        from shared.models import User
        route = routing.get_route('vision')
        if route and route.active:
            usage = db.get(EngineUsage, run.usage_id) if run.usage_id else None
            if usage and usage.status == 'running':
                return  # An uncertain effect is still being accounted for.
            if not usage or usage.status != 'reserved':
                user = db.get(User, job.user_id)
                if not user or not user.is_active:
                    run.cancel_requested = True
                    db.commit()
                    return
                from shared.admin import is_effective_admin
                placed = engine_dispatch.place_now(feature='vision', subject_id=f'{job_id}:{uuid4().hex[:26]}',
                    job_id=job_id, user_id=job.user_id, is_admin=is_effective_admin(user), allow_remote=False)
                if placed.outcome != 'placed':
                    run.dispatch_after = now + timedelta(seconds=10)
                    db.commit()
                    return  # Full never bypasses accounting on a configured route.
                run.usage_id = placed.usage_id
        run.dispatch_after = now + timedelta(seconds=35)
        run.dispatch_attempts += 1
        run.task_id = str(uuid4())
        task_id, usage_id = run.task_id, run.usage_id
        db.commit()
    send = lambda: run_full_image_task.apply_async(kwargs={'job_id': job_id, 'usage_id': usage_id}, task_id=task_id, queue=get_settings().vision_queue)
    if usage_id:
        engine_dispatch.publish_sync(SessionLocal, usage_id, send)
    else:
        send()


@celery_app.task(name='workers.image_full_tasks.reconcile')
def reconcile():
    now = datetime.utcnow()
    storage = get_minio_client()
    with SessionLocal() as db:
        candidates = [row.job_id for row in db.query(Run).filter(Run.status.in_(['pending', 'processing', 'finalizing']))]
    for job_id in candidates:
        try:
            with SessionLocal() as db:
                job, run = locked(db, job_id)
                if not run or run.status in TERMINAL:
                    continue
                if run.status == 'finalizing' and run.lease_until and run.lease_until > now:
                    continue
                expired = run.deadline_at <= now or run.cancel_requested
                if not expired:
                    db.rollback()
                    dispatch(job_id)
                    continue
                # Fence late writes before building the terminal result.
                run.status = 'finalizing'
                run.fence += 1
                run.holder = str(uuid4())
                run.lease_until = datetime.utcnow() + timedelta(seconds=30)
                holder, fence = run.holder, run.fence
                reason = 'cancelled' if run.cancel_requested else 'deadline'
                if not db.query(Step).filter(Step.job_id == job_id).first():
                    from shared.image_analysis import add_steps
                    from shared.image_full import initial_steps
                    add_steps(db, job_id, initial_steps())
                db.commit()
            payload = finish(job_id, holder, fence, storage, reason=reason, recovery=True)
            if payload:
                with SessionLocal() as db:
                    usage_id = db.get(Run, job_id).usage_id
                if usage_id:
                    from shared.engines import ledger
                    ledger.release(usage_id, error_code=reason)
        except Exception:
            logger.exception('Full vision reconciliation deferred: job=%s', job_id)

    # Deletion tombstones outlive SQL jobs and retries. A final purge after the
    # maximum hard deadline catches uploads from already fenced processes.
    from shared.models import ImageAnalysisSubmission as Submission
    with SessionLocal() as db:
        deleted = [(row.id, row.job_id, row.purge_after) for row in db.query(Submission).filter(
            Submission.deleted_at.isnot(None), Submission.purged_at.is_(None))]
    for submission_id, job_id, purge_after in deleted:
        try:
            with SessionLocal() as db:
                if db.get(Job, job_id):
                    continue
            if storage.delete_folder(storage.bucket_results, f'images/{job_id}/') is False:
                continue
            shutil.rmtree(Path(get_settings().temp_storage_path) / 'images' / job_id, ignore_errors=True)
            if purge_after and purge_after <= datetime.utcnow():
                with SessionLocal() as db:
                    row = db.get(Submission, submission_id)
                    if row:
                        row.purged_at = datetime.utcnow()
                        db.commit()
        except Exception:
            logger.warning('Full image purge deferred: job=%s', job_id)
